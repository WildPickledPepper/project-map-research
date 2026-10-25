"""Check portable evidence for the scoped static connections and A5 preparation."""
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
def load(name):return json.loads((HERE/'evidence'/name).read_text(encoding='utf-8'))

if __name__=='__main__':
    evaluation=load('evaluation.json');chains=load('chains.json');failures=load('development-failures.json')
    assert evaluation['static_connection_acceptance_passed']
    assert all(evaluation['static_connection_gates'].values())
    assert evaluation['a5_preparation_completed'] and all(evaluation['runtime_preparation_gates'].values())
    assert evaluation['new_product_runtime_scenarios']==0
    assert evaluation['historical_validation_records_used_for_tuning'] is False
    assert evaluation['loop_iteration_budget']==3
    assert chains['all_five_connections'] and len(chains['cases'])==5
    assert not chains['unpublished_callback_component_substitution']
    assert re.fullmatch('[0-9a-f]{40}',chains['facts_version']['rules_commit'])
    for case in chains['cases']:
        assert case['connected'] and case['providers'] and case['consumer_samples']
        assert all(q['status']=='conditional_return_to_frontend_state' and 'truncated' in q and 'gaps' in q for q in case['queries'])
        for sample in case['consumer_samples']:
            assert sample['source']['name']==case['consumer']
            assert sample['mode']==case['expected_mode'] and sample['field_mappings']
    assert all(not c['connected'] for c in failures['first_five_connections'])
    assert failures['initial_authored_checks']['counts']=={'tests':8,'pass':3,'fail':5}
    assert failures['initial_authored_checks']['original_failures_pass_after_repair']
    assert failures['first_a4_scoring_budget_stop']['status']=='budget_stopped'
    known=load('known-regression.json');navigation=load('navigation.json');updates=load('updates.json')
    replay=load('a4-regression.json');protocols=load('protocol-regression.json')
    for key in ['correct_protocol_pairs','producer_forward_paths','producer_reverse_paths','serialized_field_relations']:
        assert replay['counts'][key]==6
    assert replay['counts']['wrong_protocol_pairs']==0 and replay['counts']['return_state_relations']==2
    assert protocols['new_protocol_passed'] and protocols['final_protocol_passed'] and len(protocols['cases'])==5
    assert all(c['outcome']=='correct_unique_conditional' for c in protocols['cases'])
    assert chains['snapshot']==known['snapshot']==navigation['snapshot']==replay['snapshot']
    assert chains['facts_version']==known['build_version']==navigation['build_version']==replay['build_version']==updates['build_version']
    assert known['passed'] and len(known['checks'])==19 and all(known['checks'].values())
    assert navigation['passed'] and len(navigation['checks'])==26 and all(navigation['checks'].values())
    assert updates['passed'] and len(updates['checks'])==13 and all(updates['checks'].values())
    assert load('frontend-repeat.json')['equal']
    print('OK: five conditional connections; 19 known, 26 navigation, 13 refresh checks; A5 environment prepared; product runs remain 0.')
