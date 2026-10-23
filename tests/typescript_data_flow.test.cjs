const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const ts=require('typescript');
const {analyze}=require('../adapters/typescript_facts.cjs');
const {extractData}=require('../adapters/typescript_data_flow.cjs');

function graph(source,options={}) {
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'p3-data-'));
  try {fs.writeFileSync(path.join(dir,'a.ts'),source);
    return analyze(ts,dir,['a.ts'],{outputKey:'data_flow',run:ctx=>extractData(ctx,ctx.facts.nodes.filter(n=>n.kind==='callable'&&n.name==='load').map(n=>n.id),options)});
  } finally {fs.rmSync(dir,{recursive:true,force:true});}
}
const prefix='declare function load():Promise<any>;declare function schedule(fn:()=>void):void;';

test('response field consumption and a later refresh are different dependencies',()=>{
  const g=graph(prefix+'async function use(state:any){const r=await load();const values=r.records;schedule(()=>{state.lines=values;state.refresh=!state.refresh;});}').data_flow;
  const lines=g.state_writes.find(w=>w.target.path[0]==='lines'),refresh=g.state_writes.find(w=>w.target.path[0]==='refresh');
  assert.deepEqual(lines.value_dependencies[0].path,['records']);assert.equal(refresh.value_dependencies.length,0);
  assert.equal(refresh.continuation_apis.length,1);assert(lines.conditions.some(c=>c.kind==='external_callee_invokes_callback'));
});
test('array construction through a helper preserves source element fields',()=>{
  const g=graph(prefix+'function transform(items:any[]){const out:any[]=[];for(const item of items){out.push({renamed:item.label});}return out;}'
    +'async function use(state:any){const r=await load();state.lines=transform(r.entries);}').data_flow;
  assert(g.state_writes[0].value_dependencies.some(d=>JSON.stringify(d.path)==='["entries","*","label"]'));
  assert(g.field_reads.some(r=>r.call_chain.length));
});
test('known helper ignoring response input does not invent a value dependency',()=>{
  const g=graph(prefix+'function constant(items:any){return 7;}async function use(state:any){const r=await load();state.n=constant(r.records);}').data_flow;
  assert.equal(g.state_writes[0].value_dependencies.length,0);assert.equal(g.state_writes[0].continuation_apis.length,1);
});
test('two calls to the same API retain different request contexts',()=>{
  const g=graph(prefix+'async function use(state:any){const a=await load();const b=await load();state.first=a.rows;state.second=b.rows;}').data_flow;
  assert.notEqual(g.state_writes[0].value_dependencies[0].request_context,g.state_writes[1].value_dependencies[0].request_context);
});
test('an uncalled local callback has no writes; a known callback consumer uses its body',()=>{
  const g=graph(prefix+'function ignore(cb:()=>void){}async function use(state:any){const r=await load();const cb=()=>{state.lines=r.rows;};ignore(cb);}').data_flow;
  assert.equal(g.state_writes.length,0);
});
test('reassignment replaces response value and unknown calls retain a gap',()=>{
  const g=graph(prefix+'declare function opaque(x:any):any;async function use(state:any){let r=await load();r={rows:[]};state.first=r.rows;state.second=opaque(await load());}').data_flow;
  assert(g.state_writes.every(w=>!w.value_dependencies.length));assert(g.diagnostics.some(d=>d.kind==='unresolved_call_with_response_argument'));
});
test('application field and variable renaming needs no extractor changes',()=>{
  const source=prefix+'async function use(state:any){const packet=await load();state.view=packet.payload;}';
  const g=graph(source.replaceAll('packet','result').replaceAll('payload','items').replaceAll('view','display')).data_flow;
  assert.deepEqual(g.state_writes[0].target.path,['display']);assert.deepEqual(g.state_writes[0].value_dependencies[0].path,['items']);
});
test('analysis budget is visible',()=>{
  const g=graph(prefix+'async function use(state:any){const r=await load();state.lines=r.rows;}',{maxSteps:2}).data_flow;
  assert(g.entries[0].truncated);assert(g.diagnostics.some(d=>d.kind==='step_limit'));
});
test('unawaited API promise is not a fulfilled response',()=>{
  const g=graph(prefix+'async function use(state:any){const pending=load();state.bad=pending.rows;const ready=await pending;state.good=ready.rows;}').data_flow;
  assert.equal(g.state_writes.length,1);assert.deepEqual(g.state_writes[0].target.path,['good']);
});

test('both live branches keep their response conditions and later state writes',()=>{
  const g=graph(prefix+'async function use(state:any,flag:boolean){const r=await load();let x;if(flag){x=r.left;}else{x=r.right;}state.value=x;}').data_flow;
  const deps=g.state_writes.flatMap(w=>w.value_dependencies);
  for(const side of ['left','right'])assert(deps.some(d=>d.path[0]===side&&d.conditions.some(c=>c.expression==='flag'&&c.when===(side==='left'))));
});

test('source mutation through a helper is visible to the subsequent consumer',()=>{
  const g=graph(prefix+'function patch(x:any){x.from=x.to;}async function use(state:any){const r=await load();patch(r.record);state.value=r.record.from;}').data_flow;
  assert.deepEqual(g.state_writes[0].value_dependencies[0].path,['record','to']);
});

test('unknown mutation remains a qualified candidate rather than a clean source edge',()=>{
  const g=graph(prefix+'declare function opaque(x:any):void;async function use(state:any){const r=await load();opaque(r);state.value=r.rows;}').data_flow;
  assert(g.state_writes[0].value_dependencies[0].gaps.some(g=>g.kind==='possible_mutation_by_unresolved_call'));
});

test('throw and short circuit retain the condition of later writes',()=>{
  const g=graph(prefix+'async function use(state:any,flag:boolean){const r=await load();if(flag){throw Error();}flag && (state.a=r.rows);state.b=r.rows;}').data_flow;
  assert(g.state_writes.every(w=>w.conditions.some(c=>c.expression==='flag'&&c.when===false)));
  assert(g.state_writes.find(w=>w.target.path[0]==='a').conditions.some(c=>c.expression==='flag'&&c.when===true));
});

test('an unawaited async helper does not impose fulfillment on its caller',()=>{
  const g=graph(prefix+'async function helper(){await load();}function outer(state:any){load();helper();state.done=true;}').data_flow;
  assert.equal(g.entries.length,2);
  assert.equal(g.state_writes.length,0);
});
