const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const ts=require('typescript');
const {analyzeProtocol}=require('../adapters/typescript_protocol_flow.cjs');

function graph(files){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'p2-ts-'));try{
  for(const [p,s] of Object.entries(files)){fs.mkdirSync(path.dirname(path.join(dir,p)),{recursive:true});fs.writeFileSync(path.join(dir,p),s);}
  return analyzeProtocol(ts,dir,Object.keys(files));
}finally{fs.rmSync(dir,{recursive:true,force:true});}}
function fixture(body='',name='enter',value="'alpha/read'"){
  return {'a.ts':`declare const channel:WebSocket; declare const dynamic:any;
  declare const mutate:(x:any)=>void; declare const b:{invoke:(x:string)=>void};
  function make(){return (label:string)=>{const local=label; const packet={verb:local,zone:'north'}; ${body} channel.send(JSON.stringify(packet));};}
  b.invoke=make(); export function ${name}(){b.invoke(${value});}`};
}
function sent(g,name='enter'){return g.protocol.consumers.find(c=>c.name===name)?.boundaries.filter(b=>b.transport==='socket')||[];}
test('symbol aliases and field renames survive arbitrary project symbol renaming',()=>{
  const original=fixture('packet.zone="west";');let renamed=original['a.ts'];
  for(const [a,b] of Object.entries({make:'assemble',label:'tag',local:'copy',packet:'envelope',invoke:'ask',verb:'opCode',zone:'realm'}))renamed=renamed.replaceAll(new RegExp('\\b'+a+'\\b','g'),b);
  const before=sent(graph(original))[0],after=sent(graph({'a.ts':renamed}))[0];
  assert.deepEqual(before.payload.fields.verb,{state:'constant',value:'alpha/read'});
  assert.deepEqual(after.payload.fields.opCode,before.payload.fields.verb);
  assert.equal(after.payload.fields.realm.value,'west');assert(after.events.some(e=>e.kind==='argument_transfer'));
});
test('imported constants, closure arguments and destructured field aliases propagate',()=>{
  const g=graph({'v.ts':"export const CMD='read/second';",'a.ts':`import {CMD as c} from './v';declare const s:WebSocket;declare const b:{go:(x:any)=>void};
  function maker(area:string){return ({op:alias}:any)=>s.send(JSON.stringify({renamed:alias,space:area}));}
  b.go=maker('lab');function entry(){b.go({op:c});}`});
  const payload=sent(g,'entry')[0].payload.fields;assert.equal(payload.renamed.value,'read/second');assert.equal(payload.space.value,'lab');
});
test('dynamic overwrite, spread and unknown mutation never retain a stale key',()=>{
  for(const body of ['packet.verb=dynamic;','Object.assign(packet,dynamic);','mutate(packet);']){
    const b=sent(graph(fixture(body)))[0];assert.equal(b.payload.fields.verb.state,'unknown',body);
  }
  const f=fixture();f['a.ts']=f['a.ts'].replace('JSON.stringify(packet)','JSON.stringify({...packet,...dynamic})');
  assert.equal(sent(graph(f))[0].payload.fields.verb.state,'unknown');
});
test('divergent returns remain unknown; equal branch values stay constant',()=>{
  for(const [second,expected] of [["'other'",'unknown'],["'alpha/read'",'constant']]){
    const f=fixture('', 'enter','choose()');f['a.ts']+=` function choose(){if(dynamic)return 'alpha/read';return ${second};}`;
    assert.equal(sent(graph(f))[0].payload.fields.verb.state,expected);
  }
});
test('bindings with two assignments stay ambiguous',()=>{
  const f=fixture();f['a.ts']+=' b.invoke=make();';const c=graph(f).protocol.consumers.find(c=>c.name==='enter');
  assert.equal(c.status,'ambiguous_binding');assert.equal(c.boundaries.length,0);
});
test('local shadowed property does not inherit an unrelated binding',()=>{
  const f=fixture();f['a.ts']+=' function shadow(b:{invoke:(s:string)=>void}){b.invoke("shadow");}';
  assert.equal(graph(f).protocol.consumers.filter(c=>c.name==='shadow').length,0);
});
test('standard empty array does not invoke callback; project forEach uses its body',()=>{
  const f=fixture();f['a.ts']=f['a.ts'].replace('channel.send(JSON.stringify(packet));','[].forEach(()=>channel.send(JSON.stringify(packet)));');
  assert.equal(sent(graph(f)).length,0);
  const other=fixture();other['a.ts']=other['a.ts'].replace('channel.send(JSON.stringify(packet));','const local={forEach(cb:()=>void){}}; local.forEach(()=>channel.send(JSON.stringify(packet)));');
  assert.equal(sent(graph(other)).length,0);
});
test('platform type identity prevents a project class named WebSocket from becoming a send boundary',()=>{
  const f=fixture();f['a.ts']='class WebSocket{send(v:any){}}\n'+f['a.ts'];
  assert.equal(sent(graph(f)).length,0);
});
test('wire snapshot survives later mutation; finally writes happen before subsequent send',()=>{
  const f=fixture();f['a.ts']=f['a.ts'].replace('channel.send(JSON.stringify(packet));','channel.send(JSON.stringify(packet));packet.verb="later";');
  assert.equal(sent(graph(f))[0].payload.fields.verb.value,'alpha/read');
  assert.equal(sent(graph(fixture('try{}finally{packet.verb="finally";}')))[0].payload.fields.verb.value,'finally');
});

