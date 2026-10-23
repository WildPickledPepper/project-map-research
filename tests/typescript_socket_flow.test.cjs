const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),ts=require('typescript');
const {analyzeSockets}=require('../adapters/typescript_socket_flow.cjs');
function graph(source,options){
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'p3-socket-'));
  try{fs.writeFileSync(path.join(dir,'a.ts'),source);return analyzeSockets(ts,dir,['a.ts'],options).socket_flow;}
  finally{fs.rmSync(dir,{recursive:true,force:true});}
}
const source=`class Link {wire:WebSocket;
constructor(url:string,flag:boolean){if(flag)this.wire=new WebSocket(url);else this.wire=new WebSocket('ws://example.invalid');}
receive=(event:MessageEvent)=>{JSON.parse(event.data);};
fetch(){this.wire.onmessage=this.receive;this.wire.send('request');}}`;

test('constructors, field assignments and listener event parameter have source identities',()=>{
  const g=graph(source);assert.equal(g.creations.length,2);assert.equal(g.channel_bindings.length,2);
  const l=g.listener_bindings[0],send=g.transmissions[0];
  assert.equal(l.channel.root,send.receiver.root);assert.equal(l.this_binding,'lexical');assert(l.event_parameter&&l.callback_receiver_type);
  assert.equal(g.channel_bindings[0].channel.root,l.channel.root);
  assert(g.creations.every(c=>c.conditions.some(x=>x.expression==='flag')));
  assert(g.creations.some(c=>c.url.kind==='input_path'));
});

test('application field and callback renames preserve the connection',()=>{
  const g=graph(source.replaceAll('wire','transport').replaceAll('receive','acceptPacket'));
  assert.equal(g.channel_bindings[0].channel.root,g.listener_bindings[0].channel.root);
  assert.equal(g.listener_bindings[0].channel.root,g.transmissions[0].receiver.root);
});

test('an alias refers to the same channel rather than another socket field',()=>{
  const g=graph(`class C{one!:WebSocket;two!:WebSocket;handle=(e:MessageEvent)=>{};
  run(){const alias=this.one;alias.onmessage=this.handle;this.one.send('one');this.two.send('two');}}`);
  const l=g.listener_bindings[0];assert.equal(l.channel.root,g.transmissions[0].receiver.root);
  assert.notEqual(l.channel.root,g.transmissions[1].receiver.root);
});

test('a field on a different receiver does not become this instance field',()=>{
  const g=graph(`class C{wire!:WebSocket;handle=(e:MessageEvent)=>{};run(other:C){other.wire.onmessage=this.handle;this.wire.send('x');}}`);
  assert.notEqual(g.listener_bindings[0].channel.root,g.transmissions[0].receiver.root);
  assert.deepEqual(g.listener_bindings[0].channel.path,['wire']);
});

test('null assignment supersedes a prior unconditional listener in the same entry',()=>{
  const g=graph(`class C{ws!:WebSocket;handle=(e:MessageEvent)=>{};run(){this.ws.onmessage=this.handle;this.ws.onmessage=null;}}`);
  assert.equal(g.listener_bindings.length,2);assert.deepEqual(g.listener_bindings[0].superseded_by,[g.listener_bindings[1].id]);
  assert.equal(g.listener_bindings[1].action,'clear');
});

test('a conditional clear remains a lifecycle alternative',()=>{
  const g=graph(`class C{ws!:WebSocket;handle=(e:MessageEvent)=>{};run(flag:boolean){this.ws.onmessage=this.handle;if(flag)this.ws.onmessage=null;}}`);
  assert.deepEqual(g.listener_bindings[0].superseded_by,[]);assert(g.listener_bindings[1].conditions.some(c=>c.when===true));
});

test('an await permits delivery before a later clear',()=>{
  const g=graph(`class C{ws!:WebSocket;handle=(e:MessageEvent)=>{};async run(pause:Promise<void>){this.ws.onmessage=this.handle;await pause;this.ws.onmessage=null;}}`);
  assert.deepEqual(g.listener_bindings[0].superseded_by,[]);
  assert.notEqual(g.listener_bindings[0].sequence_epoch,g.listener_bindings[1].sequence_epoch);
});

test('unbound methods and explicitly bound methods keep different this semantics',()=>{
  for(const [expr,mode] of [['this.handle','event_target'],['this.handle.bind(this)','bound']]){
    const g=graph(`class C{ws!:WebSocket;handle(e:MessageEvent){};run(){this.ws.onmessage=${expr};}}`);
    assert.equal(g.listener_bindings[0].this_binding,mode);
    assert.equal(Boolean(g.listener_bindings[0].callback_receiver_type),mode==='bound');
  }
});

test('a user-defined WebSocket name is not a platform transport',()=>{
  const g=graph(`export {};class WebSocket{onmessage:any;constructor(x:string){}send(x:string){}}
  class C{ws=new WebSocket('x');run(){this.ws.onmessage=()=>{};this.ws.send('x');}}`);
  assert.equal(g.creations.length,0);assert.equal(g.listener_bindings.length,0);assert.equal(g.transmissions.length,0);
});

test('a union retains unknown transport assignment separately from native construction',()=>{
  const g=graph(`declare class Adapter{send(x:string):void;onmessage:any;}declare function adapter():Adapter;
  class C{ws:WebSocket|Adapter;constructor(flag:boolean){if(flag)this.ws=adapter();else this.ws=new WebSocket('ws://example.invalid');}
  run(){this.ws.onmessage=(e:any)=>{};this.ws.send('x');}}`);
  assert.equal(g.creations.length,1);assert.equal(g.channel_bindings.length,2);
  assert(g.channel_bindings.some(b=>b.value.kind==='unknown'));assert(g.channel_bindings.some(b=>b.value.kind==='native_socket'));
});

test('class field initializer is recorded with its initialization condition',()=>{
  const g=graph(`class C{ws=new WebSocket('ws://example.invalid');run(){this.ws.onmessage=(e:any)=>{};this.ws.send('x');}}`);
  assert.equal(g.creations.length,1);assert.equal(g.channel_bindings.length,1);
  assert(g.channel_bindings[0].conditions.some(c=>c.kind==='instance_field_initializer_not_replaced'));
  assert.equal(g.listener_bindings[0].channel.allocation,g.transmissions[0].receiver.allocation);
});

test('separate local socket allocations stay separate',()=>{
  const g=graph(`function run(){const a=new WebSocket('ws://one.invalid'),b=new WebSocket('ws://two.invalid');a.onmessage=e=>{};b.send('x');}`);
  assert.equal(g.creations.length,2);assert.notEqual(g.listener_bindings[0].channel.allocation,g.transmissions[0].receiver.allocation);
});

test('socket extraction budget exhaustion is visible',()=>{
  const g=graph(source,{maxSteps:2});assert(g.entries.some(e=>e.truncated));
});

test('dynamic URL expressions retain input origins without inventing an address',()=>{
  const g=graph("class C{ws:WebSocket;constructor(port:number){const p=window.location.pathname.replace('/old','/new');this.ws=new WebSocket(`ws://${window.location.hostname}:${port}${p}`);}}");
  const url=g.creations[0].url;assert.equal(url.kind,'source_expression');assert.equal(url.operation,'template_string');
  assert(url.inputs.some(v=>v.kind==='input_path'&&v.path.join('.')==='location.hostname'));
  assert(url.inputs.some(v=>v.kind==='input_path'&&v.path.length===0));
  assert(url.inputs.some(v=>v.operation==='String.replace'&&v.inputs[0].path.join('.')==='location.pathname'));
});
