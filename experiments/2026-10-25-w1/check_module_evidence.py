"""Validate published component accounting without accepting semantic gates."""
from collections import Counter
import json
from pathlib import Path

base = Path(__file__).parent / 'evidence'
data = json.loads((base / 'module-fact-audit.json').read_text(encoding='utf-8'))
facts = json.loads((base / 'multilang-repository-rust.json').read_text(encoding='utf-8'))
assert data['passed'] and len(data['checks']) == 6 and all(c['passed'] for c in data['checks'])
assert (data['source_commit'], data['snapshot'], data['build_version'], data['index_counts']) == (
    facts['source_commit'], facts['snapshot'], facts['build_version'], facts['index_counts'])
modules = data['modules']
assert len(modules) == len({m['id'] for m in modules}) == data['scope_basis']['required_components'] == 129
assert sum(m['required_runtime_component'] for m in modules) == 124
assert sum(m['required_support_component'] for m in modules) == 5
assert sum(len(m['sources_not_parsed']) for m in modules) == 13
assert sum(len(m['sources_without_base_facts']) for m in modules) == 41
assert dict(Counter(f['language'] for m in modules for f in m['sources_without_base_facts'])) == {'shell': 7, 'typescript': 21, 'cpp': 13}
assert all(m['G02'] == 'pending_independent_semantic_review' and m['G03_G08'] == 'not_accepted_by_this_report' for m in modules)
assert sum(sum(m['outgoing_edge_kinds'].values()) for m in modules) == sum(sum(m['incoming_edge_kinds'].values()) for m in modules)
assert data['test_role_disagreements'] == [{'path': 'server/build_fuzz/execute_fuzz_test.sh', 'audited_role': 'test', 'discovery_role': 'product'}]
assert not any(data[k] for k in ('whole_G02_accepted', 'overall_technical_acceptance', 'runtime_execution', 'historical_assets_enabled'))
print('OK: 129 component accounting records; concrete review queue retained; G02 pending.')
