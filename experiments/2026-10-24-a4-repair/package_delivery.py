"""Package measured repair results, preserving the original failed evaluation."""
import argparse
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent


def read(path): return json.loads(path.read_text(encoding='utf-8'))


def run(results,output):
    output.mkdir(parents=True,exist_ok=True)
    paths={
        'chains.json':results/'a4-repair-scoring-01/development-replay/first-results.json',
        'retest.json':results/'a4-repair-scoring-01/result.json',
        'navigation.json':results/'a4-repair-navigation-01/result.json',
        'direct-updates.json':results/'a4-repair-direct-updates-03/result.json',
        'rebuild.json':results/'a4-repair-comparison-01/comparison.json',
        'known-regression.json':results/'a4-repair-known-01/queries/validation.json',
        'publication.json':results/'a4-repair-publication-01/result.json',
    }
    data={name:read(path) for name,path in paths.items()}
    builds=[read(results/name/'result.json') for name in ['a4-repair-full-04','a4-repair-full-05']]
    versions=[read(results/name/'build/request.json')['build_version'] for name in ['a4-repair-full-04','a4-repair-full-05']]
    data['builds.json']={'runs':builds,'build_versions':versions,'concurrent_execution':True}
    python=(results/'a4-repair-python-04.txt').read_text(encoding='utf-8')
    typescript=(results/'a4-repair-typescript-03.txt').read_text(encoding='utf-8')
    data['tests.json']={'python':{'count':int(re.search(r'Ran (\d+) tests',python)[1]),'passed':'\nOK' in python and 'FAILED' not in python},
        'typescript':{'count':int(re.search(r'# tests (\d+)',typescript)[1]),'passed':'# fail 0' in typescript}}
    chain,counts=data['chains.json'],data['chains.json']['counts']
    gates={
        'six_protocol_pairs_correct_without_extra':counts['scored']==6 and counts['correct_protocol_pairs']==6 and counts['wrong_protocol_pairs']==0,
        'six_producer_paths_bidirectional':counts['producer_forward_paths']==6 and counts['producer_reverse_paths']==6,
        'six_serialized_field_relations':counts['serialized_field_relations']==6,
        'both_named_frontend_states_connected':counts['return_state_relations']==2,
        'selected_queries_not_truncated':not any(c.get('query_truncated') or c.get('scoring_error') for c in chain['cases']),
        'three_supplementary_development_protocol_cases':data['retest.json']['new_protocol_passed'],
        'two_final_frozen_protocol_cases':data['retest.json']['final_protocol_passed'],
        'full_navigation_fidelity_and_direct_entries':data['navigation.json']['passed'],
        'thirteen_real_refresh_controls':data['direct-updates.json']['passed'] and len(data['direct-updates.json']['checks'])==13,
        'nineteen_known_chain_regressions':data['known-regression.json']['passed'] and len(data['known-regression.json']['checks'])==19,
        'complete_rebuild_equal':data['rebuild.json']['equal'],
        'full_builds_within_budgets':all(b['status']=='passed' and b['elapsed_seconds']<b['budgets']['wall_seconds'] and b['peak_tree_working_set_bytes_observed']<b['budgets']['process_tree_working_set_bytes'] for b in builds),
        'controller_full_graph_validation':data['publication.json']['measured']['status']=='passed',
        'tests_passed':all(t['passed'] for t in data['tests.json'].values()),
        'same_rule_version':versions[0]==versions[1]==data['navigation.json']['build_version']==data['retest.json']['build_version']==data['direct-updates.json']['build_version'],
    }
    data['evaluation.json']={'evidence_kind':'executed_post_repair_A4_acceptance','tool_acceptance_passed':all(gates.values()),'gates':gates,
        'source_commit':data['navigation.json']['source_commit'],'build_version':versions[0],
        'original_failed_evaluation_preserved':True,'six_cases_used_for_development':True,
        'three_supplementary_cases_reused_for_development':True,
        'two_final_cases_scope':'protocol-rule holdout; complete-return robustness was subsequently repaired without adapting protocol rules to these two cases',
        'historical_validation_records_used_for_tuning':False,'new_runtime_reproductions':0,
        'file_hash_verification':'not_run_per_user_preference'}
    for name,value in data.items():
        text=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
        if re.search(r'[A-Za-z]:[\\/](?:Users|workspace)[\\/]',text):raise ValueError('Private workspace path in '+name)
        (output/name).write_text(text,encoding='utf-8')
    print(json.dumps(data['evaluation.json'],ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results',type=Path,required=True)
    p.add_argument('--output',type=Path,default=HERE/'evidence')
    a=p.parse_args();run(a.results.resolve(),a.output.resolve())
