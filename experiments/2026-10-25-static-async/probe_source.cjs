/* Execute analysis against the unchanged product debounce implementation. */
const fs=require('node:fs'),path=require('node:path'),ts=require('typescript');
const {analyze}=require('../../adapters/typescript_facts.cjs');
const {analyzeReturns}=require('../../adapters/typescript_return_flow.cjs');
const [source,output]=process.argv.slice(2);fs.mkdirSync(output,{recursive:false});
fs.copyFileSync(path.join(source,'modules/lib/src/utils/createSmartDebounceRequestFunc.ts'),path.join(output,'queue.ts'));
fs.writeFileSync(path.join(output,'fixture.ts'),`import {createSmartDebounceRequestFunc} from './queue';
declare function transport(...args:any[]):Promise<any>;
const trailing=createSmartDebounceRequestFunc(transport,{leading:false});
const leading=createSmartDebounceRequestFunc(transport,{leading:true});
export async function trailingApi(){return (await trailing('a')).body;}
export async function leadingApi(){return (await leading('b')).body;}`);
const files=['queue.ts','fixture.ts'],facts=analyze(ts,output,files),uid=name=>facts.nodes.find(n=>n.kind==='callable'&&n.name===name).id;
const result=analyzeReturns(ts,output,files,{boundarySymbols:[uid('transport')],apiEntries:['trailingApi','leadingApi'].map(uid)});
fs.writeFileSync(path.join(output,'facts.json'),JSON.stringify(result));
function leaves(v){return v.kind==='alternatives'?v.values.flatMap(leaves):v.kind==='object'?Object.values(v.fields).flatMap(leaves):[v];}
const summary=['trailingApi','leadingApi'].map(name=>({name,returned:result.return_flow.returns.filter(r=>r.source_symbol===uid(name)).map(r=>r.value),
  hasBoundaryProjection:result.return_flow.returns.filter(r=>r.source_symbol===uid(name)).some(r=>leaves(r.value).some(v=>v.kind==='input_path'&&v.path.join('/')==='body')),
  diagnostics:result.return_flow.diagnostics.filter(d=>d.entry===uid(name)).map(d=>({kind:d.kind,line:d.line,expression:d.expression}))}));
fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(summary,null,2)+'\n');console.log(JSON.stringify(summary));
