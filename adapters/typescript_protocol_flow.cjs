/* Bounded symbolic source analysis; never executes product JavaScript.
 * Names of project functions, variables, classes and message fields are inputs.
 * Only standard platform APIs (Promise/Map/JSON/Object/DOM/WebSocket) are modeled.
 */
const fs=require('node:fs'),path=require('node:path');
const {analyze}=require('./typescript_facts.cjs');

function extract(ctx) {
  const {ts,checker,loc,id,walk,callableOwner,facts,sfList}=ctx;
  const sourceFiles=new Set(ctx.relativeFiles);
  const bindingsByCall=new Map();for(const edge of facts.edges)if(edge.kind==='USES_BINDING'){
    if(!bindingsByCall.has(edge.source))bindingsByCall.set(edge.source,[]);bindingsByCall.get(edge.source).push(edge);
  }
  const lit=value=>({tag:'literal',value}),unk=reason=>({tag:'unknown',reason}),obj=(props={})=>({tag:'object',props});
  const fn=(node,env,receiver=null)=>({tag:'function',node,env:new Map(env),receiver});
  const diagnostics=[],consumers=[],ast=new Map();let active=null,steps=0;
  const src=n=>({...loc(n),expression:n.getText().slice(0,500)});
  function plain(v,depth=0) {
    if(!v||depth>8)return {state:'unknown',reason:'depth_limit'};
    if(v.tag==='literal')return v.value===undefined?{state:'undefined'}:{state:'constant',value:v.value};
    if(v.tag==='object')return {state:'object',fields:Object.fromEntries(Object.entries(v.props).map(([k,x])=>[k,plain(x,depth+1)]))};
    if(v.tag==='json')return {state:'json_string',value:plain(v.value,depth+1)};
    return {state:'unknown',reason:v.reason||v.tag};
  }
  function clone(v,memo=new Map()) {
    if(v?.tag!=='object')return v;if(memo.has(v))return memo.get(v);
    const r={...v,props:{}};memo.set(v,r);for(const [k,x] of Object.entries(v.props))r.props[k]=clone(x,memo);return r;
  }
  function merge(a,b) {
    if(a?.classNode!==b?.classNode)return unk('receiver_class_differs');
    if(a?.tag==='function'||b?.tag==='function')return a===b?a:unk('branch_callbacks_differ');
    if(JSON.stringify(plain(a))===JSON.stringify(plain(b)))return a;
    if(a?.tag==='object'&&b?.tag==='object')return {...a,props:Object.fromEntries([...new Set([...Object.keys(a.props),...Object.keys(b.props)])].map(k=>[k,merge(a.props[k],b.props[k])]))};
    return unk('branch_values_differ');
  }
  function decl(n) {let s=ts.isIdentifier(n)&&ts.isShorthandPropertyAssignment(n.parent)?checker.getShorthandAssignmentValueSymbol(n.parent):checker.getSymbolAtLocation(n);if(s?.flags&ts.SymbolFlags.Alias)s=checker.getAliasedSymbol(s);return s?.valueDeclaration||s?.declarations?.[0];}
  const external=n=>{const d=decl(n);return d&&!sourceFiles.has(loc(d).path);};
  function platformType(n,name) {
    const type=checker.getTypeAtLocation(n);
    const has=t=>t?.isUnion?.()?t.types.some(has):t?.symbol?.getName()===name&&t.symbol.declarations?.some(d=>loc(d).path.startsWith('<typescript-lib>/'));
    if(has(type))return true;
    const d=decl(n);let found=false;
    if(d?.type)walk(d.type,t=>{if(ts.isTypeReferenceNode(t)&&t.typeName.getText()===name&&external(t.typeName))found=true;});
    return found;
  }
  function unwrap(n){while(n&&(ts.isAsExpression(n)||ts.isTypeAssertionExpression(n)||ts.isParenthesizedExpression(n)||ts.isNonNullExpression(n)))n=n.expression;return n;}
  function symbol(n,c) {
    const d=decl(n);if(c.env.has(d))return c.env.get(d);if(!d)return unk('symbol_not_resolved');
    if(ts.isFunctionLike(d))return fn(d,c.env,c.receiver);
    if(ts.isClassDeclaration(d))return {tag:'class',node:d};
    if(ts.isExportAssignment(d))return ev(d.expression,c);
    if(ts.isVariableDeclaration(d)&&d.initializer) {
      if(c.resolving.has(d))return unk('recursive_initializer');c.resolving.add(d);
      const v=ev(d.initializer,c);c.resolving.delete(d);c.env.set(d,v);return v;
    }
    return unk('runtime_or_external_symbol');
  }
  function base(cls){const h=cls?.heritageClauses?.find(h=>h.token===ts.SyntaxKind.ExtendsKeyword)?.types?.[0];return h?decl(h.expression):null;}
  function method(cls,name) {
    for(let q=cls;q;q=base(q)){const m=q.members?.find(m=>m.name?.getText().replace(/^['"]|['"]$/g,'')===name&&ts.isFunctionLike(m));if(m)return m;}return null;
  }
  function get(v,key,c) {
    if(v?.tag==='object') {
      if(Object.hasOwn(v.props,key))return v.props[key];
      if(v.classNode){const m=method(v.classNode,key);return m?fn(m,c.env,v):unk('runtime_instance_field');}
      return lit(undefined);
    }
    if(v?.tag==='super'){const m=method(v.classNode,key);if(m)return fn(m,c.env,v.receiver);}
    if(v?.tag==='literal'&&typeof v.value==='string'&&key==='length')return lit(v.value.length);
    return unk('property_receiver_unknown');
  }
  function bind(name,value,c) {
    if(ts.isIdentifier(name)){c.env.set(name.parent,value);return;}
    if(ts.isObjectBindingPattern(name))for(const e of name.elements){const key=(e.propertyName||e.name).getText().replace(/^['"]|['"]$/g,'');let v=get(value,key,c);if(v.tag==='literal'&&v.value===undefined&&e.initializer)v=ev(e.initializer,c);bind(e.name,v,c);}
    if(ts.isArrayBindingPattern(name))for(const [i,e] of name.elements.entries())if(ts.isBindingElement(e))bind(e.name,get(value,String(i),c),c);
  }
  function note(n,kind,details,c){if(active)active.events.push({kind,...src(n),...details,conditions:[...c.conditions]});}
  function invalidate(v,reason,seen=new Set()) {if(v?.tag!=='object'||seen.has(v))return;seen.add(v);for(const k of Object.keys(v.props)){invalidate(v.props[k],reason,seen);v.props[k]=unk(reason);}v.props['<unknown_fields>']=unk(reason);}
  function assign(left,value,c) {
    left=unwrap(left);if(ts.isIdentifier(left)){c.env.set(decl(left),value);return;}
    if(ts.isPropertyAccessExpression(left)||ts.isElementAccessExpression(left)) {
      const v=ev(left.expression,c),k=ts.isPropertyAccessExpression(left)?lit(left.name.text):ev(left.argumentExpression,c);
      if(v.tag==='object'&&k.tag==='literal'){v.props[k.value]=value;note(left,'field_assignment',{field:String(k.value),value:plain(value)},c);}
    }
  }
  function instance(cls,args,c) {
    const v={tag:'object',props:{},classNode:cls},line=[];for(let q=cls;q;q=base(q))line.unshift(q);
    for(const q of line)for(const m of q.members||[])if(ts.isPropertyDeclaration(m)&&m.name&&m.initializer)v.props[m.name.getText()]=ev(m.initializer,{...c,receiver:v});
    const ctor=cls.members.find(ts.isConstructorDeclaration);if(ctor)invoke(fn(ctor,c.env,v),args,c);return v;
  }
  function invoke(callable,args,c,at=null) {
    if(callable?.tag!=='function')return unk('callee_not_resolved');const n=callable.node;
    if(!n.body)return unk('declaration_without_body');if(c.depth>=20)return unk('call_depth_limit');
    const sub={...c,env:new Map(callable.env),receiver:callable.receiver||c.receiver,depth:c.depth+1,current:n};
    n.parameters.forEach((p,i)=>bind(p.name,args[i]??(p.initializer?ev(p.initializer,sub):lit(undefined)),sub));
    if(at)note(at,'argument_transfer',{target:src(n),arguments:args.map(v=>plain(v))},sub);
    return ts.isBlock(n.body)?(block(n.body.statements,sub)?.value||lit(undefined)):ev(n.body,sub);
  }
  function block(statements,c) {
    const alternatives=[];
    const finish=r=>r?.thrown?r:{value:alternatives.reduce((value,other)=>merge(value,other),r?.value||lit(undefined))};
    for(const s of statements) {
      if(++steps>12000){diagnostics.push({kind:'step_limit',consumer:active?.id});return {value:unk('step_limit')};}
      if(ts.isVariableStatement(s)){for(const d of s.declarationList.declarations)bind(d.name,d.initializer?ev(d.initializer,c):lit(undefined),c);}
      else if(ts.isExpressionStatement(s))ev(s.expression,c);
      else if(ts.isReturnStatement(s))return finish({value:s.expression?ev(s.expression,c):lit(undefined)});
      else if(ts.isThrowStatement(s))return {value:unk('throw_path'),thrown:true};
      else if(ts.isBlock(s)){const r=block(s.statements,c);if(r)return finish(r);}
      else if(ts.isTryStatement(s)){
        diagnostics.push({kind:'exception_paths_not_expanded',...loc(s),consumer:active?.id});
        const r=block(s.tryBlock.statements,{...c,conditions:[...c.conditions,'try_completes_without_exception']});
        if(s.catchClause)walk(s.catchClause,n=>{if(ts.isBinaryExpression(n)&&n.operatorToken.kind===ts.SyntaxKind.EqualsToken)assign(n.left,unk('exception_path_write'),c);});
        if(s.finallyBlock){const f=block(s.finallyBlock.statements,c);if(f)return finish(f);}
        if(r)return finish(r);
      }
      else if(ts.isIfStatement(s)) {
        const condition=ev(s.expression,c),run=(b,cc)=>b?block(ts.isBlock(b)?b.statements:[b],cc):null;
        if(condition.tag==='literal'){const r=run(condition.value?s.thenStatement:s.elseStatement,c);if(r)return finish(r);}
        else {
          const branches=[s.thenStatement,s.elseStatement].map((b,i)=>{const memo=new Map(),cc={...c,env:new Map([...c.env].map(([k,v])=>[k,clone(v,memo)])),receiver:clone(c.receiver,memo),conditions:[...c.conditions,(i?'!':'')+s.expression.getText()]};return {ctx:cc,result:run(b,cc)};});
          const live=branches.filter(b=>!b.result);if(!live.length)return finish({value:merge(branches[0].result.value,branches[1].result.value)});
          for(const b of branches)if(b.result&&!b.result.thrown)alternatives.push(b.result.value);
          if(live.length===1){c.env=live[0].ctx.env;c.receiver=live[0].ctx.receiver;c.conditions=live[0].ctx.conditions;}
          else {for(const k of new Set([...live[0].ctx.env.keys(),...live[1].ctx.env.keys()]))c.env.set(k,merge(live[0].ctx.env.get(k),live[1].ctx.env.get(k)));c.receiver=merge(live[0].ctx.receiver,live[1].ctx.receiver);}
        }
      } else if(ts.isForStatement(s)||ts.isForOfStatement(s)||ts.isWhileStatement(s)||ts.isSwitchStatement(s)) {
        diagnostics.push({kind:'control_flow_not_expanded',...loc(s),consumer:active?.id});
        walk(s,n=>{if(ts.isBinaryExpression(n)&&n.operatorToken.kind===ts.SyntaxKind.EqualsToken)assign(n.left,unk('unsupported_control_flow_write'),c);});
      }
    }
    return alternatives.length?finish(null):null;
  }
  function ev(raw,c) {
    const n=unwrap(raw);if(!n)return lit(undefined);if(++steps>12000)return unk('step_limit');
    if(ts.isStringLiteralLike(n))return lit(n.text);if(ts.isNumericLiteral(n))return lit(Number(n.text));
    if(n.kind===ts.SyntaxKind.TrueKeyword||n.kind===ts.SyntaxKind.FalseKeyword)return lit(n.kind===ts.SyntaxKind.TrueKeyword);
    if(n.kind===ts.SyntaxKind.NullKeyword)return lit(null);if(n.kind===ts.SyntaxKind.ThisKeyword)return c.receiver||unk('this_unknown');
    if(n.kind===ts.SyntaxKind.SuperKeyword)return {tag:'super',classNode:base(c.current?.parent),receiver:c.receiver};
    if(ts.isIdentifier(n))return n.text==='undefined'?lit(undefined):symbol(n,c);
    if(ts.isFunctionExpression(n)||ts.isArrowFunction(n))return fn(n,c.env,c.receiver);
    if(ts.isAwaitExpression(n))return ev(n.expression,c);
    if(ts.isObjectLiteralExpression(n)) {
      const props={};for(const p of n.properties){if(ts.isSpreadAssignment(p)){const v=ev(p.expression,c);if(v.tag==='object')Object.assign(props,v.props);else {for(const k of Object.keys(props))props[k]=unk('spread_unknown');props['<unknown_spread>']=unk('spread_unknown');}continue;}
        const key=p.name?.getText().replace(/^['"]|['"]$/g,'');if(ts.isPropertyAssignment(p))props[key]=ev(p.initializer,c);else if(ts.isShorthandPropertyAssignment(p))props[key]=symbol(p.name,c);}
      note(n,'object_construction',{fields:Object.keys(props)},c);return obj(props);
    }
    if(ts.isArrayLiteralExpression(n))return {...obj({...Object.fromEntries(n.elements.map((x,i)=>[String(i),ev(x,c)])),length:lit(n.elements.length)}),array:true};
    if(ts.isPropertyAccessExpression(n)||ts.isElementAccessExpression(n)){const k=ts.isPropertyAccessExpression(n)?lit(n.name.text):ev(n.argumentExpression,c);return k.tag==='literal'?get(ev(n.expression,c),k.value,c):unk('computed_key');}
    if(ts.isTypeOfExpression(n)){const v=ev(n.expression,c);return v.tag==='literal'?lit(typeof v.value):v.tag==='json'?lit('string'):v.tag==='object'?lit('object'):v.tag==='function'?lit('function'):unk('typeof_runtime');}
    if(ts.isPrefixUnaryExpression(n)){const v=ev(n.operand,c);return n.operator===ts.SyntaxKind.ExclamationToken&&v.tag==='literal'?lit(!v.value):unk('unary_runtime');}
    if(ts.isPostfixUnaryExpression(n))return unk('runtime_counter');
    if(ts.isConditionalExpression(n)){const v=ev(n.condition,c);return v.tag==='literal'?ev(v.value?n.whenTrue:n.whenFalse,c):merge(ev(n.whenTrue,c),ev(n.whenFalse,c));}
    if(ts.isBinaryExpression(n)) {
      if(n.operatorToken.kind===ts.SyntaxKind.EqualsToken){const v=ev(n.right,c);assign(n.left,v,c);return v;}
      const a=ev(n.left,c),op=n.operatorToken.kind;if(op===ts.SyntaxKind.QuestionQuestionToken&&a.tag==='literal')return a.value==null?ev(n.right,c):a;
      if(op===ts.SyntaxKind.AmpersandAmpersandToken&&a.tag==='literal'&&!a.value)return a;if(op===ts.SyntaxKind.BarBarToken&&a.tag==='literal'&&a.value)return a;
      const b=ev(n.right,c);if(a.tag!=='literal'||b.tag!=='literal')return unk('binary_runtime');
      if(op===ts.SyntaxKind.PlusToken)return lit(a.value+b.value);if(op===ts.SyntaxKind.EqualsEqualsEqualsToken)return lit(a.value===b.value);
      if(op===ts.SyntaxKind.ExclamationEqualsEqualsToken)return lit(a.value!==b.value);if(op===ts.SyntaxKind.AmpersandAmpersandToken)return lit(a.value&&b.value);if(op===ts.SyntaxKind.BarBarToken)return lit(a.value||b.value);return unk('operator_not_supported');
    }
    if(ts.isNewExpression(n)) {
      const args=(n.arguments||[]).map(x=>ev(x,c)),name=n.expression.getText(),target=decl(n.expression);
      if(name==='Promise'&&external(n.expression)){if(args[0]?.tag==='function')invoke(args[0],[unk('resolve'),unk('reject')],c,n);return unk('promise_result');}
      if(name==='Map'&&external(n.expression))return {tag:'map'};
      if(target&&ts.isClassDeclaration(target))return instance(target,args,c);return unk('external_construction');
    }
    if(ts.isCallExpression(n)) {
      const args=n.arguments.map(a=>ev(a,c)),expr=unwrap(n.expression);
      if(ts.isPropertyAccessExpression(expr)) {
        const receiver=ev(expr.expression,c),name=expr.name.text;
        if(expr.expression.getText()==='JSON'&&external(expr.expression)){if(name==='stringify')return {tag:'json',value:args[0]};if(name==='parse'&&args[0]?.tag==='json')return args[0].value;}
        if(expr.expression.getText()==='Object'&&external(expr.expression)&&name==='assign'&&args[0]?.tag==='object'){for(const v of args.slice(1)){if(v.tag==='object')Object.assign(args[0].props,v.props);else {for(const k of Object.keys(args[0].props))args[0].props[k]=unk('unknown_assign_source');args[0].props['<unknown_fields>']=unk('unknown_assign_source');}}return args[0];}
        if(receiver.tag==='literal'&&typeof receiver.value==='string'){if(name==='split'&&args[0]?.tag==='literal')return obj(Object.fromEntries(receiver.value.split(args[0].value).map((v,i)=>[String(i),lit(v)])));if(name==='toLowerCase')return lit(receiver.value.toLowerCase());}
        if(name==='forEach'&&args[0]?.tag==='function'&&receiver.array){for(let i=0;i<receiver.props.length.value;i++)invoke(args[0],[receiver.props[i],lit(i)],c,n);return lit(undefined);}
        if(name==='forEach'&&args[0]?.tag==='function'&&checker.isArrayType(checker.getTypeAtLocation(expr.expression))){invoke(args[0],[unk('element'),unk('index')],{...c,conditions:[...c.conditions,'collection_has_element']},n);return lit(undefined);}
        const type=checker.typeToString(checker.getTypeAtLocation(expr.expression));
        const transport=name==='postMessage'&&platformType(expr.expression,'Window')?'window.postMessage':name==='send'&&platformType(expr.expression,'WebSocket')?'socket':null;
        if(transport){const payload=args[0]?.tag==='json'?args[0].value:args[0];note(n,'platform_send',{transport,payload:plain(payload),receiver_type:type},c);if(active)active.boundaries.push({transport,...src(n),payload:clone(payload),events:[...active.events],conditions:[...c.conditions]});return lit(undefined);}
        const callee=get(receiver,name,c);if(callee.tag==='function')return invoke(callee,args,c,n);
        const target=checker.getResolvedSignature(n)?.declaration;
        if(target?.body&&sourceFiles.has(loc(target).path)){const owner=ts.isClassDeclaration(target.parent)?target.parent:null;note(n,'typed_receiver_candidate',{receiver_type:type,runtime_instance:'unknown'},c);return invoke(fn(target,c.env,owner?{tag:'object',props:{},classNode:owner}:receiver),args,c,n);}
        if(receiver.tag==='map'&&name==='get')note(n,'runtime_map_selection',{key:plain(args[0])},c);
        else {for(const a of args)invalidate(a,'unresolved_call_may_mutate_argument');invalidate(receiver,'unresolved_call_may_mutate_receiver');}
        return unk('external_or_unresolved_call');
      }
      if(ts.isIdentifier(expr)&&expr.text==='String'&&external(expr)&&args[0]?.tag==='literal')return lit(String(args[0].value));
      const target=ev(expr,c);if(target.tag!=='function')for(const a of args)invalidate(a,'unresolved_call_may_mutate_argument');
      return invoke(target,args,c,n);
    }
    return unk('unsupported_expression');
  }
  for(const sf of sfList)walk(sf,n=>{if(ts.isFunctionLike(n))ast.set(id(n,'callable'),n);if(ts.isBinaryExpression(n))ast.set(id(n,'binding'),n);});
  const setters=new Map(),registrations=[];
  for(const sf of sfList)walk(sf,n=>{if(!ts.isMethodDeclaration(n)||!n.body)return;walk(n.body,x=>{
    if(!ts.isBinaryExpression(x)||x.operatorToken.kind!==ts.SyntaxKind.EqualsToken||!ts.isPropertyAccessExpression(x.left)||x.left.expression.kind!==ts.SyntaxKind.ThisKeyword)return;
    const index=n.parameters.indexOf(decl(x.right));if(index>=0)setters.set(n,{slot:x.left.name.text,index,evidence:src(x)});
  });});
  for(const call of ctx.calls){if(!ts.isCallExpression(call)||!ts.isPropertyAccessExpression(call.expression))continue;const target=checker.getResolvedSignature(call)?.declaration,rule=setters.get(target),arg=rule&&call.arguments[rule.index];
    if(rule&&arg&&(ts.isArrowFunction(arg)||ts.isFunctionExpression(arg))&&ts.isClassDeclaration(target.parent))registrations.push({cls:target.parent,callback:arg,slot:rule.slot,call,setter:rule.evidence});}
  for(const call of ctx.calls) {
    const callId=id(call,'call_site'),bindings=bindingsByCall.get(callId)||[];if(!bindings.length)continue;
    const owner=callableOwner(call),item={id:'protocol:'+callId,source_call:callId,source_owner:owner?id(owner,'callable'):null,name:owner?ctx.qualified(owner):call.expression.getText(),...loc(call),binding_count:bindings.length,events:[],boundaries:[]};
    active=item;steps=0;if(bindings.length!==1){item.status='ambiguous_binding';consumers.push(item);continue;}
    const binding=ast.get(bindings[0].target),c={env:new Map(),resolving:new Set(),receiver:null,depth:0,current:null,conditions:[bindings[0].condition]};
    const closure=binding?ev(binding.right,c):unk('binding_missing');if(closure.tag!=='function'){item.status='unknown_callable';consumers.push(item);continue;}
    note(binding,'property_binding',{source_binding:bindings[0].target},c);invoke(closure,(call.arguments||[]).map(a=>ev(a,c)),c,call);
    for(const sent of [...item.boundaries].filter(b=>b.transport==='window.postMessage'))for(const registration of registrations) {
      const receiver={tag:'object',props:{[registration.slot]:fn(registration.callback,new Map())},classNode:registration.cls},handlers=[];
      for(let cls=registration.cls;cls;cls=base(cls))for(const member of cls.members)if(ts.isConstructorDeclaration(member)&&member.body)walk(member.body,x=>{
        if(ts.isBinaryExpression(x)&&x.operatorToken.kind===ts.SyntaxKind.EqualsToken&&ts.isPropertyAccessExpression(x.left)&&x.left.name.text==='onmessage'&&(ts.isArrowFunction(x.right)||ts.isFunctionExpression(x.right)))handlers.push(x.right);
      });
      for(const handler of handlers){const before=item.boundaries.length;item.events=[...sent.events,{kind:'callback_registration',...src(registration.call),setter:registration.setter,slot:registration.slot},{kind:'message_receiver',...src(handler),connection:'deployment_scope_required'}];
        invoke(fn(handler,new Map(),receiver),[obj({data:{tag:'json',value:clone(sent.payload)}})],{...c,receiver,conditions:[...c.conditions,'registered_receiver_is_message_destination']});
        for(const boundary of item.boundaries.slice(before))boundary.receiver_scope=loc(registration.call).path;
      }
    }
    item.status=item.boundaries.length?'transport_found':'no_transport_found';consumers.push(item);
  }
  active=null;
  return {version:'0.2.0',consumers:consumers.map(t=>({...t,boundaries:t.boundaries.map(b=>({...b,payload:plain(b.payload)}))})),diagnostics,
    limits:['bounded_source_propagation','runtime_receiver_is_candidate','deployment_scope_required','unsupported_expressions_keep_unknown','unknown_control_flow_is_conditional']};
}

function analyzeProtocol(ts,root,files){return analyze(ts,root,files,{pathsFromConfigs:true,run:extract});}
module.exports={analyzeProtocol};
if(require.main===module){const [root,manifest,tsModule,output]=process.argv.slice(2),ts=require(path.resolve(tsModule));if(ts.version!=='5.9.3')throw new Error('Expected TypeScript 5.9.3');if(fs.existsSync(output))throw new Error('Use a new output file');
  const g=analyzeProtocol(ts,root,JSON.parse(fs.readFileSync(manifest,'utf8')).files.map(f=>f.path));fs.writeFileSync(output,JSON.stringify(g,null,2)+'\n');process.stdout.write(JSON.stringify({consumers:g.protocol.consumers.length,boundaries:g.protocol.consumers.flatMap(c=>c.boundaries).length})+'\n');}
