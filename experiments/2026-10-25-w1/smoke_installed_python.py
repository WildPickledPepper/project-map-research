"""Exercise installed Python extraction, mixed-language navigation and module updates."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('python','typescript','parser-cache','dll-dir','output'):ap.add_argument('--'+name,type=Path,required=True)
    args=ap.parse_args()
    for key,value in vars(args).items():setattr(args,key,value.resolve())
    if args.output.exists():ap.error('Choose a new output directory')
    output=args.output;output.mkdir(parents=True);source=output/'source';source.mkdir();workspace=output/'map';checks=[]
    env=dict(os.environ)
    for name in ('PYTHONPATH','PYTHONHOME','NODE_PATH'):env.pop(name,None)
    def run(command,expected=0):
        result=subprocess.run(list(map(str,command)),cwd=output,env=env,capture_output=True,encoding='utf-8',timeout=180)
        if result.returncode!=expected:raise RuntimeError(f'Exit {result.returncode}, expected {expected}: '+result.stderr[-3000:])
        return result
    def git(*values):return run(['git','-C',source,*values]).stdout.strip()
    def cli(*values,expected=0):
        started=time.monotonic();result=run([args.python,'-I','-X','utf8','-m','projectmap','--workspace',workspace,*values],expected)
        with (output/'commands.jsonl').open('a',encoding='utf-8') as log:
            log.write(json.dumps({'arguments':list(map(str,values)),'exit':result.returncode,'stdout':result.stdout,
                'stderr':result.stderr,'seconds':round(time.monotonic()-started,4)})+'\n')
        return json.loads(result.stdout if expected==0 else result.stderr)
    def check(name,passed):
        if not passed:raise AssertionError(name)
        checks.append({'id':name,'passed':True})
    def save(files):
        for name,body in files.items():
            path=source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(body,encoding='utf-8')
        git('add','-A');git('commit','-qm','fixture change')
    def symbol(name):return cli('query','search','--kind','callable','--text',name)['items']
    def has_path(start,end,direction='out'):
        return cli('query','path','--start',start,'--target',end,'--direction',direction,'--depth','16','--nodes','1000','--edges','3000')['found']
    git('init','-q');git('config','user.name','Installed Python test');git('config','user.email','test@example.invalid');git('config','core.autocrlf','false')
    save({'odd_workspace/main.py':'from pkg import Engine\ndef run_task(): return Engine().fetch()\n',
        'odd_workspace/pkg/__init__.py':'from .logic import Engine\n',
        'odd_workspace/pkg/logic.py':'from .store import read_value\nclass Engine:\n def fetch(self): return read_value()\n',
        'odd_workspace/pkg/store.py':'def read_value(): return 7\n',
        'elsewhere/pkg/__init__.py':'','elsewhere/pkg/store.py':'def read_value(): return -99\n',
        'namespace_case/start.py':'from support.worker import perform\nif __name__ == "__main__": perform()\n',
        'namespace_case/common.py':'def provide(): return 1\n',
        'namespace_case/support/worker.py':'import common\ndef perform(): return common.provide()\n',
        'namespace_case/support/common.py':'def provide(): return -1\n',
        'view/start.ts':"import {paint} from './helper.js';export function render(){return paint();}",
        'view/helper.js':'export function paint(){return 1;}',
        'native/main.cpp':'int query_value(){return 1;}\nint enter(){return query_value();}'})
    first=git('rev-parse','HEAD')
    location=run([args.python,'-I','-c','import projectmap;print(projectmap.__file__)']).stdout.strip()
    check('installed_package_isolated',Path(location).is_relative_to(args.python.parent.parent))
    cli('init','--source',source,'--typescript',args.typescript,'--parser-cache',args.parser_cache,'--dll-dir',args.dll_dir)
    built=cli('build');check('real_default_build_ready',built['status']=='ready')
    start=symbol('run_task')[0];values=symbol('read_value');target=next(n for n in values if n['path']=='odd_workspace/pkg/store.py')
    decoy=next(n for n in values if n['path']=='elsewhere/pkg/store.py')
    check('package_reexport_class_method_and_relative_call',has_path(start['id'],target['id']))
    check('reverse_python_path',has_path(target['id'],start['id'],'in'))
    check('same_name_other_package_not_connected',not has_path(start['id'],decoy['id']))
    check('same_version_python_source',cli('query','source','--start',target['id'])['source_commit']==first)
    check('cpp_symbols_retained',bool(symbol('query_value')))
    check('mixed_ts_js_path_retained',has_path(symbol('render')[0]['id'],symbol('paint')[0]['id']))
    namespace_start=symbol('perform')[0];providers=symbol('provide')
    actual=next(n for n in providers if n['path']=='namespace_case/common.py')
    near_decoy=next(n for n in providers if n['path']=='namespace_case/support/common.py')
    check('namespace_uses_importing_entry_root',has_path(namespace_start['id'],actual['id']))
    check('nearby_namespace_decoy_not_connected',not has_path(namespace_start['id'],near_decoy['id']))
    check('unchanged_snapshot_reused',cli('update')['status']=='unchanged')
    save({'odd_workspace/pkg/extra.py':'def extend(value): return value*2\n',
        'odd_workspace/pkg/store.py':'from .extra import extend\ndef read_value(): return extend(7)\n'})
    check('new_revision_rejects_stale_map','outdated' in cli('query','overview',expected=2)['error'])
    check('new_module_refresh_ready',cli('update')['status']=='ready')
    check('new_module_connected',has_path(symbol('run_task')[0]['id'],symbol('extend')[0]['id']))
    for relative in ('odd_workspace/pkg/extra.py','odd_workspace/pkg/feature.py'):
        if not (source/relative).resolve().is_relative_to(source.resolve()):raise ValueError('Fixture move must stay inside source')
    git('mv','odd_workspace/pkg/extra.py','odd_workspace/pkg/feature.py')
    save({'odd_workspace/pkg/store.py':'from .feature import extend\ndef read_value(): return extend(7)\n'})
    check('renamed_module_refresh_ready',cli('update')['status']=='ready')
    renamed=symbol('extend');check('renamed_module_identity',len(renamed)==1 and renamed[0]['path']=='odd_workspace/pkg/feature.py')
    check('renamed_module_connected',has_path(symbol('run_task')[0]['id'],renamed[0]['id']))
    git('rm','odd_workspace/pkg/feature.py');git('commit','-qm','delete provider and retain consumer')
    check('deleted_provider_refresh_ready',cli('update')['status']=='ready')
    check('deleted_definition_removed',not symbol('extend'))
    missing=cli('query','search','--kind','module_reference','--text','extend')['items']
    detail=cli('query','detail','--entity','node','--id',missing[0]['id']) if missing else {}
    check('missing_import_remains_queryable','module_or_symbol_not_in_export' in json.dumps(detail))
    check('tool_did_not_mutate_source',not git('status','--porcelain'))
    check('runtime_evidence_not_fabricated',cli('runtime')['items']==[])
    check('historical_assets_disabled',cli('status')['historical_assets']=={'enabled':False})
    result={'schema':'installed-python-smoke/1','source_commits':[first,git('rev-parse','HEAD')],
        'installed_rules_commit':cli('status')['installed_rules_commit'],'checks':checks,'passed':all(c['passed'] for c in checks),
        'build_counts':built['counts'],'source_modified_by_tool':False,'historical_assets_enabled':False,
        'execution':'installed CLI in isolated Python mode; production builder and navigation; analyzed source was not executed'}
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks':len(checks),'passed':result['passed']}))


if __name__=='__main__':main()