function separatedWindowFixture(event='ask'){
  return {'client/package.json':'{"name":"client"}','host/package.json':'{"name":"host"}',
    'bridge/package.json':'{"name":"bridge"}',
    'client/main.ts':`declare const b:{invoke:(x:string)=>void};
      function make(){return (label:string)=>window.parent.postMessage(JSON.stringify({event:'${event}',args:{op:label},zone:'north'}),'*');}
      b.invoke=make();export function enter(){b.invoke('alpha/read');}`,
    'bridge/receiver.ts':`export class Receiver {cb:(p:any)=>void=()=>{};
      constructor(){window.onmessage=event=>{const packet=JSON.parse(event.data);if(packet.event==='ask')this.cb(packet);};}
      set(cb:(p:any)=>void){this.cb=cb;}}`,
    'host/main.ts':`import {Receiver} from '../bridge/receiver';declare const socket:WebSocket;
      const receiver=new Receiver();receiver.set(body=>socket.send(JSON.stringify({verb:body.args.op,zone:body.zone})));`};
}
test('cross-package Window messages reach an independently analyzed receiver and socket',()=>{
  const g=graph(separatedWindowFixture()),boundary=sent(g)[0];
  assert(boundary);assert.equal(boundary.payload.fields.verb.value,'alpha/read');
  assert.equal(boundary.payload.fields.zone.value,'north');
  assert.equal(boundary.receiver_scope,'host/main.ts');
  assert(boundary.conditions.includes('registered_receiver_is_message_destination'));
  assert.equal(g.analysis_units.length,3);
});
test('cross-package forwarding respects message filters and deleted callback registration',()=>{
  assert.equal(sent(graph(separatedWindowFixture('other'))).length,0);
  const files=separatedWindowFixture();files['host/main.ts']=files['host/main.ts'].replace(/receiver.set\(body=>.*;/,'');
  assert.equal(sent(graph(files)).length,0);
});

test('direct platform sends are discovered without a property binding and keep dynamic fields unknown',()=>{
  const g=graph({'a.ts':`declare const s:WebSocket;export function direct(value:string){const packet={verb:value,space:'lab'};s.send(JSON.stringify(packet));}`});
  const rows=g.protocol.consumers.filter(c=>c.name==='direct');assert.equal(rows.length,1);
  assert.equal(rows[0].boundaries[0].payload.fields.verb.state,'unknown');assert.equal(rows[0].boundaries[0].payload.fields.space.value,'lab');
});
test('rest, spread, Map storage and scheduled closures preserve arguments with a scheduling condition',()=>{
  const g=graph({'a.ts':`declare const s:WebSocket;declare const b:{go:(x:string)=>void};
    function wrap(fn:(...xs:any[])=>void){const saved=new Map();return (...xs:any[])=>{saved.set('key',{xs});setTimeout(()=>{const state=saved.get('key');fn(...state.xs);},20);};}
    b.go=wrap((label:string)=>s.send(JSON.stringify({verb:label,zone:'north'})));export function enter(){b.go('alpha/read');}`});
  const b=sent(g)[0];assert.equal(b.payload.fields.verb.value,'alpha/read');assert(b.conditions.includes('scheduled_callback_fires_without_cancel_or_replacement'));
  assert.equal(g.protocol.consumers.filter(c=>c.discovery==='direct_platform_transport').length,0);
});
test('an exported factory callback keeps its source identity and discoverable export name',()=>{
  const g=graph({'a.ts':`declare const s:WebSocket;declare const b:{go:(x:string)=>void};b.go=(x:string)=>s.send(JSON.stringify({verb:x}));
    function wrap(cb:()=>void){return cb;}export const exported=wrap(()=>b.go('alias/read'));`});
  const row=g.protocol.consumers.find(c=>c.name==='exported');assert(row);assert(row.source_owner);assert.equal(row.aliases[0].relationship,'callback_in_export_initializer');
});
test('a shared module Map may be populated before entry; a local unmatched key stays unresolved',()=>{
  const g=graph({'a.ts':`declare const socket:WebSocket;class Link{send(tag:string){socket.send(JSON.stringify({verb:tag}));}}
    const links=new Map<string,Link>();declare const b:{go:(x:string)=>void};b.go=(tag:string)=>{const link=links.get('live');if(link===undefined)return;link.send(tag);};
    export function enter(){b.go('alpha/read');}`});assert.equal(sent(g)[0].payload.fields.verb.value,'alpha/read');
  const local=graph({'a.ts':`declare const socket:WebSocket;declare const b:{go:(x:string)=>void};function make(){const saved=new Map();return (x:string)=>{saved.set('one',x);socket.send(JSON.stringify({verb:saved.get('two')}));};}b.go=make();function enter(){b.go('alpha/read');}`});
  assert.notEqual(sent(local)[0].payload.fields.verb.state,'constant');
});
