"""Validate the native-identity/gap probe without accepting path propagation."""
import json
from pathlib import Path
import re

data=json.loads((Path(__file__).parent/'evidence/native-path-primitives.json').read_text(encoding='utf-8'))
assert data['passed'] and len(data['checks'])==5 and all(c['passed'] for c in data['checks'])
assert re.fullmatch('[0-9a-f]{40}',data['rules_commit'])
assert data['target']=='x86_64-pc-windows-msvc'
assert data['tools']['cargo'].startswith('cargo 1.94.0 ') and data['tools']['rustc'].startswith('rustc 1.94.0 ')
assert not data['loop_pattern_bindings']
assert {n['name'] for n in data['observations']}=={'root.to_path_buf','output.push','output.set_extension','value.push'}
local=next(n for n in data['observations'] if n['name']=='value.push')
assert not local['api_declarations']
assert not any(data[k] for k in ('path_value_propagation_implemented','product_executed','process_counterpart_connected','whole_G03_accepted'))
print('OK: 5 historical native path identity/gap checks at their recorded rule version.')

control=json.loads((Path(__file__).parent/'evidence/rust-path-control.json').read_text(encoding='utf-8'))
assert control['schema']=='rust-path-control-score/1' and control['passed']
assert len(control['checks'])==33 and all(c['passed'] for c in control['checks'])
assert control['source_commit']=='d4e8d1cf9f90208bcbe5371c127088f6fd66c688'
assert control['build_version']['rules_commit']=='6038f946134f23a4a52828a1fdf9cf8a653f073c'
assert control['scope']=='one_manifest_one_native_host_release_default'
assert control['context']['target']=='x86_64-pc-windows-msvc'
assert control['index_counts']['input_files']==16 and control['index_counts']['nodes']==5579 and control['index_counts']['edges']==8068
assert control['path_resolution_counts']=={'constant':10,'symbolic_base':1,'unresolved':1}
assert control['backend_program']['relative_path']=='resources/profiler/server/profiler_server.exe'
assert control['backend_program']['base_kind']=='current_executable_directory'
assert control['backend_program']['conditions']['source_call_context']==2
assert len(control['navigation'])==8 and all(n['found'] and n['snapshot_matches'] and n['stop_reason'] is None for n in control['navigation'])
assert control['required_path_gaps']==[{'path':'platform/src/webview.rs','line':92,'reasons':['path_expression_not_resolved']}]
assert not any(control[k] for k in ('original_checkout_modified','default_workspace_rebuild','installed_tool_tested','runtime_execution',
                                  'process_counterpart_connected','whole_G02_accepted','whole_G03_accepted'))
assert control['file_hash_verification']=='not_run_per_user_preference'
print('OK: 33 Rust single-context production-adapter/index checks; packaging and counterpart pairing pending.')

python=json.loads((Path(__file__).parent/'evidence/python-path-control.json').read_text(encoding='utf-8'))
assert python['schema']=='python-path-control-score/1' and python['passed']
assert len(python['checks'])==34 and all(c['passed'] for c in python['checks'])
assert python['source_commit']==control['source_commit']
assert python['build_version']['rules_commit']=='9806c76b26190ad849e5f3d5bab82e2a106f5b78'
assert python['scope']=='python_control_all_selected_python_inputs'
assert python['index_counts']['input_files']==119 and python['index_counts']['nodes']==76544 and python['index_counts']['edges']==107728
assert {v['path_style'] for v in python['selected_paths']}=={'windows'}
assert python['selected_paths'][0]['relative_path']=='server/output/build/server'
assert python['selected_paths'][1]['base_kind']=='parameter' and python['selected_paths'][1]['relative_path']=='server'
assert python['selected_paths'][3]['relative_path']=='platform/preview/resources'
assert len(python['navigation'])==8 and all(n['found'] and n['snapshot_matches'] and n['stop_reason'] is None for n in python['navigation'])
assert python['required_gap_counts']
assert not any(python[k] for k in ('original_checkout_modified','default_workspace_rebuild','installed_tool_tested','runtime_execution',
    'directory_enumeration_expanded','caller_path_contexts_expanded','process_counterpart_connected','whole_G02_accepted','whole_G03_accepted'))
