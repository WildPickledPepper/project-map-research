/* Reuse the P3 value interpreter to discover deferred response callbacks. */
const fs=require('node:fs'),path=require('node:path');
const {analyze}=require('./typescript_facts.cjs');
const {extractData}=require('./typescript_data_flow.cjs');

function analyzeResponse(ts,root,files,options={}){
  return analyze(ts,root,files,{pathsFromConfigs:true,outputKey:'response_flow',
    run:ctx=>extractData(ctx,[],{...options,responseRegistries:true})});
}
module.exports={analyzeResponse};
if(require.main===module){
  const [root,manifest,tsModule,output]=process.argv.slice(2),ts=require(path.resolve(tsModule));
  if(ts.version!=='5.9.3')throw new Error('Expected TypeScript 5.9.3');
  if(fs.existsSync(output))throw new Error('Use a new output file');
  const result=analyzeResponse(ts,root,JSON.parse(fs.readFileSync(manifest,'utf8')).files.map(f=>f.path));
  fs.writeFileSync(output,JSON.stringify(result,null,2)+'\n');
  process.stdout.write(JSON.stringify(Object.fromEntries(['entries','promises','registrations','lookups','settlements'].map(k=>[k,result.response_flow[k].length])))+'\n');
}
