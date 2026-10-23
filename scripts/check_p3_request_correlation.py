"""Check published key-origin evidence and retained transport gaps."""
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'experiments/2026-10-23-p3'))
from run_response_routing import expand


def check():
    base = ROOT / 'experiments/2026-10-23-p3'
    raw = (base / 'evidence/request-correlation.json').read_text(encoding='utf-8')
    assert not re.search(r'[A-Za-z]:[\\/]+Users[\\/]', raw)
    packed = json.loads(raw); r = expand(packed)
    manifest = json.loads((base / 'response-manifest.json').read_text(encoding='utf-8'))
    assert r['source_commit'] == manifest['source_commit'] and r['snapshot'] == r['source_commit'] + ':p3-data-v8'
    assert r['counts']['files'] == len(manifest['files']) == 148
    assert r['phase_status'] == 'P3_in_progress' and r['gate_under_test'] == 'D02_incomplete'
    assert re.fullmatch('[0-9a-f]{40}', r['rules_revision']) and r['compiler_version'] == '5.9.3'
    q = r['query']; assert q['total_links'] == 4 and len(q['links']) == 4 and not q['truncated']
    assert {l['response_send_site']['evidence'][0]['line'] for l in q['links']} == {38, 47, 61, 65}
    for link in q['links']:
        assert link['request_key_binding']['wire_path'] == ['id'] and link['response_wire_path'] == ['requestId']
        assert link['request_decoder']['wire_fields'] == ['id']
        assert link['copy_effect']['value_origins'][0]['selectors'] == ['pointee', 'member:id']
        assert link['copy_effect']['selectors'] == ['pointee', 'member:requestId']
        assert link['response_lookup']['key']['path'] == ['data', 'requestId']
        assert link['copy_effect']['evidence'] and link['conditions']
    assert len(r['request_key_bindings']) == r['counts']['request_key_bindings'] == 3
    assert all(b['matches'] and b['wire_path'] == ['id'] for b in r['request_key_bindings'])
    assert all(r['negative_checks'].values()) and q['remaining']
    assert r['tests']['passed'] and r['tests']['python'] >= 169 and r['tests']['typescript'] >= 53
    if 'followup_validation' in r:
        v = r['followup_validation']
        assert v['stored_query_unchanged'] and v['read_only_database'] and v['python_tests'] >= 170
        assert re.fullmatch('[0-9a-f]{40}', v['rules_revision'])
    s = r['storage']
    assert all(s[k] for k in ['payload_roundtrip', 'correlation_query_pass', 'callback_queries_pass', 'frontend_queries_pass'])
    assert s['native_rows_unchanged'] == 790
    assert (s['nodes'], s['edges']) == (r['counts']['nodes'], r['counts']['edges'])
    paths = {f['path'] for f in manifest['files']}
    assert all(e['path'] in paths and e['line'] > 0 for e in packed['source_evidence'].values())
    for name in ['typescript_data_flow.cjs', 'correlation_queries.py']:
        source = (ROOT / 'adapters' / name).read_text(encoding='utf-8')
        assert not any(s in source for s in ['_msgId', '_curFetchSequenceID', 'requestId', 'unit/flows', 'SetBaseResponse'])
    assert r['file_hash_verification'] == 'not_run_per_user_preference'
    print('OK: three sent-key bindings and four scoped backend copy routes; response transport remains open.')


if __name__ == '__main__': check()
