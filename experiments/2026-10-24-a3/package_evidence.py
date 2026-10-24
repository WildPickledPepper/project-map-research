"""Package compact, portable A3 evidence from external experiment directories."""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.project_map import ProjectMap


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def package(results, destination):
    destination.mkdir(parents=True, exist_ok=True)
    delivery = results / 'a3-delivery-02'
    acceptance = results / 'a3-acceptance-final-01'
    def save(name, data):
        text = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
        if re.search(r'[A-Za-z]:[\\/](?:Users|workspace)[\\/]', text):
            raise ValueError('Machine-specific workspace path in evidence: ' + name)
        (destination / name).write_text(text, encoding='utf-8')
    save('validation.json', read(acceptance / 'validation.json'))
    save('index.json', read(delivery / 'build.json'))
    save('cost.json', read(delivery / 'cost.json'))
    save('baseline.json', read(results / 'a3-baseline-01/result.json'))
    first = read(results / 'a3-delivery-01/cost.json')
    for name, row in first['queries'].items():
        result = read(results / 'a3-delivery-01' / (name + '.json'))
        row.update(query_stop_reason=result.get('stop_reason'), query_status=result.get('search_status'),
            elapsed_query_seconds=result['elapsed_seconds'])
    first['interpretation'] = 'process status is separate from query completion; trace reached its wall-time budget'
    save('cost-first.json', first)
    save('first-failures.json', {'evidence_kind': 'retained_executed_first_failures', 'items': [
        {'phase': 'authored_controls_first', 'passed': 11, 'total': 12,
            'failure': 'sub-tick deadline was not observed with Windows monotonic clock',
            'fix': 'use perf_counter for query deadlines; retain real deadline test'},
        {'phase': 'full_acceptance_first', 'status': 'stopped',
            'failure': 'harness treated output-budget continuation as a failed file-list query',
            'fix': 'accept output_budget only with returned items and a next cursor; continue paging'},
        {'phase': 'navigation_cost_first', 'status': 'trace_wall_budget',
            'failure': 'SQLite chose snapshot/ordinal scan for each adjacency read',
            'fix': 'add snapshot/source/ordinal and snapshot/target/ordinal indexes'},
        {'phase': 'typescript_environment_first', 'failed_test_files': 6,
            'failure': 'typescript dependency was unavailable because NODE_PATH was unset',
            'fix': 'set NODE_PATH to the existing pinned TypeScript installation; final 88 tests passed'}]})
    python_log = (results / 'a3-python-tests.txt').read_text(encoding='utf-8')
    ts_log = (results / 'a3-typescript-tests.txt').read_text(encoding='utf-8')
    py = re.search(r'Ran (\d+) tests in ([0-9.]+)s', python_log)
    ts = re.search(r'# tests (\d+)', ts_log)
    if not py or not ts or not python_log.rstrip().endswith('OK') or '# fail 0' not in ts_log:
        raise ValueError('Final test logs must pass')
    save('tests.json', {'evidence_kind': 'executed_local_complete_test_suites',
        'python': {'passed': int(py[1]), 'seconds': float(py[2]), 'failures': 0},
        'typescript': {'passed': int(ts[1]), 'failures': 0}, 'new_navigation_controls': 15,
        'historical_validation_candidates': 'not_used'})
    q = ProjectMap(delivery / 'map.sqlite')
    try:
        save('overview.json', q.overview(limit=100))
        save('entries.json', read(acceptance / 'entries.json'))
        witnesses = []
        for api in ('getUnitFlows', 'queryTimelineOffset', 'memoryCurveGet'):
            forward = read(acceptance / (api + '-forward.json'))
            reverse = read(acceptance / (api + '-reverse.json'))
            ids = [forward['start']] + [e['target'] for e in forward['items']]
            nodes = [q.status(uid)['items'][0] for uid in ids]
            witnesses.append({'api': api, 'forward': forward, 'reverse': reverse, 'nodes': nodes,
                'source': read(acceptance / (api + '-source.json'))})
        save('protocol-witnesses.json', witnesses)
    finally:
        q.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results', type=Path, required=True)
    p.add_argument('--output', type=Path, default=Path(__file__).parent / 'evidence')
    a = p.parse_args()
    package(a.results, a.output)
    print('Packaged portable A3 evidence')
