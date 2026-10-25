/* Reuse compiler module resolution, including a read-only workspace package view.
 * All virtual lookups map back to supplied files; no package install or product execution. */
const path=require('node:path');

function install(ts,host,{allowed,packages,options,pathConfigs,relative,diagnostics}){
  const cache=new Map();
  function modeFor(literal,sf){
    const p=literal.parent;
    if((ts.isCallExpression(p)&&ts.isIdentifier(p.expression)&&p.expression.text==='require')||ts.isExternalModuleReference(p))return ts.ModuleKind.CommonJS;
    return ts.getModeForUsageLocation?.(sf,literal,options)??ts.ModuleKind.ESNext;
  }
  function resolve(name,file,mode){
    const key=JSON.stringify([file,name,mode]);if(cache.has(key))return cache.get(key);
    const config=pathConfigs.filter(c=>path.resolve(file).startsWith(c.dir+path.sep)).sort((a,b)=>b.dir.length-a.dir.length)[0];
    const compilerOptions=config?{...options,baseUrl:config.dir,paths:config.paths}:options;
    const attempt=resolverHost=>ts.resolveModuleName(name,file,compilerOptions,resolverHost,undefined,undefined,mode).resolvedModule;
    let resolved=attempt(host);
    if(!resolved||!allowed.has(path.resolve(resolved.resolvedFileName))){
      const candidates=packages.filter(p=>name===p.data.name||name.startsWith(p.data.name+'/'));
      if(candidates.length===1){
        const pkg=candidates[0],container=path.join(path.dirname(file),'node_modules'),virtual=path.join(container,...pkg.data.name.split('/'));
        function map(p){const full=path.resolve(p);return full===virtual||full.startsWith(virtual+path.sep)?path.join(pkg.dir,path.relative(virtual,full)):full;}
        const resolverHost={...host,fileExists:p=>host.fileExists(map(p)),readFile:p=>host.readFile(map(p)),
          directoryExists:p=>{const full=path.resolve(p);return full===container||full===path.dirname(virtual)||host.directoryExists?.(map(p))||false;},
          realpath:p=>map(p)};
        resolved=attempt(resolverHost);
        if(resolved)resolved={...resolved,resolvedFileName:map(resolved.resolvedFileName),
          ...(resolved.originalPath?{originalPath:map(resolved.originalPath)}:{}),isExternalLibraryImport:false};
      }else if(candidates.length>1){
        diagnostics.push({path:relative(file),kind:'workspace_package_ambiguous',module:name,
          candidates:candidates.map(p=>relative(p.dir))});resolved=undefined;
      }
    }
    if(resolved&&!allowed.has(path.resolve(resolved.resolvedFileName)))resolved=undefined;
    if(!resolved)diagnostics.push({path:relative(file),kind:'module_outside_input',module:name,
      resolution_mode:mode===ts.ModuleKind.CommonJS?'require':'import'});
    cache.set(key,resolved);return resolved;
  }
  host.resolveModuleNameLiterals=(literals,file,redirected,compilerOptions,sf)=>literals.map(literal=>({
    resolvedModule:resolve(literal.text,file,modeFor(literal,sf))}));
  return {resolve,modeFor};
}

module.exports={install};
