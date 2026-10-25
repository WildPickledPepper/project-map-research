"""Use only an installed CLI to verify mixed calls and module lifecycle on a new repository."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('python','typescript','parser-cache','dll-dir','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    for key,value in vars(args).items():
        if isinstance(value,Path):setattr(args,key,value.resolve())
    output=args.output
    if output.exists():parser.error('Choose a new output directory')
    output.mkdir(parents=True);source=output/'source';source.mkdir();workspace=output/'map';checks=[]
    environment=dict(os.environ)
    for name in ('PYTHONPATH','PYTHONHOME','NODE_PATH'):environment.pop(name,None)
    def run(command,expected=0):
        result=subprocess.run(list(map(str,command)),cwd=output,env=environment,capture_output=True,encoding='utf-8',timeout=180)
        if result.returncode!=expected:raise RuntimeError(f'Exit {result.returncode}, expected {expected}: '+result.stderr[-3000:])
        return result
    def git(*values):return run(['git','-C',source,*values]).stdout.strip()
    def cli(*values,expected=0):
        started=time.monotonic();result=run([args.python,'-I','-X','utf8','-m','projectmap','--workspace',workspace,*values],expected)
        with (output/'commands.jsonl').open('a',encoding='utf-8') as log:
            log.write(json.dumps({'arguments':list(map(str,values)),'exit':result.returncode,
                'seconds':round(time.monotonic()-started,4),'stdout':result.stdout,'stderr':result.stderr})+'\n')
        return json.loads(result.stdout if expected==0 else result.stderr)
    def check(name,condition):
        if not condition:raise AssertionError(name)
        checks.append({'id':name,'passed':True})
    def save(files):
        for name,body in files.items():
            path=source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(body,encoding='utf-8')
        git('add','-A');git('commit','-qm','independent fixture change')
    def symbol(name):return cli('query','search','--kind','callable','--text',name)['items']
    def has_path(start,end):return cli('query','path','--start',start,'--target',end,'--depth','16','--nodes','500','--edges','1500')['found']
    git('init','-q');git('config','user.name','Mixed tool test');git('config','user.email','test@example.invalid');git('config','core.autocrlf','false')
    save({'view/package.json':'{"name":"independent-ui"}',
        'view/entry.ts':"import {calculate} from '@standalone/library';export function renderValue(){return calculate(3);}",
        'odd_structure/unit/package.json':'{"name":"@standalone/library","exports":{".":"./index.js"}}',
        'odd_structure/unit/index.js':"import {value} from './helper.cjs';export function calculate(n){return n+value();}",
        'odd_structure/unit/helper.cjs':'exports.value=function provideValue(){return 7;};',
        'separate/package.json':'{"name":"unrelated"}','separate/index.js':'export function calculate(n){return 100;}',
        'native/entry.cpp':'int handleValue(int value){return value+1;}\nint dispatch(){return handleValue(2);}'})
    initial=git('rev-parse','HEAD')
    location=run([args.python,'-I','-c','import projectmap;print(projectmap.__file__)']).stdout.strip()
    check('installed_package_isolated',Path(location).is_relative_to(args.python.resolve().parent.parent))
    cli('init','--source',source,'--typescript',args.typescript,'--parser-cache',args.parser_cache,'--dll-dir',args.dll_dir)
    built=cli('build');check('real_default_build_ready',built['status']=='ready')
    starts=symbol('renderValue');targets=symbol('provideValue');check('js_and_cjs_definitions_present',bool(starts and targets))
    check('typescript_to_js_to_cjs_path',has_path(starts[0]['id'],targets[0]['id']))
    reverse=cli('query','path','--start',targets[0]['id'],'--target',starts[0]['id'],'--direction','in','--depth','16','--nodes','500','--edges','1500')
    check('reverse_mixed_path',reverse['found'])
    decoy=[r for r in symbol('calculate') if r['path']=='separate/index.js'];check('decoy_present',bool(decoy))
    check('same_name_decoy_not_connected',not has_path(starts[0]['id'],decoy[0]['id']))
    check('javascript_source_version',cli('query','source','--start',targets[0]['id'])['source_commit']==initial)
    check('cpp_regression_present',bool(symbol('handleValue')))
    check('unchanged_snapshot_reused',cli('update')['status']=='unchanged')
    save({'new_unit/more.js':'export function extend(n){return n*2;}',
        'odd_structure/unit/index.js':"import {value} from './helper.cjs';import {extend} from '../../new_unit/more.js';export function calculate(n){return extend(n)+value();}"})
    check('new_commit_stale_rejected','outdated' in cli('query','overview',expected=2)['error'])
    check('added_module_refresh_ready',cli('update')['status']=='ready')
    check('added_module_connected',has_path(symbol('renderValue')[0]['id'],symbol('extend')[0]['id']))
    for relative in ('new_unit','renamed_box'):
        target=(source/relative).resolve()
        if target==source.resolve() or not target.is_relative_to(source.resolve()):
            raise ValueError('Module move must stay inside the new fixture source')
    git('mv','new_unit','renamed_box')
    path=source/'odd_structure/unit/index.js';path.write_text(path.read_text(encoding='utf-8').replace('../../new_unit/','../../renamed_box/'),encoding='utf-8')
    git('add','-A');git('commit','-qm','rename module')
    check('renamed_module_refresh_ready',cli('update')['status']=='ready')
    renamed=symbol('extend');check('renamed_module_identity',renamed and all(r['path']=='renamed_box/more.js' for r in renamed))
    check('renamed_module_connected',has_path(symbol('renderValue')[0]['id'],renamed[0]['id']))
    git('rm','renamed_box/more.js');git('commit','-qm','delete provider and retain consumer')
    check('deleted_provider_refresh_ready',cli('update')['status']=='ready')
    check('deleted_definition_removed',not symbol('extend'))
    diagnostics=cli('query','diagnostics','--path','odd_structure/unit/index.js')
    check('retained_consumer_reports_missing_module','module_outside_input' in json.dumps(diagnostics))
    check('tool_did_not_mutate_source',not git('status','--porcelain'))
    check('no_runtime_inherited',cli('runtime')['items']==[])
    check('no_historical_assets',cli('status')['historical_assets']=={'enabled':False})
    result={'schema':'installed-javascript-smoke/1','source_commits':[initial,git('rev-parse','HEAD')],
        'installed_rules_commit':cli('status')['installed_rules_commit'],'checks':checks,'passed':all(c['passed'] for c in checks),
        'build_counts':built['counts'],'source_modified_by_tool':False,'historical_assets_enabled':False,
        'execution':'installed CLI in isolated Python mode; production builder and navigation; synthetic source executed only by static analysis'}
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks':len(checks),'passed':result['passed']}))


if __name__=='__main__':main()
