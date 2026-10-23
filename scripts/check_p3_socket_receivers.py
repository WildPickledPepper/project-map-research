"""Check published native-channel / response-listener source evidence."""
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'experiments/2026-10-23-p3'))
from run_response_routing import expand


def check():
    base = ROOT/'experiments/2026-10-23-p3'; raw = (base/'evidence/socket-receivers.json').read_text(encoding='utf-8')
    assert not re.search(r'[A-Za-z]:[\\/]+Users[\\/]', raw)
    packed = json.loads(raw); r = expand(packed)
    manifest = json.loads((base/'transmission-manifest.json').read_text(encoding='utf-8'))
    assert r['source_commit'] == manifest['source_commit'] and r['snapshot'] == r['source_commit'] + ':p3-data-v10'
    assert r['counts']['files'] == len(manifest['files']) == 150
    assert r['phase_status'] == 'P3_in_progress' and r['gate_under_test'] == 'D02_incomplete'
    assert re.fullmatch('[0-9a-f]{40}', r['rules_revision']) and r['compiler_version'] == '5.9.3'
    q = r['query']; assert q['total_receivers'] == 1 and q['total_backend_links'] == 4 and not q['truncated']
    receiver, = q['receivers']; assert len(receiver['deliveries']) == 3
    assert receiver['socket_send']['evidence'][0]['line'] == 284 and receiver['listener']['evidence'][0]['line'] == 182
    assert receiver['listener']['this_binding'] == 'lexical' and not receiver['listener']['superseded_by']
    assert len(receiver['unresolved_channel_assignments']) == 1
    assert {c['evidence'][0]['line'] for c in receiver['native_creations']} == {95, 103, 114}
    assert all(c['url']['kind'] == 'source_expression' for c in receiver['native_creations'])
    for delivery in receiver['deliveries']:
        assert delivery['lookup']['entry'] == receiver['listener']['callback']
        assert delivery['lookup']['key']['root'] == receiver['listener']['event_parameter']
        assert delivery['lookup']['key']['transforms'][-1]['at_path'] == ['data']
    assert {b['key_correlation']['response_send_site']['evidence'][0]['line'] for b in q['backend_links']} == {38, 47, 61, 65}
    assert all(len(b['cpp_transmissions']) == 3 and b['receiver_link'] == receiver['id'] for b in q['backend_links'])
    assert all(b['network_pairing'] == 'configured_service_candidate_server_channel_origin_pending' for b in q['backend_links'])
    assert q['remaining'] and all(r['negative_checks'].values())
    assert r['tests']['passed'] and r['tests']['python'] >= 195 and r['tests']['typescript'] >= 67
    s = r['storage']; assert all(s[k] for k in ['payload_roundtrip', 'provider_query_pass', 'receiver_query_pass', 'cpp_transmission_query_pass'])
    assert s['native_rows_unchanged'] == 790
    assert (s['nodes'], s['edges']) == (r['counts']['nodes'], r['counts']['edges'])
    paths = {f['path'] for f in manifest['files']}
    assert all(e['path'] in paths and e['line'] > 0 for e in packed['source_evidence'].values())
    for name in ['typescript_data_flow.cjs', 'socket_queries.py']:
        source = (ROOT/'adapters'/name).read_text(encoding='utf-8')
        assert not any(s in source for s in ['_ws', 'fetchDataOnMessage', 'unit/flows', 'WebviewSocket', 'initHost'])
    assert r['file_hash_verification'] == 'not_run_per_user_preference'
    print('OK: native socket branches, handler binding and event-parameter lookup connect four response exits; network and API joins retain scope.')


if __name__ == '__main__': check()