assert python['file_hash_verification']=='not_run_per_user_preference'
print('OK: 34 Python repository-control/index checks; directory entries, caller contexts and process pairing pending.')

contexts=json.loads((Path(__file__).parent/'evidence/python-path-contexts.json').read_text(encoding='utf-8'))
assert contexts['schema']=='python-path-context-score/1' and contexts['passed']
assert len(contexts['checks'])==28 and all(c['passed'] for c in contexts['checks'])
assert contexts['source_commit']==python['source_commit']
assert contexts['build_version']['rules_commit']=='de7bc1d730e19be9270d8a7fafe1fcab6c50ef1e'
assert contexts['build_version']['base_facts']['rules_commit']==python['build_version']['rules_commit']
assert contexts['build_version']['base_facts']['counts']=={'nodes':76402,'edges':105988}
assert contexts['index_counts']['input_files']==119 and contexts['index_counts']['nodes']==76626 and contexts['index_counts']['edges']==110680
assert {d['relative_path']:d['caller_count'] for d in contexts['backend_destinations']}=={
    'platform/preview/resources/profiler/server':1,
    'plugins/jupyterlab/mindstudio_insight_jupyterlab/resources/profiler/server':2}
assert len(contexts['navigation'])==6 and all(n['found'] and n['snapshot_matches'] and n['stop_reason'] is None for n in contexts['navigation'])
assert contexts['path_adapter_executed_again'] and not contexts['native_semantic_stage_executed_again']
assert not any(contexts[k] for k in ('original_checkout_modified','default_workspace_rebuild','installed_tool_tested','runtime_execution',
    'directory_enumeration_expanded','process_counterpart_connected','whole_G02_accepted','whole_G03_accepted'))
assert contexts['file_hash_verification']=='not_run_per_user_preference'
print('OK: 28 recomputed-path/cached-native checks; desktop/JupyterLab contexts separate; directory entries and process pairing pending.')

patterns=json.loads((Path(__file__).parent/'evidence/python-directory-patterns.json').read_text(encoding='utf-8'))
assert patterns['schema']=='python-directory-pattern-score/1' and patterns['passed']
assert len(patterns['checks'])==31 and all(c['passed'] for c in patterns['checks'])
assert patterns['source_commit']==contexts['source_commit']
assert patterns['build_version']['rules_commit']=='5dd130d6c95da8aab4d22e09e207e05f1cabca2d'
assert patterns['index_counts']['input_files']==119 and patterns['index_counts']['nodes']==76636 and patterns['index_counts']['edges']==110788
assert patterns['source_pattern']=='server/output/{tmp}/bin/{file}' and patterns['destination_pattern']=='server/output/build/server/{file}'
assert patterns['computed_stage_path']=='server/output/build/server/profiler_server.exe'
assert set(patterns['subsequent_directory_path_correspondences'])=={
    'platform/preview/resources/profiler/server/profiler_server.exe',
    'plugins/jupyterlab/mindstudio_insight_jupyterlab/resources/profiler/server/profiler_server.exe'}
assert len(patterns['navigation'])==6 and all(n['found'] and n['snapshot_matches'] and n['stop_reason'] is None for n in patterns['navigation'])
assert patterns['path_adapter_executed_again'] and patterns['directory_patterns_extracted']
assert patterns['evaluation_path_style_selection']=='windows_explicit_reference_not_automatic_native_platform_binding'
assert not any(patterns[k] for k in ('native_semantic_stage_executed_again','original_checkout_modified','default_workspace_rebuild','installed_tool_tested','runtime_execution',
    'filter_predicates_applied','copy_contracts_applied','native_platform_automatically_bound','production_artifact_edges_emitted',
    'process_counterpart_connected','whole_G02_accepted','whole_G03_accepted'))
assert patterns['file_hash_verification']=='not_run_per_user_preference'
print('OK: 31 directory-pattern/path-correspondence checks at the recorded pre-predicate rule version.')

