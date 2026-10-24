const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),ts=require('typescript');
const {analyze}=require('../adapters/typescript_facts.cjs');
const {analyzeReturns}=require('../adapters/typescript_return_flow.cjs');

const source=`export {};
declare global {interface Window {query:(s:string)=>Promise<any>}}
abstract class Bus {
 constructor(){window.onmessage=(e:MessageEvent)=>{const packet={data:JSON.parse(e.data)};
   if(packet.data.tag==='ask')this.receive(packet);};}
 abstract receive(e:MessageEvent):void;
 send(body:any){body.sender=window.name;const targets=[window.frames[body.destination]];
   targets.forEach(target=>target.postMessage(JSON.stringify(body),'*'));}
}
class Front extends Bus {
 q=new Map<number,any>();fetch(args:any):Promise<any>{return new Promise(r=>this.q.set(1,r));}
 receive(e:MessageEvent){this.q.get(e.data.seq)(e.data);}
}
class Socket {fetch(args:any):Promise<any>{return new Promise(()=>{});}}
class Relay extends Bus {
 callback:((e:MessageEvent)=>Promise<any>)|null=null;
 attach(cb:(e:MessageEvent)=>Promise<any>){this.callback=cb;}
 async receive(e:MessageEvent){if(!this.callback)return;const res=await this.callback(e);
   this.send({tag:'ask',seq:e.data.seq,destination:e.data.sender,...res});}
}
const relay=new Relay();const socket=new Socket();
relay.attach(async e=>{const v=await socket.fetch(e.data.args);return {body:v};});
const client=new Front();
function factory(c:Front){return async (s:string)=>{const result=await c.fetch({s});return result.body;};}
window.query=factory(client);
export async function api(){return window.query('action');}
`;

function graph(code=source,options={},names={}){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'p3-return-'));
 try{fs.writeFileSync(path.join(dir,'a.ts'),code);const facts=analyze(ts,dir,['a.ts']);
   const resolve=name=>{const node=facts.nodes.find(n=>n.name===name&&n.kind==='function');
     return node?.id||facts.nodes.find(n=>n.name===name&&n.kind==='callable')?.id||facts.nodes.find(n=>n.name===name)?.id;};
   const inputs={boundarySymbols:(names.boundaries||['Front.fetch','Socket.fetch']).map(resolve),
     apiEntries:(names.apis||['api']).map(resolve),handoffSymbols:(names.handoffs||['Front.receive']).map(resolve)};
   assert(inputs.boundarySymbols.every(Boolean));assert(inputs.apiEntries.every(Boolean));
   const result=analyzeReturns(ts,dir,['a.ts'],inputs,options);return {...result.return_flow,nodes:result.nodes,inputs};
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
}
function leaves(v){if(v.kind==='alternatives')return v.values.flatMap(leaves);if(v.kind==='json_string')return leaves(v.value);
 if(v.kind==='object')return Object.values(v.fields).flatMap(leaves);return [v];}

