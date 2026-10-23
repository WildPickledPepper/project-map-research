"""Score source JSON-to-send linkage and repeat queries from native CGC storage."""
import argparse
from importlib.metadata import version
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.transmission_queries import explain_transmission
from adapters.correlation_queries import explain_correlation
from adapters import kuzu_fact_graph as store
from run_response_routing import compact, expand


def assess(graph):
    provider = next(p['id'] for p in graph['protocol']['providers'] if p['command'] == 'unit/flows')
    result = explain_transmission(graph, provider=provider)
    assert result['total_links'] == 12 and not result['truncated']
    assert {l['response_send_site']['evidence'][0]['line'] for l in result['links']} == {38, 47, 61, 65}
    for link in result['links']:
        assert link['json_source']['evidence'][0]['line'] == 169
        send = link['transmission']; assert send['evidence'][0]['line'] == 159
        assert send['transport'] == 'uWS::WebSocket::send' and send['opcode'] == 'uWS::OpCode::TEXT'
        assert len(send['deferred']) == 1 and send['deferred'][0]['evidence'][0]['line'] == 183
        kinds = {s['kind'] for s in link['lineage']['steps']}
        assert {'rapidjson_accept', 'rapidjson_buffer_string', 'lambda_capture', 'parameter_binding', 'socket_send_argument'} <= kinds
        guards = link['lineage']['conditions']
        assert any('!json.has_value()' in c.get('expression', '') and c['when'] is False for c in guards)
        assert any('!self' in c.get('expression', '') and c['when'] is False for c in guards)
        assert any('channel != nullptr' in c.get('expression', '') and c['when'] is True for c in guards)
        assert any('Status::CLOSED' in c.get('expression', '') and c['when'] is False for c in guards)
    assert any(g['kind'] == 'source_return_has_unlinked_alternative' and g['evidence'][0]['line'] == 176 for g in result['gaps'])
    transmissions = graph['cpp_transmission']['transmissions']
    assert len(transmissions) == 2 and all(len(t['traces']) == 3 for t in transmissions)
    sources = graph['cpp_transmission']['sources']
    target_source = next(s for s in sources if s['id'] == result['links'][0]['json_source']['id'])
    original = target_source['targets']
    try:
        target_source['targets'] = []
        assert not explain_transmission(graph, provider=provider)['links']
    finally: target_source['targets'] = original
    return {'evidence_kind': 'executed_source_transmission_extraction_and_persisted_query',
            'source_commit': graph['source_commit'], 'snapshot': graph['snapshot'], 'phase_status': 'P3_in_progress',
            'gate_under_test': 'D02_incomplete', 'query': result,
            'counts': {'files': len(graph['input_paths']), 'nodes': len(graph['nodes']), 'edges': len(graph['edges']),
                       'entry_candidates': len(graph['cpp_transmission']['entries']), 'json_sources': len(sources),
                       'transmissions': len(transmissions), 'response_exits': 4, 'response_send_paths': result['total_links'],
                       'encoding_branches_with_lineage': 3},
            'negative_checks': {'removing_selected_json_callee_disconnects_provider': True},
            'file_hash_verification': 'not_run_per_user_preference'}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ['graph', 'cgc-db', 'output', 'python-log', 'typescript-log']: ap.add_argument('--' + name, type=Path, required=True)
    a = ap.parse_args()
    if a.output.resolve().is_relative_to(ROOT): raise ValueError('Keep database copies outside research repository')
    a.output.mkdir(parents=True, exist_ok=False)
    graph = json.loads(a.graph.read_text(encoding='utf-8')); report = assess(graph)
    report['rules_revision'] = subprocess.check_output(['git', 'log', '-1', '--format=%H', '--',
        'adapters/cpp_transmission.py', 'adapters/cpp_library_types.py', 'adapters/transmission_graph.py', 'adapters/transmission_queries.py'], cwd=ROOT, text=True).strip()
    report['parser_versions'] = {name: version(name) for name in ['tree-sitter', 'tree-sitter-language-pack']}
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
        print('Persist JSON-to-send paths and repeat provider/correlation queries', flush=True)
        inserted = store.replace_snapshot(conn, graph); saved = store.read_snapshot(conn, graph['snapshot'])
        assert saved == graph and assess(saved) == assess(graph)
        assert explain_correlation(saved, report['query']['provider']) == explain_correlation(graph, report['query']['provider'])
        assert native == store.rows(conn.execute('MATCH (n:Function) RETURN n ORDER BY n.uid'))
        report['storage'] = {**inserted, 'payload_roundtrip': True, 'transmission_query_pass': True, 'correlation_query_pass': True,
                            'native_rows_unchanged': len(native), 'buffer_pool_mb': 1024}
    finally:
        conn.close(); db.close()
        if handle: handle.close()
    packed = compact(report); assert compact(expand(packed)) == packed
    (a.output/'transmission.json').write_text(json.dumps(packed, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['counts', 'tests', 'storage']}))
