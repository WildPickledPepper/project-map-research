const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),ts=require('typescript');
const {analyzeResponse}=require('../adapters/typescript_response_flow.cjs');
function graph(source,options){
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'p3-response-'));
  try{fs.writeFileSync(path.join(dir,'a.ts'),source);return analyzeResponse(ts,dir,['a.ts'],options).response_flow;}
  finally{fs.rmSync(dir,{recursive:true,force:true});}
}
const wrapper=`class Client {
 pending=new Map<number,(r:any)=>void>();
 fetch(key:number){return new Promise(resolve=>{this.pending.set(key,this.wrap(resolve));});}
 wrap(done:(x:any)=>void){return (packet:any)=>{if(packet.ok){done(packet.payload);}else{done({error:packet.error});}};}
 receive(event:any){const packet=JSON.parse(event.data);const callback=this.pending.get(packet.token);if(callback===undefined)return;this.pending.delete(packet.token);callback(packet);}
}`;

test('branch alternative growth is bounded and retains an entry diagnostic',()=>{
  const source='class M {q=new Map<number,any>();send(flag:any){return new Promise(resolve=>{let box={a:1};'+
    'if(flag){}else{}'.repeat(14)+'this.q.set(1,resolve);});}}';
  const g=graph(source,{maxAlternatives:4});
  assert.equal(g.budgets.max_alternatives,4);
  assert(g.diagnostics.some(d=>d.kind==='alternative_budget_exceeded'&&d.entry&&d.path==='a.ts'&&d.limit===4));
  assert(g.entries.every(e=>e.steps<20000));
});

test('a stored source closure projects a decoded response into its captured resolver',()=>{
  const g=graph(wrapper);
  assert.equal(g.registrations.length,1);assert.equal(g.lookups.length,1);
  const delivered=g.settlements.filter(s=>s.registry_context);
  assert.equal(delivered.length,2);
  const body=delivered.find(s=>s.value.kind==='input_path');
  assert.deepEqual(body.value.path,['data','payload']);assert.equal(body.value.transforms[0].kind,'JSON.parse');
  assert.deepEqual(g.lookups[0].key.path,['data','token']);
  assert.equal(body.promise,g.registrations[0].promises[0]);
  assert(body.conditions.some(c=>c.kind==='registered_value_selected'));
  assert(g.deletions.length);assert(body.call_chain.length);
});
test('branch-copied registered closures retain fulfillment after cache eviction guards',()=>{
  const code=wrapper.replace('this.pending.set(key,this.wrap(resolve));',
    'const callback=this.wrap(resolve);if(this.pending.size>7){this.pending.delete(0);}this.pending.set(key,callback);');
  const g=graph(code);
  assert(g.registrations.some(r=>r.value.kind==='alternatives'));
  assert(g.settlements.some(s=>s.registry_context&&s.value.kind==='input_path'&&s.value.path.at(-1)==='payload'));
  assert(!g.diagnostics.some(d=>d.kind==='registry_callback_unresolved'));
});

test('resolver objects preserve separate success and failure paths',()=>{
  const g=graph(`class Link {q=new Map<number,any>();send(k:number){return new Promise((ok,bad)=>this.q.set(k,{ok,bad}));}
  receive(e:any){const r=this.q.get(e.id);if(r){const {ok,bad}=r;if(e.error)bad(e.error);else ok(e.data);}}}`);
  assert.deepEqual(new Set(g.settlements.map(s=>s.mode)),new Set(['resolve','reject']));
  assert.deepEqual(g.settlements.find(s=>s.mode==='resolve').value.path,['data']);
  assert.deepEqual(g.settlements.find(s=>s.mode==='reject').value.path,['error']);
});

test('different registry declarations and classes do not share callbacks',()=>{
  const g=graph(`class One {q=new Map<number,any>();other=new Map<number,any>();send(){return new Promise(r=>this.q.set(1,r));}
  receive(x:any){const cb=this.other.get(1);cb(x);}}
  class Two {q=new Map<number,any>();receive(x:any){const cb=this.q.get(1);cb(x);}}`);
  assert.equal(g.registrations.length,1);assert.equal(g.settlements.length,0);
  assert(g.diagnostics.some(d=>d.kind==='registry_callback_unresolved'));
});

test('different literal registration and lookup keys cannot match',()=>{
  const g=graph(`class One {q=new Map<number,any>();send(){return new Promise(r=>this.q.set(1,r));}receive(x:any){const cb=this.q.get(2);cb(x);}}`);
  assert.equal(g.settlements.length,0);
});

test('project Map and Promise names do not inherit platform semantics',()=>{
  const g=graph(`export {};class Map<K,V>{set(k:K,v:V){}get(k:K):any{}}class Promise<T>{constructor(fn:any){}}
  class One {q=new Map<number,any>();send(){return new Promise(r=>this.q.set(1,r));}receive(x:any){this.q.get(1)(x);}}`);
  assert.equal(g.registrations.length,0);assert.equal(g.promises.length,0);
});