copies=json.loads((Path(__file__).parent/'evidence/artifact-copy-control.json').read_text(encoding='utf-8'))
assert copies['schema']=='artifact-copy-control-score/1' and copies['passed']
assert len(copies['checks'])==29 and all(c['passed'] for c in copies['checks'])
assert copies['source_commit']==patterns['source_commit']
assert copies['build_version']['rules_commit']=='50da0d9b0d31ebfb074ddb7856b455a0a5a46fe4'
assert copies['index_counts']['input_files']==1455 and copies['index_counts']['nodes']==294500 and copies['index_counts']['edges']==454039
assert copies['artifact_flow']['counts']['native_seeds']==12 and copies['artifact_flow']['copied_artifacts']==24
assert copies['artifact_flow']['required_gaps']==174
assert copies['flow_gap_counts']=={'copy_path_unresolved':168,'destructive_file_effect_not_expanded':6}
assert {n['path']:n['steps'] for n in copies['selected_copy_stages']}=={
    'server/output/build/server/profiler_server.exe':1,
    'platform/preview/resources/profiler/server/profiler_server.exe':2,
    'plugins/jupyterlab/mindstudio_insight_jupyterlab/resources/profiler/server/profiler_server.exe':2}
assert len(copies['navigation'])==6 and all(n['found'] and n['snapshot_matches'] and n['stop_reason'] is None for n in copies['navigation'])
assert all(copies[k] for k in ('path_adapter_executed_again','artifact_copy_flow_executed','production_copy_edges_emitted'))
assert not any(copies[k] for k in ('native_semantic_stage_executed_again','native_configure_executed_again','native_normalizer_executed_again',
    'default_workspace_rebuild','installed_tool_tested','runtime_execution','original_checkout_modified','process_counterpart_connected','whole_G02_accepted','whole_G03_accepted'))
assert copies['file_hash_verification']=='not_run_per_user_preference'
print('OK: 29 real native-to-packaging copy/index checks; runtime materialization and process pairing remain separate.')

mappings=json.loads((Path(__file__).parent/'evidence/python-mapping-paths.json').read_text(encoding='utf-8'))
assert mappings['schema']=='python-mapping-path-score/1' and mappings['passed']
assert len(mappings['checks'])==23 and all(c['passed'] for c in mappings['checks'])
assert mappings['source_commit']==copies['source_commit']
assert mappings['build_version']['rules_commit']=='bb22a5022aba9c276f3ebdd169b181b8b7c5b6bf'
assert mappings['index_counts']['input_files']==119 and mappings['index_counts']['nodes']==76648 and mappings['index_counts']['edges']==111276
assert mappings['windows_copy_paths']=={'source':'platform/target/release/MindStudioInsight.exe','destination':'platform/preview/MindStudio-Insight.exe'}
assert mappings['linux_default_selection_paths']=={'source':'platform/target/release/MindStudioInsight','destination':'platform/preview/MindStudio-Insight'}
assert mappings['macos_copy_branch_excluded']
assert mappings['host_selection']=='explicit_predicate_scoring_context_not_native_cargo_build_or_runtime'
assert len(mappings['navigation'])==4 and all(n['found'] and n['snapshot_matches'] and n['stop_reason'] is None for n in mappings['navigation'])
assert mappings['path_adapter_executed_again'] and not mappings['native_semantic_stage_executed_again']
assert not any(mappings[k] for k in ('default_workspace_rebuild','installed_tool_tested','runtime_execution','original_checkout_modified',
    'cargo_build_context_connected','process_counterpart_connected','whole_G02_accepted','whole_G03_accepted'))
assert mappings['file_hash_verification']=='not_run_per_user_preference'
print('OK: 23 guarded mapping/renaming/index checks; Cargo invocation and executable-root pairing remain separate.')

process=json.loads((Path(__file__).parent/'evidence/python-process-calls.json').read_text(encoding='utf-8'))
assert process['schema']=='python-process-control-score/1' and process['passed']
assert len(process['checks'])==32 and all(c['passed'] for c in process['checks'])
assert process['source_commit']==mappings['source_commit']
assert process['build_version']['rules_commit']=='a487ce3c8af7eec95d4dc43274cbdbab34f47aa0'
assert process['index_counts']['input_files']==119 and process['index_counts']['nodes']==76990 and process['index_counts']['edges']==115954
assert process['invocation_record_count']==316 and process['environment_effect_record_count']==26
assert process['selected_process']['argv']==['cargo.exe','build','--release']
assert process['selected_process']['cwd']=='platform' and process['selected_process']['environment']=={'CARGO_TARGET_DIR':'platform/target'}
assert process['selected_process']['environment_writer_line']==373 and not process['selected_process']['also_updates_os_environ']
assert process['selected_process']['value_binding_basis']=='same_root_resolved_source_order_conditional_on_invocation'
assert process['process_diagnostic_counts']=={'python_process_value_unresolved':336,'python_process_context_unresolved':54}
assert len(process['navigation'])==8 and all(n['found'] and n['snapshot_matches'] and n['stop_reason'] is None for n in process['navigation'])
assert process['host_selection']=='explicit_windows_source_predicate_control_not_native_cargo_build'
assert process['path_and_process_adapters_executed_again'] and not process['native_semantic_stage_executed_again']
assert not any(process[k] for k in ('default_workspace_rebuild','installed_tool_tested','runtime_execution','original_checkout_modified',
    'cargo_native_target_connected','process_counterpart_connected','whole_G02_accepted','whole_G03_accepted'))
