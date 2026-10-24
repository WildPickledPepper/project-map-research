"""Check repaired A4 evidence and retention of the first negative evaluation."""
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
def read(name):return json.loads((HERE/'evidence'/name).read_text(encoding='utf-8'))

evaluation=read('evaluation.json')
assert evaluation['tool_acceptance_passed'] and all(evaluation['gates'].values())
assert evaluation['original_failed_evaluation_preserved']
assert evaluation['six_cases_used_for_development'] and evaluation['three_supplementary_cases_reused_for_development']
assert not evaluation['historical_validation_records_used_for_tuning'] and evaluation['new_runtime_reproductions']==0
old=json.loads((HERE.parent/'2026-10-24-a4/evidence/evaluation.json').read_text(encoding='utf-8'))
assert old['tool_acceptance_passed'] is False
chains=read('chains.json')
assert not chains['independent_holdout'] and chains['counts']['scored']==6
assert chains['counts']['correct_protocol_pairs']==6 and chains['counts']['wrong_protocol_pairs']==0
assert chains['counts']['producer_forward_paths']==chains['counts']['producer_reverse_paths']==6
assert chains['counts']['serialized_field_relations']==6 and chains['counts']['return_state_relations']==2
assert all(c['protocol_outcome']=='correct_unique_conditional' and not c.get('scoring_error') and not c.get('query_truncated') for c in chains['cases'])
retest=read('retest.json')
assert retest['new_protocol_passed'] and len(retest['new_protocol_cases'])==3
assert retest['final_protocol_passed'] and len(retest['final_protocol_cases'])==2
assert all(c['source_coordinate_matched'] for c in retest['final_protocol_cases'])
assert read('navigation.json')['passed'] and len(read('navigation.json')['checks'])==26
assert read('direct-updates.json')['passed'] and len(read('direct-updates.json')['checks'])==13
assert read('direct-updates.json')['fixture_origin']=='authored_direct_platform_transport_without_property_binding'
assert read('known-regression.json')['passed'] and len(read('known-regression.json')['checks'])==19
assert read('rebuild.json')['equal'] and not read('rebuild.json')['differing_top_level_keys']
assert read('publication.json')['measured']['status']=='passed'
assert read('tests.json')=={'python':{'count':339,'passed':True},'typescript':{'count':97,'passed':True}}
assert read('first-complete-repair-chains.json')['counts']['serialized_field_relations']==5
assert len(read('serializer-probe.json')['inputs'])==27
assert [c['outcome'] for c in read('first-repair.json')['new_cases']]==['correct_unique_conditional','correct_unique_conditional','omission']
assert not read('first-repair.json')['manual_stop']['partial_graph_published']
assert all(not r['complete_graph_published'] for r in read('development-failures.json')['runs'])
for path in (HERE/'evidence').glob('*.json'):
    assert not re.search(r'[A-Za-z]:[\\/](?:Users|workspace)[\\/]',path.read_text(encoding='utf-8')),path
print('OK: A4 repaired acceptance passed; original failures, development reuse and runtime scope retained')