test('renaming application members and fields only changes extracted selectors',()=>{
  const g=graph(wrapper.replaceAll('pending','waiting').replaceAll('payload','content').replaceAll('token','sequence'));
  assert.deepEqual(g.lookups[0].key.path,['data','sequence']);
  assert(g.settlements.some(s=>s.value.kind==='input_path'&&s.value.path.at(-1)==='content'));
});

test('a callback that ignores its argument does not invent a response field',()=>{
  const g=graph(`class C {q=new Map<number,any>();send(){return new Promise(r=>this.q.set(1,()=>r(7)));}receive(x:any){this.q.get(1)(x);}}`);
  assert.deepEqual(g.settlements[0].value,{kind:'constant',value:7});
});

test('bounded extraction exposes truncated entries',()=>{
  const g=graph(wrapper,{maxSteps:4});assert(g.entries.some(e=>e.truncated));
});

test('callback selection preserves an opaque mutation gap in the delivered value',()=>{
  const g=graph(`declare function opaque(x:any):void;class C {q=new Map<number,any>();send(){return new Promise(r=>this.q.set(1,r));}
  receive(x:any){opaque(x);const cb=this.q.get(1);cb(x.body);}}`);
  assert(g.settlements[0].value.gaps.some(d=>d.kind==='possible_mutation_by_unresolved_call'));
});

test('the same lookup helper reached by two entry points keeps separate input contexts',()=>{
  const g=graph(`class C {q=new Map<number,any>();send(){return new Promise(r=>this.q.set(1,r));}
  select(k:number){return this.q.get(k);}first(a:any){this.q.get(0);this.select(1)(a.one);}second(b:any){this.q.get(0);this.select(1)(b.two);}}`);
  const out=g.settlements.filter(s=>s.registry_context);
  assert.equal(out.length,2);assert.notEqual(out[0].registry_context.lookup,out[1].registry_context.lookup);
  assert.notEqual(out[0].value.root,out[1].value.root);
  assert.deepEqual(new Set(out.map(s=>s.value.path[0])),new Set(['one','two']));
});

test('replacing a selected callback removes its resolver delivery',()=>{
  const g=graph(`class C {q=new Map<number,any>();send(){return new Promise(r=>this.q.set(1,r));}
  receive(x:any){let cb=this.q.get(1);cb=()=>{};cb(x);}}`);
  assert.equal(g.settlements.length,0);
});

test('all incompatible literal key alternatives remain unmatched',()=>{
  const g=graph(`class C {q=new Map<number,any>();send(){return new Promise(r=>this.q.set(1,r));}
  receive(x:any,flag:boolean){let k;if(flag)k=2;else k=3;this.q.get(k)(x);}}`);
  assert.equal(g.settlements.length,0);
});

test('a numeric postfix result and the wire key share the value before increment',()=>{
  const g=graph(`class C {q=new Map<number,any>();seq=0;ws!:WebSocket;
  send(){return new Promise(r=>{const id=this.seq++;this.ws.send(JSON.stringify({ticket:id}));this.q.set(id,r);});}
  receive(x:any){this.q.get(x.ticket)(x);}}`);
  const send=g.transmissions[0],key=g.registrations[0].key;
  assert.equal(send.payload.value.fields.ticket.root,key.root);
  assert.equal(send.promise_context,g.registrations[0].promise_context);
  assert.notEqual(g.counter_updates[0].before.root,g.counter_updates[0].after.root);
});

test('an input object field set before postfix registration preserves its origin',()=>{
  const g=graph(`class C {q=new Map<number,any>();seq=0;send(packet:any){return new Promise(r=>{
  packet.ticket=this.seq;window.parent.postMessage(JSON.stringify(packet),'*');this.q.set(this.seq++,r);});}}`);
  assert.equal(g.transmissions[0].payload.value.overrides.ticket.root,g.registrations[0].key.root);
});

test('JSON send snapshots survive later writes and counter increments',()=>{
  const g=graph(`class C {q=new Map<number,any>();seq=0;ws!:WebSocket;send(){return new Promise(r=>{
  const id=this.seq++;const msg={ticket:id};const text=JSON.stringify(msg);msg.ticket=this.seq++;this.ws.send(text);this.q.set(id,r);});}}`);
  assert.equal(g.transmissions[0].payload.value.fields.ticket.root,g.registrations[0].key.root);
  assert.notEqual(g.counter_updates[0].before.root,g.counter_updates[1].before.root);
});

test('a project socket class does not become a platform transport',()=>{
  const g=graph(`export {};class WebSocket {send(x:string){}}class C {q=new Map<number,any>();ws=new WebSocket();
  send(){return new Promise(r=>{this.ws.send(JSON.stringify({ticket:1}));this.q.set(1,r);});}}`);
  assert.equal(g.transmissions.length,0);
});

test('unknown numeric coercion cannot prove a shared counter value',()=>{
  const g=graph(`class C {q=new Map<number,any>();seq:any='1';ws!:WebSocket;send(){return new Promise(r=>{
  const before=this.seq;this.ws.send(JSON.stringify({ticket:before}));this.q.set(this.seq++,r);});}}`);
  assert.equal(g.registrations[0].key.kind,'unknown');
});
