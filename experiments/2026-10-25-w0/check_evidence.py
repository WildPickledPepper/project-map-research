"""Validate the published W0 checkpoint within its executed scope."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
review = json.loads((ROOT / 'evidence/scope-review.json').read_text(encoding='utf-8'))
controls = json.loads((ROOT / 'evidence/controls.json').read_text(encoding='utf-8'))
reference = json.loads((ROOT / 'scope-reference.json').read_text(encoding='utf-8'))
assert review['source_commit'] == controls['source_commit'] == reference['source_commit']
assert review['scope_checks_passed'] and len(review['checks']) == 46
assert all(c['passed'] for c in review['checks'])
assert review['summary']['tracked_files'] == 4855
assert review['summary']['unclassified_files'] == 0
assert review['summary']['logical_components'] == 166
assert review['summary']['required_runtime_components'] == 126
assert review['summary']['required_support_components'] == 4
assert review['summary']['mechanism_families'] == 18
assert review['module_obligations']['count'] == 903
assert len(review['required_modes']) == 13
assert all(m['execution_status'] == 'not_executed' for m in review['required_modes'])
assert review['G01'] == 'in_progress' and review['G01_remaining']
assert review['overall_technical_acceptance'] == 'not_passed' and not review['runtime_executed']
assert controls['passed'] and len(controls['controls']) == 7
assert not controls['source_modified']
assert all(c['passed'] and c['expected_failure'] in c['actual_failures'] for c in controls['controls'])
assert review['regression']['python'] == {'run': 370, 'passed': 370, 'skipped': 0}
assert review['regression']['typescript'] == {'run': 110, 'passed': 110}
print('OK: initial W0 checkpoint, 46 checks and 7 controls; original in-progress result retained.')

frozen = json.loads((ROOT/'evidence/freeze.json').read_text(encoding='utf-8'))
freeze_controls = json.loads((ROOT/'evidence/freeze-controls.json').read_text(encoding='utf-8'))
assert frozen['source_commit'] == reference['source_commit']
assert frozen['rules_version'] == 'a328dcd7ca1506ec36fbbb3f80b1066edecc2536'
assert frozen['audit_version'] == '8c2f114bc66e77b53b2b3f92923d1a4d7adbc1dd'
assert frozen['G01'] == 'passed' and len(frozen['checks']) == 388
assert all(c['passed'] for c in frozen['checks'])
assert len(frozen['modules']) == frozen['summary']['reviewed_required_components'] == 129
assert frozen['summary']['reviewed_runtime_components'] == 124
assert frozen['summary']['reviewed_support_components'] == 5
assert len(frozen['runtime_modes']) == 85 and len(frozen['required_module_modes']) == 129
assert all(row['mode_ids'] for row in frozen['required_module_modes'])
assert all(m['execution_status'] == 'not_executed' for m in frozen['runtime_modes'])
assert len(frozen['boundary_references']) == 19
assert len(frozen['configuration_axes']) == 103 and len(frozen['programs']) == 22
assert len(frozen['unresolved_dependencies']) == 2
assert frozen['gates_G02_G08'] == 'not_accepted'
assert frozen['overall_technical_acceptance'] == 'not_passed'
assert not frozen['runtime_executed'] and not frozen['historical_assets_enabled']
assert len(freeze_controls['controls']) == 7 and freeze_controls['passed']
assert all(c['passed'] and c['expected_failure'] in c['actual_failures'] for c in freeze_controls['controls'])
assert frozen['regression']['python'] == {'run':374,'passed':374,'skipped':0}
print('OK: W0 final scope freeze, 388 checks and 7 effective controls; G01 passed, G02-G08 remain unaccepted.')