test('source registration packages a fulfilled value and API unwraps its response field',()=>{
 const g=graph(),api=g.inputs.apiEntries[0];
 const returned=g.returns.find(r=>r.entry===api&&r.source_symbol===api);
 assert.deepEqual(returned.value.path,['body']);
 const boundary=g.boundaries.find(b=>b.id===returned.value.root);assert.equal(boundary.target,g.inputs.boundarySymbols[0]);
 const reply=g.transmissions.find(t=>t.entry===g.callback_bindings[0].entry);
 const socket=g.boundaries.find(b=>b.target===g.inputs.boundarySymbols[1]);
 assert(leaves(reply.payload).some(v=>v.root===socket.id));
 assert.equal(g.handoffs.filter(h=>h.target===g.inputs.handoffSymbols[0]).length,1);
 assert(reply.receiver.selections.length);assert(g.handoffs.some(h=>h.conditions.some(c=>c.test?.operation==='===')));
});
test('a declared external constructor base stays unknown while local class initialization continues',()=>{
 const g=graph(source.replace('export async function api(){',
   'declare const External: new()=>object; class Local extends External {value=1;} export async function api(){new Local();'));
 assert(g.returns.some(r=>r.entry===g.inputs.apiEntries[0]&&r.value.path?.[0]==='body'));
 assert(g.diagnostics.some(d=>d.kind==='base_class_outside_source_model'));
});
test('renamed wrappers and fields are discovered from source',()=>{
 const g=graph(source.replaceAll('Front','Pane').replaceAll('Socket','Transport').replaceAll('body','payload'),{},
   {boundaries:['Pane.fetch','Transport.fetch'],handoffs:['Pane.receive']});
 const api=g.inputs.apiEntries[0];assert.deepEqual(g.returns.find(r=>r.entry===api&&r.source_symbol===api).value.path,['payload']);
 assert(g.transmissions.length);
});
test('replacing global callable removes the former API projection',()=>{
 const g=graph(source.replace('window.query=factory(client);','window.query=async()=>42;'));
 const api=g.inputs.apiEntries[0];assert.deepEqual(g.returns.find(r=>r.entry===api&&r.source_symbol===api).value,{kind:'constant',value:42});
});
test('overwriting registered callback prevents a reply',()=>{
 const g=graph(source.replace('this.callback=cb;', 'this.callback=null;'));
 assert.equal(g.transmissions.length,0);
});
test('an opaque mutation keeps an explicit source gap',()=>{
 const g=graph('declare function mutate(x:any):void;\n'+source.replace('return {body:v};','mutate(v);return {body:v};'));
 assert(g.transmissions.some(t=>leaves(t.payload).some(v=>v.gaps?.length)));
});
test('clearing the Window listener removes its dispatch candidates',()=>{
 const g=graph(source.replace("if(packet.data.tag==='ask')this.receive(packet);};}","if(packet.data.tag==='ask')this.receive(packet);};window.onmessage=null;}"));
 assert.equal(g.handoffs.length,0);assert(g.window_listeners.some(l=>l.superseded_by.length));
});
test('depth and step limits remain visible',()=>{
 const g=graph(source,{maxDepth:2,maxSteps:30});
 assert(g.entries.some(e=>e.truncated)||g.diagnostics.some(d=>d.kind==='call_depth_limit'));
});
test('an unknown trailing spread cannot retain an earlier response key',()=>{
 const g=graph('declare const extra:any;\n'+source.replace('destination:e.data.sender,...res','destination:e.data.sender,...res,...extra'));
 const reply=g.transmissions.find(t=>t.entry===g.callback_bindings[0].entry);
 const value=reply.payload.value;
 assert.equal(value.fields.seq.kind,'unknown');assert(g.diagnostics.some(d=>d.kind==='spread_source_not_expanded'));
});
test('overwriting the API result field removes the former boundary projection',()=>{
 const g=graph(source.replace('return result.body;', 'result.body=17;return result.body;'));
 const api=g.inputs.apiEntries[0];assert.deepEqual(g.returns.find(r=>r.entry===api&&r.source_symbol===api).value,{kind:'constant',value:17});
});

test('callback registration through an imported class retains cross-package reply packaging',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'p3-return-units-'));
 try{
  const start=source.indexOf('const relay='),client=source.indexOf('const client=');
  const library=source.slice(0,start).replaceAll('abstract class ','export abstract class ').replaceAll('\nclass ','\nexport class ');
  const files={'shared/package.json':'{"name":"shared"}','host/package.json':'{"name":"host"}','client/package.json':'{"name":"client"}',
    'shared/bridge.ts':library,'host/main.ts':"import {Relay,Socket} from '../shared/bridge';\n"+source.slice(start,client),
    'client/main.ts':"import {Front} from '../shared/bridge';\n"+source.slice(client)};
  for(const [name,body] of Object.entries(files)){fs.mkdirSync(path.dirname(path.join(dir,name)),{recursive:true});fs.writeFileSync(path.join(dir,name),body);}
  const facts=analyze(ts,dir,Object.keys(files)),resolve=name=>facts.nodes.find(n=>n.kind==='callable'&&n.name===name).id;
  const g=analyzeReturns(ts,dir,Object.keys(files),{boundarySymbols:['Front.fetch','Socket.fetch'].map(resolve),apiEntries:[resolve('api')],handoffSymbols:[resolve('Front.receive')]}).return_flow;
  assert(g.callback_bindings.length,'imported callback setter must be discovered');
  assert(g.transmissions.some(t=>t.entry===g.callback_bindings[0].entry));
  assert.equal(new Set(g.returns.map(r=>r.id)).size,g.returns.length);
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
});
