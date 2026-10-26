"""Publish compact whole-input provider observations without raw databases/logs."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.cbm_provider import read_native


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('cbm', 'clang', 'inventory', 'output'):
        ap.add_argument('--' + name, required=True, type=Path)
    args = ap.parse_args()
    if args.output.exists():
        ap.error('Choose a new output file')
    receipt = load(args.cbm / 'receipt.json')
    clang = load(args.clang / 'facts.json')
    final = load(args.clang / 'result.json')
    inventory = load(args.inventory)
    revision = inventory['source_commit']
    assert receipt['source_commit'] == clang['components']['source_commit'] == final['source_commit'] == revision
    cbm = read_native(args.cbm / 'native.db', project=receipt['project'], paths=receipt['input_paths'],
                      source_commit=revision, provider_version=receipt['version'])
    roles = {r['path']: r['scope_role'] for r in inventory['files']}
    product = {p for p, role in roles.items() if role in {'first_party', 'build_support', 'deployment_support'}}
    diagnostics = []
    for row in clang['coverage']:
        if row['status'] != 'parsed' and row['path'] in product:
            errors = [d['native'] for d in clang['diagnostics'] if d.get('path') == row['path']
                      and d.get('native', {}).get('severity') == 1]
            diagnostics.append({'path': row['path'], 'status': row['status'], 'errors': len(errors),
                'examples': [{'message': d['message'].splitlines()[0], 'range': d.get('range'), 'code': d.get('code')}
                             for d in errors[:2]]})
    result = {'schema': 'native-repository-provider-observations/1', 'source_commit': revision,
        'cbm': {'version': receipt['version'], 'adapter': receipt['adapter'], 'seconds': receipt['seconds'],
            'input_files': len(receipt['input_paths']), 'scope_policy': receipt['scope_policy'],
            'native_counts': {k: receipt['native_result'][k] for k in ('nodes', 'edges', 'not_indexed_files_count',
                'skipped_count', 'parse_partial_count', 'parse_unusable_count')},
            'imported_nodes': len(cbm['nodes']), 'imported_edges': len(cbm['edges']),
            'coverage_statuses': dict(Counter(r['status'] for r in cbm['coverage'])),
            'non_test_shell': [r for r in cbm['coverage'] if r['path'].endswith('.sh') and r['path'] in product],
            'precision': 'inferred_native_relations_remain_candidate'},
        'clangd': {'components': {k: v for k, v in clang['components'].items()
                    if k in {'provider', 'adapter', 'version', 'multilspy', 'context', 'source_commit', 'precision_policy'}},
            'files': len(clang['coverage']), 'nodes': len(clang['nodes']), 'edges': len(clang['edges']),
            'coverage_statuses': dict(Counter(r['status'] for r in clang['coverage'])),
            'non_test_statuses': dict(Counter(r['status'] for r in clang['coverage'] if r['path'] in product)),
            'reference_budget_residuals': sum(r.get('reference_budget_exhausted', False) for r in clang['coverage']),
            'retried_budget_files': final['retried_files'], 'retry_seconds': final['seconds'],
            'non_test_diagnostics': diagnostics,
            'diagnostic_context_precision': 'candidate; original_diagnostics_and_native_AST_retained'},
        'whole_R1_passed': False, 'whole_G02_accepted': False, 'runtime_execution': False,
        'historical_assets_enabled': False, 'hash_verification': 'not_run_per_user_preference'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'cbm_files': result['cbm']['input_files'], 'clang_files': result['clangd']['files'],
                      'non_test_diagnostic_files': len(diagnostics)}))


if __name__ == '__main__':
    main()
