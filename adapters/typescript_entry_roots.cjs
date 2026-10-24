/* Discover exported callers of source transport wrappers by compiler identity. */
function roots(ctx,bindingsByCall,platformType){
  const {ts,checker,walk,id,loc,callableOwner}=ctx,reverse=new Map(),reaching=new Set(),calls=[];
  function target(call){let d=checker.getSymbolAtLocation(call.expression);if(d?.flags&ts.SymbolFlags.Alias)d=checker.getAliasedSymbol(d);
    d=d?.valueDeclaration||d?.declarations?.[0];
    if(d&&ts.isVariableDeclaration(d)&&d.initializer&&(ts.isArrowFunction(d.initializer)||ts.isFunctionExpression(d.initializer)))return d.initializer;
    if(d&&ts.isFunctionLike(d)&&d.body)return d;
    d=checker.getResolvedSignature(call)?.declaration;return d?.body?d:null;
  }
  function edge(caller,callee){if(!caller||!callee)return;if(!reverse.has(callee))reverse.set(callee,new Set());reverse.get(callee).add(caller);}
  for(const sf of ctx.dependencyFiles||ctx.sfList)walk(sf,n=>{
    if(!ts.isCallExpression(n)&&!ts.isNewExpression(n))return;
    calls.push(n);const owner=callableOwner(n),callee=target(n);edge(owner,callee);
    if(ts.isPropertyAccessExpression(n.expression)){const e=n.expression;
      if(e.name.text==='send'&&platformType(e.expression,'WebSocket')||e.name.text==='postMessage'&&platformType(e.expression,'Window'))reaching.add(owner);
    }
    if(bindingsByCall.has(id(n,'call_site')))reaching.add(owner);
    const symbol=checker.getSymbolAtLocation(n.expression),d=symbol?.valueDeclaration||symbol?.declarations?.[0];
    if(ts.isNewExpression(n)&&n.expression.getText()==='Promise'&&d&&loc(d).path.startsWith('<typescript-lib>/'))
      for(const a of n.arguments||[])if(ts.isArrowFunction(a)||ts.isFunctionExpression(a))edge(owner,a);
    if(ts.isCallExpression(n)&&ts.isPropertyAccessExpression(n.expression)&&n.expression.name.text==='forEach'&&
        checker.isArrayType(checker.getTypeAtLocation(n.expression.expression)))for(const a of n.arguments)if(ts.isArrowFunction(a)||ts.isFunctionExpression(a))edge(owner,a);
  });
  const todo=[...reaching];while(todo.length){const callee=todo.pop();for(const caller of reverse.get(callee)||[])if(!reaching.has(caller)){reaching.add(caller);todo.push(caller);}}
  function exported(n){if(n.modifiers?.some(m=>m.kind===ts.SyntaxKind.ExportKeyword))return true;
    for(let p=n.parent;p&&!ts.isSourceFile(p);p=p.parent){if(ts.isFunctionLike(p))return false;
      if(ts.isVariableStatement(p))return p.modifiers?.some(m=>m.kind===ts.SyntaxKind.ExportKeyword)||false;}return false;}
  const owned=new Set(ctx.sfList.map(sf=>loc(sf).path));
  return [...reaching].filter(n=>n&&owned.has(loc(n).path)&&exported(n)).map(owner=>({owner,call:calls.find(c=>callableOwner(c)===owner&&reaching.has(target(c)))})).filter(r=>r.call);
}
module.exports={roots};
