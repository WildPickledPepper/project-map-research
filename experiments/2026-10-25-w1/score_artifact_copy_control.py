"""Independently check real native-to-packaging edges and indexed queries."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.file_copy_contracts import map_member
from projectmap.workspace import Workspace


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--trial',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    if args.output.exists():ap.error('Choose a new evidence path')
    trial=json.loads((args.trial/'trial.json').read_text(encoding='utf-8'))
    graph=json.loads((args.trial/'graph.json').read_text(encoding='utf-8'));nodes={n['id']:n for n in graph['nodes']}
    checks=[]
    def check(name,value):checks.append({'id':name,'passed':bool(value)})
    # Independent product references are used only by this scorer.
    revision='d4e8d1cf9f90208bcbe5371c127088f6fd66c688'
    native_path='server/output/win_mingw64/bin/profiler_server.exe'
    stage='server/output/build/server/profiler_server.exe'
    desktop='platform/preview/resources/profiler/server/profiler_server.exe'
    plugin='plugins/jupyterlab/mindstudio_insight_jupyterlab/resources/profiler/server/profiler_server.exe'
    artifact=next(n for n in nodes.values() if n['kind']=='build_artifact' and n['location']=={'root':'source','path':native_path})
    configuration=nodes[artifact['build_context']];system=configuration['target_system']
    copied=[n for n in nodes.values() if n['kind']=='copied_artifact' and n['origin_artifact']==artifact['id']]
    target=next(nodes[e['source']] for e in graph['edges'] if e['kind']=='PRODUCES_ARTIFACT' and e['target']==artifact['id'])
    entry=next(n for n in nodes.values() if n['kind']=='callable' and n['name']=='main' and n['path']=='server/src/entry/server/bin/main.cpp')
    check('same_pinned_source',trial['source_commit']==graph['source_commit']==revision)
    check('control_scope_union',len(graph['input_paths'])==1455 and trial['build']['counts']['input_files']==1455 and
        sum(p.endswith(('.py','.pyi')) for p in graph['input_paths'])==119)
    check('native_host_and_target_bound',system['status']=='available' and system['name']==system['host_name']=='Windows' and
        system['host_path_style']==system['target_path_style']=='windows')
    check('native_primary_entry_preserved',target['name']=='profiler_server' and any(e['kind']=='EXECUTABLE_ENTRY_CANDIDATE' and
        e['source']==target['id'] and e['target']==entry['id'] for e in graph['edges']))
    check('three_expected_copy_locations',len(copied)==3 and {n['value']['relative_path'] for n in copied}=={stage,desktop,plugin})
    check('stages_retain_origin_context_and_host',all(n['build_context']==configuration['id'] and n['host_system']=={'name':'Windows','path_style':'windows'} and
        n['target_system']==system and n['value']['style']=='windows' for n in copied))
    check('copy_depths_and_source_lines',sorted(len(n['copy_steps']) for n in copied)==[1,2,2] and
        all(nodes[n['copy_steps'][0]['context']]['line']==189 for n in copied) and
        all(nodes[n['copy_steps'][-1]['context']]['line']==344 for n in copied if len(n['copy_steps'])==2))
    flow_edges=[e for e in graph['edges'] if e['kind']=='COPIES_ARTIFACT_TO']
    check('production_relations_emitted',len(flow_edges)==graph['artifact_copy_flow']['copied_artifacts']==24)
    check('conditional_execution_and_materialization',all(e['status']=='conditional_candidate' and e['runtime_execution']=='not_observed' and
        e['mapping']['status']=='conditional_candidate' for e in flow_edges) and
        all(n['materialization']=='not_verified' and n['runtime_execution']=='not_observed' for n in copied))
    check('all_conditions_carried_between_stages',all(any(c['kind']=='native_artifact_successfully_materialized_as_regular_file' for c in n['conditions']) and
        sum(c['kind']=='copy_source_predicates_hold' for c in n['conditions'])==len(n['copy_steps']) and
        sum(c['kind']=='copy_path_conditions_hold' for c in n['conditions'])==len(n['copy_steps']) for n in copied))
    check('runtime_predicates_remain_explicit',all(any(c['kind']=='copy_source_predicates_hold' and c['guards']['residual'] for c in n['conditions']) for n in copied))
    check('no_budget_truncation',not any(d.get('reason') in {'artifact_copy_attempt_budget','artifact_copy_depth_or_candidate_budget'} for d in graph['diagnostics']))
    check('unexpanded_paths_and_moves_remain_required',any(d.get('kind')=='artifact_copy_flow_gap' and d['required'] for d in graph['diagnostics']))
    first=next(n for n in copied if n['value']['relative_path']==stage);step=first['copy_steps'][0]
    context=nodes[step['context']];source=nodes[step['source']];destination=nodes[step['destination']]
    actual={**first['value'],'base':{'kind':'source_root','source':artifact['id']},'segments':native_path.split('/'),'conditions':[]}
    host={'name':system['host_name'],'path_style':system['host_path_style']}
    archive={**actual,'segments':actual['segments'][:-1]+['independent-static.a']}
    wrong={**actual,'segments':['different-root',*actual['segments'][1:]]}
    check('actual_suffix_filter_rejects_archive_negative',map_member(context,source,destination,archive,host_system=host)['status']=='excluded')
    check('actual_full_path_rejects_same_name_other_root',map_member(context,source,destination,wrong,host_system=host)['status']=='not_matched')
    check('directory_guard_computed_in_first_stage',any(p['condition']['kind']=='preceding_control_transfer_not_taken' and
        p['condition']['line']==186 for e in flow_edges if e['target']==first['id'] for p in e['mapping']['guards']['proof']))
    workspace=Workspace(args.trial/'workspace');navigation=[]
    for node in sorted(copied,key=lambda n:n['value']['relative_path']):
        for direction,a,b in [('out',target['id'],node['id']),('in',node['id'],target['id'])]:
            result=workspace.query('path',start=a,target=b,direction=direction,kinds=['PRODUCES_ARTIFACT','COPIES_ARTIFACT_TO'],depth=4,nodes=60,edges=90)
            row={'id':node['value']['relative_path']+':'+direction,'found':result['found'],'stop_reason':result.get('stop_reason'),
                'snapshot_matches':result['snapshot']==graph['snapshot']}
            navigation.append(row);check('navigation_'+row['id'],row['found'] and row['stop_reason'] is None and row['snapshot_matches'])
    proof=workspace.query('source',start=next(n['id'] for n in copied if n['value']['relative_path']==desktop))
    check('copy_source_navigation_same_version',proof['path']=='build/build.py' and proof['requested_line']==344 and proof['source_commit']==revision and not proof['working_tree_read'])
    version=trial['build_version']
    check('index_matches_recorded_rules',workspace.config['active']['build_version']==version==graph['version']['build_version'])
    check('cached_stages_explicit_and_unchanged',all(version[k] for k in ('component_history_unchanged','component_versions_unchanged','input_selection_unchanged')) and
        not trial['native_semantic_stage_executed_again'] and not trial['native_configure_executed_again'] and not trial['native_normalizer_executed_again'])
    check('current_paths_and_flow_executed',trial['path_adapter_executed_again'] and trial['artifact_copy_flow_executed'])
    check('no_worktree_or_reference_input',graph['provenance']['working_tree_included'] is False and graph['provenance']['reference_used_for_extraction'] is False and not trial['original_checkout_modified'])
    check('hash_preference_preserved',trial['file_hash_verification']=='not_run_per_user_preference')
    check('scope_flags_preserved',not any(trial[k] for k in ('default_workspace_rebuild','installed_tool_tested','runtime_execution','whole_G02_accepted','whole_G03_accepted')))
    portable={'schema':'artifact-copy-control-score/1','origin':'executed_production_copy_flow_cached_native_and_language_stages_independent_source_reference',
        'source_commit':revision,'snapshot':graph['snapshot'],'scope':trial['scope'],'build_version':version,'index_counts':trial['build']['counts'],
        'artifact_flow':graph['artifact_copy_flow'],'native_artifact_location':artifact['location'],
        'selected_copy_stages':[{'path':n['value']['relative_path'],'steps':len(n['copy_steps']),'source_line':n['line']} for n in copied],
        'flow_gap_counts':dict(Counter(d['reason'] for d in graph['diagnostics'] if d.get('kind')=='artifact_copy_flow_gap')),
        'navigation':navigation,'checks':checks,'passed':all(c['passed'] for c in checks),
        **{k:trial[k] for k in ('path_adapter_executed_again','artifact_copy_flow_executed','native_semantic_stage_executed_again',
            'native_configure_executed_again','native_normalizer_executed_again','default_workspace_rebuild','installed_tool_tested','runtime_execution',
            'original_checkout_modified','file_hash_verification','whole_G02_accepted','whole_G03_accepted')},
        'production_copy_edges_emitted':True,'process_counterpart_connected':False}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(portable,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks':len(checks),'passed':portable['passed'],'failed':[c['id'] for c in checks if not c['passed']]}))
    if not portable['passed']:raise SystemExit(1)


if __name__=='__main__':main()
