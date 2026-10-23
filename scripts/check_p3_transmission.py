"""Check published C++ transmission evidence, conditions and unresolved branches."""
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'experiments/2026-10-23-p3'))
from run_response_routing import expand


def check():
    base = ROOT/'experiments/2026-10-23-p3'
    raw = (base/'evidence/transmission.json').read_text(encoding='utf-8')
    assert not re.search(r'[A-Za-z]:[\\/]+Users[\\/]', raw)
    packed = json.loads(raw); r = expand(packed)
    manifest = json.loads((base/'transmission-manifest.json').read_text(encoding='utf-8'))
    assert r['source_commit'] == manifest['source_commit'] and r['snapshot'] == r['source_commit'] + ':p3-data-v9'
    assert r['counts']['files'] == len(manifest['files']) == 150
    assert r['phase_status'] == 'P3_in_progress' and r['gate_under_test'] == 'D02_incomplete'
    assert re.fullmatch('[0-9a-f]{40}', r['rules_revision'])
    assert set(r['parser_versions']) == {'tree-sitter', 'tree-sitter-language-pack'}
    q = r['query']; assert q['total_links'] == len(q['links']) == 12 and not q['truncated']
    assert {l['response_send_site']['evidence'][0]['line'] for l in q['links']} == {38, 47, 61, 65}
    for link in q['links']:
        send = link['transmission']; assert link['json_source']['evidence'][0]['line'] == 169
        assert send['transport'] == 'uWS::WebSocket::send' and send['evidence'][0]['line'] == 159
        assert send['opcode'] == 'uWS::OpCode::TEXT' and send['runtime_execution'] == 'unknown'
        assert len(send['deferred']) == 1 and send['deferred'][0]['evidence'][0]['line'] == 183
        assert {'rapidjson_accept', 'rapidjson_buffer_string', 'lambda_capture', 'socket_send_argument'} <= {s['kind'] for s in link['lineage']['steps']}
        assert link['lineage']['conditions'] and link['serializer'] and link['response_object']
    assert any(g['kind'] == 'source_return_has_unlinked_alternative' and g['evidence'][0]['line'] == 176 for g in q['gaps'])
    assert q['remaining'] and all(r['negative_checks'].values())
    assert r['tests']['passed'] and r['tests']['python'] >= 190 and r['tests']['typescript'] >= 53
    s = r['storage']; assert all(s[k] for k in ['payload_roundtrip', 'transmission_query_pass', 'correlation_query_pass'])
    assert s['native_rows_unchanged'] == 790
    assert (s['nodes'], s['edges']) == (r['counts']['nodes'], r['counts']['edges'])
    paths = {f['path'] for f in manifest['files']}
    assert all(e['path'] in paths and e['line'] > 0 for e in packed['source_evidence'].values())
    for name in ['cpp_transmission.py', 'transmission_queries.py']:
        source = (ROOT/'adapters'/name).read_text(encoding='utf-8')
        assert not any(s in source for s in ['WsSessionImpl', 'JsonDump', 'ToUtf8Str', 'unit/flows', 'responseStr'])
    assert r['file_hash_verification'] == 'not_run_per_user_preference'
    print('OK: four response exits reach typed deferred sends on three encoding branches; remaining branches and endpoint gaps retained.')


if __name__ == '__main__': check()