assert process['file_hash_verification']=='not_run_per_user_preference'
print('OK: 32 real process argv/cwd/environment and index checks; Cargo native artifacts and runtime pairing remain separate.')

cargo=json.loads((Path(__file__).parent/'evidence/cargo-source-requests.json').read_text(encoding='utf-8'))
assert cargo['schema']=='cargo-source-request-score/1' and cargo['passed']
assert len(cargo['checks'])==30 and all(c['passed'] for c in cargo['checks'])
assert cargo['source_commit']==process['source_commit']
assert cargo['build_version']['rules_commit']=='b8a4779b6ee1c35f01d53f5b773e410f628f8f55'
assert cargo['base_process_version']==process['build_version']
assert cargo['python_input_count']==119 and cargo['source_request_records']==2 and cargo['resolved_source_requests']==1
assert set(cargo['discovered_manifests'])=={'platform/Cargo.toml','platform/linux/Cargo.toml'}
request=cargo['selected_request']
assert request['argv']==['cargo.exe','build','--release'] and request['profile']=='release'
assert request['cwd']=='platform' and request['manifest']=='platform/Cargo.toml'
assert request['target_directory']=='platform/target' and request['target_directory_basis']=='source_environment'
assert request['target'] is None and request['target_basis']=='native_context_required'
assert request['features']==[] and request['no_default_features'] is False
assert request['environment_writer']=={'path':'build/build.py','line':373,'api':'os.putenv','effect':'set'}
assert any(c['kind']=='canonical_source_layout_required' for c in request['conditions'])
assert cargo['cargo_interpreter_executed_again'] and not cargo['native_semantic_stage_executed_again']
assert not any(cargo[k] for k in ('default_workspace_rebuild','native_cargo_build_executed','product_executable_run',
    'native_cargo_target_connected','process_counterpart_connected','whole_G03_accepted','original_checkout_modified'))
assert cargo['file_hash_verification']=='not_run_per_user_preference'
print('OK: 30 current Cargo source-request checks on pinned process facts; actual product target/artifact binding remains pending.')

declared=json.loads((Path(__file__).parent/'evidence/cargo-declared-control.json').read_text(encoding='utf-8'))
assert declared['schema']=='cargo-declared-control-score/1' and declared['passed']
assert len(declared['checks'])==39 and all(c['passed'] for c in declared['checks'])
assert declared['source_commit']==cargo['source_commit'] and declared['input_count']==135
assert declared['python_input_count']==119 and declared['rust_input_count']==16
assert declared['build_version']['rules_commit']=='c141f19e470c807799f35360a84683458f59bce6'
assert declared['build_version']['cached_python']==cargo['base_process_version']
assert declared['build_version']['cached_rust']['rules_commit']=='6038f946134f23a4a52828a1fdf9cf8a653f073c'
assert declared['index_counts']['nodes']==82575 and declared['index_counts']['edges']==124033
assert declared['artifact']['location']=={'root':'source','path':'platform/target/release/MindStudioInsight.exe'}
assert declared['artifact']['materialization']=='expected_output_not_built'
assert declared['copied_path']=='platform/preview/MindStudio-Insight.exe'
assert declared['target']['root_source']=={'root':'source','path':'platform/src/main.rs'}
assert len(declared['navigation'])==8 and all(n['found'] and n['snapshot_matches'] and n['stop_reason'] is None for n in declared['navigation'])
assert declared['cargo_queries_and_copy_projection_executed_again'] and not declared['python_rust_semantics_executed_again']
assert not any(declared[k] for k in ('default_workspace_rebuild','installed_tool_tested','product_compiled','build_scripts_executed',
    'product_executable_run','process_counterpart_connected','whole_G03_accepted','original_checkout_modified'))
