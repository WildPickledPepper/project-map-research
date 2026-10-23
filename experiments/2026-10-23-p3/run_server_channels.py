"""Validate accepted server channel joins and persisted end-to-end candidates."""
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
from adapters.server_channel_queries import explain_server_channels
from adapters.socket_queries import explain_socket_receivers
from adapters.transmission_queries import explain_transmission
from adapters import kuzu_fact_graph as store
from run_response_routing import compact, expand


def assess(graph):
    provider = next(p['id'] for p in graph['protocol']['providers'] if p['command'] == 'unit/flows')
    result = explain_server_channels(graph, provider=provider)
    assert result['total_origins'] == 1 and result['total_links'] == 4 and not result['truncated']
    origin, = result['origins']; init = origin['channel_initialization']; write = origin['store']; read = origin['consumer']
    assert origin['registration']['evidence'][0]['line'] == 66
    listen, = origin['listen_candidates']; assert listen['evidence'][0]['line'] == 68
    assert init['member_record']['name'] == 'channel' and init['constructed_type'] == 'Dic::Server::WsSessionImpl'
    assert init['origin']['parameter'] == init['parameter'] == 0
    assert init['evidence'][0]['line'] == 133 and init['evidence'][1]['line'] == 29
    assert write['allocation'] == init['allocation']
    assert (write['member'], write['receiver_instance']) == (read['member'], read['receiver_instance'])
    assert origin['manager_instance']['kind'] == 'static_local_object'
    assert {b['response_send_site']['evidence'][0]['line'] for b in result['links']} == {38, 47, 61, 65}
    assert all(len(b['transmissions']) == 3 for b in result['links'])
    socket = explain_socket_receivers(graph, provider=provider)
    assert len(socket['server_channel_origins']) == 1 and socket['total_backend_links'] == 4 and not socket['truncated']
    assert 'server_accept_session_channel_origin' not in socket['remaining']
    assert all(b['server_channel_origins'] == [origin['id']] for b in socket['backend_links'])
    assert all(b['network_pairing'] == 'configured_service_candidate_with_source_server_channel_origin' for b in socket['backend_links'])
    negatives = {}
    flow = graph['server_channels']
    for group in ['channel_initializers', 'object_stores', 'member_getters']:
        original = flow[group]
        try:
            flow[group] = []
            assert not explain_server_channels(graph, provider=provider)['links']
            remaining = explain_socket_receivers(graph, provider=provider)
            assert remaining['total_backend_links'] == 4 and 'server_accept_session_channel_origin' in remaining['remaining']
            assert explain_transmission(graph, provider=provider)['total_links'] == 12
            negatives['removing_' + group + '_disconnects_server_origin_only'] = True
        finally: flow[group] = original
    return {'evidence_kind': 'executed_source_server_channel_join_and_persisted_query', 'source_commit': graph['source_commit'],
        'snapshot': graph['snapshot'], 'phase_status': 'P3_in_progress', 'gate_under_test': 'D02_incomplete',
        'query': result, 'socket_query': socket, 'negative_checks': negatives,
        'counts': {'files': len(graph['input_paths']), 'nodes': len(graph['nodes']), 'edges': len(graph['edges']),
            'registrations': len(flow['registrations']), 'listeners': len(flow['listeners']), 'allocations': len(flow['allocations']),
            'channel_initializers': len(flow['channel_initializers']), 'object_stores': len(flow['object_stores']),
            'member_getters': len(flow['member_getters']), 'member_consumers': len(flow['member_consumers']),
            'origin_links': 1, 'backend_response_exits': 4, 'cpp_send_paths': 12, 'promise_deliveries': 3},
        'parser_versions': {'tree-sitter': '0.25.2', 'tree-sitter-language-pack': '1.20.0'},
        'external_model': {'repository': 'uNetworking/uWebSockets', 'revision': '045bbc11ef4f3ec933c112579d3e8922302a798b',
            'file': 'src/App.h', 'open_callback_line': 289, 'registration_line': 310, 'handler_transfer_line': 420,
            'product_binary_version': 'not_verified'}, 'file_hash_verification': 'not_run_per_user_preference'}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ['graph', 'cgc-db', 'output', 'python-log', 'typescript-log']: ap.add_argument('--' + name, type=Path, required=True)
    a = ap.parse_args()
    if a.output.resolve().is_relative_to(ROOT): raise ValueError('Keep database copies outside research repository')
    a.output.mkdir(parents=True, exist_ok=False)
    graph = json.loads(a.graph.read_text(encoding='utf-8')); report = assess(graph)
    report['rules_revision'] = subprocess.check_output(['git', 'log', '-1', '--format=%H', '--',
        'adapters/cpp_socket_origin.py', 'adapters/server_channel_graph.py', 'adapters/server_channel_queries.py', 'adapters/socket_queries.py'], cwd=ROOT, text=True).strip()
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
        print('Persist server channel origins and repeat response / socket queries', flush=True)
        inserted = store.replace_snapshot(conn, graph); saved = store.read_snapshot(conn, graph['snapshot'])
        assert saved == graph and assess(saved) == assess(graph)
        assert native == store.rows(conn.execute('MATCH (n:Function) RETURN n ORDER BY n.uid'))
        report['storage'] = {**inserted, 'payload_roundtrip': True, 'provider_query_pass': True, 'combined_socket_query_pass': True,
                            'native_rows_unchanged': len(native), 'buffer_pool_mb': 1024}
    finally:
        conn.close(); db.close()
        if handle: handle.close()
    packed = compact(report); assert compact(expand(packed)) == packed
    (a.output/'server-channels.json').write_text(json.dumps(packed, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['counts', 'tests', 'storage']}))
