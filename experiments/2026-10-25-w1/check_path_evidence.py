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
