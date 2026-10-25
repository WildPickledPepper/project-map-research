"""Validate the portable native-component receipt, separately from product acceptance."""
import json
from pathlib import Path, PurePosixPath

data = json.loads((Path(__file__).parent / 'evidence/cmake-native-probe.json').read_text(encoding='utf-8'))
assert data['schema'] == 'cmake-native-component-probe/1'
assert data['cmake'] == 'cmake version 3.31.6'
assert data['origin'] == 'executed_independent_fixtures_unmodified_native_cmake'
assert data['passed'] and len(data['checks']) == 62 and all(r['passed'] for r in data['checks'])
assert {r['id'] for r in data['records']} == {'nested.base', 'nested.extra', 'renamed.base', 'renamed.extra'}
for row in data['records']:
    assert row['configuration'] == 'Release' and row['native_version'] == '3.31.6'
    assert row['codemodel_version']['major'] == 2
    assert row['target_name'] not in PurePosixPath(row['artifacts'][0]).name
    assert row['dependencies'] and all(not PurePosixPath(p).is_absolute() and ':' not in p for p in row['artifacts'] + row['sources'])
    assert any(p.endswith('/startup.cpp') for p in row['sources'])
    assert any(p.endswith('/extra.cpp') for p in row['sources']) == row['feature']
    assert {'add_executable', 'register_program'} <= {r.get('command') for r in row['declaration']}
assert not any(data[k] for k in ('product_repository_configured', 'product_built', 'production_graph_generated',
                               'process_counterpart_connected', 'whole_G02_accepted', 'whole_G03_accepted'))
product = json.loads((Path(__file__).parent / 'evidence/cmake-native-repository.json').read_text(encoding='utf-8'))
assert product['passed'] and len(product['checks']) == 24 and all(r['passed'] for r in product['checks'])
assert product['source_commit'] == 'd4e8d1cf9f90208bcbe5371c127088f6fd66c688' and product['source_export_files'] == 1417
assert product['tools']['cmake'] == 'cmake version 3.31.6' and product['configuration'] == 'Release' and product['generator'] == 'Ninja'
assert product['target_type_counts'] == {'UTILITY': 28, 'SHARED_LIBRARY': 3, 'EXECUTABLE': 1, 'STATIC_LIBRARY': 1}
assert product['selected_target_source_count'] == 408 and product['selected_target']['type'] == 'EXECUTABLE'
assert product['entry'][0]['path'] == 'server/src/entry/server/bin/main.cpp'
assert product['linked_targets'] == ['msinsight', 'sqlite', 'uv_a']
assert product['first_failure']['returncode'] != 0 and not product['first_failure']['successful_reply_available']
assert not any(product[k] for k in ('product_source_compiled', 'product_executed', 'production_graph_generated',
                                  'process_counterpart_connected', 'whole_G02_accepted', 'whole_G03_accepted'))
failed=json.loads((Path(__file__).parent/'evidence/cmake-production-first-failure.json').read_text(encoding='utf-8'))
production=json.loads((Path(__file__).parent/'evidence/cmake-production.json').read_text(encoding='utf-8'))
assert not failed['passed'] and failed['index_counts']['input_files']==1334 and not failed['native_node_counts']
assert any(not c['passed'] and c['id']=='complete_cpp_cmake_control_scope' for c in failed['checks'])
assert production['passed'] and len(production['checks'])==32 and all(c['passed'] for c in production['checks'])
assert production['source_commit']==failed['source_commit']==product['source_commit']
assert production['scope']==failed['scope']=='cmake_cpp_control'
assert production['index_counts']['input_files']==1336 and production['index_counts']['nodes']==217840 and production['index_counts']['edges']==343093
assert production['build_version']['rules_commit']=='07dcab66e14cdc5e94e4e7074320dbb7632388ee'
assert production['native_node_counts']['build_configuration']==1 and production['native_node_counts']['build_target']==33
assert production['selected_target_sources']['total']==408
assert production['entry']['path']=='server/src/entry/server/bin/main.cpp'
assert production['primary_artifact']['location']=={'root':'source','path':'server/output/win_mingw64/bin/profiler_server.exe'}
assert len(production['navigation'])==6 and all(r['found'] and r['stop_reason'] is None for r in production['navigation'])
assert production['process_counterpart_status']=='pending_packaging_path_and_runtime_program_identity'
assert not any(production[k] for k in ('runtime_execution','product_compiled','whole_G02_accepted','whole_G03_accepted'))
print('OK: 62 fixture, 24 native and 32 production CMake checks; first failure retained; process pairing pending.')

system=json.loads((Path(__file__).parent/'evidence/cmake-system-replay.json').read_text(encoding='utf-8'))
assert system['schema']=='cmake-system-replay-score/1' and system['passed']
assert len(system['checks'])==23 and all(c['passed'] for c in system['checks'])
assert system['source_commit']==production['source_commit']
assert system['build_version']['rules_commit']=='45a9fdca0bfe98c562d43532e07ec3b6bd8b41ac'
assert system['build_version']['reused_cpp_facts']['rules_commit']==production['build_version']['rules_commit']
assert system['index_counts']['input_files']==1336 and system['index_counts']['nodes']==217840 and system['index_counts']['edges']==343093
assert system['target_system']['name']==system['target_system']['host_name']=='Windows'
assert system['target_system']['host_path_style']==system['target_system']['target_path_style']=='windows'
assert system['target_system']['cross_compiling'] is False
assert system['target_system']['processor_interpretation']=='cmake_system_processor_not_verified_compiler_architecture'
assert system['native_relocation']['build_root_relocated'] and system['native_relocation']['source_root_relocated']
assert len(system['navigation'])==4 and all(n['found'] and n['snapshot_matches'] and n['stop_reason'] is None for n in system['navigation'])
assert system['native_normalizer_executed_again'] and not any(system[k] for k in (
    'native_configure_executed_again','cpp_extraction_executed_again','default_workspace_rebuild','runtime_execution','original_checkout_modified',
    'production_copy_edges_emitted','process_counterpart_connected','whole_G02_accepted','whole_G03_accepted'))
assert system['file_hash_verification']=='not_run_per_user_preference'
print('OK: 23 current native-system replay/index checks; target and host bound; copy/process propagation pending.')
