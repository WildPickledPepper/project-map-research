const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const ts=require('typescript');
const {analyze}=require('../adapters/typescript_facts.cjs');

function graph(files){
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'mixed-language-facts-'));
  try{
    for(const [name,body] of Object.entries(files)){const p=path.join(root,name);fs.mkdirSync(path.dirname(p),{recursive:true});fs.writeFileSync(p,body);}
    return analyze(ts,root,Object.keys(files));
  }finally{fs.rmSync(root,{recursive:true,force:true});}
}
function pairs(g,kind){const byId=new Map(g.nodes.map(n=>[n.id,n]));return g.edges.filter(e=>e.kind===kind).map(e=>[byId.get(e.source),byId.get(e.target),e]);}

test('TS caller resolves a JS constructor and method without same-name cross-linking',()=>{
  const g=graph({'client.ts':"import {Engine} from './unit.js';const value=new Engine();value.run();",
    'unit.js':'export class Engine {constructor(){} run(){return 1;}}',
    'other.js':'export class Engine {constructor(){} run(){return 2;}}'});
  const calls=pairs(g,'STATIC_CALL_TARGET').filter(([a])=>a.path==='client.ts');
  assert.equal(calls.length,2);assert(calls.every(([,b])=>b.path==='unit.js'));
  assert(calls.every(([,b])=>b.language==='javascript'&&b.id.startsWith('js:')));
  assert.equal(g.coverage.length,3);
});

test('JS caller resolves TS function and re-export alias',()=>{
  const g=graph({'launch.mjs':"import {chosen} from './barrel.js';export function launch(){return chosen();}",
    'barrel.js':"export {execute as chosen} from './core.ts';",'core.ts':'export function execute(){return 42;}',
    'decoy.ts':'export function execute(){return 99;}'});
  assert(pairs(g,'STATIC_CALL_TARGET').some(([a,b])=>a.path==='launch.mjs'&&b.path==='core.ts'&&b.name==='execute'));
  assert(pairs(g,'IMPORTS_MODULE').some(([a,b])=>a.path==='launch.mjs'&&b.path==='barrel.js'));
  assert(pairs(g,'IMPORTS_MODULE').some(([a,b])=>a.path==='barrel.js'&&b.path==='core.ts'));
});

test('CommonJS named and function exports resolve through require',()=>{
  const g=graph({'main.cjs':"const {build}=require('./named.cjs');const invoke=require('./callable.cjs');build();invoke();",
    'named.cjs':'exports.build=function build(){return 1;};',
    'callable.cjs':'module.exports=function execute(){return 2;};'});
  const calls=pairs(g,'STATIC_CALL_TARGET').filter(([a])=>a.path==='main.cjs');
  assert(calls.some(([,b])=>b.path==='named.cjs'&&b.name==='build'));
  assert(calls.some(([,b])=>b.path==='callable.cjs'&&b.name==='execute'));
  assert.equal(pairs(g,'IMPORTS_MODULE').filter(([a])=>a.path==='main.cjs').length,2);
});

test('workspace conditional exports preserve import and require branches',()=>{
  const g=graph({'apps/web/package.json':'{"name":"web","type":"module"}',
    'apps/web/entry.mjs':"import {answer} from '@fixture/tool';answer();",
    'apps/job/package.json':'{"name":"job"}','apps/job/entry.cjs':"const {answer}=require('@fixture/tool');answer();",
    'lib/package.json':'{"name":"@fixture/tool","exports":{".":{"import":"./esm.mjs","require":"./common.cjs"}}}',
    'lib/esm.mjs':'export function answer(){return 1;}', 'lib/common.cjs':'exports.answer=function answer(){return 2;};'});
  const calls=pairs(g,'STATIC_CALL_TARGET');
  assert(calls.some(([a,b])=>a.path==='apps/web/entry.mjs'&&b.path==='lib/esm.mjs'));
  assert(calls.some(([a,b])=>a.path==='apps/job/entry.cjs'&&b.path==='lib/common.cjs'));
  assert(!calls.some(([a,b])=>a.path==='apps/job/entry.cjs'&&b.path==='lib/esm.mjs'));
});