assert declared['file_hash_verification']=='not_run_per_user_preference'
print('OK: 39 current Cargo metadata/filename/packaging/index checks; expected launcher connected, current_exe binding pending.')

deployment=json.loads((Path(__file__).parent/'evidence/executable-deployment-control.json').read_text(encoding='utf-8'))
assert deployment['schema']=='executable-deployment-control-score/1' and deployment['passed']
assert len(deployment['checks'])==46 and all(c['passed'] for c in deployment['checks'])
assert deployment['source_commit']==declared['source_commit'] and deployment['input_count']==1471
assert deployment['cached_input_counts']=={'cpp':1336,'python':119,'rust':16}
assert deployment['build_version']['rules_commit']=='91f16b8169e46baabb878a5dc890802039757d7c'
assert deployment['build_version']['cached_rule_versions']=={'cpp':'45a9fdca0bfe98c562d43532e07ec3b6bd8b41ac',
    'python':'a487ce3c8af7eec95d4dc43274cbdbab34f47aa0','rust':'6038f946134f23a4a52828a1fdf9cf8a653f073c'}
assert deployment['index_counts']['nodes']==300443 and deployment['index_counts']['edges']==467230
assert deployment['selected_chain']['launcher']=='platform/preview/MindStudio-Insight.exe'
assert deployment['selected_chain']['backend']=='platform/preview/resources/profiler/server/profiler_server.exe'
assert deployment['selected_chain']['target']=='profiler_server'
assert deployment['selected_chain']['cpp_entry']['path']=='server/src/entry/server/bin/main.cpp'
assert deployment['selected_chain']['process_start']=={'path':'platform/src/default.rs','line':175}
assert deployment['deployment_counts']['counts']=={'bindings':2,'artifact_matches':1} and deployment['deployment_counts']['required_gaps']==0
assert len(deployment['navigation'])==12 and all(n['found'] and n['snapshot_matches'] and n['stop_reason'] is None for n in deployment['navigation'])
assert next(n['witness_edges'] for n in deployment['navigation'] if n['id']=='rust_main_cpp_main_out')==11
assert next(n['witness_edges'] for n in deployment['navigation'] if n['id']=='build_request_cpp_main_out')==15
assert next(n['witness_edges'] for n in deployment['navigation'] if n['id']=='process_start_cpp_main_out')==6
assert deployment['current_cargo_copy_deployment_executed_again'] and not deployment['language_semantics_executed_again']
assert not any(deployment[k] for k in ('cmake_configure_executed_again','default_workspace_rebuild','installed_tool_tested',
    'product_compiled','product_executable_run','runtime_process_identity_observed','whole_G03_accepted','original_checkout_modified'))
assert deployment['file_hash_verification']=='not_run_per_user_preference'
print('OK: 46 selected Windows release/default startup checks; 12 bidirectional paths join Rust spawn and C++ entry conditionally; runtime identity pending.')

arguments=json.loads((Path(__file__).parent/'evidence/rust-argument-control.json').read_text(encoding='utf-8'))
assert arguments['schema']=='rust-argument-control-score/1' and arguments['passed']
assert len(arguments['checks'])==45 and all(c['passed'] for c in arguments['checks'])
assert arguments['source_commit']==deployment['source_commit'] and arguments['input_count']==16
assert arguments['build_version']['rules_commit']=='2390be16d4be33664355933fa95a4f2a24e2b3d2'
assert arguments['build_version']['base_facts']['rules_commit']=='6038f946134f23a4a52828a1fdf9cf8a653f073c'
assert arguments['index_counts']['nodes']==5611 and arguments['index_counts']['edges']==8124
assert arguments['template_summary']['counts']=={'templates':15,'complete_source_templates':9}
assert arguments['selected_chain']=={'command':{'path':'platform/src/default.rs','line':176},
    'url':{'path':'platform/src/webview.rs','line':115},'shared_binding':{'path':'platform/src/default.rs','line':393},
    'selector':{'path':'platform/src/default.rs','line':393},'value_kind':'binding_projection',
    'command_prefix':'--wsPort=','url_prefix':'wry://localhost/resources/profiler/frontend/index.html?port='}
