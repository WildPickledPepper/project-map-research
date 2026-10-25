const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),ts=require('typescript');
const {analyze}=require('../adapters/typescript_facts.cjs');
const {analyzeReturns}=require('../adapters/typescript_return_flow.cjs');
const {analyzeData}=require('../adapters/typescript_data_flow.cjs');

function run(files,mode='return',options={}){
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'map-async-'));
  try{
    for(const [file,body] of Object.entries(files)){fs.mkdirSync(path.dirname(path.join(root,file)),{recursive:true});fs.writeFileSync(path.join(root,file),body);}
    const facts=analyze(ts,root,Object.keys(files)),uid=name=>facts.nodes.find(n=>n.kind==='callable'&&n.name===name).id;
    const graph=mode==='return'?analyzeReturns(ts,root,Object.keys(files),{boundarySymbols:[uid('transport')],apiEntries:[uid('api')]},options).return_flow:
      analyzeData(ts,root,Object.keys(files),[uid('load')],options).data_flow;
    return {graph,uid};
  }finally{fs.rmSync(root,{recursive:true,force:true});}
}
function leaves(v){return v.kind==='alternatives'?v.values.flatMap(leaves):v.kind==='object'?Object.values(v.fields).flatMap(leaves):[v];}
const deferred=`
declare function transport(...args:any[]):Promise<any>;
function wrap(fn:(...args:any[])=>Promise<any>){
  const pending=new Map<string,any>();
  return (...args:any[])=>new Promise((resolve,reject)=>{
    const state={args,resolve,reject};pending.set('one',state);
    setTimeout(async()=>{const current=pending.get('one');if(current!==state)return;
      const result=await fn(...current.args);current.resolve(result);pending.delete('one');},3);
  });
}
const request=wrap(transport);
export async function api(){const response=await request('payload');return response.body;}
`;
test('a saved resolver and scheduled rest arguments retain the fulfilled boundary projection',()=>{
  const {graph:g,uid}=run({'a.ts':deferred});const returned=g.returns.find(r=>r.entry===uid('api')&&r.source_symbol===uid('api'));
  assert(leaves(returned.value).some(v=>v.kind==='input_path'&&v.path.join('/')==='body'));
  assert(g.boundaries.some(b=>b.arguments[0]?.value==='payload'));
  assert(g.promise_settlements.some(s=>s.mode==='resolve'&&s.conditions.some(c=>c.kind==='scheduled_callback_candidate')));
});
test('rejecting or replacing a saved resolver removes the fulfillment projection',()=>{
  for(const code of [deferred.replace('current.resolve(result)','current.reject(result)'),
      deferred.replace("setTimeout(async()=>", "state.resolve=()=>{};setTimeout(async()=>")]){
    const {graph:g,uid}=run({'a.ts':code});
    assert(!g.returns.filter(r=>r.source_symbol===uid('api')).some(r=>leaves(r.value).some(v=>v.kind==='input_path')));
  }
});
test('canceling a scheduled callback prevents its boundary and result',()=>{
  const code=deferred.replace('setTimeout(async()=>','const timer=setTimeout(async()=>').replace('},3);','},3);clearTimeout(timer);');
  const {graph:g}=run({'a.ts':code});assert.equal(g.boundaries.length,0);
});
test('an earlier rejection or constant fulfillment wins over a later response settlement',()=>{
  for(const first of ['reject(9);','resolve(9);']){
    const code=deferred.replace('const state={args,resolve,reject};',first+'const state={args,resolve,reject};');
    const {graph:g,uid}=run({'a.ts':code});
    assert(!g.returns.filter(r=>r.source_symbol===uid('api')).some(r=>leaves(r.value).some(v=>v.kind==='input_path')));
    assert(g.promise_settlements.some(s=>s.ignored_after_prior_settlement));
  }
});
test('renamed deferred wrappers retain cross-file symbol and field identity',()=>{
  const body=deferred.slice(deferred.indexOf('function wrap'),deferred.indexOf('const request='));
  const files={'queue.ts':body.replace('function wrap','export function assemble').replaceAll('pending','holding'),
    'api.ts':`import {assemble as build} from './queue';declare function transport(...args:any[]):Promise<any>;
      const request=build(transport);export async function api(){return (await request('other')).renamed;}`};
  const {graph:g,uid}=run(files);assert(g.returns.filter(r=>r.source_symbol===uid('api')).some(r=>leaves(r.value).some(v=>v.path?.[0]==='renamed')));
});
test('a leading queue settles after the source result has been assigned',()=>{
  const code=`declare function transport():Promise<any>;
    function wrap(fn:()=>Promise<any>){return ()=>new Promise(resolve=>{
      const state={queue:[{resolve}],result:undefined as any};
      setTimeout(()=>{while(state.queue.length>0){const item=state.queue.shift()!;item.resolve(state.result);}},1);
      async function execute(){state.result=await fn();}execute();
    });}const request=wrap(transport);export async function api(){return (await request()).rows;}`;
  const {graph:g,uid}=run({'a.ts':code});
  assert(g.returns.filter(r=>r.source_symbol===uid('api')).some(r=>leaves(r.value).some(v=>v.path?.join('/')==='rows')));
});

