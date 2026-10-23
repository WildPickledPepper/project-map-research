/* Source response dependencies, local construction and frontend state writes.
 * API roots are supplied by the preceding protocol graph. No application names
 * or fields are matching rules. Values are symbolic; product code is not run.
 */
const fs=require('node:fs'),path=require('node:path');
const {analyze}=require('./typescript_facts.cjs');

function extractData(ctx,apiSymbols,{maxSteps=20000,maxDepth=12}={}) {
  const {ts,checker,loc,id,callableOwner,qualified}=ctx,apis=new Set(apiSymbols);
  const src=n=>({...loc(n),expression:n.getText().slice(0,500)});
  const unknown=reason=>({tag:'unknown',reason}),literal=value=>({tag:'literal',value});
  const entries=new Map(),writes=[],reads=[],calls=[],diagnostics=[];let steps=0,currentEntry=null;
  const unwrap=n=>{while(n&&(ts.isAsExpression(n)||ts.isParenthesizedExpression(n)||ts.isNonNullExpression(n)||ts.isTypeAssertionExpression(n)))n=n.expression;return n;};
  function decl(n){let s=ts.isIdentifier(n)&&ts.isShorthandPropertyAssignment(n.parent)?checker.getShorthandAssignmentValueSymbol(n.parent):checker.getSymbolAtLocation(n);if(s?.flags&ts.SymbolFlags.Alias)s=checker.getAliasedSymbol(s);return s?.valueDeclaration||s?.declarations?.[0];}
  const inside=n=>n&&ctx.relativeFiles.includes(loc(n).path);
  function target(n){const d=checker.getResolvedSignature(n)?.declaration;return inside(d)&&ts.isFunctionLike(d)?d:null;}
  for(const call of ctx.calls){const t=target(call);if(t&&apis.has(id(t,'callable'))){const owner=callableOwner(call);if(owner?.body)entries.set(id(owner,'callable'),owner);}}
  function uniq(items){return [...new Map(items.map(v=>[JSON.stringify(v),v])).values()];}
  function dependencies(v,seen=new Set()) {
    if(!v||seen.has(v))return [];seen.add(v);
    if(v.tag==='promise')return [];
    if(v.tag==='response')return [{api:v.api,request_context:v.request_context,api_call:v.api_call,path:v.path,evidence:v.evidence,
      conditions:v.conditions||[],gaps:v.gaps||[],call_chain:v.call_chain||[]}];
    if(v.tag==='union')return uniq(v.values.flatMap(x=>dependencies(x,seen)));
    return uniq([...(v.dependencies||[]),...Object.values(v.props||{}).flatMap(x=>dependencies(x,seen))]);
  }
  function clone(v,memo=new Map()) {
    if(!v||typeof v!=='object'||v.tag==='function')return v;
    if(memo.has(v))return memo.get(v);const out={...v};memo.set(v,out);
    if(v.props)out.props=Object.fromEntries(Object.entries(v.props).map(([k,x])=>[k,clone(x,memo)]));
    if(v.values)out.values=v.values.map(x=>clone(x,memo));return out;
  }
  function merge(a,b){if(a===b)return a;return {tag:'union',values:[...(a?.tag==='union'?a.values:[a||unknown('missing_branch')]),...(b?.tag==='union'?b.values:[b||unknown('missing_branch')])]};}
  function note(n,kind,c,extra={}){diagnostics.push({kind,...src(n),entry:currentEntry,call_chain:c.chain,...extra});}
  function guarded(v,conditions){
    const out=clone(v),seen=new Set();
    function visit(x){if(!x||seen.has(x))return;seen.add(x);x.conditions=uniq([...(x.conditions||[]),...conditions]);
      if(x.dependencies)x.dependencies=x.dependencies.map(d=>({...d,conditions:uniq([...(d.conditions||[]),...conditions])}));
      for(const y of Object.values(x.props||{}))visit(y);for(const y of x.values||[])visit(y);}
    visit(out);return out;
  }
  function get(v,key,n,c) {
    if(v?.tag==='union')return v.values.map(x=>get(x,key,n,c)).reduce(merge);
    if(v?.props&&Object.hasOwn(v.props,key))return v.props[key];
    if(v?.tag==='response'){
      const out={...v,path:[...v.path,key],evidence:[...v.evidence,src(n)],call_chain:c.chain,props:{}};
      reads.push({id:id(n,'response_read'),entry:currentEntry,source_symbol:id(c.current,'callable'),
        response:dependencies(out)[0],conditions:uniq([...c.conditions,...(v.conditions||[])]),evidence:[src(n)],call_chain:c.chain});
      v.props[key]=out;return out;
    }
    if(v?.tag==='input'){const out={...v,path:[...v.path,key],props:{}};v.props[key]=out;return out;}
    if(v?.tag==='object')return key==='*'&&v.array?Object.values(v.props).reduce(merge,literal(undefined)):v.props['*']||literal(undefined);
    return unknown('property_source_unresolved');
  }
  function bind(name,value,c) {
    if(ts.isIdentifier(name)){c.env.set(name.parent,value);return;}
    if(ts.isObjectBindingPattern(name))for(const e of name.elements){const key=(e.propertyName||e.name).getText().replace(/^['"]|['"]$/g,'');bind(e.name,get(value,key,e,c),c);}
    if(ts.isArrayBindingPattern(name))name.elements.forEach((e,i)=>{if(ts.isBindingElement(e))bind(e.name,get(value,String(i),e,c),c);});
  }
  function fn(n,c){return {tag:'function',node:n,env:c.env,receiver:c.receiver};}
  function symbol(n,c) {
    const d=decl(n);if(c.env.has(d))return c.env.get(d);
    if(!d)return unknown('symbol_unresolved');
    if(ts.isFunctionLike(d))return fn(d,c);
    if(ts.isVariableDeclaration(d)&&d.initializer){if(c.resolving.has(d))return unknown('initializer_cycle');c.resolving.add(d);const v=ev(d.initializer,c);c.resolving.delete(d);c.env.set(d,v);return v;}
    return unknown('external_or_runtime_value');
  }
  function assign(left,value,c,at,operation='=') {
    left=unwrap(left);
    if(ts.isIdentifier(left)){c.env.set(decl(left),value);return;}
    if(!ts.isPropertyAccessExpression(left)&&!ts.isElementAccessExpression(left))return;
    const receiver=ev(left.expression,c),key=ts.isPropertyAccessExpression(left)?literal(left.name.text):ev(left.argumentExpression,c);
    const prop=key.tag==='literal'?String(key.value):'*';
    function put(r){
      if(r.tag==='union'){r.values.forEach(put);return;}
      if(r.tag==='input')writes.push({id:id(at,'state_write'),entry:currentEntry,source_symbol:id(c.current,'callable'),
        target:{root:r.root,path:[...r.path,prop]},operation,value_dependencies:dependencies(value),
        continuation_apis:[...c.awaited],conditions:uniq([...c.conditions,...(r.conditions||[])]),evidence:[src(at)],call_chain:c.chain});
      if(r.props){r.props[prop]=value;
        if(prop==='*')r.dependencies=uniq([...(r.dependencies||[]),...dependencies(key)]);
      } else note(at,'assignment_receiver_unresolved',c);
    }
    put(receiver);
  }
  function invoke(callable,args,c,at) {
    if(callable?.tag!=='function'||!callable.node.body)return unknown('callee_body_unresolved');
    const n=callable.node;if(c.depth>=maxDepth){note(at||n,'call_depth_limit',c);return unknown('call_depth_limit');}
    const isAsync=n.modifiers?.some(m=>m.kind===ts.SyntaxKind.AsyncKeyword);
    const sub={...c,env:new Map(callable.env),awaited:isAsync?new Set(c.awaited):c.awaited,receiver:callable.receiver||c.receiver,depth:c.depth+1,current:n,
      chain:at?[...c.chain,{call_site:id(at,'call_site'),target:id(n,'callable'),evidence:[src(at),src(n)]}]:c.chain};
    n.parameters.forEach((p,i)=>bind(p.name,args[i]??(p.initializer?ev(p.initializer,sub):literal(undefined)),sub));
    const value=ts.isBlock(n.body)?block(n.body.statements,sub)||literal(undefined):ev(n.body,sub);
    return isAsync?{tag:'promise',value,awaited:[...sub.awaited]}:value;
  }
  function block(statements,c) {
    const returned=[];
    for(const s of statements){
      if(++steps>maxSteps){note(s,'step_limit',c);return unknown('step_limit');}
      if(ts.isVariableStatement(s)){for(const d of s.declarationList.declarations)bind(d.name,d.initializer?ev(d.initializer,c):literal(undefined),c);}
      else if(ts.isExpressionStatement(s))ev(s.expression,c);
      else if(ts.isReturnStatement(s)){returned.push(s.expression?ev(s.expression,c):literal(undefined));break;}
      else if(ts.isThrowStatement(s)){note(s,'throw_path',c);returned.push({tag:'throw'});break;}
      else if(ts.isBlock(s)){const r=block(s.statements,c);if(r){returned.push(r);break;}}
      else if(ts.isIfStatement(s)){
        const condition=ev(s.expression,c),run=(branch,cc)=>branch?block(ts.isBlock(branch)?branch.statements:[branch],cc):null;
        if(condition.tag==='literal'){const r=run(condition.value?s.thenStatement:s.elseStatement,c);if(r){returned.push(r);break;}}
        else {
          const branches=[s.thenStatement,s.elseStatement].map((branch,i)=>{const memo=new Map(),cc={...c,env:new Map([...c.env].map(([k,v])=>[k,clone(v,memo)])),receiver:clone(c.receiver,memo),awaited:new Set(c.awaited),
            conditions:[...c.conditions,{...src(s.expression),when:i===0}]};return {ctx:cc,result:run(branch,cc)};});
          returned.push(...branches.filter(b=>b.result).map(b=>guarded(b.result,b.ctx.conditions)));
          const live=branches.filter(b=>!b.result);if(!live.length)break;
          if(live.length===1){c.env=live[0].ctx.env;c.receiver=live[0].ctx.receiver;c.conditions=live[0].ctx.conditions;c.awaited=live[0].ctx.awaited;}
          else {for(const k of new Set([...live[0].ctx.env.keys(),...live[1].ctx.env.keys()]))c.env.set(k,merge(guarded(live[0].ctx.env.get(k),live[0].ctx.conditions),guarded(live[1].ctx.env.get(k),live[1].ctx.conditions)));c.awaited=new Set([...live[0].ctx.awaited,...live[1].ctx.awaited]);}
        }
      } else if(ts.isForOfStatement(s)) {
        const collection=ev(s.expression,c),sub={...c,env:new Map(c.env),conditions:[...c.conditions,{...src(s.expression),kind:'range_iteration',cardinality:'runtime_unknown'}]};
        const declarations=ts.isVariableDeclarationList(s.initializer)?s.initializer.declarations:[];
        if(collection.tag==='object'&&collection.array&&Object.keys(collection.props).length===0)continue;
        if(declarations[0])bind(declarations[0].name,guarded(get(collection,'*',s.expression,c),sub.conditions),sub);
        block(ts.isBlock(s.statement)?s.statement.statements:[s.statement],sub);
        for(const [key,value] of sub.env)if(c.env.has(key)&&c.env.get(key)!==value)c.env.set(key,merge(c.env.get(key),guarded(value,sub.conditions)));
      } else if(ts.isTryStatement(s)) {
        note(s,'exception_paths_not_expanded',c);const r=block(s.tryBlock.statements,{...c,conditions:[...c.conditions,{...src(s),kind:'try_completes_without_exception'}]});
        if(s.finallyBlock)block(s.finallyBlock.statements,c);if(r){returned.push(r);break;}
      } else if(ts.isForStatement(s)||ts.isWhileStatement(s)||ts.isSwitchStatement(s))note(s,'control_flow_not_expanded',c);
    }
    return returned.length?returned.reduce(merge):null;
  }
  function ev(raw,c) {
    const n=unwrap(raw);if(!n)return literal(undefined);if(++steps>maxSteps)return unknown('step_limit');
    if(ts.isStringLiteralLike(n))return literal(n.text);if(ts.isNumericLiteral(n))return literal(Number(n.text));
    if(n.kind===ts.SyntaxKind.TrueKeyword||n.kind===ts.SyntaxKind.FalseKeyword)return literal(n.kind===ts.SyntaxKind.TrueKeyword);
    if(n.kind===ts.SyntaxKind.NullKeyword)return literal(null);
    if(n.kind===ts.SyntaxKind.ThisKeyword)return c.receiver||unknown('this_unresolved');
    if(ts.isIdentifier(n))return n.text==='undefined'?literal(undefined):symbol(n,c);
    if(ts.isArrowFunction(n)||ts.isFunctionExpression(n))return fn(n,c);
    if(ts.isAwaitExpression(n)){
      function fulfilled(value){
        if(value.tag==='promise'){for(const uid of value.awaited||[])c.awaited.add(uid);return fulfilled(value.value);}
        if(value.tag==='union')return value.values.map(fulfilled).reduce(merge);
        for(const d of dependencies(value))c.awaited.add(d.request_context);return value;
      }
      return fulfilled(ev(n.expression,c));
    }
    if(ts.isObjectLiteralExpression(n)){
      const value={tag:'object',props:{},dependencies:[]};
      for(const p of n.properties){if(ts.isSpreadAssignment(p)){const v=ev(p.expression,c);Object.assign(value.props,v.props||{});value.dependencies.push(...dependencies(v));continue;}
        const key=p.name?.getText().replace(/^['"]|['"]$/g,'');if(ts.isPropertyAssignment(p))value.props[key]=ev(p.initializer,c);else if(ts.isShorthandPropertyAssignment(p))value.props[key]=symbol(p.name,c);}
      return value;
    }
    if(ts.isArrayLiteralExpression(n))return {tag:'object',array:true,props:Object.fromEntries(n.elements.map((v,i)=>[String(i),ev(v,c)])),dependencies:[]};
    if(ts.isPropertyAccessExpression(n)||ts.isElementAccessExpression(n)){
      const key=ts.isPropertyAccessExpression(n)?literal(n.name.text):ev(n.argumentExpression,c);return get(ev(n.expression,c),key.tag==='literal'?String(key.value):'*',n,c);
    }
    if(ts.isPrefixUnaryExpression(n)){
      const value=ev(n.operand,c);if(n.operator===ts.SyntaxKind.ExclamationToken&&value.tag==='literal')return literal(!value.value);
      return {tag:'computed',dependencies:dependencies(value)};
    }
    if(ts.isBinaryExpression(n)){
      const op=n.operatorToken.kind;if(op===ts.SyntaxKind.EqualsToken){const value=ev(n.right,c);assign(n.left,value,c,n);return value;}
      if(op>=ts.SyntaxKind.FirstCompoundAssignment&&op<=ts.SyntaxKind.LastCompoundAssignment){const value={tag:'computed',dependencies:uniq([...dependencies(ev(n.left,c)),...dependencies(ev(n.right,c))])};assign(n.left,value,c,n,n.operatorToken.getText());return value;}
      const a=ev(n.left,c);
      if(op===ts.SyntaxKind.QuestionQuestionToken){if(a.tag==='literal')return a.value==null?ev(n.right,c):a;return merge(a,ev(n.right,{...c,conditions:[...c.conditions,{...src(n.left),kind:'nullish'}]}));}
      if(op===ts.SyntaxKind.AmpersandAmpersandToken&&a.tag==='literal'&&!a.value)return a;
      if(op===ts.SyntaxKind.BarBarToken&&a.tag==='literal'&&a.value)return a;
      const shortCircuit=op===ts.SyntaxKind.AmpersandAmpersandToken||op===ts.SyntaxKind.BarBarToken;
      const b=ev(n.right,shortCircuit&&a.tag!=='literal'?{...c,conditions:[...c.conditions,{...src(n.left),when:op===ts.SyntaxKind.AmpersandAmpersandToken}]}:c);
      if(shortCircuit)return a.tag==='literal'?b:merge(a,b);
      if(a.tag==='literal'&&b.tag==='literal'){
        if(op===ts.SyntaxKind.EqualsEqualsEqualsToken)return literal(a.value===b.value);
        if(op===ts.SyntaxKind.ExclamationEqualsEqualsToken)return literal(a.value!==b.value);
      }
      return {tag:'computed',dependencies:uniq([...dependencies(a),...dependencies(b)])};
    }
    if(ts.isConditionalExpression(n)){const v=ev(n.condition,c);if(v.tag==='literal')return ev(v.value?n.whenTrue:n.whenFalse,c);
      const branches=[n.whenTrue,n.whenFalse].map((b,i)=>{const conditions=[...c.conditions,{...src(n.condition),when:i===0}];return guarded(ev(b,{...c,conditions}),conditions);});return branches.reduce(merge);}
    if(ts.isCallExpression(n)) {
      const callee=target(n),args=n.arguments.map(a=>ev(a,c)),callId=id(n,'call_site');
      if(callee&&apis.has(id(callee,'callable'))){
        const request_context=[currentEntry,...c.chain.map(s=>s.call_site),callId].join('/');
        const record={api:id(callee,'callable'),api_call:callId,request_context,entry:currentEntry,evidence:[src(n)]};calls.push(record);
        return {tag:'promise',value:{tag:'response',...record,path:[],props:{},conditions:c.conditions}};
      }
      if(ts.isPropertyAccessExpression(n.expression)) {
        const receiver=ev(n.expression.expression,c),name=n.expression.name.text;
        if(receiver.tag==='object'&&receiver.array&&name==='push'){
          receiver.props['*']=receiver.props['*']?merge(receiver.props['*'],args[0]):args[0];return literal(undefined);
        }
        if(callee?.body)return invoke({...fn(callee,c),receiver},args,c,n);
      }
      const callable=ev(n.expression,c);
      if(callable.tag==='function'&&callable.node.body)return invoke(callable,args,c,n);
      if(callee?.body)return invoke(fn(callee,c),args,c,n);
      // A passed closure has a conditional execution edge, not an assumed library
      // implementation. Known local callees are interpreted before this fallback.
      for(const arg of args)if(arg.tag==='function')invoke(arg,[],{...c,conditions:[...c.conditions,{kind:'external_callee_invokes_callback',...src(n)}]},n);
      if(args.some(a=>dependencies(a).length)){
        note(n,'unresolved_call_with_response_argument',c,{argument_dependencies:args.map(a=>dependencies(a))});
        const seen=new Set();function taint(v){if(!v||seen.has(v))return;seen.add(v);
          const gap={kind:'possible_mutation_by_unresolved_call',...src(n)};
          if(v.tag==='response')v.gaps=uniq([...(v.gaps||[]),gap]);
          if(v.dependencies)v.dependencies=v.dependencies.map(d=>({...d,gaps:uniq([...(d.gaps||[]),gap])}));
          for(const x of Object.values(v.props||{}))taint(x);for(const x of v.values||[])taint(x);}
        args.forEach(taint);
      }
      return unknown('external_or_unresolved_call');
    }
    if(ts.isNewExpression(n))return {tag:'object',root:id(n,'allocation'),props:{},dependencies:[]};
    return unknown('expression_not_modeled:'+ts.SyntaxKind[n.kind]);
  }
  const analyzed=[];
  for(const [uid,entry] of entries){
    currentEntry=uid;steps=0;const c={env:new Map(),receiver:null,resolving:new Set(),current:entry,conditions:[],awaited:new Set(),chain:[],depth:0};
    entry.parameters.forEach(p=>bind(p.name,{tag:'input',root:id(p,'input_binding'),path:[],props:{}},c));
    if(ts.isBlock(entry.body))block(entry.body.statements,c);else ev(entry.body,c);
    analyzed.push({source_symbol:uid,name:qualified(entry),...loc(entry),steps,truncated:steps>maxSteps});
  }
  return {version:'0.1.0',api_symbols:[...apis],entries:analyzed,api_calls:uniq(calls),field_reads:uniq(reads),
    state_writes:uniq(writes.filter(w=>w.value_dependencies.length||w.continuation_apis.length)),diagnostics:uniq(diagnostics),
    limits:['API_fulfillment_is_an_input_boundary_pending_transport_join','source_dependencies_not_executed_values',
      'range_iterations_symbolic','external_callbacks_require_callee_invocation','unresolved_call_results_keep_unknown',
      'exceptions_and_some_control_flow_not_expanded','state_roots_are_entry_parameters',
      'conditional_alias_and_callback_effects_are_candidates','branch_caller_alias_effects_not_composed',
      'opaque_mutations_keep_candidate_with_gap'],budgets:{max_steps:maxSteps,max_depth:maxDepth}};
}

function analyzeData(ts,root,files,apis,options){return analyze(ts,root,files,{pathsFromConfigs:true,outputKey:'data_flow',run:ctx=>extractData(ctx,apis,options)});}
module.exports={analyzeData,extractData};
if(require.main===module){const [root,manifest,base,tsModule,output]=process.argv.slice(2),ts=require(path.resolve(tsModule));
  if(ts.version!=='5.9.3')throw new Error('Expected TypeScript 5.9.3');if(fs.existsSync(output))throw new Error('Use a new output file');
  const g=JSON.parse(fs.readFileSync(base,'utf8')),matched=new Set(g.protocol.results.filter(r=>r.matches?.length).map(r=>r.message));
  const apis=[...new Set(g.edges.filter(e=>e.kind==='EMITS_MESSAGE'&&matched.has(e.target)).map(e=>e.source))];
  const result=analyzeData(ts,root,JSON.parse(fs.readFileSync(manifest,'utf8')).files.map(f=>f.path),apis);
  fs.writeFileSync(output,JSON.stringify(result,null,2)+'\n');process.stdout.write(JSON.stringify({entries:result.data_flow.entries.length,reads:result.data_flow.field_reads.length,writes:result.data_flow.state_writes.length})+'\n');
}