assert arguments['required_template_gap_counts']=={'scalar_expression_not_expanded':4,'scalar_iteration_instance_not_bound':2}
assert len(arguments['navigation'])==6 and all(n['found'] and n['snapshot_matches'] and n['stop_reason'] is None and n['witness_edges']==2 for n in arguments['navigation'])
assert arguments['argument_projection_executed_again'] and not arguments['native_semantic_stage_executed_again']
assert not any(arguments[k] for k in ('default_workspace_rebuild','installed_tool_tested','runtime_execution','cpp_argument_decode_connected',
    'backend_listener_connected','whole_G03_accepted','original_checkout_modified'))
assert arguments['file_hash_verification']=='not_run_per_user_preference'
print('OK: 45 selected Rust CLI/WebView shared-value checks; six bidirectional paths; C++ decoding and listener pairing pending.')

decoders=json.loads((Path(__file__).parent/'evidence/cpp-string-decoder-control.json').read_text(encoding='utf-8'))
assert decoders['schema']=='cpp-string-decoder-control-score/1' and decoders['passed']
assert len(decoders['checks'])==39 and all(c['passed'] for c in decoders['checks'])
assert decoders['source_commit']==arguments['source_commit'] and decoders['input_count']==1323
assert decoders['build_version']['rules_commit']=='0f386bf9d64f648ec1dbba71091c1b5d137edb84'
assert decoders['index_counts']['nodes']==93639 and decoders['index_counts']['edges']==115584
assert decoders['decoder_summary']['counts']=={'decoders':7} and decoders['decoder_summary']['required_gaps']==1
assert len(decoders['selected_decoders'])==7 and all(d['path']=='server/msinsight/src/base/ParamsParser.cpp' and d['parameter_index']==0 for d in decoders['selected_decoders'])
assert {d['key']:(d['target'],d['line']) for d in decoders['selected_decoders']}=={
    '--wsPort=':('ParseWsPort',38),'--wsHost=':('ParseWsHost',42),'--logPath=':('ParseLogPath',46),
    '--logLevel=':('ParseLogLevel',50),'--logSize=':('ParseLogSize',54),'--eventDir=':('ParseEventDir',59),'--scanPort=':('ParseScan',63)}
assert len(decoders['required_decoder_gaps'])==1
gap=decoders['required_decoder_gaps'][0]
assert gap['path']=='server/src/modules/timeline/core/database/DataBaseManager.cpp' and gap['line']==876
assert gap['reason']=='slice_offset_not_proven_as_find_plus_key_length' and gap['required']
assert len(decoders['navigation'])==2 and all(n['found'] and n['snapshot_matches'] and n['stop_reason'] is None and n['witness_edges']==1 for n in decoders['navigation'])
assert decoders['cpp_source_extraction_executed_again']
assert not any(decoders[k] for k in ('cmake_configure_executed_again','default_workspace_rebuild','installed_tool_tested','runtime_execution',
    'argv_origin_connected','rust_argument_paired','backend_listener_connected','whole_G03_accepted','original_checkout_modified'))
assert decoders['file_hash_verification']=='not_run_per_user_preference'
print('OK: 39 all-C++ string-decoding checks; seven source targets and two paths; one other decoder gap retained, argv/instance binding pending.')

argv=json.loads((Path(__file__).parent/'evidence/cpp-argv-control.json').read_text(encoding='utf-8'))
assert argv['schema']=='cpp-argv-origin-control-score/1' and argv['passed']
assert len(argv['checks'])==63 and all(c['passed'] for c in argv['checks'])
assert argv['source_commit']==decoders['source_commit'] and argv['input_count']==1323
assert argv['build_version']['rules_commit']=='edd48dc86ad474c53837f8457e82627d0faf8a0d'
assert argv['index_counts']['nodes']==93647 and argv['index_counts']['edges']==115599
assert argv['argv_summary']['entry_candidates']==1 and argv['argv_summary']['counts']=={'bindings':7,'complete_origins':7}
assert argv['argv_summary']['required_gaps']==0 and argv['required_origin_gaps']==[]
assert argv['decoder_summary']['required_gaps']==1
assert len(argv['selected_bindings'])==7 and {b['key'] for b in argv['selected_bindings']}=={d['key'] for d in decoders['selected_decoders']}
assert all(b['entry']=={'path':'server/src/entry/server/bin/main.cpp','name':'main'} and b['call_count']==2 and b['origin_complete'] and
    b['origin_count']==2 and b['conditional_append_count']==2 for b in argv['selected_bindings'])
