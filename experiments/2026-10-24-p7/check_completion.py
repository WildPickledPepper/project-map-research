"""Check the portable P7 acceptance package, without source checkout or hashes."""
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE/'evidence'


def read(name):
    return json.loads((EVIDENCE/name).read_text(encoding='utf-8'))


def main():
    validation = read('validation.json')
    assert validation['passed'] and len(validation['checks']) == 20
    assert all(validation['checks'].values())
    assert validation['rebuild']['status'] == 'passed'
    assert not validation['rebuild']['differing_top_level_keys']
    assert validation['rebuild']['first'] != validation['rebuild']['second']
    assert validation['counts']['input_files'] == 191
    assert validation['counts']['nodes'] == 31298 and validation['counts']['edges'] == 45196
    assert not validation['whole_repository_semantics']
    assert validation['P6'] == 'pending_external_assets' and validation['memory_runtime'] == 'not_executed'
    chains = {c['api']: c for c in validation['chains']}
    assert set(chains) == {'getUnitFlows', 'queryTimelineOffset', 'memoryCurveGet'}
    assert len({c['provider'] for c in chains.values()}) == 3
    for api in ('getUnitFlows', 'memoryCurveGet'):
        chain = chains[api]['chain']
        assert chain['status'] == 'conditional_source_chain' and chain['summary']['states']
        assert chain['conditions'] and chain['unexpanded']
    assert validation['negative_results'] == {
        'delete_provider': 'unmatched', 'change_command': 'unmatched',
        'different_module': 'unmatched', 'removed_field_links': 0}
    catalog, inventory = read('coverage-summary.json'), read('inventory.json')
    assert catalog['source_commit'] == inventory['source_commit'] == validation['source_commit']
    assert catalog['snapshot'] == validation['snapshot']
    assert catalog['scan'] == {'tracked_files': 4855, 'not_source_or_manifest': 2368, 'text_scanned': 2487}
    assert not catalog['unread'] and len(catalog['capabilities']) == 18
    assert inventory['tracked_files'] == sum(g['tracked_files'] for g in catalog['top_level_groups'])
    assert len(inventory['modules']) == 34
    languages = {x['name']: x for x in catalog['languages']}
    for name, count in [('Python', 119), ('Rust', 13)]:
        assert languages[name]['tracked_files'] == count and languages[name]['graph_input_files'] == 0
    for capability in catalog['capabilities']:
        assert len(capability['evidence']) <= 3
        assert capability['evidence_truncated'] == (capability['evidence_total'] > 3)
    first, probe = read('first-pass.json'), read('instrumented-regression.json')
    assert first['first_result_preserved'] and first['publication'] == 'failed'
    assert first['protocols']['Memory/view/memoryUsage'] == 'unmatched'
    assert not probe['passed'] and not probe['checks']['getUnitFlows_return_to_state']
    assert probe['source_commit'] != validation['source_commit']
    review, usage = read('ai-review.json'), read('ai-usage.json')
    assert review['method'] == 'coordinator_manual_review_against_frozen_required_facts_and_evidence'
    assert review['status'] == 'passed_after_remediation'
    assert usage['tokens'] == usage['context_tokens'] == 'not_exposed'
    task_ids = {f'T{i:02}' for i in range(1, 12)}
    trials = {t['participant']: t for t in usage['trials']}
    assert set(trials) == {'a', 'b', 'upstream'}
    assert {t['participant']: t['passed_tasks'] for t in review['trials']} == {'a': 10, 'b': 11, 'upstream': 11}
    for scored in review['trials']:
        name = scored['participant']; metadata = trials[name]['input']
        assert not metadata['gold_included']
        assert len(scored['tasks']) == 11 and {t['task'] for t in scored['tasks']} == task_ids
        assert sum(t['passed'] for t in scored['tasks']) == scored['passed_tasks']
        answers = read(f'ai-{name}-answers.json')
        assert {a['id'] for a in answers} == task_ids
        assert all(a['answer'] and a['evidence'] for a in answers)
        assert {t['task'] for t in trials[name]['tasks']} == task_ids
        if name == 'upstream':
            assert metadata['source_commit'] == validation['source_commit']
            assert metadata['tasks_version'] == 'p7-ai-tasks/3-upstream'
    assert review['P6'] == 'pending_external_assets'
    for file in EVIDENCE.iterdir():
        if file.suffix in {'.json', '.jsonl', '.md'}:
            assert not re.search(r'[A-Za-z]:[\\/](?:Users|workspace)[\\/]', file.read_text(encoding='utf-8')), file.name
    print('OK: P7 Q01-Q05 independent scope; 20 source checks, first failures and isolated AI review retained; P6 pending.')


if __name__ == '__main__':
    main()
