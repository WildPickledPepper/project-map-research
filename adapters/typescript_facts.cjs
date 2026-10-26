/* Compiler-backed TS declarations/calls plus explicit conditional global bindings. */
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {sourceFile,language}=require('./ecmascript_sources.cjs');

function analyzeUnit(ts, root, relativeFiles, extension=null, roots=relativeFiles) {
  root = path.resolve(root);
  const allowed = new Set(relativeFiles.map(p => path.resolve(root,p)));
  const options = {target:ts.ScriptTarget.ES2020, module:ts.ModuleKind.ESNext,
    moduleResolution:ts.ModuleResolutionKind.Bundler, jsx:ts.JsxEmit.React,
    strict:true, skipLibCheck:true, noEmit:true, allowJs:true, checkJs:false, experimentalDecorators:true};
  const host = ts.createCompilerHost(options);
  const originalRead = host.readFile.bind(host), originalExists = host.fileExists.bind(host);
  const libRoot=path.resolve(path.dirname(ts.getDefaultLibFilePath(options)));
  const internal = p => path.resolve(p).startsWith(root+path.sep);
  const permitted=p=>allowed.has(path.resolve(p)) || (path.dirname(path.resolve(p))===libRoot && /^lib[.].*[.]d[.]ts$|^lib[.]d[.]ts$/.test(path.basename(p)));
  host.fileExists = p => permitted(p) && originalExists(p);
  host.readFile = p => permitted(p) ? originalRead(p)?.replaceAll('\r\n','\n') : undefined;
  const packages = [];
  for (const p of relativeFiles.filter(p => p.endsWith('package.json'))) {
    const data = JSON.parse(fs.readFileSync(path.join(root,p),'utf8'));
    if (data.name) packages.push({dir:path.dirname(path.join(root,p)),data});
  }
  const moduleMisses = [];
  const pathConfigs=[];
  if(extension?.pathsFromConfigs)for(const p of relativeFiles.filter(p=>p.endsWith('/tsconfig.json')||p==='tsconfig.json')) {
    const parsed=ts.parseConfigFileTextToJson(p,fs.readFileSync(path.join(root,p),'utf8'));
    if(!parsed.error && parsed.config?.compilerOptions?.paths)
      pathConfigs.push({path:p,dir:path.resolve(root,path.dirname(p)),paths:parsed.config.compilerOptions.paths});
  }
  const modules=require('./ecmascript_modules.cjs').install(ts,host,{allowed,packages,options,pathConfigs,
    relative:p=>internal(p)?path.relative(root,p).replaceAll('\\','/'):'<outside-input>',diagnostics:moduleMisses});
  const program = ts.createProgram(roots.map(p=>path.resolve(root,p)).filter(sourceFile),options,host);
  const checker = program.getTypeChecker();
  const nodes = new Map(), edges = [], diagnostics = [], sourceHashes=new Map(), scopeCache=new Map();
  const owned=new Set(roots.map(p=>path.resolve(root,p)));
  const sfList = program.getSourceFiles().filter(f => owned.has(path.resolve(f.fileName)) && sourceFile(f.fileName));
  function rel(p) { return internal(p)?path.relative(root,p).replaceAll('\\','/'):'<typescript-lib>/'+path.basename(p); }
  function loc(n) { const sf=n.getSourceFile(), pos=sf.getLineAndCharacterOfPosition(n.getStart(sf));
    return {path:rel(sf.fileName),line:pos.line+1,column:pos.character+1}; }
  function id(n,kind) { const l=loc(n);return (language(l.path)==='javascript'?'js:':'ts:')+crypto.createHash('sha256').update(`${l.path}:${kind}:${n.getStart()}:${n.end}`).digest('hex').slice(0,24); }
  function shortName(n) {
    if(ts.isSourceFile(n))return rel(n.fileName);
    if(n.name) return n.name.getText();
    if(n.parent&&(ts.isVariableDeclaration(n.parent) || ts.isPropertyAssignment(n.parent))) return n.parent.name.getText();
    const l=loc(n); return `<lambda@${l.line}:${l.column}>`;
  }
  function qualified(n) {
    const parts=[shortName(n)];
    for(let p=n.parent;p;p=p.parent) if(ts.isClassDeclaration(p)||ts.isInterfaceDeclaration(p)||ts.isFunctionLike(p)||
      ts.isModuleDeclaration(p)||ts.isEnumDeclaration(p)||ts.isTypeAliasDeclaration(p)) parts.unshift(shortName(p));
    return parts.join('.');
  }
  function node(n,kind) {
    const uid=id(n,kind);
    if(!nodes.has(uid)) nodes.set(uid,{id:uid,kind,...loc(n),name:qualified(n),language:language(n.getSourceFile().fileName),
      evidence_kind:'typescript_compiler_ast',compiler_version:ts.version,
      source_sha256:(()=>{const sf=n.getSourceFile();if(!sourceHashes.has(sf.fileName))
        sourceHashes.set(sf.fileName,crypto.createHash('sha256').update(sf.text.replaceAll('\r\n','\n')).digest('hex'));
        return sourceHashes.get(sf.fileName);})(),
      ...(kind==='callable'?{parameters:n.parameters?.map(p=>p.getText())||[],
        type_parameters:n.typeParameters?.map(p=>p.getText())||[],definition:!!n.body}:{} )});
    return uid;
  }
  function edge(source,target,kind,evidence,status='static',extra={}) {
    edges.push({source,target,kind,status,evidence, ...extra});
  }
  function callableOwner(n) { for(let p=n.parent;p;p=p.parent)if(ts.isFunctionLike(p))return p;return null; }
  function walk(n,fn) { fn(n); ts.forEachChild(n,c=>walk(c,fn)); }
  function codeModule(sf){const uid=node(sf,'code_module');Object.assign(nodes.get(uid),{name:rel(sf.fileName)});return uid;}
  function moduleReference(n,literal,syntax){
    const sf=n.getSourceFile(),uid=node(n,'module_reference'),name=literal&&ts.isStringLiteralLike(literal)?literal.text:null;
    const mode=syntax==='require'?ts.ModuleKind.CommonJS:literal?modules.modeFor(literal,sf):ts.ModuleKind.ESNext;
    const elements=n.importClause?.namedBindings?.elements??n.exportClause?.elements;
    const onlyTypes=!!(n.importClause?.isTypeOnly||n.isTypeOnly||(!n.importClause?.name&&elements?.length&&elements.every(e=>e.isTypeOnly)));
    const record=nodes.get(uid);Object.assign(record,{name:name??n.getText(),module_specifier:name,syntax,
      resolution_mode:mode===ts.ModuleKind.CommonJS?'require':'import',resolution:'unresolved',
      type_only:onlyTypes,bindings:n.importClause?.getText()??n.exportClause?.getText()??null});
    edge(codeModule(sf),uid,'CONTAINS_IMPORT',[loc(n)],'source_relation');
    if(syntax==='require'){
      const symbol=checker.getSymbolAtLocation(n.expression);
      if(symbol?.declarations?.some(d=>allowed.has(path.resolve(d.getSourceFile().fileName)))){record.reason='shadowed_require';return;}
    }
    if(name===null){record.reason='module_name_not_static_string';return;}
    const resolved=modules.resolve(name,sf.fileName,mode),target=resolved&&program.getSourceFile(resolved.resolvedFileName);
    if(!target){record.reason=resolved?'resolved_module_not_in_program':'module_target_outside_input_or_ambiguous';return;}
    record.resolution='static_source_module';
    edge(uid,codeModule(target),'IMPORTS_MODULE',[loc(n),loc(target)],'source_relation',
      {basis:'typescript_module_resolution',resolution_mode:record.resolution_mode,type_only:record.type_only,runtime_execution:'not_observed'});
  }
  const calls=[], assignments=[], semanticErrors=new Map();
  for(const sf of sfList) {
    const errors=[];semanticErrors.set(sf.fileName,errors);
    for(const d of program.getSemanticDiagnostics(sf)) {
      errors.push({start:d.start||0,end:(d.start||0)+(d.length||1)});
      diagnostics.push({path:rel(sf.fileName),kind:'typescript_semantic',code:d.code,
        line:sf.getLineAndCharacterOfPosition(d.start||0).line+1,
        message:ts.flattenDiagnosticMessageText(d.messageText,' ').replaceAll(root,'<source>')});
    }
  }
  for(const sf of sfList){codeModule(sf);
    for(const [syntax,references] of [['types',sf.typeReferenceDirectives],['path',sf.referencedFiles],['lib',sf.libReferenceDirectives]])
      for(const reference of references){
        const pos=sf.getLineAndCharacterOfPosition(reference.pos),uid=`ts:directive:${rel(sf.fileName)}:${syntax}:${reference.pos}:${reference.end}`;
        const location={path:rel(sf.fileName),line:pos.line+1,column:pos.character+1};
        nodes.set(uid,{id:uid,kind:'module_reference',...location,name:reference.fileName,module_specifier:reference.fileName,
          syntax:'triple_slash_'+syntax,language:language(sf.fileName),evidence_kind:'typescript_compiler_reference_directive',
          compiler_version:ts.version,type_only:true,resolution:'recorded_not_loaded',runtime_execution:'not_applicable'});
        edge(codeModule(sf),uid,'CONTAINS_IMPORT',[location],'source_relation');
      }
    walk(sf,n=>{
    if((ts.isImportDeclaration(n)||ts.isExportDeclaration(n))&&n.moduleSpecifier)moduleReference(n,n.moduleSpecifier,ts.isImportDeclaration(n)?'import':'reexport');
    if(ts.isImportEqualsDeclaration(n)&&ts.isExternalModuleReference(n.moduleReference))moduleReference(n,n.moduleReference.expression,'import_equals');
    if(ts.isCallExpression(n)&&ts.isIdentifier(n.expression)&&n.expression.text==='require')moduleReference(n,n.arguments[0],'require');
    if(ts.isCallExpression(n)&&n.expression.kind===ts.SyntaxKind.ImportKeyword)moduleReference(n,n.arguments[0],'dynamic_import');
    if(ts.isFunctionLike(n) && n.parameters)node(n,'callable');
    if(ts.isClassDeclaration(n)||ts.isInterfaceDeclaration(n)||ts.isTypeAliasDeclaration(n)||
      ts.isEnumDeclaration(n)||ts.isModuleDeclaration(n)){
      const uid=node(n,'type');Object.assign(nodes.get(uid),{declaration_kind:ts.SyntaxKind[n.kind]});
      edge(codeModule(sf),uid,'CONTAINS_DECLARATION',[loc(n)],'source_relation');
    }
    if(ts.isVariableDeclaration(n)||ts.isPropertyDeclaration(n)||ts.isPropertySignature(n)||
      ts.isEnumMember(n)||ts.isParameter(n)||ts.isBindingElement(n)){
      const uid=node(n,ts.isParameter(n)?'parameter':'value');
      Object.assign(nodes.get(uid),{declaration_kind:ts.SyntaxKind[n.kind],declared_type:n.type?.getText()||null,
        ...(ts.isEnumMember(n)?{constant_value:checker.getConstantValue(n)??null}:{})});
      const owner=callableOwner(n);
      edge(owner?node(owner,'callable'):codeModule(sf),uid,'CONTAINS_DECLARATION',[loc(n)],'source_relation');
      if(ts.isEnumMember(n))edge(node(n.parent,'type'),uid,'DECLARES_MEMBER',[loc(n)],'source_relation');
    }
    if(ts.isCallExpression(n)||ts.isNewExpression(n))calls.push(n);
    if(ts.isBinaryExpression(n)&&n.operatorToken.kind===ts.SyntaxKind.EqualsToken &&
      (ts.isPropertyAccessExpression(n.left)||ts.isElementAccessExpression(n.left)))assignments.push(n);
  });}
  const unionTargets=new WeakMap();
  function alternatives(call){
    if(unionTargets.has(call))return unionTargets.get(call);
    const type=checker.getTypeAtLocation(call.expression),out=new Set();
    if(type.isUnion?.())for(const member of type.types)
      for(const sig of checker.getSignaturesOfType(member,ts.isNewExpression(call)?ts.SignatureKind.Construct:ts.SignatureKind.Call)){
        const d=sig.declaration;if(d&&allowed.has(path.resolve(d.getSourceFile().fileName))&&ts.isFunctionLike(d))out.add(d);
      }
    const result=[...out];unionTargets.set(call,result);return result;
  }
  function targetOf(call) {
    if(alternatives(call).length>1)return null;
    const sig=checker.getResolvedSignature(call), d=sig?.declaration;
    return d && allowed.has(path.resolve(d.getSourceFile().fileName)) && ts.isFunctionLike(d) ? d : null;
  }
  function appScope(n) {
    const file=path.resolve(n.getSourceFile().fileName);
    if(!scopeCache.has(file))scopeCache.set(file,packages.filter(p=>file.startsWith(p.dir+path.sep)).sort((a,b)=>b.dir.length-a.dir.length)[0]?.data.name || '<analysis-root>');
    return scopeCache.get(file);
  }
  function propertyKey(expr) {
    const base=expr.expression;
    if(!base||!ts.isIdentifier(base))return null;
    const prop=ts.isPropertyAccessExpression(expr)?expr.name.text:
      ts.isElementAccessExpression(expr)&&ts.isStringLiteral(expr.argumentExpression)?expr.argumentExpression.text:null;
    if(prop===null)return null;
    const symbol=checker.getSymbolAtLocation(base), decl=symbol?.valueDeclaration || symbol?.declarations?.[0];
    if(!decl)return null;
    return `${appScope(expr)}:${id(decl,'object')}:${prop}`;
  }
  const writes=new Map();
  for(const a of assignments) {
    const key=propertyKey(a.left);if(!key)continue;
    const uid=node(a,'binding');
    Object.assign(nodes.get(uid),{name:a.left.getText(),right:a.right.getText(),scope:appScope(a),
      condition:'binding_is_active_at_call_in_same_runtime_scope'});
    const returned=[];
    if(ts.isArrowFunction(a.right)||ts.isFunctionExpression(a.right))returned.push(a.right);
    else if(ts.isCallExpression(a.right)) {
      const factory=targetOf(a.right);
      if(factory) {
        edge(uid,node(factory,'callable'),'BINDS_RESULT_OF',[loc(a),loc(factory)],'conditional');
        function scan(n) {
          if(n!==factory.body && ts.isFunctionLike(n))return;
          if(ts.isReturnStatement(n)&&n.expression&&(ts.isArrowFunction(n.expression)||ts.isFunctionExpression(n.expression)))returned.push(n.expression);
          ts.forEachChild(n,scan);
        }
        if(factory.body)scan(factory.body);
      }
    }
    for(const target of returned)edge(uid,node(target,'callable'),'BINDS_CALLABLE',[loc(a),loc(target)],'conditional',
      {condition:'assignment_executed_and_factory_returns_this_callable'});
    writes.set(key,[...(writes.get(key)||[]),{uid,returned,loc:loc(a)}]);
  }
  for(const call of calls) {
    const uid=node(call,'call_site'), owner=callableOwner(call);
    const hasError=(semanticErrors.get(call.getSourceFile().fileName)||[]).some(e=>e.start<call.end && e.end>call.getStart());
    const target=hasError?null:targetOf(call),possible=hasError?[]:alternatives(call);
    Object.assign(nodes.get(uid),{name:call.expression.getText(),arguments:call.arguments?.map(a=>a.getText())||[],resolution:'unresolved'});
    if(owner)edge(node(owner,'callable'),uid,'OBSERVES_CALL',[loc(call)]);
    for(const [index,arg] of (call.arguments||[]).entries()) {
      if(ts.isArrowFunction(arg)||ts.isFunctionExpression(arg))
        edge(uid,node(arg,'callable'),'PASSES_CALLBACK',[loc(call),loc(arg)],'source_relation',
          {argument_index:index,basis:'direct_function_literal_argument',execution:'depends_on_callee_invocation'});
    }
    const property=ts.isPropertyAccessExpression(call.expression)||ts.isElementAccessExpression(call.expression)?propertyKey(call.expression):null;
    const bindings=property && writes.get(property);
    if(bindings?.length && !hasError) {
      nodes.get(uid).resolution=bindings.length>1?'ambiguous_binding':'conditional_binding';
      for(const b of bindings) {
        edge(uid,b.uid,'USES_BINDING',[loc(call),b.loc],'conditional',
          {condition:'binding_is_active_at_call_in_same_runtime_scope',scope:appScope(call)});
        for(const returned of b.returned)edge(uid,node(returned,'callable'),'BOUND_CALL_CANDIDATE',[loc(call),b.loc,loc(returned)],'candidate');
      }
    } else if(possible.length>1){
      nodes.get(uid).resolution='ambiguous_callable_type';nodes.get(uid).reason='callable_union_requires_target_selection';
      for(const candidate of possible)edge(uid,node(candidate,'callable'),'STATIC_CALL_CANDIDATE',[loc(call),loc(candidate)],'candidate',
        {basis:'typescript_callable_union_members',runtime_dispatch:'not_observed'});
    } else if(target) {
      const kind=ts.isMethodSignature(target)||!target.body?'STATIC_DECLARATION_TARGET':'STATIC_CALL_TARGET';
      edge(uid,node(target,'callable'),kind,[loc(call),loc(target)],'static',
        {basis:'typescript_getResolvedSignature',runtime_dispatch:'not_observed'});
      nodes.get(uid).resolution='static_declaration';
    } else nodes.get(uid).reason=hasError?'compiler_diagnostic_at_call':'no_input_callable_or_runtime_binding';
  }
  for(const sf of sfList) {
    for(const d of program.getSyntacticDiagnostics(sf))diagnostics.push({path:rel(sf.fileName),kind:'typescript_syntax',code:d.code,
      line:sf.getLineAndCharacterOfPosition(d.start||0).line+1,message:ts.flattenDiagnosticMessageText(d.messageText,' ')});
  }
  diagnostics.push(...moduleMisses);
  const result={schema_version:1,extractor:'typescript_facts',version:'0.1.0',compiler_version:ts.version,
    compiler_options:options,compiler_options_origin:'fixed_analysis_preset_not_product_tsconfig',
    coverage:sfList.map(f=>({path:rel(f.fileName),status:'parsed'})),nodes:[...nodes.values()],edges,diagnostics,
    limits:['input_closed_no_external_package_types','static_declaration_not_runtime_dispatch',
      'global_binding_edges_require_recorded_execution_condition','factory_returns_limited_to_direct_function_literals',
      'javascript_checked_by_compiler_inference_with_checkJs_false','module_edges_are_source_dependencies_not_observed_execution']};
  if(extension) {
    result.path_configs=pathConfigs.map(c=>({path:c.path,paths:c.paths}));
    result[extension.outputKey||'protocol']=extension.run({ts,program,checker,root,relativeFiles,sfList,
      dependencyFiles:program.getSourceFiles().filter(f=>allowed.has(path.resolve(f.fileName))),
      loc,id,qualified,walk,calls,assignments,callableOwner,appScope,targetOf,facts:result});
  }
  return result;
}

function analyze(ts,root,relativeFiles,extension=null){
  const {partition,merge}=require('./typescript_analysis_units.cjs'),units=partition(relativeFiles);
  if(!units.length)return analyzeUnit(ts,root,relativeFiles,extension);
  return merge(units.map(unit=>analyzeUnit(ts,root,relativeFiles,extension,unit.root_files)),units,
    extension?(extension.outputKey||'protocol'):null);
}
module.exports={analyze};
if(require.main===module) {
  const [root,manifest,tsModule,output]=process.argv.slice(2);
  const ts=require(path.resolve(tsModule)), data=JSON.parse(fs.readFileSync(manifest,'utf8'));
  if(ts.version!=='5.9.3')throw new Error('Expected TypeScript 5.9.3');
  if(fs.existsSync(output))throw new Error('Use a new output file');
  const result=analyze(ts,root,data.files.map(f=>f.path));
  fs.writeFileSync(output,JSON.stringify(result,null,2)+'\n');
  process.stdout.write(JSON.stringify({nodes:result.nodes.length,edges:result.edges.length,diagnostics:result.diagnostics.length})+'\n');
}
