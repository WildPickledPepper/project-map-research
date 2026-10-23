"""Validate the published callback evidence and its remaining transport scope."""
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'experiments/2026-10-23-p3'))
from run_response_routing import expand


def check():
    base = ROOT / 'experiments/2026-10-23-p3'
    raw = (base / 'evidence/response-callbacks.json').read_text(encoding='utf-8')
    assert not re.search(r'[A-Za-z]:[\\/]+Users[\\/]', raw)
    packed = json.loads(raw); report = expand(packed)
    manifest = json.loads((base / 'response-manifest.json').read_text(encoding='utf-8'))
    assert report['source_commit'] == manifest['source_commit']
    assert report['snapshot'] == report['source_commit'] + ':p3-data-v7'
    assert report['counts']['files'] == len(manifest['files']) == 148
    assert report['phase_status'] == 'P3_in_progress' and report['gate_under_test'] == 'D02_incomplete'
    assert re.fullmatch('[0-9a-f]{40}', report['rules_revision'])
    ws, frame = report['queries']['Connection.fetch'], report['queries']['ClientConnector.fetch']
    assert ws['total_deliveries'] == 3 and frame['total_deliveries'] == 2
    for query in [ws, frame]:
        assert not query['truncated'] and not query['extraction_truncated']
        assert query['transport_status'] == 'network_and_API_boundary_join_pending'
        assert len(query['registrations']) == 1 and not query['unmatched_lookups']
        for d in query['deliveries']:
            r, lookup, s = d['registration'], d['lookup'], d['settlement']
            assert (r['registry'], r['receiver_type']) == (lookup['registry'], lookup['receiver_type'])
            assert s['promise'] in r['promises'] and s['evidence']
            assert any(c.get('kind') == 'registered_value_selected' for c in s['conditions'])
    assert {d['settlement']['mode'] for d in frame['deliveries']} == {'resolve', 'reject'}
    assert any(p['decoded_json_path'] == ['body'] for d in ws['deliveries'] for p in d['projections'])
    assert all(any(c.get('expression') == '!isImport && isOldRequest' and c.get('when') is False
                   for c in d['settlement']['conditions']) for d in ws['deliveries'])
    assert report['counts']['registry_deliveries'] == 5 and report['remaining']
    assert all(report['negative_checks'].values()) and report['compiler_version'] == '5.9.3'
    assert report['tests']['passed'] and report['tests']['python'] >= 162 and report['tests']['typescript'] >= 48
    s = report['storage']
    assert all(s[k] for k in ['payload_roundtrip', 'callback_queries_pass', 'frontend_queries_pass', 'backend_response_queries_pass'])
    assert s['native_rows_unchanged'] == 790
    assert (s['nodes'], s['edges']) == (report['counts']['nodes'], report['counts']['edges'])
    paths = {f['path'] for f in manifest['files']}
    assert all(e['path'] in paths and e['line'] > 0 for e in packed['source_evidence'].values())
    for name in ['typescript_data_flow.cjs', 'typescript_response_flow.cjs', 'callback_graph.py', 'callback_queries.py']:
        source = (ROOT / 'adapters' / name).read_text(encoding='utf-8')
        assert not any(s in source for s in ['_responseHandlers', '_msgSequence', 'requestId', 'ClientConnector', 'import/action', 'unit/flows'])
    assert report['file_hash_verification'] == 'not_run_per_user_preference'
    print('OK: five scoped callback/Promise projections and stored queries; transport/API join remains open.')


if __name__ == '__main__': check()