assert len(argv['navigation'])==4 and all(n['found'] and n['snapshot_matches'] and n['stop_reason'] is None for n in argv['navigation'])
assert {n['id']:n['witness_edges'] for n in argv['navigation']}=={'entry_decoder_out':3,'entry_decoder_in':3,'entry_parse_value_out':4,'entry_parse_value_in':4}
assert argv['cpp_source_extraction_executed_again'] and argv['argv_origin_connected']
assert not any(argv[k] for k in ('cmake_configure_executed_again','default_workspace_rebuild','installed_tool_tested','runtime_execution',
    'rust_argument_paired','backend_listener_connected','whole_G03_accepted','original_checkout_modified'))
assert argv['file_hash_verification']=='not_run_per_user_preference'
print('OK: 63 all-C++ argv/preparation/decoder checks; seven source bindings, four paths; Rust word pairing and listener identities pending.')

process=json.loads((Path(__file__).parent/'evidence/process-argument-control.json').read_text(encoding='utf-8'))
assert process['schema']=='process-argument-control-score/1' and process['passed']
assert len(process['checks'])==41 and all(c['passed'] for c in process['checks'])
assert process['source_commit']==argv['source_commit'] and process['input_count']==1471
assert process['build_version']['rules_commit']=='b41c5b7cc679790d1cab058f08164998903a2519'
assert {k:v['rules_commit'] for k,v in process['build_version']['cached_build_versions'].items()}=={
    'startup':'91f16b8169e46baabb878a5dc890802039757d7c','rust_arguments':'2390be16d4be33664355933fa95a4f2a24e2b3d2','cpp_argv':'edd48dc86ad474c53837f8457e82627d0faf8a0d'}
assert process['cached_argument_input_counts']=={'rust_arguments':16,'cpp_argv':1323}
assert process['index_counts']['nodes']==300492 and process['index_counts']['edges']==467344
assert process['argument_binding_summary']['counts']=={'words_without_bound_program':7,'words_with_bound_program':3,'matches':2,'unmatched_words':1}
assert process['argument_binding_summary']['required_gaps']==2 and process['argument_binding_summary']['payload_equivalence']=='not_established'
assert process['selected_chain']['template']=={'path':'platform/src/default.rs','line':176}
assert process['selected_chain']['decoder']=={'path':'server/msinsight/src/base/ParamsParser.cpp','line':38}
assert process['selected_chain']['target']=='Dic::Server::ParamsParser::ParseWsPort' and process['selected_chain']['provider']=='profiler_server'
assert process['selected_chain']['backend_path']=='platform/preview/resources/profiler/server/profiler_server.exe'
assert {g['reason'] for g in process['required_binding_gaps']}=={'argument_payload_source_unresolved','no_decoder_for_sourced_word_in_bound_program'}
assert next(g for g in process['required_binding_gaps'] if g['reason']=='no_decoder_for_sourced_word_in_bound_program')['literal_prefix']=='--notStrict'
assert len(process['navigation'])==6 and all(n['found'] and n['snapshot_matches'] and n['stop_reason'] is None for n in process['navigation'])
assert {n['id']:n['witness_edges'] for n in process['navigation']}=={'template_parse_out':4,'template_parse_in':4,
    'spawn_parse_out':5,'spawn_parse_in':5,'binding_native_target_out':1,'binding_native_target_in':1}
assert process['default_navigation']['found'] and process['default_navigation']['snapshot_matches'] and process['default_navigation']['stop_reason'] is None
assert process['default_navigation']['witness_edges']==4 and process['default_navigation']['output_bytes']<=131072
assert process['current_argument_binding_executed_again'] and not process['language_semantics_executed_again']
assert not any(process[k] for k in ('cmake_configure_executed_again','default_workspace_rebuild','installed_tool_tested','product_compiled','runtime_execution',
    'payload_value_equivalence_established','backend_listener_connected','whole_G03_accepted','original_checkout_modified'))
