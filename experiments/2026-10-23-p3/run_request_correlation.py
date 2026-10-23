"""Validate request-key copies across scoped TS, protocol and C++ evidence."""
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
from adapters.correlation_queries import explain_correlation, request_key_bindings
from adapters.callback_queries import explain_callbacks
from adapters.frontend_queries import explain_frontend
from adapters import kuzu_fact_graph as store
from run_response_routing import compact, expand


def assess(graph):
    provider = next(p['id'] for p in graph['protocol']['providers'] if p['command'] == 'unit/flows')
    result = explain_correlation(graph, provider)
    assert result['total_links'] == 4 and not result['truncated'] and not result['gaps']
    assert {r['response_send_site']['evidence'][0]['line'] for r in result['links']} == {38, 47, 61, 65}
    for link in result['links']:
        assert link['request_key_binding']['wire_path'] == ['id']
        assert link['response_wire_path'] == ['requestId']
        assert link['request_decoder']['wire_fields'] == ['id']
        assert link['copy_effect']['value_origins'][0]['selectors'] == ['pointee', 'member:id']
        assert link['copy_effect']['selectors'] == ['pointee', 'member:requestId']
        assert link['response_lookup']['key']['path'] == ['data', 'requestId']
        assert link['copy_effect']['evidence'] and link['response_field_mapping']
    flow = graph['response_callbacks']; bindings = request_key_bindings(flow)
    assert len(bindings) == 3 and bindings == flow['request_key_bindings']
    by_id = {t['id']: t for t in flow['transmissions']}
    assert sorted(by_id[b['transmission']]['transport'] for b in bindings) == ['WebSocket.send', 'window.postMessage', 'window.postMessage']
    assert all(b['wire_path'] == ['id'] for b in bindings)
    # Remove the decoded origin in memory: equal spelling at later stages is
    # insufficient to reconnect the request. Restore before persistence.
    original = graph['data']['response_routing']['decoded_fields']
    try:
        graph['data']['response_routing']['decoded_fields'] = [d for d in original if d['member'] != 'id']
        assert not explain_correlation(graph, provider)['links']
    finally: graph['data']['response_routing']['decoded_fields'] = original
    return {'evidence_kind': 'executed_source_key_correlation_and_persisted_query',
            'source_commit': graph['source_commit'], 'snapshot': graph['snapshot'],
            'phase_status': 'P3_in_progress', 'gate_under_test': 'D02_incomplete',
            'counts': {'files': len(graph['input_paths']), 'nodes': len(graph['nodes']), 'edges': len(graph['edges']),
                       'transmissions': len(flow['transmissions']), 'counter_updates': len(flow['counter_updates']),
                       'request_key_bindings': len(bindings), 'backend_key_copy_routes': result['total_links']},
            'query': result, 'request_key_bindings': bindings,
            'transmissions': [by_id[b['transmission']] for b in bindings], 'counter_updates': flow['counter_updates'],
            'negative_checks': {'removing_decoder_origin_disconnects_correlation': True},
            'compiler_version': '5.9.3', 'file_hash_verification': 'not_run_per_user_preference'}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ['graph', 'cgc-db', 'output', 'python-log', 'typescript-log']: ap.add_argument('--' + name, type=Path, required=True)
    a = ap.parse_args()
    if a.output.resolve().is_relative_to(ROOT): raise ValueError('Keep database copies outside research repository')
    a.output.mkdir(parents=True, exist_ok=False)
    graph = json.loads(a.graph.read_text(encoding='utf-8')); report = assess(graph)
    report['rules_revision'] = subprocess.check_output(['git', 'log', '-1', '--format=%H', '--',
        'adapters/typescript_data_flow.cjs', 'adapters/callback_graph.py', 'adapters/correlation_queries.py'], cwd=ROOT, text=True).strip()
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
        print('Persist key correlation and repeat correlation/callback/frontend queries', flush=True)
        inserted = store.replace_snapshot(conn, graph); saved = store.read_snapshot(conn, graph['snapshot'])
        assert saved == graph and assess(saved) == assess(graph)
        assert explain_frontend(saved) == explain_frontend(graph)
        assert explain_callbacks(saved) == explain_callbacks(graph)
        assert native == store.rows(conn.execute('MATCH (n:Function) RETURN n ORDER BY n.uid'))
        report['storage'] = {**inserted, 'payload_roundtrip': True, 'correlation_query_pass': True,
                            'callback_queries_pass': True, 'frontend_queries_pass': True,
                            'native_rows_unchanged': len(native), 'buffer_pool_mb': 1024}
    finally:
        conn.close(); db.close()
        if handle: handle.close()
    packed = compact(report); assert compact(expand(packed)) == packed
    (a.output / 'request-correlation.json').write_text(json.dumps(packed, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['counts', 'tests', 'storage']}))
