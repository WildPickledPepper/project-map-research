"""Reuse P7 known-chain acceptance with automatically discovered current modules."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'experiments/2026-10-24-p7')]
from adapters.repository_discovery import discover
from coverage_catalog import scan
from run_acceptance import run


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('source', 'build', 'runtime-store', 'output'): p.add_argument('--'+key, type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    request = json.loads((a.build/'request.json').read_text(encoding='utf-8'))
    discovery = discover(a.source, request['source_commit'])
    inventory = {'source_commit': request['source_commit'], 'tracked_files': len(discovery['files']),
        'modules': [{**m, 'file_count': m['files'],
            'metadata': [{'path': path, 'line': 1, 'kind': 'tracked_build_manifest'} for path in m['manifests']],
            'dependencies': [], 'dependency_scan': 'not_performed_in_legacy_overview_adapter'} for m in discovery['modules']],
        'origin': 'A1_automatic_discovery_for_known_P7_regression'}
    catalog = scan(a.source, request)
    for name, value in [('inventory.json', inventory), ('catalog.json', catalog)]:
        (a.output/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    result = run(a.build/'graph.json', a.output/'inventory.json', a.output/'catalog.json', a.runtime_store, a.output/'queries')
    print(json.dumps({'passed': result['passed'], 'checks': result['checks']}))
    sys.exit(0 if result['passed'] else 1)
