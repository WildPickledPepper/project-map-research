"""Check published iframe return and scoped state reverse-query evidence."""
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'experiments/2026-10-23-p3'))
from run_response_routing import expand


def check():
    base = ROOT/'experiments/2026-10-23-p3'
    raw = (base/'evidence/return-bridge.json').read_text(encoding='utf-8')
    assert not re.search(r'[A-Za-z]:[\\/]+Users[\\/]', raw)
    packed = json.loads(raw); r = expand(packed)
    manifest = json.loads((base/'server-channels-manifest.json').read_text(encoding='utf-8'))
    assert r['source_commit'] == manifest['source_commit']
    assert r['snapshot'] == r['source_commit'] + ':p3-data-v12'
    assert r['counts']['files'] == len(manifest['files']) == 154
    assert re.fullmatch('[0-9a-f]{40}', r['rules_revision'])
    assert r['phase_status'] == 'P3_in_progress'
    assert r['gate_under_test'] == 'D02_D03_D05_pending_combined_acceptance'
    q = r['query']; assert q['total_bridges'] == 1 and q['total_links'] == 4 and not q['truncated']
    bridge, = q['bridges']
    assert bridge['reply_value_path'] == ['body'] and bridge['upstream_projection']['path'] == []
    assert {l['response_send_site']['evidence'][0]['line'] for l in q['links']} == {38, 47, 61, 65}
    states = {w['write']['state_node'] for l in q['links'] for w in l['writes']}
    assert len(states) == 2 and set(r['reverse_queries']) == states
    assert all(v['links'] == 4 and v['api'] == bridge['api'] for v in r['reverse_queries'].values())
    for link in q['links']:
        assert len(link['writes']) == 2 and link['wire_to_api']['decoded_json_path'] == ['body']
        production = [p for w in link['writes'] for m in w['value_mappings'] for p in m['production']]
        assert bool(production) == (link['response_send_site']['evidence'][0]['line'] in {61, 65})
    assert len(r['negative_checks']) == 6 and all(r['negative_checks'].values())
    assert r['all_return_summary']['links'] == 8 and r['all_return_summary']['error_object_fulfillment_removed']
    assert r['tests']['passed'] and r['tests']['python'] >= 223 and r['tests']['typescript'] >= 76
    s = r['storage']
    assert all(s[k] for k in ['payload_roundtrip', 'field_query_pass', 'reverse_queries_pass', 'negative_queries_pass'])
    assert s['native_rows_unchanged'] == 790
    assert (s['nodes'], s['edges']) == (r['counts']['nodes'], r['counts']['edges'])
    paths = {f['path'] for f in manifest['files']}
    assert all(e['path'] in paths and e['line'] > 0 for e in packed['source_evidence'].values())
    for name in ['typescript_return_flow.cjs', 'return_bridge_queries.py', 'return_bridge_graph.py']:
        source = (ROOT/'adapters'/name).read_text(encoding='utf-8')
        assert not any(s in source for s in ['unit/flows', 'unitAllFlows', 'getUnitFlows', 'singleLinkLine', 'requestModule'])
    assert r['file_hash_verification'] == 'not_run_per_user_preference'
    print('OK: source iframe replies connect four response exits to two state writes and reverse queries; combined P3 acceptance pending.')


if __name__ == '__main__': check()
