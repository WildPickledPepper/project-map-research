"""Cross-file/service/update controls in an independent, authored Git project."""
import argparse
from copy import deepcopy
from functools import partial
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from adapters.snapshot_inputs import commit, validate_path
from adapters.snapshot_refresh import Refresher, atomic_json, read_snapshot
from adapters.data_graph import RESOURCE_IMPACT_KINDS
from adapters.fact_queries import find_path
from scripts.build_project_snapshot import build, build_version
from tests.test_cpp_protocol import SOURCE

CLIENT='''import {helper} from './util';
declare const channel:WebSocket; declare const b:{invoke:(x:string)=>void};
function make(){return (label:string)=>channel.send(JSON.stringify({wireTag:label,space:'north'}));}
b.invoke=make(); export function entry(){helper();b.invoke('alpha/read');}
'''
RESOURCE='''namespace shared {
struct Cache {std::map<int,int> data;
void put(){data[1]=7;} int get(){return data.at(1);} int other(){return data.at(2);}};
struct Separate {std::map<int,int> data;int get(){return data.at(1);}};
}'''


def run(output,typescript):
    output=Path(output).resolve();typescript=Path(typescript).resolve()
    if output.is_relative_to(ROOT) or ROOT.is_relative_to(output):raise ValueError('Keep outputs external')
    output.mkdir(parents=True,exist_ok=False);repo=output/'source';repo.mkdir()
    git=lambda *args:subprocess.check_output(['git','-C',str(repo),*args],stderr=subprocess.PIPE)
    git('init','-q');git('config','user.name','A2 authored controls');git('config','user.email','test@example.invalid');git('config','core.autocrlf','false')
    files={f'{side}/package.json':json.dumps({'name':'authored-'+side}) for side in ('front-one','front-two')}
    files.update({f'{side}/api.ts':CLIENT for side in ('front-one','front-two')})
    files.update({f'{side}/util.ts':'export function helper(){return 1;}' for side in ('front-one','front-two')})
    files.update({'back-one/protocol.cpp':'namespace one {\n'+SOURCE+'\n}',
                  'back-two/protocol.cpp':'namespace two {\n'+SOURCE+'\n}',
                  'back-one/resources.cpp':RESOURCE})
    config={'version':1,'scope':{'discovery':{}},'storage':'json','deployment':{'services':[
        {'id':'one','consumer_paths':['front-one'],'provider_paths':['back-one']},
        {'id':'two','consumer_paths':['front-two'],'provider_paths':['back-two']}]}}
    version=build_version(typescript);cases={};checks={}

    def save(contents):
        tracked=git('ls-files','-z').decode().strip('\0').split('\0')
        for name in tracked:
            if name and name not in contents:git('rm','--',validate_path(name))
        for name,body in contents.items():
            file=repo/validate_path(name);file.parent.mkdir(parents=True,exist_ok=True);file.write_text(body,encoding='utf-8',newline='\n')
        git('add','-A');git('commit','-qm','Authored control step')

    def case(name,contents,configuration=None):
        save(contents)
        chosen=configuration or config
        runner=Refresher(repo,output/'store',lambda:chosen,lambda:version,partial(build,typescript=typescript))
        state=runner.run()
        if state['status']!='up_to_date':raise ValueError('Control build did not publish: '+name)
        loc=read_snapshot(output/'store');graph=json.loads((Path(loc['directory'])/'graph.json').read_text(encoding='utf-8'))
        nodes={n['id']:n for n in graph['nodes']};providers={p['id']:p for p in graph['protocol']['providers']}
        consumers={}
        for result in graph['protocol']['results']:
            path=nodes.get(result.get('message'),{}).get('path') or nodes.get(result['consumer'].removeprefix('protocol:'),{}).get('path','')
            if not path:continue
            consumers[path]={'status':result['status'],'name':result['name'],
                'matches':[{'command':providers[m['provider']]['command'],'provider_path':providers[m['provider']]['path'],
                            'scope_values':providers[m['provider']]['scope_values'],'gaps':m['gaps']} for m in result['matches']]}
        cases[name]={'source_commit':graph['source_commit'],'snapshot':graph['snapshot'],
            'inputs':graph['input_paths'],'consumers':consumers,'nodes':len(nodes),'edges':len(graph['edges'])}
        return graph,consumers

    def matched(row,server):return row['status']=='matched_conditional' and len(row['matches'])==1 and row['matches'][0]['provider_path'].startswith(server+'/')
    graph,base=case('baseline',files)
    checks['same_command_and_scope_isolated_by_service']=matched(base['front-one/api.ts'],'back-one') and matched(base['front-two/api.ts'],'back-two')
    nodes={n['id']:n for n in graph['nodes']}
    checks['typescript_import_call_has_source_target']=any(e['kind']=='STATIC_CALL_TARGET' and nodes[e['source']]['path']=='front-one/api.ts' and nodes[e['target']]['path']=='front-one/util.ts' for e in graph['edges'])
    def symbol(name):return next(n['id'] for n in graph['nodes'] if n['kind']=='callable' and n['name']==name and n['definition'])
    checks['shared_resource_connects_read_write']=find_path(graph,symbol('shared::Cache::put'),symbol('shared::Cache::get'),RESOURCE_IMPACT_KINDS)['found']
    checks['different_constant_key_not_connected']=not find_path(graph,symbol('shared::Cache::put'),symbol('shared::Cache::other'),RESOURCE_IMPACT_KINDS)['found']
    checks['same_member_name_other_owner_not_connected']=not find_path(graph,symbol('shared::Cache::put'),symbol('shared::Separate::get'),RESOURCE_IMPACT_KINDS)['found']

    changed=deepcopy(files);changed['back-one/protocol.cpp']=changed['back-one/protocol.cpp'].replace('alpha/read','omega/go')
    _,rows=case('provider_command_changed',changed)
    checks['provider_edit_invalidates_unchanged_consumer']=not rows['front-one/api.ts']['matches'] and matched(rows['front-two/api.ts'],'back-two')
    deleted=deepcopy(files);deleted['back-one/protocol.cpp']=deleted['back-one/protocol.cpp'].replace('entries.emplace(ACTION,std::make_unique<SpecificWork>());','')
    _,rows=case('registration_deleted',deleted)
    checks['deleted_registration_removes_match']=not rows['front-one/api.ts']['matches'] and matched(rows['front-two/api.ts'],'back-two')
    dynamic=deepcopy(files);dynamic['back-one/protocol.cpp']=dynamic['back-one/protocol.cpp'].replace('ACTION="alpha/read"','ACTION=runtime()')
    _,rows=case('dynamic_provider_command',dynamic)
    checks['dynamic_command_not_promoted_to_unique_match']=not rows['front-one/api.ts']['matches']
    duplicate=deepcopy(files);needle='entries.emplace(ACTION,std::make_unique<SpecificWork>());'
    duplicate['back-one/protocol.cpp']=duplicate['back-one/protocol.cpp'].replace(needle,needle+needle)
    _,rows=case('duplicate_registration',duplicate)
    checks['duplicate_provider_preserves_ambiguity']=rows['front-one/api.ts']['status']=='ambiguous' and len(rows['front-one/api.ts']['matches'])==2
    scoped=deepcopy(files);scoped['front-one/api.ts']=scoped['front-one/api.ts'].replace("space:'north'","space:'elsewhere'")
    _,rows=case('different_module',scoped)
    checks['different_module_not_matched']=not rows['front-one/api.ts']['matches'] and matched(rows['front-two/api.ts'],'back-two')
    renamed=deepcopy(files)
    for path in ('back-one/protocol.cpp','front-one/api.ts'):
        for before,after in {'ACTION':'CODE','SpecificWork':'Job','execute':'run','wireTag':'operation','space':'tenant','entry':'launch','make':'assemble'}.items():
            renamed[path]=re.sub(r'\b'+before+r'\b',after,renamed[path])
        renamed[path]=renamed[path].replace('alpha/read','renamed/read')
    _,rows=case('names_and_wire_fields_renamed',renamed)
    checks['renamed_symbols_fields_command_reconnect']=matched(rows['front-one/api.ts'],'back-one') and rows['front-one/api.ts']['name']=='launch' and rows['front-one/api.ts']['matches'][0]['command']=='renamed/read'
    moved=deepcopy(files);moved['back-one/renamed.cpp']=moved.pop('back-one/protocol.cpp')
    changed_graph,rows=case('provider_file_renamed',moved)
    checks['file_rename_replans_and_removes_old_nodes']=matched(rows['front-one/api.ts'],'back-one') and not any(n['path']=='back-one/protocol.cpp' for n in changed_graph['nodes'])
    removed=deepcopy(files);removed.pop('back-one/protocol.cpp')
    changed_graph,rows=case('provider_file_deleted',removed)
    checks['file_delete_removes_provider_and_edges']=not rows['front-one/api.ts']['matches'] and not any(n['path']=='back-one/protocol.cpp' for n in changed_graph['nodes'])
    unbound=deepcopy(config);unbound['deployment']={'services':[]}
    _,rows=case('missing_service_binding',files,unbound)
    checks['unknown_service_keeps_both_candidates']=rows['front-one/api.ts']['status']=='ambiguous' and len(rows['front-one/api.ts']['matches'])==2 and all('service_scope_unknown_or_ambiguous' in p['gaps'] for p in rows['front-one/api.ts']['matches'])
    result={'evidence_kind':'executed_authored_cross_language_source_mutation_controls','fixture_origin':'authored_no_historical_sample',
        'build_version':version,'checks':checks,'passed':all(checks.values()),'cases':cases,
        'confidence':'source relations and conditional candidates; no runtime execution claim',
        'file_hash_verification':'not_run_per_user_preference'}
    atomic_json(output/'result.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--typescript',type=Path,required=True)
    a=p.parse_args();r=run(a.output,a.typescript)
    print(json.dumps({'passed':r['passed'],'checks':r['checks']}));raise SystemExit(0 if r['passed'] else 1)
