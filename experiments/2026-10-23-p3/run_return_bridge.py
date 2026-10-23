"""Validate source return bridges, rejection filters and reverse state queries."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.return_bridge_queries import alternatives, explain_return_bridge
from adapters.socket_queries import explain_socket_receivers
from adapters import kuzu_fact_graph as store
from run_response_routing import compact, expand


def assess(graph):
    provider = next(p['id'] for p in graph['protocol']['providers'] if p['command'] == 'unit/flows')
    result = explain_return_bridge(graph, provider, field_path=['unitAllFlows'])
    assert result['total_bridges'] == 1 and result['total_links'] == 4 and not result['truncated']
    bridge, = result['bridges']; assert bridge['api_return']['value']['path'] == ['body']
    assert bridge['reply_value_path'] == ['body'] and bridge['upstream_projection']['path'] == []
    assert {l['response_send_site']['evidence'][0]['line'] for l in result['links']} == {38, 47, 61, 65}
    states = {w['write']['state_node'] for l in result['links'] for w in l['writes']}
    assert len(states) == 2 and all(len(l['writes']) == 2 for l in result['links'])
    assert all(l['wire_to_api']['decoded_json_path'] == ['body'] for l in result['links'])
    for link in result['links']:
        production = [p for w in link['writes'] for m in w['value_mappings'] for p in m['production']]
        assert bool(production) == (link['response_send_site']['evidence'][0]['line'] in {61, 65})
    reverse = {}
    for state in states:
        queried = explain_return_bridge(graph, provider, state=state, field_path=['unitAllFlows'])
        assert queried['total_links'] == 4 and all(len(l['writes']) == 1 and l['writes'][0]['write']['state_node'] == state for l in queried['links'])
        reverse[state] = {'links': queried['total_links'], 'api': bridge['api'], 'provider': provider}
    all_values = explain_return_bridge(graph, provider)
    assert all_values['total_links'] == 8 and not all_values['truncated']
    assert all(l['socket_delivery']['settlement']['value']['kind'] == 'input_path' for l in all_values['links'])
    negatives = {}; original = graph['return_flow']
    for label in ['key', 'tag', 'destination', 'api_projection', 'listener', 'callback_registration']:
        flow = graph['return_flow'] = deepcopy(original)
        if label in {'key', 'tag'}:
            reply = next(t for t in flow['transmissions'] if t['id'] == bridge['reply_send']['id'])
            for payload in alternatives(reply['payload']['value']): payload['fields']['id' if label == 'key' else 'event'] = {'kind': 'constant', 'value': 'changed'}
        elif label == 'destination': next(t for t in flow['transmissions'] if t['id'] == bridge['reply_send']['id'])['receiver']['selections'] = []
        elif label == 'api_projection': next(r for r in flow['returns'] if r['id'] == bridge['api_return']['id'])['value']['path'] = ['missing']
        elif label == 'listener': next(l for l in flow['window_listeners'] if l['id'] == bridge['client_handoff']['listener'])['superseded_by'] = ['controlled-test']
        else: flow['callback_bindings'] = []
        assert not explain_return_bridge(graph, provider, field_path=['unitAllFlows'])['links']
        assert explain_socket_receivers(graph, provider=provider)['total_backend_links'] == 4
        negatives[label + '_change_disconnects_return_only'] = True
    graph['return_flow'] = original
    return {'evidence_kind': 'executed_source_return_bridge_and_reverse_state_queries', 'source_commit': graph['source_commit'],
        'snapshot': graph['snapshot'], 'phase_status': 'P3_in_progress', 'gate_under_test': 'D02_D03_D05_pending_combined_acceptance',
        'query': result, 'reverse_queries': reverse, 'negative_checks': negatives,
        'all_return_summary': {'links': all_values['total_links'], 'writes_per_link': [len(l['writes']) for l in all_values['links']],
            'error_object_fulfillment_removed': True, 'conditional_path_feasibility': 'guards_retained_not_fully_solved'},
        'counts': {'files': len(graph['input_paths']), 'nodes': len(graph['nodes']), 'edges': len(graph['edges']),
            'entries': len(original['entries']), 'boundaries': len(original['boundaries']), 'returns': len(original['returns']),
            'window_listeners': len(original['window_listeners']), 'handoffs': len(original['handoffs']),
            'bridges_for_provider': 1, 'field_return_links': 4, 'field_state_writes': 2, 'state_reverse_queries': 2},
        'compiler_version': '5.9.3', 'file_hash_verification': 'not_run_per_user_preference'}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ['graph', 'cgc-db', 'output', 'python-log', 'typescript-log']: ap.add_argument('--' + name, type=Path, required=True)
    a = ap.parse_args()
    if a.output.resolve().is_relative_to(ROOT): raise ValueError('Keep database copies outside research repository')
    a.output.mkdir(parents=True, exist_ok=False)
    graph = json.loads(a.graph.read_text(encoding='utf-8')); report = assess(graph)
    report['rules_revision'] = subprocess.check_output(['git', 'log', '-1', '--format=%H', '--',
        'adapters/typescript_data_flow.cjs', 'adapters/typescript_return_flow.cjs', 'adapters/return_bridge_graph.py', 'adapters/return_bridge_queries.py'], cwd=ROOT, text=True).strip()
    py, ts = (p.read_text(encoding='utf-8') for p in [a.python_log, a.typescript_log])
    assert re.search(r'\nOK\s*$', py) and '# fail 0' in ts
    report['tests'] = {'passed': True, 'python': int(re.search(r'Ran (\d+) tests', py)[1]), 'typescript': int(re.search(r'# pass (\d+)', ts)[1])}
    wal = Path(str(a.cgc_db) + '.wal')
    if wal.exists() and wal.stat().st_size: raise ValueError('Close native database before copying')
    shutil.copy2(a.cgc_db, a.output/'cgc.kuzu')
    handle = os.add_dll_directory(os.environ['PROJECT_MAP_DLL_DIR']) if os.name == 'nt' and os.environ.get('PROJECT_MAP_DLL_DIR') else None
    import kuzu
    db = kuzu.Database(str(a.output/'cgc.kuzu'), buffer_pool_size=1024*1024*1024); conn = kuzu.Connection(db)
    try:
        native = store.rows(conn.execute('MATCH (n:Function) RETURN n ORDER BY n.uid'))
        print('Persist return bridges and repeat field / reverse / negative queries', flush=True)
        inserted = store.replace_snapshot(conn, graph); saved = store.read_snapshot(conn, graph['snapshot'])
        assert saved == graph and assess(saved) == assess(graph)
        assert native == store.rows(conn.execute('MATCH (n:Function) RETURN n ORDER BY n.uid'))
        report['storage'] = {**inserted, 'payload_roundtrip': True, 'field_query_pass': True, 'reverse_queries_pass': True,
            'negative_queries_pass': True, 'native_rows_unchanged': len(native), 'buffer_pool_mb': 1024}
    finally:
        conn.close(); db.close()
        if handle: handle.close()
    packed = compact(report); assert compact(expand(packed)) == packed
    (a.output/'return-bridge.json').write_text(json.dumps(packed, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['counts', 'tests', 'storage']}))
