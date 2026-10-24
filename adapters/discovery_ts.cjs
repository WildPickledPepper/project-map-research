/* File-local discovery through the pinned TypeScript compiler; no inferred edges. */
const fs = require('node:fs');
const path = require('node:path');
const readline = require('node:readline');

function analyze(ts, name, source) {
  const sf = ts.createSourceFile(name, source, ts.ScriptTarget.Latest, true,
    name.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const out = {path:name, evidence_kind:'typescript_compiler_ast', compiler_version:ts.version,
    symbols:[], types:[], interfaces:[], imports:[], calls:[], registrations:[], resources:[], entries:[], diagnostics:[],
    limits:['file_local_syntax_only','types_not_checked','call_targets_not_resolved',
      'registration_hints_not_proven_registrations','declarations_not_runtime_resources']};
  const registration=/(register|subscribe|addEventListener|(?:^|\.)(on|set|emplace|insert)$)/i;
  function loc(n) { const start=n.getStart(sf), p=sf.getLineAndCharacterOfPosition(start);
    return {line:p.line+1,column:p.character+1,start_offset:start,end_offset:n.end}; }
  function short(n) {return n.name?.getText(sf) || (ts.isVariableDeclaration(n.parent)?n.parent.name.getText(sf):`<lambda@${loc(n).line}>`);}
  function qualified(n) {const parts=[short(n)];for(let p=n.parent;p;p=p.parent)
    if(ts.isClassLike(p)||ts.isInterfaceDeclaration(p)||ts.isModuleDeclaration(p)||ts.isFunctionLike(p))parts.unshift(short(p));return parts.join('.');}
  function exported(n) {return n.modifiers?.some(m=>m.kind===ts.SyntaxKind.ExportKeyword || m.kind===ts.SyntaxKind.DefaultKeyword);}
  function walk(n) {
    if(ts.isFunctionLike(n) && n.parameters) {
      const s={name:short(n),qualified_name:qualified(n),kind:ts.SyntaxKind[n.kind],definition:!!n.body,
        parameters:n.parameters.map(p=>p.getText(sf)),...loc(n)};out.symbols.push(s);
      if(!n.body)out.interfaces.push(s);
      if(exported(n))out.entries.push({kind:'exported_callable_candidate',name:s.qualified_name,...loc(n)});
    }
    if(ts.isClassLike(n)||ts.isInterfaceDeclaration(n)||ts.isTypeAliasDeclaration(n)||ts.isEnumDeclaration(n)) {
      const t={name:short(n),qualified_name:qualified(n),kind:ts.SyntaxKind[n.kind],...loc(n)};out.types.push(t);
      if(ts.isInterfaceDeclaration(n))out.interfaces.push(t);
    }
    if(ts.isImportDeclaration(n)||ts.isExportDeclaration(n))out.imports.push({module:n.moduleSpecifier?.getText(sf)||null,
      kind:ts.SyntaxKind[n.kind],...loc(n)});
    if(ts.isCallExpression(n)||ts.isNewExpression(n)) {
      const args=n.arguments?.map(a=>a.getText(sf))||[], callee=n.expression.getText(sf);
      const c={callee_spelling:callee.slice(0,500),argument_spellings:args.map(a=>a.slice(0,500)),
        spellings_truncated:callee.length>500||args.some(a=>a.length>500),resolution:'unresolved',...loc(n)};
      out.calls.push(c);
      if(registration.test(callee))out.registrations.push({kind:'registration_call_candidate',callee:c.callee_spelling,
        basis:'ast_call_with_generic_spelling_hint',resolution:'unresolved',...loc(n)});
    }
    if(ts.isPropertyDeclaration(n)||ts.isPropertySignature(n)||
      (ts.isVariableDeclaration(n)&&ts.isVariableDeclarationList(n.parent)&&ts.isVariableStatement(n.parent.parent)&&n.parent.parent.parent===sf))
      out.resources.push({kind:'declaration_candidate',name:n.name?.getText(sf),type:n.type?.getText(sf)||null,...loc(n)});
    ts.forEachChild(n,walk);
  }
  walk(sf);
  for(const d of sf.parseDiagnostics)out.diagnostics.push({kind:'syntax_error',code:d.code,
    line:sf.getLineAndCharacterOfPosition(d.start||0).line+1,message:ts.flattenDiagnosticMessageText(d.messageText,' ')});
  out.status=out.diagnostics.length?'syntax_errors':'parsed';return out;
}

function metadata(ts, root, name, source) {
  const parsed=ts.parseConfigFileTextToJson(name,source);
  if(parsed.error)return {path:name,status:'manifest_error',diagnostics:[{kind:'invalid_json',message:ts.flattenDiagnosticMessageText(parsed.error.messageText,' ')}]};
  const c=parsed.config;
  if(name.split('/').pop()==='package.json')return {path:name,status:'metadata_parsed',kind:'package',name:c.name,
    scripts:c.scripts||{},entries:{main:c.main,module:c.module,exports:c.exports,bin:c.bin},workspaces:c.workspaces||[],
    dependencies:Object.fromEntries(['dependencies','devDependencies','peerDependencies'].map(k=>[k,c[k]||{}]))};
  const internal=p=>{const rel=path.relative(root,path.resolve(p));return rel===''||(!rel.startsWith('..'+path.sep)&&rel!=='..'&&!path.isAbsolute(rel));};
  const host={useCaseSensitiveFileNames:true,
    readDirectory:(p,...args)=>internal(p)?ts.sys.readDirectory(p,...args).filter(internal):[],
    fileExists:p=>internal(p)&&ts.sys.fileExists(p),readFile:p=>internal(p)?ts.sys.readFile(p):undefined};
  const result=ts.parseJsonConfigFileContent(c,host,path.dirname(path.join(root,name)),undefined,path.join(root,name));
  return {path:name,status:result.errors.length?'metadata_with_diagnostics':'metadata_parsed',kind:'tsconfig',
    declared:{extends:c.extends,include:c.include,exclude:c.exclude,files:c.files,references:c.references,compilerOptions:c.compilerOptions||{}},
    matched_source_files:result.fileNames.map(p=>path.relative(root,p).split(path.sep).join('/')).sort(),
    diagnostics:result.errors.map(d=>({kind:'config_diagnostic',code:d.code,message:ts.flattenDiagnosticMessageText(d.messageText,' ').split(root).join('<source>')})),
    applied_to_syntax:false,external_packages_loaded:false};
}

module.exports={analyze,metadata};
if(require.main===module) {
  const [sourceRoot,tsModule]=process.argv.slice(2), root=path.resolve(sourceRoot), ts=require(path.resolve(tsModule));
  if(ts.version!=='5.9.3')throw new Error('Expected TypeScript 5.9.3');
  readline.createInterface({input:process.stdin,crlfDelay:Infinity}).on('line',line=>{
    try {const request=JSON.parse(line), file=path.resolve(root,request.path), rel=path.relative(root,file);
      if(rel.startsWith('..'+path.sep)||rel==='..'||path.isAbsolute(rel))throw new Error('Unsafe input');
      const body=fs.readFileSync(file,'utf8');
      const facts=request.task==='manifest'?metadata(ts,root,request.path,body):analyze(ts,request.path,body);
      process.stdout.write(JSON.stringify({ok:true,facts})+'\n');
    }catch(e){process.stdout.write(JSON.stringify({ok:false,error:String(e.message)})+'\n');}
  });
}
