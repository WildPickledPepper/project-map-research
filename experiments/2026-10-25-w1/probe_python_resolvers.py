"""Compare unchanged CGC call records and Jedi inference on independent source fixtures."""
import argparse
import ast
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import tokenize

CASES={
 'relative_alias':({'pkg/__init__.py':'from .impl import run as expose\n',
  'pkg/impl.py':'def run(): return 1\n','client.py':'from pkg import expose\ndef entry(): return expose()\n'},
  'client.py','expose()',{'pkg/impl.py:run'}),
 'instance_inheritance':({'pkg/__init__.py':'','pkg/base.py':'class Base:\n def run(self): return 1\n',
  'pkg/unit.py':'from .base import Base\nclass Child(Base): pass\n',
  'client.py':'from pkg.unit import Child\nobj=Child()\ndef entry(): return obj.run()\n'},
  'client.py','obj.run()',{'pkg/base.py:run'}),
 'same_name_decoy':({'left.py':'def execute(): return 1\n','right.py':'def execute(): return 2\n',
  'client.py':'from left import execute\ndef entry(): return execute()\n'},
  'client.py','execute()',{'left.py:execute'}),
 'branch_union':({'client.py':'def left(): return 1\ndef right(): return 2\ndef entry(flag):\n target=left if flag else right\n return target()\n'},
  'client.py','target()',{'client.py:left','client.py:right'}),
 'same_line':({'client.py':'def hit(): return 1\ndef entry(): return hit()+hit()\n'},
  'client.py','hit()',{'client.py:hit'}),
 'callback_argument':({'worker.py':'def action(): return 1\n',
  'client.py':'from worker import action\ndef register(callback): pass\ndef entry(): register(action)\n'},
  'client.py','action)',{'worker.py:action'}),
 'parameter_shadow':({'client.py':'def execute(): return 1\ndef entry(execute): return execute()\n'},
  'client.py','execute()',set()),
}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ('output','cgc','parser-cache'):ap.add_argument('--'+key,type=Path,required=True)
    ap.add_argument('--dll-dir',type=Path)
    args=ap.parse_args()
    for key,value in vars(args).items():
        if isinstance(value,Path):setattr(args,key,value.resolve())
    if args.output.exists():ap.error('Choose a new output directory')
    args.output.mkdir(parents=True)
    import jedi
    import tree_sitter_language_pack as pack
    pack.configure(pack.PackConfig(cache_dir=str(args.parser_cache)))
    handles=[os.add_dll_directory(str(args.dll_dir))] if os.name=='nt' and args.dll_dir else []
    sys.path.insert(0,str(args.cgc/'src'))
    cache=args.output/'cgc-home';cache.mkdir();Path.home=classmethod(lambda cls:cache)
    os.environ.update(LOG_FILE_PATH=str(args.output/'cgc.log'),ENABLE_APP_LOGS='ERROR',SCIP_INDEXER='false')
    from codegraphcontext.tools.tree_sitter_parser import TreeSitterParser
    native=TreeSitterParser('python');rows=[]
    for name,(sources,caller,needle,expected) in CASES.items():
        root=args.output/name;root.mkdir()
        for path,code in sources.items():
            dest=root/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(code,encoding='utf-8')
        code=sources[caller];offset=code.rfind(needle);line=code[:offset].count('\n')+1
        start=offset-(code.rfind('\n',0,offset)+1);word=needle.split('(')[0].rstrip(')')
        column=start+len(word)
        project=jedi.Project(root,sys_path=[str(root)],smart_sys_path=False,load_unsafe_extensions=False)
        script=jedi.Script(code,path=root/caller,project=project)
        results=script.infer(line,column)
        targets=sorted({d.module_path.relative_to(root).as_posix()+':'+d.name for d in results
                        if d.module_path and d.module_path.is_relative_to(root) and d.type in {'function','class'}})
        data=native.parse(root/caller)
        (root/'cgc-native.json').write_text(json.dumps(data,indent=2,default=str),encoding='utf-8')
        calls=data['function_calls']
        rows.append({'id':name,'expected':sorted(expected),'jedi_targets':targets,'passed':set(targets)==expected,
            'cgc_calls':[{k:v for k,v in c.items() if k in {'name','full_name','line_number','context','args','inferred_obj_type'}} for c in calls],
            'native_call_coordinates_have_column':all('column' in c or 'column_number' in c for c in calls),
            'ast_call_count':sum(isinstance(n,ast.Call) for n in ast.walk(ast.parse(code)))})
    for handle in handles:handle.close()
    result={'schema':'python-resolver-component-probe/1','jedi':jedi.__version__,
        'parso':importlib.metadata.version('parso'),'cgc':'93c9685bff9151f50a3121e9913e5ba2d27c1191',
        'checks':rows,'passed':all(r['passed'] for r in rows),'product_code_executed':False,
        'graph_generated':False,'scope':'independent fixtures; unchanged public Jedi infer and CGC parser APIs'}
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