const pagination=`declare function load():Promise<any>;declare function transfer(x:any):void;
  async function pages(){let merged:any=null;for(;;){const page=await load();
    if(merged===null)merged={...page,rows:[]};merged.rows=merged.rows.concat(page.rows);
    if(page.done)break;
  }return merged;}
  export async function use(){const data=await pages();transfer({data});}`;
test('pagination carries accumulated fields to an external handoff',()=>{
  const {graph:g}=run({'a.ts':pagination},'data');
  assert(g.consumptions.some(c=>c.mode==='external_argument_handoff'&&c.value_dependencies.some(d=>d.path.join('/')==='rows/*')));
  assert(g.consumptions.some(c=>c.value_dependencies.some(d=>d.conditions.some(x=>x.kind==='bounded_loop_iteration'))));
});
test('a nested throwing validation guard preserves the successful pagination continuation',()=>{
  const code=pagination.replace('merged={...page,rows:[]};','{merged={...page,rows:[]};if(!Number.isSafeInteger(page.total))throw Error();}');
  const {graph:g}=run({'a.ts':code},'data');
  assert(g.consumptions.some(c=>c.mode==='external_argument_handoff'&&c.value_dependencies.some(d=>d.path.join('/')==='rows/*')));
});
test('zero iterations, removed accumulation and code after unconditional break add no field flow',()=>{
  const empty=pagination.replace('for(;;)','while(false)');
  assert(!run({'a.ts':empty},'data').graph.api_calls.length);
  const removed=pagination.replace('merged.rows.concat(page.rows)','[]');
  const {graph:g}=run({'a.ts':removed},'data');
  assert(!g.consumptions.some(c=>c.value_dependencies.some(d=>d.path[0]==='rows')));
  const unreachable=pagination.replace('const page=await load();','break;const page=await load();');
  assert.equal(run({'a.ts':unreachable},'data').graph.api_calls.length,0);
});
test('bounded loops report truncation and an infinite loop cannot prove a later handoff',()=>{
  const code=`declare function load():Promise<any>;declare function transfer(x:any):void;
    async function use(){const response=await load();while(true){}transfer(response.rows);}`;
  const {graph:g}=run({'a.ts':code},'data',{maxLoopIterations:2});
  assert(g.diagnostics.some(d=>d.kind==='loop_iteration_budget_exceeded'));assert.equal(g.consumptions.length,0);
});
test('sorting source array values keeps field origins while local sort implementations stay explicit',()=>{
  const code=`declare function load():Promise<any>;async function use(){return (await load()).rows.map((x:any)=>({label:x.title})).sort((a:any,b:any)=>0);}`;
  const {graph:g}=run({'a.ts':code},'data');assert(g.consumptions.some(c=>c.value_dependencies.some(d=>d.path.join('/')==='rows/*/title')));
});
test('a conditional callable alias keeps API identity and its selection condition',()=>{
  const code=`declare function load():Promise<any>;declare function transfer(x:any):void;function other(){return {rows:[]};}
    async function use(flag:boolean){const request=flag?load:other;const response=await request();transfer(response.rows);}`;
  const {graph:g}=run({'a.ts':code},'data');
  assert(g.consumptions.some(c=>c.value_dependencies.some(d=>d.path[0]==='rows'&&d.conditions.some(x=>x.expression==='flag'&&x.when===true))));
});

module.exports={run,leaves};
