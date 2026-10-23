"""Check published accepted-channel and scoped session source evidence."""
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'experiments/2026-10-23-p3'))
from run_response_routing import expand


def check():
    base = ROOT/'experiments/2026-10-23-p3'; raw = (base/'evidence/server-channels.json').read_text(encoding='utf-8')
    assert not re.search(r'[A-Za-z]:[\\/]+Users[\\/]', raw)
    packed = json.loads(raw); r = expand(packed)
    manifest = json.loads((base/'server-channels-manifest.json').read_text(encoding='utf-8'))
    assert r['source_commit'] == manifest['source_commit'] and r['snapshot'] == r['source_commit'] + ':p3-data-v11'
    assert r['counts']['files'] == len(manifest['files']) == 154
    assert r['phase_status'] == 'P3_in_progress' and r['gate_under_test'] == 'D02_incomplete'
    assert re.fullmatch('[0-9a-f]{40}', r['rules_revision'])
    q = r['query']; assert q['total_origins'] == 1 and q['total_links'] == 4 and not q['truncated']
    origin, = q['origins']; initial = origin['channel_initialization']; write = origin['store']; read = origin['consumer']
    assert origin['registration']['evidence'][0]['line'] == 66 and len(origin['listen_candidates']) == 1
    assert initial['member_record']['name'] == 'channel' and initial['evidence'][0]['line'] == 133
    assert initial['allocation'] == write['allocation']
    assert (write['member'], write['receiver_instance']) == (read['member'], read['receiver_instance'])
    assert origin['manager_instance']['kind'] == 'static_local_object'
    assert {l['response_send_site']['evidence'][0]['line'] for l in q['links']} == {38, 47, 61, 65}
    assert all(len(l['transmissions']) == 3 and l['origin_link'] == origin['id'] for l in q['links'])
    socket = r['socket_query']; assert socket['total_backend_links'] == 4 and not socket['truncated']
    assert 'server_accept_session_channel_origin' not in socket['remaining']
    assert all(b['server_channel_origins'] == [origin['id']] for b in socket['backend_links'])
    assert q['remaining'] and all(r['negative_checks'].values())
    assert r['tests']['passed'] and r['tests']['python'] >= 217 and r['tests']['typescript'] >= 67
    s = r['storage']; assert all(s[k] for k in ['payload_roundtrip', 'provider_query_pass', 'combined_socket_query_pass'])
    assert s['native_rows_unchanged'] == 790
    assert (s['nodes'], s['edges']) == (r['counts']['nodes'], r['counts']['edges'])
    paths = {f['path'] for f in manifest['files']}
    assert all(e['path'] in paths and e['line'] > 0 for e in packed['source_evidence'].values())
    for name in ['cpp_socket_origin.py', 'server_channel_queries.py', 'server_channel_graph.py']:
        source = (ROOT/'adapters'/name).read_text(encoding='utf-8')
        assert not any(s in source for s in ['WsSessionImpl', 'WsSessionManager', 'OnOpenCb', 'unit/flows', 'GetSessionPtr'])
    assert r['file_hash_verification'] == 'not_run_per_user_preference'
    print('OK: accepted socket, constructor member and scoped session getter connect four response exits; API join remains pending.')


if __name__ == '__main__': check()
