"""Exercise an installed wheel on a new source repository without importing research code."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--python',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    output=a.output.resolve()
    if output.exists():p.error('Choose a new output directory')
    output.mkdir(parents=True);source=output/'source';source.mkdir();workspace=output/'map';checks=[]
    environment=dict(os.environ);environment.pop('PYTHONPATH',None);environment.pop('PYTHONHOME',None)
    def run(args,expected=0):
        result=subprocess.run(list(map(str,args)),cwd=output,env=environment,capture_output=True,encoding='utf-8',timeout=180)
        if result.returncode!=expected:raise RuntimeError(f'Exit {result.returncode}, expected {expected}: '+result.stderr[-3000:])
        return result
    def git(*args):return run(['git','-C',source,*args]).stdout.strip()
    def cli(*args,expected=0):
        started=time.monotonic();result=run([a.python,'-I','-X','utf8','-m','projectmap','--workspace',workspace,*args],expected)
        with (output/'commands.jsonl').open('a',encoding='utf-8') as log:
            log.write(json.dumps({'arguments':list(map(str,args)),'exit':result.returncode,'seconds':round(time.monotonic()-started,4),
                'stdout':result.stdout,'stderr':result.stderr},ensure_ascii=False)+'\n')
        return json.loads(result.stdout if expected==0 else result.stderr)
    def check(name,condition):
        if not condition:raise AssertionError(name)
        checks.append({'name':name,'passed':True})
    git('init','-q');git('config','user.name','Tool smoke');git('config','user.email','test@example.invalid')
    git('config','core.autocrlf','false')
    (source/'ui').mkdir();(source/'backend').mkdir()
    (source/'ui/package.json').write_text('{"name":"smoke-ui"}',encoding='utf-8')
    (source/'ui/api.ts').write_text('export function fetchOne(value: number): number { return value + 1; }\nexport function render(){return fetchOne(2);}\n',encoding='utf-8')
    (source/'backend/main.cpp').write_text('int handleOne(int value){return value+1;}\nint dispatch(){return handleOne(2);}\n',encoding='utf-8')
    git('add','-A');git('commit','-qm','initial');first=git('rev-parse','HEAD')
    location=run([a.python,'-I','-c','import projectmap;print(projectmap.__file__)']).stdout.strip()
    check('installed_package_not_research_checkout',Path(location).is_relative_to(a.python.resolve().parent.parent))
    check('no_history_on_init',cli('init','--source',source)['historical_assets']=={'enabled':False})
    cli('setup');check('doctor_with_real_cpp_parser',cli('doctor','--probe-parser')['ready_for_build'])
    built=cli('build');check('real_build_ready',built['status']=='ready')
    check('repeat_update_reuses_snapshot',cli('update')['status']=='unchanged')
    check('automatic_module_discovery',len(cli('query','overview')['items'])>=2)
    ts=cli('query','search','--text','fetchOne')['items'];cpp=cli('query','search','--text','handleOne')['items']
    check('typescript_extracted',bool(ts));check('cpp_extracted',bool(cpp))
    node=ts[0]['id'];check('snapshot_source_navigation',cli('query','source','--start',node)['source_commit']==first)
    check('reverse_impact_available',cli('query','impact','--start',node)['query']=='walk')
    check('no_source_mutations',not git('status','--porcelain'))
    old_snapshot=built['snapshot']
    path=source/'ui/api.ts';path.write_text(path.read_text(encoding='utf-8').replace('fetchOne','fetchRenamed'),encoding='utf-8')
    git('add','-A');git('commit','-qm','rename');second=git('rev-parse','HEAD')
    check('stale_map_rejected','outdated' in cli('query','overview',expected=2)['error'])
    refreshed=cli('update');check('new_snapshot_published',refreshed['snapshot']!=old_snapshot)
    check('name_change_discovered',bool(cli('query','search','--text','fetchRenamed')['items']))
    check('old_name_removed',not cli('query','search','--text','fetchOne')['items'])
    path.write_text('uncommitted content',encoding='utf-8');status=cli('status')
    check('dirty_worktree_reported_and_excluded',status['worktree_has_changes'] and not status['worktree_included'])
    check('runtime_missing_is_empty',cli('runtime')['items']==[])
    report={'evidence_kind':'executed_installed_wheel','package_location':location,'source_commits':[first,second],
        'snapshot':refreshed['snapshot'],'rules_commit':status['installed_rules_commit'],'build_counts':built['counts'],
        'checks':checks,'historical_assets_enabled':False,'accuracy_experiment':'not_run'}
    (output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':len(checks),'result':str(output/'result.json')}))


if __name__=='__main__':main()
