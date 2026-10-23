"""Controllable synthetic builder for process-crash and publication tests."""
import argparse
import json
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.snapshot_refresh import Refresher

VERSION = {'rules': 'synthetic_refresh_test'}


def synthetic_builder(source, request, output, log):
    nodes = [{'id': 'fixture:' + path, 'kind': 'synthetic_file', 'path': path, 'line': 1,
              'name': path, 'content': (source/path).read_text(encoding='utf-8')} for path in request['input_paths']]
    graph = {'snapshot': request['snapshot'], 'source_commit': request['source_commit'],
             'version': {k: request[k] for k in ['source_commit', 'snapshot', 'config', 'build_version']},
             'input_paths': request['input_paths'], 'nodes': nodes, 'edges': [],
             'provenance': {'working_tree_included': False, 'evidence_kind': 'synthetic_controller_test'}}
    (output/'graph.json').write_text(json.dumps(graph), encoding='utf-8')
    return {'nodes': len(nodes), 'edges': 0, 'files': len(nodes), 'storage': 'json', 'storage_roundtrip': False}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    for key in ['source', 'store', 'config', 'ready']: ap.add_argument('--'+key, type=Path, required=True)
    a = ap.parse_args()

    def blocked_builder(source, request, output, log):
        synthetic_builder(source, request, output, log)
        a.ready.write_text('builder is waiting with a private partial graph', encoding='utf-8')
        threading.Event().wait(30)
        raise RuntimeError('Test failed to terminate the waiting worker')

    refresher = Refresher(a.source, a.store, lambda: json.loads(a.config.read_text(encoding='utf-8')),
                          lambda: VERSION, blocked_builder)
    refresher.run()
