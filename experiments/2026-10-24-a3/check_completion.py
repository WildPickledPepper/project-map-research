"""Validate portable A3 delivery evidence without loading external graphs."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
def read(name):
    return json.loads((ROOT / 'evidence' / name).read_text(encoding='utf-8'))

validation, index, cost = read('validation.json'), read('index.json'), read('cost.json')
assert validation['passed'] and len(validation['checks']) == 27 and all(validation['checks'].values())
assert validation['source_commit'] == 'd4e8d1cf9f90208bcbe5371c127088f6fd66c688'
assert validation['snapshot'] == index['snapshot']
assert validation['navigation_version'] == index['navigation_version']
assert validation['counts'] == index['counts']
expected = {'tracked_files': 4855, 'input_files': 2310, 'modules': 29, 'nodes': 271737,
    'edges': 386100, 'entries': 136, 'providers': 109, 'diagnostic_records': 33154, 'module_relation_groups': 143}
assert index['counts'] == expected
assert validation['details']['entries']['assessed'] == 126
assert validation['historical_validation_candidates'] == 'not_used'
assert cost['build']['status'] == 'passed' and cost['index_bytes'] > 0
assert len(cost['queries']) == 7
for query in cost['queries'].values():
    assert query['status'] == 'passed' and query['query_stop_reason'] is None
    assert query['elapsed_seconds'] < query['process_budgets']['seconds']
    assert query['peak_tree_working_set_bytes_observed'] < query['process_budgets']['working_set_bytes']
tests = read('tests.json')
assert tests['python']['passed'] == 329 and tests['typescript']['passed'] == 88
assert tests['new_navigation_controls'] == 15
entries = read('entries.json')
assert len(entries) == 136 and sum(e['node'] is not None for e in entries) == 126
witnesses = read('protocol-witnesses.json')
assert len(witnesses) == 3
for row in witnesses:
    assert row['forward']['found'] and row['reverse']['found'] and len(row['forward']['items']) == 5
    assert not row['source']['working_tree_read']
    assert row['forward']['snapshot'] == index['snapshot']
assert len(read('overview.json')['items']) == 29
assert read('baseline.json')['file_hash_verification'] == 'not_run_per_user_preference'
assert read('cost-first.json')['queries']['trace']['query_stop_reason'] == 'wall_time_budget'
assert len(read('first-failures.json')['items']) == 4
for path in (ROOT / 'evidence').glob('*.json'):
    assert not re.search(r'[A-Za-z]:[\\/](?:Users|workspace)[\\/]', path.read_text(encoding='utf-8')), path
assert (ROOT / 'evidence/project-map.md').exists()
print('OK: A3 full-graph navigation; 27 acceptance checks, 15 controls, 329 Python / 88 TypeScript tests')
