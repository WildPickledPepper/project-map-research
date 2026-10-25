"""Independent Insight target/launcher/entry/packaging reference and navigation."""
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
    check('pinned_source',graph['source_commit']==trial['source_commit']=='d4e8d1cf9f90208bcbe5371c127088f6fd66c688')
    check('complete_python_rust_control_union',trial['input_count']==135 and trial['python_input_count']==119 and trial['rust_input_count']==16)
    targets=[n for n in nodes.values() if n['kind']=='build_target'];artifacts=[n for n in nodes.values() if n['kind']=='build_artifact']
    shipped=[n for n in nodes.values() if n['kind']=='copied_artifact']
    check('one_target_artifact_and_renamed_copy',len(targets)==len(artifacts)==len(shipped)==1)
    if not (len(targets)==len(artifacts)==len(shipped)==1):raise ValueError('Expected one launcher chain for independent reference')
    target=targets[0];artifact=artifacts[0];copy=shipped[0];context=nodes[target['build_context']]
    bindings=[e for e in graph['edges'] if e['kind']=='REQUESTS_BUILD_CONTEXT_CANDIDATE'];check('one_source_context_binding',len(bindings)==1)
    request=nodes[bindings[0]['source']];invocation=nodes[request['source_invocation']]
    entries=[nodes[e['target']] for e in graph['edges'] if e['source']==target['id'] and e['kind']=='EXECUTABLE_ENTRY_CANDIDATE']
    check('one_rust_main_candidate',len(entries)==1)
    entry=entries[0]
    check('metadata_target_name_and_manifest',target['name']=='MindStudioInsight' and target['path']=='platform/Cargo.toml')
    check('metadata_root_source',target['root_source']=={'root':'source','path':'platform/src/main.rs'})
    check('rust_main_source_and_kind',entry['name']=='main' and entry['path']=='platform/src/main.rs' and entry.get('definition'))
    check('exact_expected_primary_path',artifact['location']=={'root':'source','path':'platform/target/release/MindStudioInsight.exe'})
    check('artifact_not_claimed_compiled',artifact['materialization']=='expected_output_not_built' and artifact['runtime_execution']=='not_observed')
    check('exact_renamed_distribution_path',copy['value']['relative_path']=='platform/preview/MindStudio-Insight.exe')
    check('copy_operation_source_location',copy['path']=='build/build.py' and copy['line']==532)
    check('same_target_copy_origin',copy['origin_artifact']==artifact['id'])
    check('source_invocation_and_caller',invocation['path']=='build/build.py' and invocation['line']==644 and
        any(nodes[c]['path']=='build/build.py' and nodes[c]['line']==404 for c in invocation['call_stack']))
    spec=request['request']
    check('source_command_and_configuration',spec['argv']==['cargo.exe','build','--release'] and spec['cwd']=='platform' and
        spec['manifest']=='platform/Cargo.toml' and spec['profile']=='release' and spec['target_directory']=='platform/target')
    check('default_feature_request_and_declared_release_cfg',target['features_requested']==[] and target['default_features_requested'] and
        target['profile']['debug_assertions'] is False and target['profile']['basis']=='declared_profile_conditional_on_configuration')
    system=context['target_system']
    check('native_query_host_and_target',system['host_name']==system['name']=='Windows' and system['host_target']==system['target']=='x86_64-pc-windows-msvc')
    check('source_target_mode_kept_conditional',context['state']=='declared_output_plan' and spec['target'] is None and spec['target_basis']=='native_context_required')
    required={'canonical_source_layout_required','source_process_invocation_reached_and_succeeds','source_build_target_selection_equals_projection',
        'source_compiler_flags_preserve_cargo_binary_output_contract','native_artifact_successfully_materialized_as_regular_file'}
    check('source_build_and_materialization_conditions_reach_copy',required<={c['kind'] for c in copy['conditions']})
    check('conditional_binding_not_execution',bindings[0]['status']=='conditional_candidate' and bindings[0]['runtime_execution']=='not_observed')
    workspace=Workspace(args.trial/'workspace');navigation=[]
    routes=[('request_context',invocation['id'],context['id'],['SOURCE_BUILD_REQUEST','REQUESTS_BUILD_CONTEXT_CANDIDATE']),
        ('target_entry',target['id'],entry['id'],['EXECUTABLE_ENTRY_CANDIDATE']),
        ('target_copy',target['id'],copy['id'],['PRODUCES_ARTIFACT','COPIES_ARTIFACT_TO']),
        ('request_copy',invocation['id'],copy['id'],['SOURCE_BUILD_REQUEST','REQUESTS_BUILD_CONTEXT_CANDIDATE','CONFIGURES_BUILD_TARGET','PRODUCES_ARTIFACT','COPIES_ARTIFACT_TO'])]
    for label,left,right,kinds in routes:
        for direction,start,end in [('out',left,right),('in',right,left)]:
            route=workspace.query('path',start=start,target=end,direction=direction,kinds=kinds,depth=7,nodes=80,edges=80)
            row={'id':label+'_'+direction,'found':route['found'],'stop_reason':route.get('stop_reason'),'snapshot_matches':route['snapshot']==graph['snapshot']}
            navigation.append(row);check('navigation_'+row['id'],row['found'] and row['stop_reason'] is None and row['snapshot_matches'])
    for label,node,path in [('target',target,'platform/Cargo.toml'),('entry',entry,'platform/src/main.rs'),('copy',copy,'build/build.py')]:
        proof=workspace.query('source',start=node['id'])
        check('same_version_source_'+label,proof['path']==path and proof['source_commit']==trial['source_commit'] and not proof['working_tree_read'])
    gaps=[d for d in graph['diagnostics'] if d['kind']=='cargo_declared_artifact_gap']
    check('build_script_output_gap_retained',any(d['reason']=='build_script_outputs_require_native_build_evidence' and d['path']=='platform/build.rs' and d['required'] for d in gaps))
    check('other_build_mode_manifest_gap_retained',any(d['reason']=='cargo_manifest_without_selected_build_context' and d['path']=='platform/linux/Cargo.toml' and d['required'] for d in gaps))
    check('successful_native_query_commands',all(code==0 for code in trial['native_query_returncodes']) and
        any(label.startswith('metadata-') for label in trial['native_query_labels']) and any(label.startswith('binary-template-') for label in trial['native_query_labels']))
    check('fixed_native_versions',trial['cargo_version'].startswith('cargo 1.94.0 ') and trial['rustc_version'].startswith('rustc 1.94.0 '))
    check('versioned_source_facts_explicitly_reused',trial['build_version']['cached_python']['rules_commit']=='a487ce3c8af7eec95d4dc43274cbdbab34f47aa0' and
        trial['cargo_queries_and_copy_projection_executed_again'] and not trial['python_rust_semantics_executed_again'])
    check('no_full_compile_runtime_or_whole_gate_claim',not any(trial[k] for k in ('default_workspace_rebuild','installed_tool_tested','product_compiled',
        'build_scripts_executed','product_executable_run','process_counterpart_connected','whole_G03_accepted')))
    check('source_and_reference_not_extraction_worktree',not graph['provenance']['working_tree_included'] and not graph['provenance']['reference_used_for_extraction'] and not trial['original_checkout_modified'])
    check('no_file_hash_verification',trial['file_hash_verification']=='not_run_per_user_preference')
    score={**trial,'schema':'cargo-declared-control-score/1','checks':checks,'passed':all(c['passed'] for c in checks),'navigation':navigation,
        'target':{'name':target['name'],'manifest':target['path'],'root_source':target['root_source'],'profile':target['profile']},
        'artifact':{k:artifact[k] for k in ('name','location','materialization')},'copied_path':copy['value']['relative_path'],
        'target_system':system,'gap_reasons':[{'reason':d['reason'],'path':d.get('path')} for d in gaps]}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(score,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks':len(checks),'passed':score['passed'],'failed':[c['id'] for c in checks if not c['passed']]}))
    if not score['passed']:raise SystemExit(1)


if __name__=='__main__':main()