test('JS JSX MJS CJS MTS CTS sources are not omitted by compiler partitions',()=>{
  const files={'a.js':'export function a(){}','b.jsx':'export function b(){return <section/>;}',
    'c.mjs':'export function c(){}','d.cjs':'exports.d=function d(){};',
    'e.mts':'export function e():number{return 1;}','f.cts':'export function f():number{return 2;}'};
  const g=graph(files);assert.deepEqual(new Set(g.coverage.map(r=>r.path)),new Set(Object.keys(files)));
  assert(!g.diagnostics.some(d=>d.kind==='typescript_syntax'));
});

test('shadowed require and a dynamic module name never invent module targets',()=>{
  const g=graph({'entry.js':"function custom(require){return require('./real.js');} export function dynamic(name){return require(name);}",
    'real.js':'export function run(){return 1;}'});
  assert.equal(pairs(g,'IMPORTS_MODULE').filter(([a])=>a.path==='entry.js').length,0);
  assert(g.nodes.some(n=>n.kind==='module_reference'&&n.reason==='shadowed_require'));
  assert(g.nodes.some(n=>n.kind==='module_reference'&&n.reason==='module_name_not_static_string'));
});

test('adding, moving, removing an imported JS module recomputes targets',()=>{
  const consumer="import {use} from './added.js';export function entry(){return use();}";
  const absent=graph({'entry.ts':consumer});assert.equal(pairs(absent,'STATIC_CALL_TARGET').length,0);
  const added=graph({'entry.ts':consumer,'added.js':'export function use(){return 1;}'});
  assert(pairs(added,'STATIC_CALL_TARGET').some(([,b])=>b.path==='added.js'));
  const moved=graph({'entry.ts':consumer.replace('./added.js','./odd_layout/renamed.js'),
    'odd_layout/renamed.js':'export function use(){return 1;}'});
  assert(!moved.nodes.some(n=>n.path==='added.js'));
  assert(pairs(moved,'STATIC_CALL_TARGET').some(([,b])=>b.path==='odd_layout/renamed.js'));
  const removed=graph({'entry.ts':consumer});assert(!removed.nodes.some(n=>n.path==='added.js'));
});

test('identical calls on the same line keep distinct positions and identities',()=>{
  const g=graph({'a.js':'export function go(){} go(); go();'});
  const calls=pairs(g,'STATIC_CALL_TARGET');assert.equal(calls.length,2);
  assert.notEqual(calls[0][0].id,calls[1][0].id);assert.notEqual(calls[0][0].column,calls[1][0].column);
});

test('duplicate workspace package names remain ambiguous without a package context',()=>{
  const g=graph({'entry.mjs':"import {run} from 'duplicate';run();",'first/package.json':'{"name":"duplicate"}',
    'first/index.js':'export function run(){}','second/package.json':'{"name":"duplicate"}','second/index.js':'export function run(){}'});
  assert(g.diagnostics.some(d=>d.kind==='workspace_package_ambiguous'));
  assert.equal(pairs(g,'IMPORTS_MODULE').filter(([a])=>a.path==='entry.mjs').length,0);
  assert.equal(pairs(g,'STATIC_CALL_TARGET').filter(([a])=>a.path==='entry.mjs').length,0);
});

test('type-only dependencies are recorded with their source role',()=>{
  const g=graph({'entry.ts':"import {type Payload} from './schema.js';export type T=Payload;",
    'schema.ts':'export interface Payload {value:string;}'});
  const imports=pairs(g,'IMPORTS_MODULE');assert.equal(imports.length,1);
  assert.equal(imports[0][2].type_only,true);assert.equal(imports[0][2].runtime_execution,'not_observed');
});

test('a computed method selected from two alternatives is not a certain call target',()=>{
  const g=graph({'a.js':"export class Router {first(x){return x;}second(x){return x;} run(flag){const method=flag?'first':'second';return this[method](1);}}"});
  assert(!pairs(g,'STATIC_CALL_TARGET').some(([a])=>a.name==='this[method]'));
  const call=g.nodes.find(n=>n.kind==='call_site'&&n.name==='this[method]');
  assert(call&&call.resolution!=='static_declaration');
  const candidates=pairs(g,'STATIC_CALL_CANDIDATE').filter(([a])=>a.id===call.id);
  assert.deepEqual(new Set(candidates.map(([,b])=>b.name)),new Set(['Router.first','Router.second']));
});
