"""Add an authored module in a separate clone; exercise discovery and resume."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.repository_discovery import discover, generated_config
from adapters.snapshot_inputs import commit, select_inputs
from adapters.snapshot_refresh import atomic_json
from scripts.build_project_snapshot import build_version
from scripts.discover_repository import run, read

MODULE = 'a1_authored_extension'
FILES = {
    'package.json': '{"name":"authored-discovery-extension","private":true}',
    'tsconfig.json': '{"compilerOptions":{"strict":true},"include":["src"]}',
    'src/client.ts': '''export interface Envelope { value:number; }
declare const wire:{send:(label:string, body:Envelope)=>void};
declare const hooks:Map<string,(body:Envelope)=>void>;
export function dispatch(body:Envelope){wire.send('demo/read',body);}
hooks.set('demo/read',dispatch);
''',
    'server/CMakeLists.txt': 'project(authored_extension)\nadd_library(authored_extension registry.cpp)\n',
    'server/query.h': 'namespace Authored { struct Reader {virtual int read(int value)=0;}; }\n',
    'server/registry.cpp': '''#include <map>
#include <string>
#include <functional>
#include "query.h"
namespace Authored {
std::map<std::string,std::function<int(int)>> routes;
void install(){routes.emplace("demo/read", [](int value){return value;});}
}
'''
}


def trial(source, revision, output, typescript):
    source=Path(source).resolve(); output=Path(output).resolve(); typescript=Path(typescript).resolve()
    if (output.is_relative_to(ROOT) or ROOT.is_relative_to(output) or
        output.is_relative_to(source) or source.is_relative_to(output)):
        raise ValueError('Keep mutation outputs separate from both repositories')
    output.mkdir(parents=True,exist_ok=False); clone=output/'source-copy'
    git=lambda *args:subprocess.check_output(['git','-C',str(clone),*args],stderr=subprocess.PIPE)
    subprocess.run(['git','clone','--shared','--no-checkout',str(source),str(clone)],check=True,capture_output=True)
    git('remote','set-url','--push','origin','disabled://a1-authored-experiment')
    git('config','user.name','A1 authored fixture');git('config','user.email','test@example.invalid')
    git('config','core.autocrlf','false');git('checkout','--detach',commit(source,revision))
    version=build_version(typescript); base=discover(clone)
    if (clone/MODULE).exists():raise ValueError('Authored module path already exists')
    for name,body in FILES.items():
        file=clone/MODULE/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_text(body,encoding='utf-8',newline='\n')
    git('add',MODULE);git('commit','-qm','Add self-authored discovery module')
    added_commit=commit(clone)
    first=run(clone,'HEAD',output/'added',typescript,max_files=3,version=version)
    before={p.name:p.read_bytes() for p in (output/'added/facts').glob('*.json')}
    second=run(clone,'HEAD',output/'added',typescript,resume=True,version=version)
    report=read(output/'added/discovery.json');rows={r['path']:r for r in report['files']}
    getfacts=lambda p:read(output/'added'/rows[MODULE+'/'+p]['facts'])['facts']
    client=getfacts('src/client.ts');server=getfacts('server/registry.cpp');header=getfacts('server/query.h')
    auto_scope=generated_config(report)
    selected=select_inputs(clone,'HEAD',auto_scope)
    expected={MODULE+'/'+p for p in FILES}
    checks={
        'new_files_not_in_base':not expected.intersection(r['path'] for r in base['files']),
        'all_added_files_automatically_selected':expected <= {r['path'] for r in selected['files']},
        'ts_interface_extracted':any(i['name']=='Envelope' for i in client['interfaces']),
        'cpp_interface_extracted':any(i['pure_virtual'] for i in header['interfaces']),
        'ts_registration_candidate_extracted':any(c['callee']=='hooks.set' for c in client['registrations']),
        'cpp_registration_candidate_extracted':any(c['callee']=='routes.emplace' for c in server['registrations']),
        'run_budget_leaves_explicit_pending':first['status']=='partial' and first['statuses'].get('pending_budget',0)>0,
        'resume_completes':second['status']=='complete_with_diagnostics',
        'previous_fact_files_unchanged':all((output/'added/facts'/p).read_bytes()==body for p,body in before.items()),
        'all_files_have_processing_status':all(r['status']!='pending' for r in report['files'])}
    git('mv',MODULE+'/src/client.ts',MODULE+'/src/renamed.ts')
    git('rm',MODULE+'/server/query.h');git('commit','-qm','Rename and delete authored inputs')
    changed_commit=commit(clone)
    changed=select_inputs(clone,'HEAD',auto_scope)
    changed_paths={r['path'] for r in changed['files']}
    checks['rename_found_without_config_change']=MODULE+'/src/renamed.ts' in changed_paths and MODULE+'/src/client.ts' not in changed_paths
    checks['deleted_file_absent']=MODULE+'/server/query.h' not in changed_paths
    result={'evidence_kind':'executed_authored_source_mutation_in_separate_clone',
        'base_source_commit':base['source_commit'],'added_source_commit':added_commit,'changed_source_commit':changed_commit,
        'build_version':version,'checks':checks,'passed':all(checks.values()),
        'base_tracked_files':len(base['files']),'added_summary':second,
        'changed_selected_files':len(changed['files']),'authored_paths':sorted(expected),
        'first_budget_result':first,'resume_attempts':report['attempts'],
        'fixture_origin':'self_authored_generic_module_no_historical_sample',
        'interpretation':'File discovery and local AST candidates only; no cross-language matching claimed',
        'push_remote':'disabled','file_hash_verification':'not_run_per_user_preference'}
    atomic_json(output/'result.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','output','typescript'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--revision',required=True);a=p.parse_args()
    result=trial(a.source,a.revision,a.output,a.typescript)
    print(json.dumps({'passed':result['passed'],'checks':result['checks']}));raise SystemExit(0 if result['passed'] else 1)
