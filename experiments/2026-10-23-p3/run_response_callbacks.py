"""Check real callback registrations, projections and persisted query results."""
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
from adapters.callback_queries import explain_callbacks
from adapters.frontend_queries import explain_frontend
from adapters.response_queries import explain_response
from adapters import kuzu_fact_graph as store
from run_response_routing import compact, expand


def assess(graph):
    names = {n['id']: n['name'] for n in graph['nodes']}
    requests = {name: next(n['id'] for n in graph['nodes'] if n['kind'] == 'callable' and n['name'] == name)
                for name in ['Connection.fetch', 'ClientConnector.fetch']}
    queries = {name: explain_callbacks(graph, uid) for name, uid in requests.items()}
    ws, frame = queries.values()
    assert ws['total_deliveries'] == 3 and frame['total_deliveries'] == 2
    for query in queries.values():
        assert not query['truncated'] and not query['extraction_truncated']
        assert len(query['registrations']) == 1 and not query['unmatched_lookups']
        assert query['transport_status'] == 'network_and_API_boundary_join_pending'
        for delivery in query['deliveries']:
            r, lookup, s = (delivery[k] for k in ['registration', 'lookup', 'settlement'])
            assert r['registry'] == lookup['registry'] and r['receiver_type'] == lookup['receiver_type']
            assert s['promise'] in r['promises'] and s['evidence'] and s['call_chain'] is not None
            assert any(c.get('kind') == 'registered_value_selected' for c in s['conditions'])
    assert all(d['settlement']['mode'] == 'resolve' for d in ws['deliveries'])
    assert {d['lookup']['key']['path'][-1] for d in ws['deliveries']} == {'requestId'}
    assert any(p['decoded_json_path'] == ['body'] for d in ws['deliveries'] for p in d['projections'])
    assert any(p['decoded_json_path'] == [] for d in ws['deliveries'] for p in d['projections'])
    assert {tuple(p['output_path']) for d in ws['deliveries'] for p in d['projections']} == {(), ('error', 'code'), ('error', 'message')}
    assert all(any(c.get('expression') == '!isImport && isOldRequest' and c.get('when') is False
                   for c in d['settlement']['conditions']) for d in ws['deliveries'])
    assert {d['settlement']['mode'] for d in frame['deliveries']} == {'resolve', 'reject'}
    for delivery in frame['deliveries']:
        assert delivery['lookup']['key']['path'] == ['data', 'id']
        s = delivery['settlement']
        assert s['value']['path'] == (['data'] if s['mode'] == 'resolve' else ['data', 'body', 'error'])
    ws_receiver = ws['deliveries'][0]['settlement']['entry']
    assert not explain_callbacks(graph, requester=requests['ClientConnector.fetch'], receiver=ws_receiver)['deliveries']
    data = graph['response_callbacks']
    return {'evidence_kind': 'executed_source_callback_extraction_query_and_storage',
            'source_commit': graph['source_commit'], 'snapshot': graph['snapshot'],
            'phase_status': 'P3_in_progress', 'gate_under_test': 'D02_incomplete',
            'counts': {'files': len(graph['input_paths']), 'nodes': len(graph['nodes']), 'edges': len(graph['edges']),
                       **{k: len(data[k]) for k in ['entries', 'promises', 'registrations', 'lookups', 'settlements']},
                       'registry_deliveries': 5},
            'queries': queries, 'symbols': {uid: names[uid] for uid in requests.values()},
            'callback_bindings': data['callback_bindings'],
            'negative_checks': {'cross_registry_receiver': True, 'key_and_instance_conditions_retained': True},
            'remaining': ['C++ serialized response to socket send', 'request counter to wire key and response key equality',
                          'postMessage receiver/response wrapping and Promise-to-API return join',
                          'D03 cross-transport reverse impact', 'D05 whole-chain explanation'],
            'file_hash_verification': 'not_run_per_user_preference'}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ['graph', 'cgc-db', 'output', 'python-log', 'typescript-log']: ap.add_argument('--' + name, type=Path, required=True)
    a = ap.parse_args()
    if a.output.resolve().is_relative_to(ROOT): raise ValueError('Keep database copies outside research repository')
    a.output.mkdir(parents=True, exist_ok=False)
    graph = json.loads(a.graph.read_text(encoding='utf-8')); report = assess(graph)
    report['rules_revision'] = subprocess.check_output(['git', 'log', '-1', '--format=%H', '--',
        'adapters/typescript_data_flow.cjs', 'adapters/typescript_response_flow.cjs', 'adapters/callback_graph.py', 'adapters/callback_queries.py'], cwd=ROOT, text=True).strip()
    report['compiler_version'] = '5.9.3'
    py, ts = (p.read_text(encoding='utf-8') for p in [a.python_log, a.typescript_log])
    assert re.search(r'\nOK\s*$', py) and '# fail 0' in ts
    report['tests'] = {'passed': True, 'python': int(re.search(r'Ran (\d+) tests', py)[1]), 'typescript': int(re.search(r'# pass (\d+)', ts)[1])}
    wal = Path(str(a.cgc_db) + '.wal')
    if wal.exists() and wal.stat().st_size: raise ValueError('Close native database before copying')
    shutil.copy2(a.cgc_db, a.output / 'cgc.kuzu')
    handle = os.add_dll_directory(os.environ['PROJECT_MAP_DLL_DIR']) if os.name == 'nt' and os.environ.get('PROJECT_MAP_DLL_DIR') else None
    import kuzu
    db = kuzu.Database(str(a.output / 'cgc.kuzu'), buffer_pool_size=1024*1024*1024); conn = kuzu.Connection(db)
    try:
        native = store.rows(conn.execute('MATCH (n:Function) RETURN n ORDER BY n.uid'))
        print('Persist callback graph and repeat callback/frontend/response queries', flush=True)
        inserted = store.replace_snapshot(conn, graph); saved = store.read_snapshot(conn, graph['snapshot'])
        assert saved == graph and assess(saved) == assess(graph)
        assert explain_frontend(saved) == explain_frontend(graph)
        provider = next(p['id'] for p in graph['protocol']['providers'] if p['command'] == 'unit/flows')
        assert explain_response(saved, provider) == explain_response(graph, provider)
        assert native == store.rows(conn.execute('MATCH (n:Function) RETURN n ORDER BY n.uid'))
        report['storage'] = {**inserted, 'payload_roundtrip': True, 'callback_queries_pass': True,
                            'frontend_queries_pass': True, 'backend_response_queries_pass': True,
                            'native_rows_unchanged': len(native), 'buffer_pool_mb': 1024}
    finally:
        conn.close(); db.close()
        if handle: handle.close()
    packed = compact(report); assert compact(expand(packed)) == packed
    (a.output / 'response-callbacks.json').write_text(json.dumps(packed, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['counts', 'tests', 'storage']}))
