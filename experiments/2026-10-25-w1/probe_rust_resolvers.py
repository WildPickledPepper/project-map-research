"""Compare unmodified CGC Rust records and rust-analyzer on independent fixtures.

Fixture build contexts are explicit experiment inputs, not product discovery rules.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import unquote,urlparse
from urllib.request import url2pathname

from rust_lsp_probe import Client

CASES={
 'alias_reexport':({'src/lib.rs':'mod left; mod right; mod api {pub use crate::left::run as invoke;} pub fn entry(){api::invoke();}',
  'src/left.rs':'pub fn run(){}','src/right.rs':'pub fn run(){}'},'src/lib.rs','invoke();',[],{'src/left.rs:run'}),
 'super_inline':({'src/lib.rs':'fn run(){} mod nested {pub fn entry(){super::run();}}'},'src/lib.rs','run();',[],{'src/lib.rs:run'}),
 'impl_receiver':({'src/lib.rs':'struct A; struct B; impl A {fn run(&self){}} impl B {fn run(&self){}} fn entry(){let a=A;a.run();}'},
  'src/lib.rs','run();',[],{'src/lib.rs:run@1:32'}),
 'trait_object':({'src/lib.rs':'trait Work {fn run(&self);} struct A; struct B; impl Work for A {fn run(&self){}} impl Work for B {fn run(&self){}} fn entry(w:&dyn Work){w.run();}'},
  'src/lib.rs','run();',[],{'src/lib.rs:run@1:16'}),
 'closure_binding':({'src/lib.rs':'fn action(){} fn entry(){let callback=||action();callback();}'},
  'src/lib.rs','callback();',[],{'src/lib.rs:callback'}),
 'glob_import':({'src/lib.rs':'mod actions {pub fn run(){}} use actions::*; fn entry(){run();}'},
  'src/lib.rs','run();',[],{'src/lib.rs:run'}),
 'cfg_windows':({'src/lib.rs':'#[cfg(windows)] #[path="win.rs"] mod selected; #[cfg(unix)] #[path="unix.rs"] mod selected; fn entry(){selected::run();}',
  'src/win.rs':'pub fn run(){}','src/unix.rs':'pub fn run(){}'},'src/lib.rs','run();',['windows'],{'src/win.rs:run'}),
 'cfg_unix':({'src/lib.rs':'#[cfg(windows)] #[path="win.rs"] mod selected; #[cfg(unix)] #[path="unix.rs"] mod selected; fn entry(){selected::run();}',
  'src/win.rs':'pub fn run(){}','src/unix.rs':'pub fn run(){}'},'src/lib.rs','run();',['unix'],{'src/unix.rs:run'}),
 'shadowed_function':({'src/lib.rs':'fn action(){} fn entry(action:fn()){action();}'},
  'src/lib.rs','action();',[],{'src/lib.rs:action@1:24'}),
 'macro_expansion':({'src/lib.rs':'macro_rules! make {()=>{fn generated(){}}} make!(); fn entry(){generated();}'},
  'src/lib.rs','generated();',[],{'src/lib.rs:generated','src/lib.rs:make!'}),
 'path_override':({'src/lib.rs':'#[path="adapter/core.rs"] mod worker; fn entry(){worker::run();}',
  'src/adapter/core.rs':'pub fn run(){}'},'src/lib.rs','run();',[],{'src/adapter/core.rs:run'}),
 'unicode_position':({'src/lib.rs':'fn run(){} fn entry(){let _label="\U0001f9ed";run();}'},
  'src/lib.rs','run();',[],{'src/lib.rs:run'}),
}


def project(root,cfg):
    return {'crates':[{'display_name':'independent_probe','root_module':str(root/'src/lib.rs'),
        'edition':'2021','deps':[],'cfg':cfg,'is_workspace_member':True,
        'source':{'include_dirs':[str(root)],'exclude_dirs':[]}}]}


def position(code,needle):
    offset=code.rfind(needle)
    if offset<0:raise ValueError('Missing probe token')
    line=code[:offset].count('\n');prefix=code[code.rfind('\n',0,offset)+1:offset]
    return {'line':line,'character':len(prefix.encode('utf-16-le'))//2+1}


def locations(values,root):
    if not values:return []
    if isinstance(values,dict):values=[values]
    result=[]
    for value in values:
        uri=value.get('targetUri',value.get('uri'))
        path=Path(url2pathname(unquote(urlparse(uri).path))).resolve()
        if not path.is_relative_to(root):
            result.append({'external':True});continue
        relative=path.relative_to(root).as_posix()
        selection=value.get('targetSelectionRange',value.get('range'))
        code=path.read_text(encoding='utf-8').splitlines()[selection['start']['line']]
        start=selection['start']['character'];end=selection['end']['character']
        name=code.encode('utf-16-le')[2*start:2*end].decode('utf-16-le')
        result.append({'path':relative,'name':name,'line':selection['start']['line']+1,'column':start+1})
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ('output','cgc','parser-cache','rust-analyzer'):ap.add_argument('--'+key,type=Path,required=True)
    ap.add_argument('--dll-dir',type=Path);args=ap.parse_args()
    for key,value in vars(args).items():
        if isinstance(value,Path):setattr(args,key,value.resolve())
    if args.output.exists():ap.error('Choose a new output directory')
    revision=subprocess.check_output(['git','-C',str(args.cgc),'rev-parse','HEAD'],text=True).strip()
    if revision!='93c9685bff9151f50a3121e9913e5ba2d27c1191':raise ValueError('Use the pinned upstream CGC revision')
    args.output.mkdir(parents=True)
    import tree_sitter_language_pack as pack
    pack.configure(pack.PackConfig(cache_dir=str(args.parser_cache)))
    handles=[os.add_dll_directory(str(args.dll_dir))] if os.name=='nt' and args.dll_dir else []
    sys.path.insert(0,str(args.cgc/'src'))
    home=args.output/'cgc-home';home.mkdir();Path.home=classmethod(lambda cls:home)
    os.environ.update(LOG_FILE_PATH=str(args.output/'cgc.log'),ENABLE_APP_LOGS='ERROR',SCIP_INDEXER='false')
    from codegraphcontext.tools.tree_sitter_parser import TreeSitterParser
    native=TreeSitterParser('rust');rows=[]
    for name,(sources,caller,needle,cfg,expected) in CASES.items():
        root=args.output/name;root.mkdir()
        for path,code in sources.items():
            target=root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(code,encoding='utf-8')
        context=project(root,cfg);(root/'rust-project.json').write_text(json.dumps(context),encoding='utf-8')
        raw=native.parse(root/caller)
        (root/'cgc-native.json').write_text(json.dumps(raw,indent=2,default=str),encoding='utf-8')
        with Client(args.rust_analyzer,root,context,root/'server.log') as client:
            pos=position(sources[caller],needle)
            result=client.at('textDocument/definition',caller,pos)
            (root/'definition.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            target=locations(result,root)
            implementation=locations(client.at('textDocument/implementation',caller,pos),root) if name=='trait_object' else []
            status=[e['params'] for e in client.events if e.get('method')=='experimental/serverStatus']
        observed={f"{t['path']}:{t['name']}"+(f"@{t['line']}:{t['column']}" if any('@' in e for e in expected) else '') for t in target if 'path' in t}
        implementation_ok=name!='trait_object' or {(t['name'],t['column']) for t in implementation}=={('run',69),('run',103)}
        row={'id':name,'cfg':cfg,'expected':sorted(expected),'definitions':target,'implementations':implementation,
            'passed':observed==expected and implementation_ok,'server_health':status[-1]['health'] if status else 'not_reported',
            'cgc_function_count':len(raw.get('functions',[])),
            'cgc_calls':[{k:v for k,v in c.items() if k in {'name','full_name','line_number','context','args','inferred_obj_type'}} for c in raw.get('function_calls',[])],
            'native_call_coordinates_have_column':all('column' in c or 'column_number' in c for c in raw.get('function_calls',[]))}
        rows.append(row);print(json.dumps(row),flush=True)
    for handle in handles:handle.close()
    result={'schema':'rust-resolver-component-probe/1','cgc':revision,
        'rust_analyzer':subprocess.check_output([str(args.rust_analyzer),'--version'],text=True).strip(),
        'checks':rows,'passed':all(r['passed'] for r in rows),'product_code_executed':False,
        'graph_generated':False,'cargo_invoked':False,'build_scripts_enabled':False,'proc_macros_enabled':False,
        'scope':'explicit independent rust-project contexts; unchanged CGC parser and rust-analyzer definition APIs'}
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks':len(rows),'passed':result['passed'],'failed':[r['id'] for r in rows if not r['passed']]}))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
