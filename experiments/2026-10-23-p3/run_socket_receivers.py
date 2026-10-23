"""Validate native request channel, listener and response event-parameter joins."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.socket_queries import explain_socket_receivers
from adapters.transmission_queries import explain_transmission
from adapters import kuzu_fact_graph as store
from run_response_routing import compact, expand


def assess(graph):
    provider = next(p['id'] for p in graph['protocol']['providers'] if p['command'] == 'unit/flows')
    result = explain_socket_receivers(graph, provider=provider)
    assert result['total_receivers'] == 1 and result['total_backend_links'] == 4 and not result['truncated']
    receiver, = result['receivers']; assert len(receiver['deliveries']) == 3
    assert receiver['socket_send']['evidence'][0]['line'] == 284
    assert receiver['listener']['evidence'][0]['line'] == 182 and receiver['listener']['this_binding'] == 'lexical'
    assert len(receiver['native_creations']) == 3 and len(receiver['unresolved_channel_assignments']) == 1
    assert {c['evidence'][0]['line'] for c in receiver['native_creations']} == {95, 103, 114}
    assert all(c['url']['kind'] == 'source_expression' for c in receiver['native_creations'])
    for delivery in receiver['deliveries']:
        assert delivery['lookup']['entry'] == receiver['listener']['callback']
        assert delivery['lookup']['key']['root'] == receiver['listener']['event_parameter']
        assert delivery['lookup']['key']['transforms'][-1]['at_path'] == ['data']
    assert {b['key_correlation']['response_send_site']['evidence'][0]['line'] for b in result['backend_links']} == {38, 47, 61, 65}
    assert all(len(b['cpp_transmissions']) == 3 and b['receiver_link'] == receiver['id'] for b in result['backend_links'])
    listeners = graph['socket_flow']['listener_bindings']
    business = next(l for l in listeners if l['id'] == receiver['listener']['id'])
    callback = business['callback']
    try:
        business['callback'] = None
        assert not explain_socket_receivers(graph, provider=provider)['backend_links']
        assert explain_transmission(graph, provider=provider)['total_links'] == 12
    finally: business['callback'] = callback
    flow = graph['socket_flow']
    return {'evidence_kind': 'executed_source_socket_receiver_join_and_persisted_query', 'source_commit': graph['source_commit'],
            'snapshot': graph['snapshot'], 'phase_status': 'P3_in_progress', 'gate_under_test': 'D02_incomplete',
            'query': result, 'counts': {'files': len(graph['input_paths']), 'nodes': len(graph['nodes']), 'edges': len(graph['edges']),
                'entries': len(flow['entries']), 'native_creations': len(flow['creations']), 'channel_assignments': len(flow['channel_bindings']),
                'listener_bindings': len(listeners), 'send_contexts': len(flow['transmissions']), 'receiver_links': 1,
                'backend_response_exits': 4, 'cpp_send_paths': 12, 'promise_deliveries': 3},
            'socket_creations': flow['creations'], 'channel_assignments': flow['channel_bindings'], 'listener_bindings': listeners,
            'negative_checks': {'removing_receiver_disconnects_returns_while_cpp_paths_remain': True},
            'compiler_version': '5.9.3', 'file_hash_verification': 'not_run_per_user_preference'}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ['graph', 'cgc-db', 'output', 'python-log', 'typescript-log']: ap.add_argument('--' + name, type=Path, required=True)
    a = ap.parse_args()
    if a.output.resolve().is_relative_to(ROOT): raise ValueError('Keep database copies outside research repository')
    a.output.mkdir(parents=True, exist_ok=False)
    graph = json.loads(a.graph.read_text(encoding='utf-8')); report = assess(graph)
    report['rules_revision'] = subprocess.check_output(['git', 'log', '-1', '--format=%H', '--',
        'adapters/typescript_data_flow.cjs', 'adapters/typescript_socket_flow.cjs', 'adapters/socket_graph.py', 'adapters/socket_queries.py'], cwd=ROOT, text=True).strip()
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
        print('Persist socket receiver bindings and repeat provider/receiver/transmission queries', flush=True)
        inserted = store.replace_snapshot(conn, graph); saved = store.read_snapshot(conn, graph['snapshot'])
        assert saved == graph and assess(saved) == assess(graph)
        assert explain_socket_receivers(saved) == explain_socket_receivers(graph)
        assert explain_transmission(saved, provider=report['query']['provider']) == explain_transmission(graph, provider=report['query']['provider'])
        assert native == store.rows(conn.execute('MATCH (n:Function) RETURN n ORDER BY n.uid'))
        report['storage'] = {**inserted, 'payload_roundtrip': True, 'provider_query_pass': True, 'receiver_query_pass': True,
                            'cpp_transmission_query_pass': True, 'native_rows_unchanged': len(native), 'buffer_pool_mb': 1024}
    finally:
        conn.close(); db.close()
        if handle: handle.close()
    packed = compact(report); assert compact(expand(packed)) == packed
    (a.output/'socket-receivers.json').write_text(json.dumps(packed, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['counts', 'tests', 'storage']}))
