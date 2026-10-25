"""Check that the independent scope evaluator rejects concrete inventory defects."""
from copy import deepcopy
import argparse
import json
from pathlib import Path
import tempfile

from verify_scope import verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Choose a new controls output directory')
    reference = json.loads(Path(__file__).with_name('scope-reference.json').read_text(encoding='utf-8'))
    original = {p.name: json.loads(p.read_text(encoding='utf-8')) for p in args.inventory.glob('*.json')}
    cases = [
        ('missing_file', 'all_committed_paths_exactly_once',
         lambda d: d['module-inventory.json']['files'].pop()),
        ('missing_proxy_module', 'all_required_scopes_discovered',
         lambda d: d['module-inventory.json'].update(modules=[m for m in d['module-inventory.json']['modules']
                                                            if m['id'] != 'plugins/ProfilerServerProxy'])),
        ('invented_edge', 'signals_are_candidates_with_unresolved_counterparts',
         lambda d: d['boundary-inventory.json']['boundaries'][0].update(counterpart='invented_target')),
        ('hidden_rust_gap', 'required_language_gaps_remain_visible',
         lambda d: d['coverage-baseline.json']['whole_project_languages_missing'].remove('rust')),
        ('empty_mechanism_marked_inapplicable', 'no_signal_remains_unknown',
         lambda d: next(r for r in d['mechanism-matrix.json']['items'] if r['signal_count'] == 0)
                        .update(applicability='not_applicable')),
        ('wrong_source_revision', 'all_documents_same_source_and_rules',
         lambda d: d['runtime-modes.json'].update(source_commit='incorrect_revision')),
        ('overall_pass_with_missing_semantics', 'no_historical_asset_input_or_overall_pass',
         lambda d: d['coverage-baseline.json'].update(overall_technical_acceptance='passed')),
    ]
    results = []
    with tempfile.TemporaryDirectory(prefix='scope-evaluator-controls-') as folder:
        for name, expected, mutation in cases:
            docs = deepcopy(original)
            mutation(docs)
            dest = Path(folder) / name
            dest.mkdir()
            for path, doc in docs.items():
                (dest / path).write_text(json.dumps(doc), encoding='utf-8')
            actual = verify(args.source, dest, reference)
            failures = [c['id'] for c in actual['checks'] if not c['passed']]
            results.append({'id': name, 'expected_failure': expected, 'actual_failures': failures,
                            'passed': expected in failures and not actual['scope_checks_passed']})
    result = {'schema': 'scope-review-controls/1', 'source_commit': reference['source_commit'],
              'mutation_target': 'temporary_inventory_outputs_only', 'source_modified': False,
              'controls': results, 'passed': all(r['passed'] for r in results)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
