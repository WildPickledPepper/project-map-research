"""Independently verify Insight's selected desktop startup file/entry chain."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from projectmap.workspace import Workspace


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--trial',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    if args.output.exists():ap.error('Choose a new score file')
    trial=json.loads((args.trial/'trial.json').read_text(encoding='utf-8'))
    graph=json.loads((args.trial/'graph.json').read_text(encoding='utf-8'));nodes={n['id']:n for n in graph['nodes']};checks=[]
    def check(name,value):checks.append({'id':name,'passed':bool(value)})
    check('same_pinned_source',trial['source_commit']==graph['source_commit']=='d4e8d1cf9f90208bcbe5371c127088f6fd66c688')
    check('exact_control_input_union',trial['input_count']==1471 and trial['cached_input_counts']=={'cpp':1336,'python':119,'rust':16})
    matches=[e for e in graph['edges'] if e['kind']=='RESOLVES_EXECUTABLE_TARGET_CANDIDATE']
    check('one_conditional_backend_target',len(matches)==1)
    if len(matches)!=1:raise ValueError('Independent selected startup reference requires one backend candidate')
    match=matches[0];bound=nodes[match['source']];provider=nodes[match['target']];backend=nodes[match['artifact']]
    image=nodes[bound['deployment']];cargo_target=nodes[image['build_target']];raw_path=nodes[bound['source_path_value']]
    constructor=nodes[bound['consumer']];analysis=nodes[bound['analysis_context']];cpp_config=nodes[provider['build_context']]
    cfg=nodes[image['build_context']]
    rust_entry=next(nodes[e['target']] for e in graph['edges'] if e['source']==cargo_target['id'] and e['kind']=='EXECUTABLE_ENTRY_CANDIDATE')
    cpp_entry=next(nodes[e['target']] for e in graph['edges'] if e['source']==provider['id'] and e['kind']=='EXECUTABLE_ENTRY_CANDIDATE')
    source_request=next(nodes[e['source']] for e in graph['edges'] if e['target']==cfg['id'] and e['kind']=='REQUESTS_BUILD_CONTEXT_CANDIDATE')
    invocation=nodes[source_request['source_invocation']]
    starts=[nodes[e['source']] for e in graph['edges'] if e['kind']=='USES_COMMAND' and e['target']==constructor['id'] and
        (not e.get('analysis_contexts') or analysis['id'] in e['analysis_contexts'])]
    check('process_start_uses_the_same_command_instance',len(starts)==1 and starts[0]['path']=='platform/src/default.rs' and starts[0]['line']==175)
    check('cargo_target_and_rust_entry',cargo_target['name']=='MindStudioInsight' and rust_entry['name']=='main' and rust_entry['path']=='platform/src/main.rs')
    check('renamed_launcher_image',image['image_location']=={'root':'source','path':'platform/preview/MindStudio-Insight.exe'})
    check('original_launcher_lineage',nodes[image['origin_artifact']]['location']=={'root':'source','path':'platform/target/release/MindStudioInsight.exe'})
    check('rust_program_source_location',raw_path['path']==constructor['path']=='platform/src/default.rs' and raw_path['line']==constructor['line']==164)
    check('symbolic_directory_and_full_suffix',raw_path['value']['base']['kind']=='current_executable_directory' and
        raw_path['value']['relative_path']=='resources/profiler/server/profiler_server.exe')
    check('cargo_main_owns_program_path',raw_path['root_function']==rust_entry['id'] and bound['ownership_basis']=='native_call_frames_rooted_at_cargo_entry')
    check('release_default_windows_context',analysis['workspace']=='platform/Cargo.toml' and analysis['target']=='x86_64-pc-windows-msvc' and
        analysis['debug_assertions'] is False and analysis['features']==['MindStudioInsight/default'])
    expected='platform/preview/resources/profiler/server/profiler_server.exe'
    check('computed_full_runtime_layout_path',bound['location']=={'root':'source','path':expected})
    check('matched_full_packaging_path',backend['value']['relative_path']==expected and backend['path']=='build/build.py' and backend['line']==344)
    check('backend_origin_from_native_target',nodes[backend['origin_artifact']]['location']=={'root':'source','path':'server/output/win_mingw64/bin/profiler_server.exe'})
    check('cpp_target_identity',provider['name']=='profiler_server' and provider['target_type']=='EXECUTABLE')
    check('cpp_entry_from_target_membership',cpp_entry['name']=='main' and cpp_entry['path']=='server/src/entry/server/bin/main.cpp')
    check('single_conditional_producer_status',bound['match_status']=='single_conditional_producer' and bound['matched_producer_targets']==[provider['id']])
    check('no_execution_upgrade',match['status']=='conditional_candidate' and match['runtime_execution']==bound['runtime_execution']=='not_observed')
    kinds={c['kind'] for c in match['conditions']}
    for kind in ('running_process_image_matches_deployment','deployed_layout_matches_recorded_relative_files','consumer_path_reached_in_running_binary',
        'native_rust_cfg_and_features_equal_analysis_context','deployed_path_resolution_has_no_symlink_or_mount_redirection',
        'deployment_artifact_lineage_matches_recorded_producer','target_os_loader_accepts_provider_image'):
        check('condition_'+kind,kind in kinds)
    check('cpp_processor_declaration_not_verified_architecture',cpp_config['target_system']['declared_processor']=='AMD64' and
        cpp_config['target_system']['processor_interpretation']=='cmake_system_processor_not_verified_compiler_architecture')
    deployment=graph['executable_deployment']
    check('two_images_two_bound_paths_one_match',deployment['deployment_images']==2 and deployment['current_exe_source_paths']==1 and
        deployment['counts']=={'bindings':2,'artifact_matches':1} and deployment['required_gaps']==0)
    check('unpackaged_build_image_remains_unmatched',any(d['kind']=='executable_deployment_gap' and
        d['reason']=='no_artifact_at_deployment_candidate_path' and not d['required'] for d in graph['diagnostics']))
    workspace=Workspace(args.trial/'workspace');navigation=[]
    call_kinds=['OBSERVES_CALL','STATIC_CALL_TARGET','STATIC_CALL_CANDIDATE','DECLARES_BOUNDARY','COMMAND_PROGRAM',
        'PATH_VALUE_CANDIDATE','PATH_DEPLOYMENT_BINDING','RESOLVES_EXECUTABLE_TARGET_CANDIDATE','EXECUTABLE_ENTRY_CANDIDATE']
    startup_kinds=call_kinds+['SOURCE_BUILD_REQUEST','REQUESTS_BUILD_CONTEXT_CANDIDATE','CONFIGURES_BUILD_TARGET']
    routes=[('rust_main_cpp_main',rust_entry['id'],cpp_entry['id'],call_kinds),
        ('build_request_cpp_main',invocation['id'],cpp_entry['id'],startup_kinds),
        ('process_start_cpp_main',starts[0]['id'],cpp_entry['id'],['USES_COMMAND',*call_kinds]),
        ('rust_path_backend_file',raw_path['id'],backend['id'],['PATH_DEPLOYMENT_BINDING','MATCHES_DEPLOYED_ARTIFACT_CANDIDATE']),
        ('image_backend_target',image['id'],provider['id'],['RESOLVES_DEPLOYED_PATH_CANDIDATE','RESOLVES_EXECUTABLE_TARGET_CANDIDATE']),
        ('backend_file_origin',backend['origin_artifact'],backend['id'],['COPIES_ARTIFACT_TO'])]
    for label,left,right,kinds in routes:
        for direction,start,end in [('out',left,right),('in',right,left)]:
            result=workspace.query('path',start=start,target=end,direction=direction,kinds=kinds,depth=64,nodes=3000,edges=10000,output_bytes=524288,seconds=10)
            row={'id':label+'_'+direction,'found':result['found'],'stop_reason':result.get('stop_reason'),
                'snapshot_matches':result['snapshot']==graph['snapshot'],'witness_edges':len(result['items'])}
            navigation.append(row);check('navigation_'+row['id'],row['found'] and row['stop_reason'] is None and row['snapshot_matches'])
    for label,node,path in [('rust',raw_path,'platform/src/default.rs'),('cpp',cpp_entry,'server/src/entry/server/bin/main.cpp'),('packaging',backend,'build/build.py')]:
        proof=workspace.query('source',start=node['id'])
        check('same_version_source_'+label,proof['source_commit']==trial['source_commit'] and proof['path']==path and not proof['working_tree_read'])
    check('current_projection_with_versioned_semantic_reuse',trial['current_cargo_copy_deployment_executed_again'] and not trial['language_semantics_executed_again'] and not trial['cmake_configure_executed_again'])
    check('no_full_build_runtime_or_whole_gate_claim',not any(trial[k] for k in ('default_workspace_rebuild','installed_tool_tested','product_compiled',
        'product_executable_run','runtime_process_identity_observed','whole_G03_accepted','original_checkout_modified')))
    check('no_file_hash_verification',trial['file_hash_verification']=='not_run_per_user_preference')
    score={**trial,'schema':'executable-deployment-control-score/1','checks':checks,'passed':all(c['passed'] for c in checks),'navigation':navigation,
        'selected_chain':{'launcher':image['image_location']['path'],'rust_program':{'path':raw_path['path'],'line':raw_path['line']},
            'process_start':{'path':starts[0]['path'],'line':starts[0]['line']},
            'backend':expected,'native_backend_origin':nodes[backend['origin_artifact']]['location']['path'],
            'target':provider['name'],'cpp_entry':{'path':cpp_entry['path'],'line':cpp_entry['line']}},'deployment_counts':deployment}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(score,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks':len(checks),'passed':score['passed'],'failed':[c['id'] for c in checks if not c['passed']],'navigation':navigation}))
    if not score['passed']:raise SystemExit(1)


if __name__=='__main__':main()
