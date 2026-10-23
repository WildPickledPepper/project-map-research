/* Source return packaging and API unwrapping, using extracted Promise boundaries. */
const fs=require('node:fs'),path=require('node:path');
const {analyze}=require('./typescript_facts.cjs');
const {extractData}=require('./typescript_data_flow.cjs');
function analyzeReturns(ts,root,files,inputs,options={}){
  return analyze(ts,root,files,{pathsFromConfigs:true,outputKey:'return_flow',
    run:ctx=>extractData(ctx,[],{...options,...inputs,responseRegistries:true,returnOnly:true})});
}
module.exports={analyzeReturns};
if(require.main===module){
  const [root,manifest,base,tsModule,output]=process.argv.slice(2),ts=require(path.resolve(tsModule));
  if(ts.version!=='5.9.3')throw new Error('Expected TypeScript 5.9.3');
  if(fs.existsSync(output))throw new Error('Use a new output file');
  const g=JSON.parse(fs.readFileSync(base,'utf8'));
  const result=analyzeReturns(ts,root,JSON.parse(fs.readFileSync(manifest,'utf8')).files.map(f=>f.path),{
    boundarySymbols:[...new Set(g.response_callbacks.registrations.map(r=>r.entry))],
    apiEntries:g.frontend.api_symbols,handoffSymbols:[...new Set(g.response_callbacks.settlements.filter(s=>s.registry_context).map(s=>s.entry))]});
  fs.writeFileSync(output,JSON.stringify(result,null,2)+'\n');
  process.stdout.write(JSON.stringify(Object.fromEntries(['entries','boundaries','returns','transmissions','window_listeners','handoffs'].map(k=>[k,result.return_flow[k].length])))+'\n');
}