assert process['file_hash_verification']=='not_run_per_user_preference'
print('OK: 41 deployed-program/word/argv checks; six paths and default-budget query; payload, literal-switch and listener work retained.')

members=json.loads((Path(__file__).parent/'evidence/cpp-member-control.json').read_text(encoding='utf-8'))
first_members=json.loads((Path(__file__).parent/'evidence/cpp-member-control-first-score.json').read_text(encoding='utf-8'))
assert members['schema']=='cpp-member-declaration-control-score/1' and members['passed']
assert len(members['checks'])==24 and all(c['passed'] for c in members['checks'])
assert not first_members['passed'] and [c['id'] for c in first_members['checks'] if not c['passed']]==['opposite_win32_guards']
assert first_members['snapshot']==members['snapshot'] and first_members['member_summary']==members['member_summary']
assert members['source_commit']==argv['source_commit'] and members['input_count']==1323
assert members['build_version']['rules_commit']=='66f3a2fd3ff074f8d323cdd8c80da100b096846b'
assert members['index_counts']['nodes']==103575 and members['index_counts']['edges']==125520
assert members['member_summary']=={'adapter':'cpp_source_member_declaration_alternatives/0.1.0','members':4967,
    'declarations':4969,'conditional_members':4449,'configuration_selection':'not_performed'}
assert members['required_member_gap_counts']=={'member_declarator_not_expanded':51}
assert members['selected_member']['path']=='server/msinsight/src/base/ParamsParser.h'
assert [v['line'] for v in members['selected_member']['variants']]==[35,37]
assert [v['default_expression'] for v in members['selected_member']['variants']]==['""','"./"']
assert len(members['navigation'])==4 and all(n['found'] and n['snapshot_matches'] and n['stop_reason'] is None and n['witness_edges']==2 for n in members['navigation'])
assert members['cpp_source_extraction_executed_again']
assert not any(members[k] for k in ('cmake_configure_executed_again','default_workspace_rebuild','installed_tool_tested','runtime_execution',
    'argv_origin_connected','rust_argument_paired','backend_listener_connected','whole_G03_accepted','original_checkout_modified'))
assert members['file_hash_verification']=='not_run_per_user_preference'
print('OK: 24 conditional-member checks and four paths; first score preserved; 51 reference-return method classification gaps pending.')

method_members=json.loads((Path(__file__).parent/'evidence/cpp-member-method-control.json').read_text(encoding='utf-8'))
assert method_members['schema']=='cpp-member-declaration-control-score/1' and method_members['passed']
assert len(method_members['checks'])==28 and all(c['passed'] for c in method_members['checks'])
assert method_members['source_commit']==members['source_commit'] and method_members['input_count']==1323
assert method_members['build_version']['rules_commit']=='5f63b56032cad783ffb39273406192cf8d34302d'
assert method_members['index_counts']['nodes']==103509 and method_members['index_counts']['edges']==125454
assert method_members['member_summary']=={'adapter':'cpp_source_member_declaration_alternatives/0.1.1','members':4934,
    'declarations':4936,'conditional_members':4417,'configuration_selection':'not_performed'}
assert method_members['required_member_gap_counts']=={} and method_members['selected_member']==members['selected_member']
delta=method_members['member_catalog_delta']
assert delta['previous_snapshot']==members['snapshot'] and delta['previous_build_version']==members['build_version']
assert delta['removed_member_entries']==delta['removed_entries_still_method_nodes']==33 and delta['added_member_entries']==0
assert len(method_members['navigation'])==4 and all(n['found'] and n['snapshot_matches'] and n['stop_reason'] is None and n['witness_edges']==2 for n in method_members['navigation'])
assert method_members['cpp_source_extraction_executed_again'] and method_members['decoder_summary']['required_gaps']==1
assert not any(method_members[k] for k in ('cmake_configure_executed_again','default_workspace_rebuild','installed_tool_tested','runtime_execution',
    'argv_origin_connected','rust_argument_paired','backend_listener_connected','whole_G03_accepted','original_checkout_modified'))
assert method_members['file_hash_verification']=='not_run_per_user_preference'
print('OK: 28 same-source member rechecks; 51 false gaps cleared, 33 callable declarations removed from data catalog and retained as methods.')
