const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'), os=require('node:os'), path=require('node:path');
const ts=require('typescript');
const {analyze}=require('../adapters/typescript_facts.cjs');

function graph(files) {
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'p1-ts-'));
  try {
    for(const [p,s] of Object.entries(files)){fs.mkdirSync(path.dirname(path.join(dir,p)),{recursive:true});fs.writeFileSync(path.join(dir,p),s);}
    return analyze(ts,dir,Object.keys(files));
  } finally {fs.rmSync(dir,{recursive:true,force:true});}
}
function pairs(g,kind){const nodes=new Map(g.nodes.map(n=>[n.id,n]));return g.edges.filter(e=>e.kind===kind).map(e=>[nodes.get(e.source),nodes.get(e.target),e]);}

test('generic override and arrow callback use subclass; super uses base',()=>{
  const g=graph({'a.ts':'abstract class Base { send<T>(x:T){return x;} } class Child extends Base { send<T>(x:T){return super.send(x);} fetch(){const cb=()=>this.send(1);return cb();} }'});
  const p=pairs(g,'STATIC_CALL_TARGET');
  assert(p.some(([a,b])=>a.name==='this.send'&&b.name==='Child.send'));
  assert(p.some(([a,b])=>a.name==='super.send'&&b.name==='Base.send'));
  assert(g.nodes.some(n=>n.name==='Base.send'&&n.type_parameters?.[0]==='T'));
});
test('factory binding links imported factory and returned callable',()=>{
  const g=graph({'factory.ts':'export function make(){return (s:string)=>s;}','entry.ts':"import {make} from './factory'; declare const bridge:{run:(s:string)=>string}; bridge.run=make(); export function entry(){return bridge.run('x');}"});
  assert.equal(pairs(g,'BINDS_RESULT_OF').length,1);
  assert.equal(pairs(g,'BOUND_CALL_CANDIDATE').length,1);
  assert.equal(pairs(g,'USES_BINDING')[0][2].status,'conditional');
});
test('multiple assignments retain ambiguity',()=>{
  const g=graph({'a.ts':"declare const b:{run:()=>number}; b.run=()=>1; b.run=()=>2; b.run();"});
  assert.equal(pairs(g,'BOUND_CALL_CANDIDATE').length,2);
  assert(g.nodes.some(n=>n.kind==='call_site'&&n.name==='b.run'&&n.resolution==='ambiguous_binding'));
});
test('shadowed receiver does not inherit global binding',()=>{
  const g=graph({'a.ts':"declare const b:{run:()=>number}; b.run=()=>1; function use(b:{run:()=>number}){return b.run();}"});
  assert.equal(pairs(g,'USES_BINDING').length,0);
});
test('delete assignment from input removes binding edges',()=>{
  const g=graph({'a.ts':'declare const b:{run:()=>number}; b.run();'});
  assert.equal(pairs(g,'USES_BINDING').length,0);
});
test('separate package runtime scopes do not cross-bind globals',()=>{
  const g=graph({'a/package.json':'{"name":"app-a"}','b/package.json':'{"name":"app-b"}',
    'a/boot.ts':'window.alert=()=>{};','b/use.ts':"window.alert('x');"});
  assert.equal(pairs(g,'USES_BINDING').length,0);
});
test('independent package globals have separate compiler declarations',()=>{
  const g=graph({'a/package.json':'{"name":"a"}','b/package.json':'{"name":"b"}',
    'a/boot.ts':'export {};declare global {interface Window {query:(x:string)=>void;}} window.query=x=>{};',
    'a/use.ts':"window.query('a');",
    'b/boot.ts':'export {};declare global {interface Window {query:(x:number,y:number)=>void;}} window.query=(x,y)=>{};',
    'b/use.ts':'window.query(1,2);'});
  assert.equal(pairs(g,'USES_BINDING').length,2);
  assert(!g.diagnostics.some(d=>d.kind==='typescript_semantic'));
  assert.equal(g.analysis_units.length,2);
});
test('test mocks do not create product global binding ambiguity',()=>{
  const g=graph({'package.json':'{"name":"app"}',
    'boot.ts':'export {};declare global {interface Window {query:(x:string)=>void;}} window.query=x=>{};',
    'use.ts':"window.query('a');",'tests/use.test.ts':"window.query=x=>{};window.query('test');"});
  const call=g.nodes.find(n=>n.path==='use.ts'&&n.kind==='call_site');
  assert.equal(call.resolution,'conditional_binding');
  const bindings=pairs(g,'USES_BINDING').filter(([a])=>a.id===call.id);
  assert.equal(bindings.length,1);assert.equal(bindings[0][1].path,'boot.ts');
  assert.equal(g.analysis_units.length,2);
  assert.equal(g.coverage.length,3);
});
test('workspace imports retain targets across automatic compiler root units',()=>{
  const g=graph({'a/package.json':'{"name":"a"}','b/package.json':'{"name":"b","exports":{".":"./api.ts"}}',
    'a/use.ts':"import {helper} from 'b';helper();",'b/api.ts':'export function helper(){return 1;}'});
  assert(pairs(g,'STATIC_CALL_TARGET').some(([a,b])=>a.path==='a/use.ts'&&b.path==='b/api.ts'));
});
test('symbolic records are unit-scoped while source identities and literal values are preserved',()=>{
  const {scopeFlow}=require('../adapters/typescript_analysis_units.cjs');
  const flow={records:[{id:'generated',source_symbol:'source',value:'generated'}],references:[{root:'generated',target:'source'}]};
  const a=scopeFlow(flow,'a'),b=scopeFlow(flow,'b');
  assert.notEqual(a.records[0].id,b.records[0].id);
  assert.equal(a.references[0].root,a.records[0].id);
  assert.equal(a.references[0].target,'source');assert.equal(a.records[0].value,'generated');
});
test('semantic error does not publish a certain call target',()=>{
  const g=graph({'a.ts':"function f(x:number){} f('wrong');"});
  assert.equal(pairs(g,'STATIC_CALL_TARGET').length,0);
  assert(g.nodes.some(n=>n.reason==='compiler_diagnostic_at_call'));
});
test('unavailable module is diagnosed and no target invented',()=>{
  const g=graph({'a.ts':"import {foo} from 'missing-package';foo();"});
  assert(g.diagnostics.some(d=>d.kind==='module_outside_input'));
  assert.equal(pairs(g,'STATIC_CALL_TARGET').length,0);
});
test('same-named exports resolve via their own imports',()=>{
  const g=graph({'a.ts':'export function run(){return 1;}','b.ts':'export function run(){return 2;}',
    'use.ts':"import {run} from './a'; run();"});
  assert.equal(pairs(g,'STATIC_CALL_TARGET')[0][1].path,'a.ts');
});
test('invalid syntax is retained as a diagnostic',()=>{
  const g=graph({'a.ts':'function broken( { return 1;'});
  assert(g.diagnostics.some(d=>d.kind==='typescript_syntax'));
});

test('line ending changes preserve graph identity',()=>{
  const source='function f() { return 1; }\nf();\n';
  assert.deepEqual(graph({'a.ts':source}),graph({'a.ts':source.replaceAll('\n','\r\n')}));
});
test('invalid call to a bound function stays unresolved',()=>{
  const g=graph({'a.ts':"declare const b:{run:(s:string)=>string}; b.run=s=>s; b.run(42);"});
  assert.equal(pairs(g,'BOUND_CALL_CANDIDATE').length,0);
  assert(g.nodes.some(n=>n.reason==='compiler_diagnostic_at_call'));
});
test('callback argument preserves owner and invocation condition',()=>{
  const g=graph({'a.ts':'class Client { send(){} fetch(){return new Promise(resolve=>{this.send();resolve(1);});} }'});
  const callback=pairs(g,'PASSES_CALLBACK');
  assert.equal(callback.length,1);
  assert.equal(callback[0][0].name,'Promise');
  assert(callback[0][1].name.startsWith('Client.fetch.'));
  assert.equal(callback[0][2].execution,'depends_on_callee_invocation');
  assert(pairs(g,'STATIC_CALL_TARGET').some(([a,b])=>a.name==='this.send'&&b.name==='Client.send'));
});
