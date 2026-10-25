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
print('OK: 62 native CMake checks; product graph and boundary acceptance remain pending.')
