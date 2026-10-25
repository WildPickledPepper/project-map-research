"""Independent Insight source/config reference, separate from the interpreter."""
import argparse
import json
from pathlib import Path


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--trial',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    if args.output.exists():ap.error('Choose a new evidence file')
    trial=json.loads((args.trial/'trial.json').read_text(encoding='utf-8'))
    requests=json.loads((args.trial/'requests.json').read_text(encoding='utf-8'));checks=[]
    def check(name,value):checks.append({'id':name,'passed':bool(value)})
    reference='d4e8d1cf9f90208bcbe5371c127088f6fd66c688'
    check('same_pinned_source',trial['source_commit']==reference)
    check('all_original_python_inputs',trial['python_input_count']==119)
    check('two_manifests_discovered_without_business_list',set(trial['discovered_manifests'])=={'platform/Cargo.toml','platform/linux/Cargo.toml'})
    check('two_cargo_records_one_build_request',len(requests)==trial['source_request_records']==2 and trial['resolved_source_requests']==1)
    good=[r for r in requests if not r['request']['gaps']];check('one_source_resolved_request',len(good)==1)
    if len(good)!=1:raise ValueError('A unique resolved build is required for the remaining independent reference')
    row=good[0];spec=row['request'];env=spec['environment_sources']['CARGO_TARGET_DIR']
    writer=row['environment_writers'].get(env.get('writer'))
    check('process_location',row['path']=='build/build.py' and row['line']==644)
    check('caller_location',{'path':'build/build.py','line':404} in row['call_stack'])
    check('exact_build_argv',spec['argv']==['cargo.exe','build','--release'])
    check('working_directory_from_source_root',spec['cwd']=='platform')
    check('nearest_manifest_from_source_cwd',spec['manifest']=='platform/Cargo.toml')
    check('release_profile_option',spec['profile']=='release')
    check('no_explicit_features_defaults_remain_enabled',spec['features']==[] and spec['no_default_features'] is False)
    check('target_directory_from_source_environment',spec['target_directory']=='platform/target' and spec['target_directory_basis']=='source_environment')
    check('environment_writer_location',writer=={'path':'build/build.py','line':373,'api':'os.putenv','effect':'set'})
    check('source_environment_value_is_symbolic_root',env['known'] and env['value']['text'] is None and
        env['value']['path_value']['base']['kind']=='canonical_source_root' and env['value']['path_value']['relative_path']=='platform/target')
    check('environment_source_layout_conditions_retained',any(c['kind']=='canonical_source_layout_required' for c in env['source_conditions']))
    check('environment_source_conditions_enter_request',all(c in spec['conditions'] for c in env['source_conditions']))
    check('unsupplied_target_environment_not_invented',not spec['environment_sources']['CARGO_BUILD_TARGET']['known'] and
        spec['target'] is None and spec['target_basis']=='native_context_required')
    conditions={c['kind'] for c in spec['conditions']}
    for kind in ('source_process_invocation_reached_and_succeeds','source_executable_resolves_to_recorded_cargo',
        'source_environment_operation_succeeds','no_unmodeled_environment_write_before_child_start',
        'source_build_target_environment_and_config_equal_native_capture','source_cargo_configuration_toolchain_and_build_inputs_equal_native_capture'):
        check('condition_'+kind,kind in conditions)
    check('fetch_does_not_become_an_executable_build',any(r['request']['argv']==['cargo.exe','fetch'] and
        'cargo_command_not_supported' in r['request']['gaps'] for r in requests))
    check('source_host_selection_remains_explicit',trial['host_selection']=={'host_system':{'name':'Windows','path_style':'windows'},
        'basis':'explicit_source_predicate_control_not_native_host_measurement'})
    check('base_process_facts_version_retained',trial['base_process_version']['rules_commit']=='a487ce3c8af7eec95d4dc43274cbdbab34f47aa0')
    check('interpreter_executed_again_only',trial['cargo_interpreter_executed_again'] and not trial['native_semantic_stage_executed_again'])
    check('source_unchanged_and_no_file_hash_verification',not trial['original_checkout_modified'] and trial['file_hash_verification']=='not_run_per_user_preference')
    check('no_native_full_or_runtime_claim',not any(trial[k] for k in ('default_workspace_rebuild','native_cargo_build_executed',
        'product_executable_run','native_cargo_target_connected','process_counterpart_connected','whole_G03_accepted')))
    portable={**trial,'schema':'cargo-source-request-score/1','checks':checks,'passed':all(c['passed'] for c in checks),
        'selected_request':{'path':row['path'],'line':row['line'],'source_caller_line':404,
            **{k:spec[k] for k in ('argv','cwd','manifest','profile','target_directory','target_directory_basis','target','target_basis','features','no_default_features')},
            'environment_writer':writer,'conditions':spec['conditions']}}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(portable,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks':len(checks),'passed':portable['passed'],'failed':[c['id'] for c in checks if not c['passed']]}))
    if not portable['passed']:raise SystemExit(1)


if __name__=='__main__':main()
