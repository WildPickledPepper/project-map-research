/* Replay a proposed entry-discovery change while the committed builder runs. */
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),{execFileSync}=require('node:child_process');
const base=path.resolve(__dirname,'../../adapters/typescript_protocol_flow.cjs');
const helper=JSON.stringify(path.resolve(__dirname,'prototype_roots.cjs'));
const insertion=`
  const existingOwners=new Set(consumers.map(t=>t.source_owner));
  for(const {owner,call} of receiversOnly?[]:require(${helper}).roots(ctx,bindingsByCall,platformType)){
    const ownerId=id(owner,'callable');if(existingOwners.has(ownerId))continue;existingOwners.add(ownerId);
    const item={id:'protocol:'+id(call,'call_site'),source_call:id(call,'call_site'),source_owner:ownerId,name:ctx.qualified(owner),...loc(call),binding_count:0,discovery:'exported_source_wrapper',events:[],boundaries:[]};
    active=item;steps=0;const c={env:new Map(),resolving:new Set(),receiver:null,depth:0,current:owner,conditions:['exported_source_call_path_candidate']};
    invoke(fn(owner,c.env),owner.parameters.map(()=>unk('entry_parameter_runtime')),c);
    for(const sent of [...item.boundaries].filter(b=>b.transport==='window.postMessage'))dispatch(item,sent,c);
    item.status=item.boundaries.length?'transport_found':'no_transport_found';consumers.push(item);
  }
`;
const source=execFileSync('git',['show','2631af8:adapters/typescript_protocol_flow.cjs'],{cwd:path.resolve(__dirname,'../..'),encoding:'utf8'}).replace('  // A transport is an entry',insertion+'  // A transport is an entry');
const replay=new Module(base,module);replay.filename=base;replay.paths=module.paths;replay._compile(source,base);
const [root,manifest,typescript,output]=process.argv.slice(2);
const g=replay.exports.analyzeProtocol(require(path.resolve(typescript)),path.resolve(root),JSON.parse(fs.readFileSync(manifest,'utf8')).files.map(f=>f.path));
if(fs.existsSync(output))throw Error('Use a new output');fs.writeFileSync(output,JSON.stringify(g));
process.stdout.write(JSON.stringify({consumers:g.protocol.consumers.length,boundaries:g.protocol.consumers.flatMap(c=>c.boundaries).length})+'\n');
