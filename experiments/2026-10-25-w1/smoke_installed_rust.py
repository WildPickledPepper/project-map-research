"""Run installed mixed-language Rust queries and source module lifecycle updates."""
import argparse
import json
import os
from pathlib import Path
import subprocess


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('python','typescript','parser-cache','dll-dir','output'):ap.add_argument('--'+name,type=Path,required=True)
    args=ap.parse_args()
    for key,value in vars(args).items():setattr(args,key,value.resolve())
    if args.output.exists():ap.error('Choose a new output directory')
    output=args.output;output.mkdir(parents=True);source=output/'source';source.mkdir();workspace=output/'map';checks=[]
    env=dict(os.environ)
    for key in ('PYTHONPATH','PYTHONHOME','NODE_PATH'):env.pop(key,None)
    def run(command,expected=0):
        value=subprocess.run(list(map(str,command)),cwd=output,env=env,capture_output=True,encoding='utf-8',timeout=240)
        if value.returncode!=expected:raise RuntimeError(f'Exit {value.returncode}, expected {expected}: '+value.stderr[-3000:])
        return value
    def git(*values):return run(['git','-C',source,*values]).stdout.strip()
    def cli(*values,expected=0):
        value=run([args.python,'-I','-X','utf8','-m','projectmap','--workspace',workspace,*values],expected)
        with (output/'commands.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps({'arguments':list(map(str,values)),'exit':value.returncode,'stdout':value.stdout,'stderr':value.stderr})+'\n')
        return json.loads(value.stdout if expected==0 else value.stderr)
    def check(name,passed):
        if not passed:raise AssertionError(name)
        checks.append({'id':name,'passed':True})
    def save(values):
        for path,body in values.items():
            target=source/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(body,encoding='utf-8')
        git('add','-A');git('commit','-qm','authored fixture revision')
    def find(kind,name):return cli('query','search','--kind',kind,'--text',name)['items']
    def symbol(name,path=None):return next(n for n in find('callable',name) if n['name']==name and (path is None or n['path']==path))
    def path(start,end,direction='out'):
        return cli('query','path','--start',start,'--target',end,'--direction',direction,
            '--kinds','OBSERVES_CALL,STATIC_CALL_TARGET,STATIC_CALL_CANDIDATE','--depth','16','--nodes','1000','--edges','3000')['found']
    git('init','-q');git('config','user.name','Installed Rust fixture');git('config','user.email','test@example.invalid');git('config','core.autocrlf','false')
    save({'Cargo.toml':'[package]\nname="independent_map"\nversion="0.1.0"\nedition="2021"\n[lib]\npath="logic/entry.rs"\n',
        'logic/entry.rs':'#[path="../implementation/engine.rs"]mod engine;#[path="../unused/engine.rs"]mod decoy;pub fn begin(n:u32)->u32{engine::answer(n)}',
        'implementation/engine.rs':'pub fn answer(n:u32)->u32{n+1}\n',
        'unused/engine.rs':'pub fn answer(n:u32)->u32{n+99}',
        'worker/task.py':'def python_entry(): return 1\n',
        'native/service.cpp':'int cpp_entry(){return 1;}',
        'view/start.ts':"import {paint} from './helper.js';export function render(){return paint();}",
        'view/helper.js':'export function paint(){return 1;}'})
    first=git('rev-parse','HEAD')
    location=run([args.python,'-I','-c','import projectmap;print(projectmap.__file__)']).stdout.strip()
    check('installed_package_isolated',Path(location).is_relative_to(args.python.parent.parent))
    cli('init','--source',source,'--typescript',args.typescript,'--parser-cache',args.parser_cache,'--dll-dir',args.dll_dir)
    built=cli('build');check('real_default_mixed_build_ready',built['status']=='ready')
    start=symbol('begin');actual=symbol('answer','implementation/engine.rs');decoy=symbol('answer','unused/engine.rs')
    check('cargo_custom_root_and_path_module_connected',path(start['id'],actual['id']))
    check('reverse_rust_path',path(actual['id'],start['id'],'in'))
    check('same_name_module_not_connected',not path(start['id'],decoy['id']))
    check('same_version_rust_source',cli('query','source','--start',actual['id'])['source_commit']==first)
    check('python_retained',bool(find('callable','python_entry')))
    check('cpp_retained',bool(find('callable','cpp_entry')))
    check('mixed_ts_js_retained',path(symbol('render')['id'],symbol('paint')['id']))
    check('unchanged_snapshot_reused',cli('update')['status']=='unchanged')
    save({'implementation/addon.rs':'pub fn expand(n:u32)->u32{n*2}',
        'implementation/engine.rs':'#[path="addon.rs"]mod addon;pub fn answer(n:u32)->u32{addon::expand(n)}'})
    check('new_revision_rejects_stale_map','outdated' in cli('query','overview',expected=2)['error'])
    check('new_module_refresh_ready',cli('update')['status']=='ready')
    check('new_module_connected',path(symbol('begin')['id'],symbol('expand')['id']))
    before=source/'implementation/addon.rs';after=source/'implementation/feature.rs'
    if not before.resolve().is_relative_to(source) or not after.resolve().is_relative_to(source):raise ValueError('Fixture rename escaped source')
    git('mv','implementation/addon.rs','implementation/feature.rs')
    save({'implementation/engine.rs':'#[path="feature.rs"]mod feature;pub fn answer(n:u32)->u32{feature::expand(n)}'})
    check('renamed_module_refresh_ready',cli('update')['status']=='ready')
    renamed=symbol('expand');check('renamed_module_identity',renamed['path']=='implementation/feature.rs')
    check('renamed_module_connected',path(symbol('begin')['id'],renamed['id']))
    git('rm','implementation/feature.rs');git('commit','-qm','delete provider while retaining consumer')
    check('deleted_provider_refresh_ready',cli('update')['status']=='ready')
    check('deleted_definition_removed',not find('callable','expand'))
    missing=find('call_site','feature::expand')
    detail=cli('query','detail','--entity','node','--id',missing[0]['id']) if missing else {}
    check('unresolved_call_remains_queryable','unresolved' in json.dumps(detail) and 'reason' in json.dumps(detail))
    check('tool_did_not_mutate_source',not git('status','--porcelain'))
    check('runtime_evidence_not_fabricated',cli('runtime')['items']==[])
    check('historical_assets_disabled',cli('status')['historical_assets']=={'enabled':False})
    result={'schema':'installed-rust-smoke/1','source_commits':[first,git('rev-parse','HEAD')],
        'installed_rules_commit':cli('status')['installed_rules_commit'],'checks':checks,'passed':all(c['passed'] for c in checks),
        'build_counts':built['counts'],'source_modified_by_tool':False,'historical_assets_enabled':False,
        'execution':'isolated installed CLI; native Rust tools; analyzed source not executed; Cargo module add/rename/delete'}
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks':len(checks),'passed':result['passed']}))


if __name__=='__main__':main()
