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
