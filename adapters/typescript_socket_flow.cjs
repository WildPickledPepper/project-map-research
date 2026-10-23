/* Discover browser socket construction, sends and handler bindings using the
 * existing P3 source value interpreter and compiler declaration identities. */
const fs=require('node:fs'),path=require('node:path');
const {analyze}=require('./typescript_facts.cjs');
const {extractData}=require('./typescript_data_flow.cjs');

function analyzeSockets(ts,root,files,options={}){
  return analyze(ts,root,files,{pathsFromConfigs:true,outputKey:'socket_flow',
    run:ctx=>extractData(ctx,[],{...options,responseRegistries:true,socketOnly:true})});
}
module.exports={analyzeSockets};
if(require.main===module){
  const [root,manifest,tsModule,output]=process.argv.slice(2),ts=require(path.resolve(tsModule));
  if(ts.version!=='5.9.3')throw new Error('Expected TypeScript 5.9.3');
  if(fs.existsSync(output))throw new Error('Use a new output file');
  const result=analyzeSockets(ts,root,JSON.parse(fs.readFileSync(manifest,'utf8')).files.map(f=>f.path));
  fs.writeFileSync(output,JSON.stringify(result,null,2)+'\n');
  process.stdout.write(JSON.stringify(Object.fromEntries(['entries','creations','channel_bindings','listener_bindings','transmissions'].map(k=>[k,result.socket_flow[k].length])))+'\n');
}
