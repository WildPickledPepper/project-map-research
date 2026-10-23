/* Source response dependencies, local construction and frontend state writes.
 * API roots are supplied by the preceding protocol graph. No application names
 * or fields are matching rules. Values are symbolic; product code is not run.
 */
const fs=require('node:fs'),path=require('node:path');
const {analyze}=require('./typescript_facts.cjs');

function extractData(ctx,apiSymbols,{maxSteps=20000,maxDepth=12,responseRegistries=false,socketOnly=false,
    returnOnly=false,boundarySymbols=[],apiEntries=[],handoffSymbols=[]}={}) {
  const {ts,checker,loc,id,callableOwner,qualified}=ctx,apis=new Set(apiSymbols);
  const src=n=>({...loc(n),expression:n.getText().slice(0,500)});
  const unknown=reason=>({tag:'unknown',reason}),literal=value=>({tag:'literal',value});
  const entries=new Map(),writes=[],reads=[],calls=[],diagnostics=[];let steps=0,currentEntry=null;
  const promiseEntries=new Map(),lookupEntries=new Map(),registrations=[],lookups=[],settlements=[],promises=[],deletions=[],callbackBindings=[];
  const transmissions=[],counterUpdates=[];
  const socketEntries=new Map(),socketCreations=[],channelBindings=[],listenerBindings=[];
  const boundarySet=new Set(boundarySymbols),returnBoundaries=[],returnValues=[],returnBindings=[],windowListeners=[],handoffs=[],guardTests=[];
  const handoffSet=new Set(handoffSymbols),ast=new Map();
  if(returnOnly)for(const sf of ctx.sfList)ctx.walk(sf,n=>{if(ts.isFunctionLike(n))ast.set(id(n,'callable'),n);if(ts.isBinaryExpression(n))ast.set(id(n,'binding'),n);});
  let socketEpoch=0;
  let phase='consumers';
  const unwrap=n=>{while(n&&(ts.isAsExpression(n)||ts.isParenthesizedExpression(n)||ts.isNonNullExpression(n)||ts.isTypeAssertionExpression(n)))n=n.expression;return n;};
  function decl(n){let s=ts.isIdentifier(n)&&ts.isShorthandPropertyAssignment(n.parent)?checker.getShorthandAssignmentValueSymbol(n.parent):checker.getSymbolAtLocation(n);if(s?.flags&ts.SymbolFlags.Alias)s=checker.getAliasedSymbol(s);return s?.valueDeclaration||s?.declarations?.[0];}
  const inside=n=>n&&ctx.relativeFiles.includes(loc(n).path);
  function target(n){const d=checker.getResolvedSignature(n)?.declaration;return inside(d)&&ts.isFunctionLike(d)?d:null;}
  const standard=(n,name)=>{const d=decl(n);return n.getText()===name&&d&&loc(d).path.startsWith('<typescript-lib>/');};
  function platform(n,name){
    const check=t=>t?.isUnion?.()?t.types.some(check):t?.symbol?.getName()===name&&t.symbol.declarations?.some(d=>loc(d).path.startsWith('<typescript-lib>/'));
    if(check(checker.getTypeAtLocation(n)))return true;
    // An unresolved alternative can erase a union's checker type. Retain the
    // explicit standard-library alternative as a transport candidate.
    const d=decl(n);let found=false;
    if(d?.type)ctx.walk(d.type,t=>{if(ts.isTypeReferenceNode(t)&&standard(t.typeName,name))found=true;});
    return found;
  }
  for(const call of ctx.calls){const t=target(call);if(t&&apis.has(id(t,'callable'))){const owner=callableOwner(call);if(owner?.body)entries.set(id(owner,'callable'),owner);}}
  if(responseRegistries)for(const call of ctx.calls){
    const owner=callableOwner(call);if(!owner?.body)continue;
    if(ts.isNewExpression(call)&&standard(call.expression,'Promise'))promiseEntries.set(id(owner,'callable'),owner);
    if(ts.isCallExpression(call)&&ts.isPropertyAccessExpression(call.expression)&&call.expression.name.text==='get'&&platform(call.expression.expression,'Map'))lookupEntries.set(id(owner,'callable'),owner);
  }
  if(socketOnly){
    for(const call of ctx.calls){const owner=callableOwner(call);if(!owner?.body)continue;
      if(ts.isNewExpression(call)&&standard(call.expression,'WebSocket') ||
         ts.isCallExpression(call)&&ts.isPropertyAccessExpression(call.expression)&&call.expression.name.text==='send'&&platform(call.expression.expression,'WebSocket'))
        socketEntries.set(id(owner,'callable'),owner);
    }
    for(const assignment of ctx.assignments){const left=unwrap(assignment.left),owner=callableOwner(assignment);
      if(owner?.body&&ts.isPropertyAccessExpression(left)&&left.name.text==='onmessage'&&platform(left.expression,'WebSocket'))socketEntries.set(id(owner,'callable'),owner);
    }
  }
  function uniq(items){return [...new Map(items.map(v=>[JSON.stringify(v),v])).values()];}
  function channelIdentity(v){
    if(v.kind==='input_path')return JSON.stringify([v.kind,v.root,v.path,v.receiver_type||null]);
    if(v.kind==='native_socket')return JSON.stringify([v.kind,v.allocation]);
    return null;
  }
  const contextualId=(n,kind,c)=>[currentEntry,...c.chain.map(s=>s.call_site),id(n,kind)].join('/');
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
    if(v.tag==='json')out.value=clone(v.value,memo);
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
  function ownerClass(n){for(let q=n;q;q=q.parent)if(ts.isClassDeclaration(q))return q;return null;}
  function baseClass(n){const h=n?.heritageClauses?.find(h=>h.token===ts.SyntaxKind.ExtendsKeyword)?.types?.[0];return h?decl(h.expression):null;}
  function member(cls,key){for(let q=cls;q;q=baseClass(q)){const m=q.members?.find(x=>x.name?.getText().replace(/^['"]|['"]$/g,'')===key);if(m)return m;}return null;}
  function resolverRefs(v,seen=new Set()){
    if(!v||seen.has(v))return [];seen.add(v);if(v.tag==='resolver')return [{promise:v.promise,mode:v.mode}];
    const children=[...Object.values(v.props||{}),...(v.values||[]),...(v.tag==='function'?[...v.env.values()]:[])];
    return uniq(children.flatMap(x=>resolverRefs(x,seen)));
  }
  function describe(v,depth=0,seen=new Set()){
    if(!v)return {kind:'undefined'};if(depth>8||seen.has(v))return {kind:'unknown',reason:'value_description_limit'};seen.add(v);
    if(v.tag==='literal')return v.value===undefined?{kind:'undefined'}:{kind:'constant',value:v.value};
    if(v.tag==='input')return {kind:'input_path',root:v.root,path:v.path,transforms:v.transforms||[],evidence:v.evidence||[],conditions:v.conditions||[],gaps:v.gaps||[],
      ...(v.receiver_type?{receiver_type:v.receiver_type}:{}),
      ...(returnOnly&&v.selections?{selections:v.selections}:{}),
      ...(v.assigned?.length?{overrides:Object.fromEntries(v.assigned.map(k=>[k,describe(v.props[k],depth+1,new Set(seen))]))}:{})};
    if(v.tag==='function')return {kind:'source_callback',source_symbol:id(v.node,'callable'),resolvers:resolverRefs(v)};
    if(v.tag==='resolver')return {kind:'promise_resolver',promise:v.promise,mode:v.mode};
    if(v.tag==='union')return {kind:'alternatives',values:v.values.map(x=>describe(x,depth+1,new Set(seen)))};
    if(v.tag==='registry_lookup')return {kind:'registry_lookup',lookup:v.lookup,selectors:v.selectors};
    if(v.tag==='json')return {kind:'json_string',value:describe(v.value,depth+1,new Set(seen)),evidence:v.evidence};
    if(v.tag==='native_socket')return {kind:'native_socket',allocation:v.allocation,evidence:v.evidence};
    if(returnOnly&&v.tag==='promise')return describe(v.value,depth+1,new Set(seen));
    if(returnOnly&&v.tag==='instance')return {kind:'source_instance',receiver_type:id(v.classNode,'type'),allocation:v.allocation||null};
    if((socketOnly||returnOnly)&&v.tag==='computed'&&v.inputs)return {kind:'source_expression',operation:v.operation,
      inputs:v.inputs.map(x=>describe(x,depth+1,new Set(seen))),evidence:v.evidence||[]};
    if(v.tag==='object')return {kind:'object',fields:Object.fromEntries(Object.entries(v.props).map(([k,x])=>[k,describe(x,depth+1,new Set(seen))]))};
    return {kind:'unknown',reason:v.reason||v.tag};
  }
  function settle(resolver,args,c,n){
    settlements.push({id:id(n,'promise_settlement'),promise:resolver.promise,mode:resolver.mode,entry:currentEntry,
      source_symbol:id(c.current,'callable'),value:describe(args[0]),registry_context:c.registryContext||null,
      conditions:c.conditions,evidence:[src(n)],call_chain:c.chain});return literal(undefined);
  }
  function invokeLookup(value,args,c,n){
    const lookup=lookups.find(r=>r.id===value.lookup);if(!lookup)return unknown('lookup_not_recorded');
    const selected=[];
    for(const registration of registrations){
      const r=registration.record;
      if(r.registry!==lookup.registry||r.receiver_type!==lookup.receiver_type)continue;
      function constants(v){if(v.kind==='constant')return [v.value];if(v.kind!=='alternatives')return null;
        const parts=v.values.map(constants);return parts.every(Boolean)?parts.flat():null;}
      const left=constants(r.key),right=constants(lookup.key);
      if(left&&right&&!left.some(a=>right.includes(a)))continue;
      let callback=registration.value;for(const key of value.selectors)callback=get(callback,key,n,c);
      const condition={kind:'registered_value_selected',registration:r.id,lookup:lookup.id,
        receiver:'same_runtime_instance',key:'registration_key_equals_lookup_key',lifetime:'registration_reaches_lookup_without_replacement_or_deletion',
        callback_value:'captured_callback_fields_not_modified_before_invocation'};
      const cc={...c,conditions:[...c.conditions,...r.conditions,condition],registryContext:{registration:r.id,lookup:lookup.id,selectors:value.selectors}};
      if(callback.tag==='resolver')selected.push(settle(callback,args,cc,n));
      else if(callback.tag==='function')selected.push(invoke(callback,args,cc,n));
      else note(n,'registered_value_not_callable',cc);
    }
    if(!selected.length)note(n,'registry_callback_unresolved',c,{lookup:lookup.id,selectors:value.selectors});
    return selected.length?selected.reduce(merge):unknown('registry_callback_unresolved');
  }
  function get(v,key,n,c) {
    if(v?.tag==='union')return v.values.map(x=>get(x,key,n,c)).reduce(merge);
    if(v?.props&&Object.hasOwn(v.props,key))return v.props[key];
    if(returnOnly&&v?.tag==='super'){
      const m=member(v.classNode,key);return m&&ts.isFunctionLike(m)?{...fn(m,c),receiver:v.receiver}:unknown('base_member_unresolved');
    }
    if(responseRegistries&&v?.tag==='registry_lookup')return {...v,selectors:[...v.selectors,key]};
    if(responseRegistries&&v?.tag==='instance'){
      const m=member(v.classNode,key);if(!m)return unknown('instance_member_unresolved');
      if(ts.isFunctionLike(m))return {...fn(m,c),receiver:v};
      if(m.initializer&&(ts.isArrowFunction(m.initializer)||ts.isFunctionExpression(m.initializer)))return {...fn(m.initializer,c),receiver:v};
      let value;
      if(socketOnly&&m.initializer&&ts.isNewExpression(m.initializer)&&standard(m.initializer.expression,'WebSocket')){
        const cc={...c,conditions:[...c.conditions,{kind:'instance_field_initializer_not_replaced',...src(m)}]};
        value=ev(m.initializer,cc);
        channelBindings.push({id:contextualId(m,'channel_initializer',c)+':'+channelBindings.length,source_site:id(m,'binding'),
          entry:currentEntry,source_symbol:id(c.current,'callable'),channel:{kind:'input_path',root:id(m,'instance_binding'),path:[],receiver_type:id(v.classNode,'type')},
          value:describe(value),conditions:cc.conditions,evidence:[src(m)],call_chain:c.chain});
        v.props[key]=value;return value;
      }
      if(m.initializer&&ts.isNewExpression(m.initializer)&&standard(m.initializer.expression,'Map'))
        value={tag:'registry',registry:id(m,'map_binding'),receiver_type:id(v.classNode,'type'),evidence:[src(m)]};
      else value={tag:'input',root:id(m,'instance_binding'),path:[],props:{},evidence:[src(m)],...(socketOnly?{receiver_type:id(v.classNode,'type')}:{})};
      v.props[key]=value;return value;
    }
    if(v?.tag==='response'){
      const out={...v,path:[...v.path,key],evidence:[...v.evidence,src(n)],call_chain:c.chain,props:{}};
      reads.push({id:id(n,'response_read'),entry:currentEntry,source_symbol:id(c.current,'callable'),
        response:dependencies(out)[0],conditions:uniq([...c.conditions,...(v.conditions||[])]),evidence:[src(n)],call_chain:c.chain});
      v.props[key]=out;return out;
    }
    if(v?.tag==='input'){const out={...v,path:[...v.path,key],props:{},...(responseRegistries?{assigned:[],evidence:[...(v.evidence||[]),src(n)]}:{})};v.props[key]=out;return out;}
    if(v?.tag==='object')return key==='*'&&v.array?Object.values(v.props).reduce(merge,literal(undefined)):v.props['*']||literal(undefined);
    return unknown('property_source_unresolved');
  }
  function bind(name,value,c) {
    if(ts.isIdentifier(name)){c.env.set(name.parent,value);return;}
    if(ts.isObjectBindingPattern(name))for(const e of name.elements){const key=(e.propertyName||e.name).getText().replace(/^['"]|['"]$/g,'');let v=get(value,key,e,c);
      if(returnOnly&&v.tag==='literal'&&v.value===undefined&&e.initializer)v=ev(e.initializer,c);bind(e.name,v,c);}
    if(ts.isArrayBindingPattern(name))name.elements.forEach((e,i)=>{if(ts.isBindingElement(e))bind(e.name,get(value,String(i),e,c),c);});
  }
  function fn(n,c){return {tag:'function',node:n,env:c.env,receiver:c.receiver};}
  function symbol(n,c) {
    const d=decl(n);if(c.env.has(d))return c.env.get(d);
    if(!d)return unknown('symbol_unresolved');
    if((socketOnly||returnOnly)&&loc(d).path.startsWith('<typescript-lib>/')&&platform(n,'Window'))return {tag:'input',root:id(d,'platform_binding'),path:[],props:{},evidence:[src(n)]};
    if(returnOnly&&ts.isExportAssignment(d))return ev(d.expression,c);
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
    if(returnOnly&&prop==='onmessage'&&platform(left.expression,'Window')){
      const callback=value.tag==='function'?value:null;
      const record={id:contextualId(at,'window_listener',c)+':'+windowListeners.length,entry:currentEntry,
        source_symbol:id(c.current,'callable'),receiver_type:c.receiver?.classNode?id(c.receiver.classNode,'type'):null,
        channel:describe(receiver),callback:callback?id(callback.node,'callable'):null,
        event_parameter:callback?.node.parameters[0]?id(callback.node.parameters[0],'input_binding'):null,
        conditions:c.conditions,evidence:[src(at)],superseded_by:[]};
      for(const old of windowListeners)if(old.record.entry===currentEntry&&old.record.receiver_type===record.receiver_type&&
        channelIdentity(old.record.channel)===channelIdentity(record.channel)&&JSON.stringify(old.record.conditions)===JSON.stringify(record.conditions))old.record.superseded_by.push(record.id);
      windowListeners.push({record,callback});
    }
    if(socketOnly){
      if(receiver.tag==='instance'&&platform(left,'WebSocket')){
        const m=member(receiver.classNode,prop);
        if(m)channelBindings.push({id:contextualId(at,'channel_assignment',c)+':'+channelBindings.length,source_site:id(at,'binding'),
          entry:currentEntry,source_symbol:id(c.current,'callable'),channel:{kind:'input_path',root:id(m,'instance_binding'),path:[],receiver_type:id(receiver.classNode,'type')},
          value:describe(value),conditions:c.conditions,evidence:[src(at),src(m)],call_chain:c.chain});
      }
      if(prop==='onmessage'&&platform(left.expression,'WebSocket')){
        const callback=value.tag==='function'?value:null,cls=callback&&ownerClass(callback.node);
        const mode=callback?(ts.isArrowFunction(callback.node)?'lexical':callback.boundReceiver?'bound':'event_target'):'unresolved';
        const parameter=callback?.node.parameters?.[0];
        const record={id:contextualId(at,'socket_listener',c)+':'+listenerBindings.length,source_site:id(at,'binding'),entry:currentEntry,
          source_symbol:id(c.current,'callable'),channel:describe(receiver),property:prop,
          callback:callback?id(callback.node,'callable'):null,event_parameter:parameter?id(parameter,'input_binding'):null,
          this_binding:mode,callback_receiver_type:mode==='lexical'&&cls?id(cls,'type'):mode==='bound'&&callback.receiver?.classNode?id(callback.receiver.classNode,'type'):null,
          action:callback?'install':value.tag==='literal'&&value.value===null?'clear':'unknown',
          conditions:c.conditions,evidence:[src(at)],call_chain:c.chain,sequence_epoch:socketEpoch,superseded_by:[]};
        for(const old of listenerBindings)if(old.entry===currentEntry&&channelIdentity(old.channel)&&channelIdentity(old.channel)===channelIdentity(record.channel)&&
            old.sequence_epoch===socketEpoch&&JSON.stringify(old.conditions)===JSON.stringify(record.conditions)&&JSON.stringify(old.call_chain)===JSON.stringify(record.call_chain))old.superseded_by.push(record.id);
        listenerBindings.push(record);
      }
    }
    if(responseRegistries&&value.tag==='function')callbackBindings.push({id:id(at,'callback_assignment'),entry:currentEntry,
      receiver:describe(receiver),property:prop,callback:id(value.node,'callable'),conditions:c.conditions,evidence:[src(at)]});
    function put(r){
      if(r.tag==='union'){r.values.forEach(put);return;}
      if(r.tag==='input')writes.push({id:id(at,'state_write'),entry:currentEntry,source_symbol:id(c.current,'callable'),
        target:{root:r.root,path:[...r.path,prop]},operation,value_dependencies:dependencies(value),
        continuation_apis:[...c.awaited],conditions:uniq([...c.conditions,...(r.conditions||[])]),evidence:[src(at)],call_chain:c.chain});
      if(r.props){r.props[prop]=value;
        if(responseRegistries)r.assigned=uniq([...(r.assigned||[]),prop]);
        if(prop==='*')r.dependencies=uniq([...(r.dependencies||[]),...dependencies(key)]);
      } else note(at,'assignment_receiver_unresolved',c);
    }
    put(receiver);
  }
  function invoke(callable,args,c,at) {
    if(callable?.tag!=='function'||!callable.node.body)return unknown('callee_body_unresolved');
    const n=callable.node;if(c.depth>=maxDepth){note(at||n,'call_depth_limit',c);return unknown('call_depth_limit');}
    if(returnOnly&&c.windowReplay&&handoffSet.has(id(n,'callable'))){
      handoffs.push({id:contextualId(at||n,'window_handoff',c)+':'+handoffs.length,listener:c.windowReplay,target:id(n,'callable'),
        target_parameters:n.parameters.map(p=>id(p,'input_binding')),
        receiver_type:callable.receiver?.classNode?id(callable.receiver.classNode,'type'):null,
        arguments:args.map(a=>describe(a)),conditions:c.conditions,evidence:[src(at||n)],call_chain:c.chain});
      return literal(undefined);
    }
    if(returnOnly&&boundarySet.has(id(n,'callable'))){
      const uid=contextualId(at||n,'return_boundary',c),record={id:uid,entry:currentEntry,target:id(n,'callable'),
        call_site:at?id(at,'call_site'):null,receiver_type:ownerClass(n)?id(ownerClass(n),'type'):null,
        arguments:args.map(a=>describe(a)),conditions:c.conditions,evidence:[src(at||n)],call_chain:c.chain};
      returnBoundaries.push(record);
      return {tag:'promise',value:{tag:'input',root:uid,path:[],props:{},evidence:record.evidence,conditions:c.conditions},awaited:[]};
    }
    const isAsync=n.modifiers?.some(m=>m.kind===ts.SyntaxKind.AsyncKeyword);
    const sub={...c,env:new Map(callable.env),awaited:isAsync?new Set(c.awaited):c.awaited,receiver:callable.receiver||c.receiver,depth:c.depth+1,current:n,
      chain:at?[...c.chain,{call_site:id(at,'call_site'),target:id(n,'callable'),evidence:[src(at),src(n)]}]:c.chain};
    n.parameters.forEach((p,i)=>bind(p.name,args[i]??(p.initializer?ev(p.initializer,sub):literal(undefined)),sub));
    const value=ts.isBlock(n.body)?block(n.body.statements,sub)||literal(undefined):ev(n.body,sub);
    if(returnOnly)returnValues.push({id:contextualId(at||n,'source_return',sub)+':'+returnValues.length,entry:currentEntry,
      source_symbol:id(n,'callable'),value:describe(value),conditions:sub.conditions,evidence:[src(n)],call_chain:sub.chain});
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
        if(returnOnly)guardTests.push({source_symbol:id(c.current,'callable'),entry:currentEntry,...src(s.expression),test:describe(condition)});
        if(condition.tag==='literal'){const r=run(condition.value?s.thenStatement:s.elseStatement,c);if(r){returned.push(r);break;}}
        else {
          const branches=[s.thenStatement,s.elseStatement].map((branch,i)=>{const memo=new Map(),cc={...c,env:new Map([...c.env].map(([k,v])=>[k,clone(v,memo)])),receiver:clone(c.receiver,memo),awaited:new Set(c.awaited),
            conditions:[...c.conditions,{...src(s.expression),when:i===0,...(returnOnly?{test:describe(condition)}:{})}]};return {ctx:cc,result:run(branch,cc)};});
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
    if(returnOnly&&n.kind===ts.SyntaxKind.SuperKeyword)return {tag:'super',classNode:baseClass(ownerClass(c.current)),receiver:c.receiver};
    if(ts.isIdentifier(n))return n.text==='undefined'?literal(undefined):symbol(n,c);
    if(ts.isArrowFunction(n)||ts.isFunctionExpression(n))return fn(n,c);
    if(returnOnly&&ts.isTypeOfExpression(n)){
      const v=ev(n.expression,c);return v.tag==='literal'?literal(typeof v.value):v.tag==='function'?literal('function'):
        v.tag==='json'?literal('string'):v.tag==='object'||v.tag==='instance'?literal('object'):unknown('runtime_typeof');
    }
    if(ts.isAwaitExpression(n)){
      if(socketOnly)socketEpoch++;
      function fulfilled(value){
        if(value.tag==='promise'){for(const uid of value.awaited||[])c.awaited.add(uid);return fulfilled(value.value);}
        if(value.tag==='union')return value.values.map(fulfilled).reduce(merge);
        for(const d of dependencies(value))c.awaited.add(d.request_context);return value;
      }
      return fulfilled(ev(n.expression,c));
    }
    if(socketOnly&&ts.isTemplateExpression(n))return {tag:'computed',operation:'template_string',
      inputs:[literal(n.head.text),...n.templateSpans.flatMap(s=>[ev(s.expression,c),literal(s.literal.text)])],evidence:[src(n)]};
    if(ts.isObjectLiteralExpression(n)){
      const value={tag:'object',props:{},dependencies:[]};
      for(const p of n.properties){if(ts.isSpreadAssignment(p)){const v=ev(p.expression,c);
        if(returnOnly&&v.tag!=='object'){
          for(const k of Object.keys(value.props))value.props[k]=unknown('unresolved_spread_may_overwrite_field');
          note(p,'spread_source_not_expanded',c);
        }else Object.assign(value.props,v.props||{});
        value.dependencies.push(...dependencies(v));continue;}
        const key=p.name?.getText().replace(/^['"]|['"]$/g,'');if(ts.isPropertyAssignment(p))value.props[key]=ev(p.initializer,c);else if(ts.isShorthandPropertyAssignment(p))value.props[key]=symbol(p.name,c);}
      return value;
    }
    if(ts.isArrayLiteralExpression(n))return {tag:'object',array:true,props:Object.fromEntries(n.elements.map((v,i)=>[String(i),ev(v,c)])),dependencies:[]};
    if(ts.isPropertyAccessExpression(n)||ts.isElementAccessExpression(n)){
      const key=ts.isPropertyAccessExpression(n)?literal(n.name.text):ev(n.argumentExpression,c),receiver=ev(n.expression,c);
      const result=get(receiver,key.tag==='literal'?String(key.value):'*',n,c);
      if(returnOnly&&ts.isElementAccessExpression(n)&&key.tag!=='literal'&&result.tag==='input')
        return {...result,selections:[...(result.selections||[]),{at_path:receiver.path||[],key:describe(key),evidence:[src(n)]}]};
      return result;
    }
    if(ts.isPrefixUnaryExpression(n)){
      const value=ev(n.operand,c);if(n.operator===ts.SyntaxKind.ExclamationToken&&value.tag==='literal')return literal(!value.value);
      if(responseRegistries&&n.operator===ts.SyntaxKind.MinusToken&&value.tag==='literal')return literal(-value.value);
      return {tag:'computed',dependencies:dependencies(value)};
    }
    if(responseRegistries&&ts.isPostfixUnaryExpression(n)){
      const before=ev(n.operand,c),type=checker.getTypeAtLocation(n.operand);
      const numeric=t=>t.isUnion?.()?t.types.every(numeric):!!(t.flags&(ts.TypeFlags.NumberLike|ts.TypeFlags.BigIntLike));
      const after={tag:'input',root:contextualId(n,'counter_after',c),path:[],props:{},evidence:[src(n)]};
      assign(n.operand,after,c,n,n.operator===ts.SyntaxKind.PlusPlusToken?'++':'--');
      const value=before.tag==='literal'&&typeof before.value==='number'?before:numeric(type)?before:unknown('counter_numeric_coercion_unresolved');
      counterUpdates.push({id:contextualId(n,'counter_update',c),entry:currentEntry,operation:n.operator===ts.SyntaxKind.PlusPlusToken?'++':'--',
        before:describe(value),after:describe(after),conditions:c.conditions,evidence:[src(n)],call_chain:c.chain});
      return value;
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
      return {tag:'computed',dependencies:uniq([...dependencies(a),...dependencies(b)]),
        ...((socketOnly||returnOnly)?{operation:ts.tokenToString(op),inputs:[a,b],evidence:[src(n)]}:{})};
    }
    if(ts.isConditionalExpression(n)){const v=ev(n.condition,c);if(v.tag==='literal')return ev(v.value?n.whenTrue:n.whenFalse,c);
      const branches=[n.whenTrue,n.whenFalse].map((b,i)=>{const conditions=[...c.conditions,{...src(n.condition),when:i===0}];return guarded(ev(b,{...c,conditions}),conditions);});return branches.reduce(merge);}
    if(ts.isCallExpression(n)) {
      const callee=target(n),args=n.arguments.map(a=>ev(a,c)),callId=id(n,'call_site');
      if(returnOnly){
        const bindings=ctx.facts.edges.filter(e=>e.source===callId&&e.kind==='USES_BINDING');
        if(bindings.length){
          if(bindings.length!==1){note(n,'ambiguous_global_binding',c);return unknown('ambiguous_global_binding');}
          const assignment=ast.get(bindings[0].target),callable=assignment?ev(assignment.right,c):null;
          if(callable?.tag==='function')return invoke(callable,args,{...c,conditions:[...c.conditions,{kind:'source_global_binding',
            binding:bindings[0].target,evidence:[src(assignment)],condition:bindings[0].condition}]},n);
          return unknown('global_binding_not_callable');
        }
        if(n.expression.kind===ts.SyntaxKind.SuperKeyword){
          const cls=baseClass(ownerClass(c.current)),ctor=cls?.members.find(ts.isConstructorDeclaration);
          return ctor?invoke({...fn(ctor,c),receiver:c.receiver},args,c,n):literal(undefined);
        }
      }
      if(callee&&apis.has(id(callee,'callable'))){
        const request_context=[currentEntry,...c.chain.map(s=>s.call_site),callId].join('/');
        const record={api:id(callee,'callable'),api_call:callId,request_context,entry:currentEntry,evidence:[src(n)]};calls.push(record);
        return {tag:'promise',value:{tag:'response',...record,path:[],props:{},conditions:c.conditions}};
      }
      if(ts.isPropertyAccessExpression(n.expression)) {
        const receiver=ev(n.expression.expression,c),name=n.expression.name.text;
        if(socketOnly&&name==='replace'){
          const declaration=checker.getResolvedSignature(n)?.declaration;
          if(declaration&&loc(declaration).path.startsWith('<typescript-lib>/')&&declaration.parent?.name?.getText()==='String')
            return {tag:'computed',operation:'String.replace',inputs:[receiver,...args],evidence:[src(n)]};
        }
        if(socketOnly&&name==='bind'&&receiver.tag==='function'&&loc(decl(n.expression)||n).path.startsWith('<typescript-lib>/'))
          return {...receiver,receiver:args[0],boundReceiver:true};
        if(responseRegistries&&standard(n.expression.expression,'JSON')&&name==='stringify')return {tag:'json',value:clone(args[0]),evidence:[src(n)]};
        if(responseRegistries&&((name==='send'&&platform(n.expression.expression,'WebSocket'))||(name==='postMessage'&&platform(n.expression.expression,'Window')))){
          transmissions.push({id:contextualId(n,socketOnly?'socket_send':returnOnly?'return_transmission':'transmission',c)+':'+transmissions.length,source_site:callId,entry:currentEntry,promise_context:c.promiseContext||null,
            transport:name==='send'?'WebSocket.send':'window.postMessage',receiver:describe(receiver),payload:describe(clone(args[0])),
            ...(returnOnly?{target_origin:describe(args[1])}:{}),
            conditions:c.conditions,evidence:[src(n)],call_chain:c.chain});return literal(undefined);
        }
        if(responseRegistries&&name==='forEach'&&platform(n.expression.expression,'Array')&&args[0]?.tag==='function'){
          function iterate(collection){
            if(collection.tag==='union'){collection.values.forEach(iterate);return;}
            if(collection.tag==='object'&&collection.array){for(const item of Object.values(collection.props))invoke(args[0],[item],{...c,conditions:[...c.conditions,{kind:'array_iteration',...src(n)}]},n);}
            else {note(n,'array_elements_unresolved',c);invoke(args[0],[unknown('runtime_array_element')],{...c,conditions:[...c.conditions,{kind:'array_nonempty_and_callback_invoked',...src(n)}]},n);}
          }
          iterate(receiver);return literal(undefined);
        }
        if(returnOnly&&name==='includes'&&receiver.tag==='object'&&receiver.array&&args[0]?.tag==='literal'&&
            Object.values(receiver.props).every(v=>v.tag==='literal'))return literal(Object.values(receiver.props).some(v=>v.value===args[0].value));
        if(responseRegistries&&standard(n.expression.expression,'JSON')&&name==='parse'){
          function decode(value){
            if(value?.tag==='union')return value.values.map(decode).reduce(merge);
            if(value?.tag==='json')return clone(value.value);
            if(value?.tag==='input')return {...value,props:{},transforms:[...(value.transforms||[]),{kind:'JSON.parse',at_path:value.path,evidence:[src(n)]}],conditions:c.conditions};
            return unknown('json_input_unresolved');
          }
          return decode(args[0]);
        }
        if(responseRegistries&&receiver.tag==='registry'){
          const record={id:contextualId(n,'registry_'+name,c),source_site:id(n,'call_site'),registry:receiver.registry,receiver_type:receiver.receiver_type,
            entry:currentEntry,promise_context:c.promiseContext||null,key:describe(args[0]),conditions:c.conditions,evidence:[...receiver.evidence,src(n)],call_chain:c.chain};
          if(name==='set'&&phase==='register'&&resolverRefs(args[1]).length){
            const captured=resolverRefs(args[1]);registrations.push({record:{...record,value:describe(args[1]),promises:uniq(captured.map(r=>r.promise))},value:args[1]});
          }
          if(name==='get'&&phase==='lookup'){lookups.push(record);return {tag:'registry_lookup',lookup:record.id,selectors:[]};}
          if(name==='delete')deletions.push(record);
          return unknown('runtime_registry_operation');
        }
        if(receiver.tag==='object'&&receiver.array&&name==='push'){
          receiver.props['*']=receiver.props['*']?merge(receiver.props['*'],args[0]):args[0];return literal(undefined);
        }
        if(returnOnly){const dynamic=get(receiver,name,n,c);if(dynamic.tag==='function')return invoke(dynamic,args,c,n);}
        if(callee?.body)return invoke({...fn(callee,c),receiver},args,c,n);
      }
      const callable=ev(n.expression,c);
      if(responseRegistries&&callable.tag==='resolver')return settle(callable,args,c,n);
      if(responseRegistries&&callable.tag==='registry_lookup'&&phase==='lookup')return invokeLookup(callable,args,c,n);
      if(callable.tag==='function'&&callable.node.body)return invoke(callable,args,c,n);
      if(callee?.body)return invoke(fn(callee,c),args,c,n);
      // A passed closure has a conditional execution edge, not an assumed library
      // implementation. Known local callees are interpreted before this fallback.
      for(const arg of args)if(arg.tag==='function')invoke(arg,[],{...c,conditions:[...c.conditions,{kind:'external_callee_invokes_callback',...src(n)}]},n);
      if(responseRegistries){
        const seen=new Set(),affected=[];function mark(v){if(!v||seen.has(v))return;seen.add(v);
          if(v.tag==='input'){const gap={kind:'possible_mutation_by_unresolved_call',...src(n)};v.gaps=uniq([...(v.gaps||[]),gap]);affected.push(describe(v));}
          for(const x of Object.values(v.props||{}))mark(x);for(const x of v.values||[])mark(x);}
        args.forEach(mark);if(affected.length)note(n,'unresolved_call_with_input_argument',c,{inputs:affected});
      }
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
    if(ts.isNewExpression(n)){
      if(returnOnly){
        const cls=decl(n.expression);
        if(cls&&ts.isClassDeclaration(cls)){
          const instance={tag:'instance',classNode:cls,props:{},allocation:contextualId(n,'source_instance',c)},line=[];
          for(let q=cls;q;q=baseClass(q))line.unshift(q);
          const cc={...c,receiver:instance};
          for(const q of line)for(const m of q.members)if(ts.isPropertyDeclaration(m)&&m.initializer)instance.props[m.name.getText()]=ev(m.initializer,cc);
          let ctor=null;for(let q=cls;q&&!ctor;q=baseClass(q))ctor=q.members.find(ts.isConstructorDeclaration);
          if(ctor)invoke({...fn(ctor,cc),receiver:instance},(n.arguments||[]).map(a=>ev(a,c)),c,n);
          return instance;
        }
      }
      if(socketOnly&&standard(n.expression,'WebSocket')){
        const allocation=contextualId(n,'socket_allocation',c),args=(n.arguments||[]).map(a=>ev(a,c));
        socketCreations.push({id:allocation,entry:currentEntry,source_symbol:id(c.current,'callable'),transport:'WebSocket',
          url:describe(args[0]),url_expression:n.arguments?.[0]?src(n.arguments[0]):null,conditions:c.conditions,evidence:[src(n)],call_chain:c.chain});
        return {tag:'native_socket',allocation,props:{},evidence:[src(n)]};
      }
      if(responseRegistries&&standard(n.expression,'Promise')){
        const uid=contextualId(n,'promise',c),args=(n.arguments||[]).map(a=>ev(a,c));
        promises.push({id:uid,entry:currentEntry,source_symbol:id(c.current,'callable'),conditions:c.conditions,evidence:[src(n)]});
        if(args[0]?.tag==='function')invoke(args[0],[{tag:'resolver',promise:uid,mode:'resolve'},{tag:'resolver',promise:uid,mode:'reject'}],{...c,promiseContext:uid},n);
        return {tag:'promise',value:unknown('settlement_deferred'),awaited:[]};
      }
      if(responseRegistries&&standard(n.expression,'Map'))return {tag:'registry',registry:id(n,'map_binding'),receiver_type:'local:'+currentEntry,evidence:[src(n)]};
      return {tag:'object',root:id(n,'allocation'),props:{},dependencies:[]};
    }
    return unknown('expression_not_modeled:'+ts.SyntaxKind[n.kind]);
  }
  const analyzed=[];
  function analyzeEntry(uid,entry){
    currentEntry=uid;steps=0;socketEpoch=0;const cls=responseRegistries&&ownerClass(entry);
    const c={env:new Map(),receiver:cls?{tag:'instance',classNode:cls,props:{}}:null,resolving:new Set(),current:entry,conditions:[],awaited:new Set(),chain:[],depth:0};
    entry.parameters.forEach(p=>bind(p.name,{tag:'input',root:id(p,'input_binding'),path:[],props:{},...(responseRegistries?{evidence:[src(p)]}:{})},c));
    if(ts.isBlock(entry.body))block(entry.body.statements,c);else ev(entry.body,c);
    analyzed.push({source_symbol:uid,name:qualified(entry),...loc(entry),steps,truncated:steps>maxSteps,...(responseRegistries?{phase}:{})});
  }
  for(const [uid,entry] of entries)analyzeEntry(uid,entry);
  if(returnOnly){
    const setters=new Map(),registrations=[];
    for(const n of ast.values())if(ts.isMethodDeclaration(n)&&n.body)ctx.walk(n.body,x=>{
      if(ts.isBinaryExpression(x)&&x.operatorToken.kind===ts.SyntaxKind.EqualsToken&&ts.isPropertyAccessExpression(x.left)&&x.left.expression.kind===ts.SyntaxKind.ThisKeyword){
        const index=n.parameters.indexOf(decl(x.right));if(index>=0)setters.set(n,{slot:x.left.name.text,index,assignment:x});
      }
    });
    for(const call of ctx.calls){if(!ts.isCallExpression(call)||!ts.isPropertyAccessExpression(call.expression))continue;
      const rule=setters.get(target(call)),arg=rule&&call.arguments[rule.index];
      if(arg&&(ts.isArrowFunction(arg)||ts.isFunctionExpression(arg)))registrations.push({call,rule,arg,cls:ownerClass(target(call))});
    }
    function context(entry){currentEntry=id(entry,'callable');steps=0;return {env:new Map(),receiver:null,resolving:new Set(),current:entry,conditions:[],awaited:new Set(),chain:[],depth:0};}
    function inputs(entry){return entry.parameters.map(p=>({tag:'input',root:id(p,'input_binding'),path:[],props:{},evidence:[src(p)]}));}
    for(const registration of registrations){
      const {call,rule,arg,cls}=registration;if(!cls)continue;
      for(const entry of cls.members){if(!ts.isMethodDeclaration(entry)||!entry.body)continue;let invokesSlot=false;
        ctx.walk(entry.body,n=>{if(ts.isCallExpression(n)&&ts.isPropertyAccessExpression(n.expression)&&n.expression.expression.kind===ts.SyntaxKind.ThisKeyword&&n.expression.name.text===rule.slot)invokesSlot=true;});
        if(!invokesSlot)continue;handoffSet.add(id(entry,'callable'));
        const c=context(entry),receiver=ev(call.expression.expression,c);
        if(receiver.tag!=='instance'){note(call,'registered_receiver_unresolved',c);continue;}
        invoke({...fn(target(call),c),receiver},call.arguments.map(a=>ev(a,c)),c,call);
        returnBindings.push({id:id(call,'return_callback_binding'),entry:currentEntry,receiver_type:id(receiver.classNode,'type'),
          entry_parameters:entry.parameters.map(p=>id(p,'input_binding')),
          slot:rule.slot,callback:id(arg,'callable'),evidence:[src(call),src(rule.assignment)],conditions:c.conditions});
        invoke({...fn(entry,c),receiver},inputs(entry),c,null);
        analyzed.push({source_symbol:currentEntry,name:qualified(entry),...loc(entry),steps,truncated:steps>maxSteps,phase:'reply'});
      }
    }
    for(const uid of apiEntries){const entry=ast.get(uid);if(!entry?.body)continue;const c=context(entry);
      invoke(fn(entry,c),inputs(entry),c,null);analyzed.push({source_symbol:uid,name:qualified(entry),...loc(entry),steps,truncated:steps>maxSteps,phase:'api_return'});
    }
    phase='request_send';for(const uid of boundarySymbols){const entry=ast.get(uid);if(entry?.body)analyzeEntry(uid,entry);}
    phase='delivery_guards';for(const uid of handoffSymbols){const entry=ast.get(uid);if(entry?.body)analyzeEntry(uid,entry);}
    const listeners=[...windowListeners],seen=new Set();
    for(const {record,callback} of listeners){if(!callback||record.superseded_by.length)continue;
      const signature=JSON.stringify([record.entry,record.receiver_type,record.callback]);if(seen.has(signature))continue;seen.add(signature);
      const c=context(callback.node);c.windowReplay=record.id;
      invoke(callback,inputs(callback.node),c,null);
      analyzed.push({source_symbol:currentEntry,name:qualified(callback.node),...loc(callback.node),steps,truncated:steps>maxSteps,phase:'window_receiver'});
    }
    return {version:'0.1.0',entries:analyzed,boundaries:uniq(returnBoundaries),returns:uniq(returnValues),callback_bindings:uniq(returnBindings),
      transmissions:uniq(transmissions),window_listeners:windowListeners.map(r=>r.record),handoffs:uniq(handoffs),guard_tests:uniq(guardTests),diagnostics:uniq(diagnostics),
      limits:['fulfilled_boundary_values_are_source_inputs','window_destination_and_origin_require_matching_deployment',
        'registered_callback_requires_same_receiver_and_lifetime','exceptions_and_unresolved_mutations_keep_gaps','runtime_delivery_not_observed'],
      budgets:{max_steps:maxSteps,max_depth:maxDepth}};
  }
  if(socketOnly){phase='socket';for(const [uid,entry] of socketEntries)analyzeEntry(uid,entry);
    return {version:'0.1.0',entries:analyzed,creations:uniq(socketCreations),channel_bindings:uniq(channelBindings),listener_bindings:uniq(listenerBindings),
      transmissions:uniq(transmissions),diagnostics:uniq(diagnostics),budgets:{max_steps:maxSteps,max_depth:maxDepth},
      limits:['native_WebSocket_alternative_requires_source_branch','class_field_identity_requires_same_runtime_instance',
        'listener_must_remain_active_until_delivery','dynamic_URL_kept_as_source_expression','source_endpoint_is_not_observed_network_connection',
        'nonstandard_socket_alternatives_remain_unknown','unsupported_expressions_and_control_flow_keep_unknown']};
  }
  if(responseRegistries){phase='register';for(const [uid,entry] of promiseEntries)analyzeEntry(uid,entry);
    phase='lookup';for(const [uid,entry] of lookupEntries)analyzeEntry(uid,entry);
    return {version:'0.2.0',entries:analyzed,promises:uniq(promises),registrations:uniq(registrations.map(r=>r.record)),transmissions:uniq(transmissions),counter_updates:uniq(counterUpdates),
      lookups:uniq(lookups),settlements:uniq(settlements),deletions:uniq(deletions),callback_bindings:uniq(callbackBindings),diagnostics:uniq(diagnostics),
      limits:['registry_join_requires_same_runtime_instance_and_equal_key','registration_lifetime_requires_runtime_or_reaching_definition_validation',
        'source_projection_not_observed_fulfillment','callback_and_promise_selection_is_contextual_candidate','network_transport_and_API_boundary_join_pending',
        'unsupported_expressions_and_exception_paths_keep_unknown'],budgets:{max_steps:maxSteps,max_depth:maxDepth}};
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
