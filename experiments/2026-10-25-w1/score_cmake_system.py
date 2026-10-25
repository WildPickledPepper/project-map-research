"""Score current native-system replay independently of cached C++ extraction."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from projectmap.workspace import Workspace


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--trial',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    if args.output.exists():ap.error('Choose a new evidence output path')
    trial=json.loads((args.trial/'trial.json').read_text(encoding='utf-8'))
    graph=json.loads((args.trial/'graph.json').read_text(encoding='utf-8'));nodes={n['id']:n for n in graph['nodes']}
    checks=[]
    def check(name,value):checks.append({'id':name,'passed':bool(value)})
    # Product target, artifact and entry references remain confined to scoring.
    reference={'commit':'d4e8d1cf9f90208bcbe5371c127088f6fd66c688','artifact':'server/output/win_mingw64/bin/profiler_server.exe',
        'target':'profiler_server','entry':'server/src/entry/server/bin/main.cpp'}
    configuration=next(n for n in nodes.values() if n['kind']=='build_configuration');system=configuration['target_system']
    target=next(n for n in nodes.values() if n['kind']=='build_target' and n['name']==reference['target'])
    artifact=next(n for n in nodes.values() if n['kind']=='build_artifact' and n['location']=={'root':'source','path':reference['artifact']})
    entry=next(n for n in nodes.values() if n['kind']=='callable' and n['name']=='main' and n['path']==reference['entry'])
    record=trial['native_records'][0];reused=trial['build_version']['reused_cpp_facts']
    check('pinned_source',trial['source_commit']==graph['source_commit']==reference['commit'])
    check('control_input_scope_unchanged',len(graph['input_paths'])==1336 and trial['build']['counts']['input_files']==1336)
    check('single_native_context_replayed',len(trial['native_records'])==1 and record['context']['status']=='configured' and configuration['configuration']=='Release')
    check('native_generator_version',configuration['cmake_version']=='3.31.6' and configuration['generator']['name']=='Ninja')
    check('native_target_system_windows',system['status']=='available' and system['name']=='Windows' and system['target_path_style']=='windows')
    check('native_host_filesystem_windows',system['host_name']=='Windows' and system['host_path_style']=='windows' and system['cross_compiling'] is False)
    check('processor_record_not_compiler_architecture_claim',system['declared_processor']=='AMD64' and system['processor_interpretation']=='cmake_system_processor_not_verified_compiler_architecture')
    check('generated_system_source_bound',system['basis']=='cmake_generated_system_literals' and system['file']=='CMakeFiles/3.31.6/CMakeSystem.cmake')
    check('system_metadata_identical_across_views',system==record['context']['target_system']==graph['native_build']['contexts'][0]['target_system'])
    check('published_roots_explicitly_relocated',record['context']['relocation']=={
        'build_root_relocated':True,'source_root_relocated':True,'basis':'caller_recorded_configure_roots_native_reply_checked'})
    check('native_artifact_keeps_build_context',artifact['build_context']==target['build_context']==configuration['id'])
    check('native_source_membership_and_entry_recomputed',record['nodes']==599 and record['edges']==601 and record['source_joins']==4906 and
          any(e['source']==target['id'] and e['target']==entry['id'] and e['kind']=='EXECUTABLE_ENTRY_CANDIDATE' for e in graph['edges']))
    check('no_platform_metadata_gap',not any(d.get('kind') in {'cmake_target_system_unavailable','cmake_target_path_style_unavailable','cmake_host_path_style_unavailable'} for d in graph['diagnostics']))
    check('cached_cpp_components_and_inputs_unchanged',reused['component_history_unchanged'] and reused['component_versions_unchanged'] and reused['input_selection_unchanged'] and
          reused['counts']=={'nodes':217241,'edges':337586})
    check('replay_execution_scope_explicit',trial['native_normalizer_executed_again'] and not trial['native_configure_executed_again'] and
          not trial['cpp_extraction_executed_again'] and not trial['default_workspace_rebuild'])
    workspace=Workspace(args.trial/'workspace');navigation=[]
    for label,start,goal,kinds in [('configuration_artifact',configuration['id'],artifact['id'],['CONFIGURES_BUILD_TARGET','PRODUCES_ARTIFACT']),
                                  ('target_entry',target['id'],entry['id'],['EXECUTABLE_ENTRY_CANDIDATE'])]:
        for direction,a,b in [('out',start,goal),('in',goal,start)]:
            result=workspace.query('path',start=a,target=b,direction=direction,kinds=kinds,depth=3)
            row={'id':label+'_'+direction,'found':result['found'],'stop_reason':result.get('stop_reason'),'snapshot_matches':result['snapshot']==graph['snapshot']}
            navigation.append(row);check('navigation_'+row['id'],row['found'] and row['stop_reason'] is None and row['snapshot_matches'])
    source=workspace.query('source',start=entry['id'],context=1)
    check('same_source_commit_navigation',source['source_commit']==reference['commit'] and source['path']==reference['entry'] and not source['working_tree_read'])
    check('same_index_rule_version',workspace.config['active']['snapshot']==graph['snapshot'] and workspace.config['active']['build_version']==trial['build_version']==graph['version']['build_version'])
    check('unchanged_original_no_file_hash_verification',not trial['original_checkout_modified'] and trial['file_hash_verification']=='not_run_per_user_preference')
    check('no_runtime_or_full_acceptance_claim',not trial['runtime_execution'] and not trial['whole_G03_accepted'] and graph['provenance']['reference_used_for_extraction'] is False)
    portable={'schema':'cmake-system-replay-score/1','origin':'executed_current_native_normalizer_cached_unchanged_cpp_facts_separate_source_reference',
        'source_commit':graph['source_commit'],'snapshot':graph['snapshot'],'scope':trial['scope'],'build_version':trial['build_version'],
        'index_counts':trial['build']['counts'],'native_node_counts':dict(Counter(n['kind'] for n in nodes.values() if n.get('language')=='cmake')),
        'target_system':system,'native_configuration':{k:configuration[k] for k in ('id','configuration','cmake_version','generator')},
        'native_relocation':record['context']['relocation'],'native_replay_seconds':record['replay_seconds'],
        'artifact_location':artifact['location'],'entry_path':entry['path'],'navigation':navigation,'checks':checks,'passed':all(c['passed'] for c in checks),
        'native_configure_executed_again':False,'cpp_extraction_executed_again':False,'native_normalizer_executed_again':True,
        'default_workspace_rebuild':False,'runtime_execution':False,'original_checkout_modified':trial['original_checkout_modified'],
        'file_hash_verification':trial['file_hash_verification'],'production_copy_edges_emitted':False,'process_counterpart_connected':False,
        'whole_G02_accepted':False,'whole_G03_accepted':False}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(portable,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks':len(checks),'passed':portable['passed'],'failed':[c['id'] for c in checks if not c['passed']]}))
    if not portable['passed']:raise SystemExit(1)


if __name__=='__main__':main()
