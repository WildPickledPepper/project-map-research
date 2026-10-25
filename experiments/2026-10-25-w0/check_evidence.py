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
print('OK: W0 scope checkpoint, 46 checks, 7 effective controls; G01 remains in progress.')
