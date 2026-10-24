"""Check A4 delivery fidelity, including the negative tool acceptance result."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
def read(name): return json.loads((ROOT/'evidence'/name).read_text(encoding='utf-8'))

evaluation = read('evaluation.json')
assert evaluation['evaluation_complete'] and all(evaluation['delivery_checks'].values())
assert evaluation['tool_acceptance_passed'] is False
assert evaluation['extraction_rules_adapted_to_validation'] is False
assert evaluation['initial_reference_corrected_after_first_output'] is True
raw, reviewed = read('first-chain-results-raw.json'), read('reviewed-chain-results.json')
assert raw['counts']['correct_protocol_pairs'] == 2 and raw['counts']['scored'] == 6
assert reviewed['counts']['correct_protocol_pairs'] == 3 and reviewed['counts']['wrong_protocol_pairs'] == 0
assert reviewed['protocol_outcomes'] == {'identified_unknown': 1, 'correct_unique_conditional': 3, 'unmatched_expected_provider': 2}
assert reviewed['counts']['serialized_field_relations'] == 2
assert reviewed['counts']['return_state_relations'] == 0 and reviewed['counts']['state_reference_denominator'] == 2
assert not any(r.get('scoring_error') for r in reviewed['cases'])
assert len(read('history.json')['records']) == 12
assert read('history.json')['counts']['runtime_reproduced'] == 0
assert read('history-pair.json')['passed'] and len(read('history-pair.json')['versions']['before']['input_paths']) == 2
controls, updated = read('update-controls.json'), read('updated-map.json')
assert controls['passed'] and len(controls['checks']) == 13 and all(controls['checks'].values())
assert updated['update_fidelity_passed'] and len(updated['checks']) == 9
assert updated['protocol_discovery_passed'] is False and len(updated['direct_socket_sends_found']) == 2
assert updated['counts']['input_files'] == 2315 and updated['counts']['modules'] == 31
assert read('rebuild.json')['equal'] and not read('rebuild.json')['differing_top_level_keys']
assert read('rebuild.json')['counts'] == {'nodes': 271837, 'edges': 386207, 'inputs': 2315}
for run in read('full-builds.json')['runs']:
    assert run['status'] == 'passed' and run['elapsed_seconds'] < run['budgets']['wall_seconds']
    assert run['peak_tree_working_set_bytes_observed'] < run['budgets']['process_tree_working_set_bytes']
assert read('publication-validation.json')['measured']['status'] == 'passed'
known = read('known-regression.json')
assert known['passed'] and len(known['checks']) == 19 and all(known['checks'].values())
assert read('tests.json')['python']['passed'] == 334 and read('tests.json')['typescript']['passed'] == 88
assert read('first-failures.json')['items'][0]['unintended_changed_paths'] == 130
for path in (ROOT/'evidence').glob('*.json'):
    assert not re.search(r'[A-Za-z]:[\\/](?:Users|workspace)[\\/]', path.read_text(encoding='utf-8')), path
print('OK: A4 evaluation delivered; negative connection/discovery acceptance retained; updates/rebuild/regression passed')
