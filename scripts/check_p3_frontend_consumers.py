"""Check published frontend evidence without running the product or hashing files."""
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'experiments/2026-10-23-p3'))
from run_response_routing import expand


def check():
    base = ROOT / 'experiments/2026-10-23-p3'
    raw = (base / 'evidence/frontend-consumers.json').read_text(encoding='utf-8')
    assert not re.search(r'[A-Za-z]:[\\/]+Users[\\/]', raw)
    r = expand(json.loads(raw))
    manifest = json.loads((base / 'response-manifest.json').read_text(encoding='utf-8'))
    assert r['source_commit'] == manifest['source_commit']
    assert r['snapshot'] == r['source_commit'] + ':p3-data-v6'
    assert r['counts']['files'] == len(manifest['files']) == 148
    assert r['phase_status'] == 'P3_in_progress' and r['gate_under_test'] == 'D02_incomplete'
    assert re.fullmatch('[0-9a-f]{40}', r['rules_revision'])
    q = r['query']
    assert q['transport_status'] == 'pending_transport_join'
    assert not q['truncated'] and not q['extraction_truncated']
    assert len(q['api_calls']) == 2 and len(q['writes']) == 6
    contexts = {c['request_context'] for c in q['api_calls']}
    assert len(contexts) == 2
    values = [w for w in q['writes'] if w['matching_dependencies']]
    assert len(values) == 2 and len({w['state_node'] for w in values}) == 2
    assert set(r['field_query_write_ids']) == {w['id'] for w in values}
    for w in q['writes']:
        assert set(w['matching_continuations']) <= contexts
        assert w['conditions'] and w['evidence']
        if w['matching_dependencies']:
            assert w['target']['path'] == ['singleLinkLine']
            assert len({tuple(d['path']) for d in w['matching_dependencies']}) == 6
            assert all(d['request_context'] in contexts and d['call_chain'] for d in w['matching_dependencies'])
    assert all(r['negative_checks'].values()) and q['gaps'] and r['remaining']
    assert r['compiler']['compiler_version'] == '5.9.3'
    assert r['tests']['passed'] and r['tests']['python'] >= 158 and r['tests']['typescript'] >= 36
    s = r['storage']
    assert s['payload_roundtrip'] and s['stored_frontend_query_pass'] and s['stored_response_query_pass']
    assert s['native_rows_unchanged'] == 790
    assert (s['nodes'], s['edges']) == (r['counts']['nodes'], r['counts']['edges'])
    paths = {f['path'] for f in manifest['files']}
    for e in json.loads(raw)['source_evidence'].values():
        assert e['path'] in paths and e['line'] > 0
    for name in ['typescript_data_flow.cjs', 'frontend_graph.py', 'frontend_queries.py']:
        source = (ROOT / 'adapters' / name).read_text(encoding='utf-8')
        assert not any(w in source for w in ['getUnitFlows', 'unitAllFlows', 'singleLinkLine', 'renderTrigger', 'AscendUnit', 'FilterLinkLine'])
    assert r['file_hash_verification'] == 'not_run_per_user_preference'
    print('OK: scoped frontend value/continuation dependencies and stored queries; D02 transport join remains open.')


if __name__ == '__main__': check()
