/* Source classification shared by discovery and the compiler-backed adapters. */
const path=require('node:path');
const sourceFile=name=>/\.(?:[cm]?[jt]s|[jt]sx)$/i.test(name);
const language=name=>/\.(?:[cm]?js|jsx)$/i.test(name)?'javascript':'typescript';
function scriptKind(ts,name){
  const suffix=path.extname(name).toLowerCase();
  if(suffix==='.jsx')return ts.ScriptKind.JSX;
  if(suffix==='.tsx')return ts.ScriptKind.TSX;
  return language(name)==='javascript'?ts.ScriptKind.JS:ts.ScriptKind.TS;
}
module.exports={sourceFile,language,scriptKind};
