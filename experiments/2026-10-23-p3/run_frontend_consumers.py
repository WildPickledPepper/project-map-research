"""Score extracted frontend consumers and repeat queries after native Kuzu storage."""
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
from adapters.frontend_queries import explain_frontend
from adapters.response_queries import explain_response
from adapters import kuzu_fact_graph as store
from run_response_routing import compact, expand


def assess(graph):
    names = {n['id']: n['name'] for n in graph['nodes']}
    api = next(n['id'] for n in graph['nodes'] if n['kind'] == 'callable' and n['name'] == 'getUnitFlows')
    query = explain_frontend(graph, api=api)
    assert not query['truncated'] and not query['extraction_truncated']
    assert len(query['api_calls']) == 2 and len(query['writes']) == 6
    assert len({c['request_context'] for c in query['api_calls']}) == 2
    assert {names[c['entry']] for c in query['api_calls']} == {'onClick', 'getSingleFlow'}
    values = [w for w in query['writes'] if w['matching_dependencies']]
    assert len(values) == 2
    expected = {('unitAllFlows', '*', 'cat'), ('unitAllFlows', '*', 'flows', '*', 'cat'),
                ('unitAllFlows', '*', 'flows', '*', 'from'), ('unitAllFlows', '*', 'flows', '*', 'from', 'dbPath'),
                ('unitAllFlows', '*', 'flows', '*', 'to'), ('unitAllFlows', '*', 'flows', '*', 'to', 'dbPath')}
    for write in values:
        assert write['target']['path'] == ['singleLinkLine']
        assert {tuple(d['path']) for d in write['matching_dependencies']} == expected
        assert all(d['call_chain'] for d in write['matching_dependencies'])
        assert any(c.get('kind') == 'external_callee_invokes_callback' for c in write['conditions'])
        assert any(d['gaps'] for d in write['matching_dependencies'])
        reverse = explain_frontend(graph, state=write['state_node'])
        assert len(reverse['writes']) == 1 and len(reverse['api_calls']) == 1
        assert reverse['api_calls'][0]['entry'] == write['entry']
    continuation = [w for w in query['writes'] if not w['matching_dependencies']]
    assert sorted(w['target']['path'][0] for w in continuation) == ['drawLineMode', 'linkLines', 'renderTrigger', 'renderTrigger']
    field = explain_frontend(graph, api=api, field_path=['unitAllFlows'])
    assert len(field['writes']) == 2
    assert not explain_frontend(graph, api=api, field_path=['absentField'])['writes']
    other = next(c['api'] for c in graph['frontend']['api_calls'] if c['api'] != api)
    assert not explain_frontend(graph, api=other, state=values[0]['state_node'])['writes']
    assert query['transport_status'] == 'pending_transport_join'
    return {'evidence_kind': 'executed_source_extraction_and_scoped_frontend_query',
            'source_commit': graph['source_commit'], 'snapshot': graph['snapshot'],
            'phase_status': 'P3_in_progress', 'gate_under_test': 'D02_incomplete',
            'counts': {'files': len(graph['input_paths']), 'nodes': len(graph['nodes']), 'edges': len(graph['edges']),
                       'entries_analyzed': len(graph['frontend']['entries']), 'api_calls_extracted': len(graph['frontend']['api_calls']),
                       'field_reads_extracted': len(graph['frontend']['field_reads']), 'state_writes_extracted': len(graph['frontend']['state_writes']),
                       'target_requests': 2, 'target_value_writes': 2, 'target_continuation_writes': 4},
            'query': query, 'field_query_write_ids': [w['id'] for w in field['writes']],
            'negative_checks': {'unrelated_field': True, 'unrelated_api': True, 'state_receiver_scope': True},
            'symbols': {uid: names[uid] for uid in {api, other, *(c['entry'] for c in graph['frontend']['api_calls'])}},
            'compiler': graph['provenance']['frontend_compiler'],
            'remaining': ['D02 JSON transport and request/response callback correlation',
                          'D02 frontend unpacking and join to API fulfillment boundary',
                          'D03 response field reverse influence across transport', 'D05 whole-chain explanation',
                          'conditional queue transfer model'],
            'file_hash_verification': 'not_run_per_user_preference'}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ['graph', 'cgc-db', 'output', 'python-log', 'typescript-log']:
        ap.add_argument('--' + name, type=Path, required=True)
    a = ap.parse_args()
    if a.output.resolve().is_relative_to(ROOT):
        raise ValueError('Keep database copies outside the research repository')
    a.output.mkdir(parents=True, exist_ok=False)
    graph = json.loads(a.graph.read_text(encoding='utf-8')); report = assess(graph)
    report['rules_revision'] = subprocess.check_output(['git', 'log', '-1', '--format=%H', '--',
        'adapters/typescript_data_flow.cjs', 'adapters/frontend_graph.py', 'adapters/frontend_queries.py'], cwd=ROOT, text=True).strip()
    py = a.python_log.read_text(encoding='utf-8'); ts = a.typescript_log.read_text(encoding='utf-8')
    assert re.search(r'\nOK\s*$', py) and '# fail 0' in ts
    report['tests'] = {'python': int(re.search(r'Ran (\d+) tests', py)[1]),
                       'typescript': int(re.search(r'# pass (\d+)', ts)[1]), 'passed': True}
    wal = Path(str(a.cgc_db) + '.wal')
    if wal.exists() and wal.stat().st_size:
        raise ValueError('Close native database before copying')
    shutil.copy2(a.cgc_db, a.output / 'cgc.kuzu')
    handle = os.add_dll_directory(os.environ['PROJECT_MAP_DLL_DIR']) if os.name == 'nt' and os.environ.get('PROJECT_MAP_DLL_DIR') else None
    import kuzu
    db = kuzu.Database(str(a.output / 'cgc.kuzu'), buffer_pool_size=1024*1024*1024)
    conn = kuzu.Connection(db)
    try:
        native = store.rows(conn.execute('MATCH (n:Function) RETURN n ORDER BY n.uid'))
        print('Persist frontend graph and repeat frontend/response queries', flush=True)
        inserted = store.replace_snapshot(conn, graph)
        saved = store.read_snapshot(conn, graph['snapshot'])
        assert saved == graph and assess(saved) == assess(graph)
        provider = next(p['id'] for p in graph['protocol']['providers'] if p['command'] == 'unit/flows')
        response = explain_response(graph, provider)
        assert len(response['routes']) == 4 and explain_response(saved, provider) == response
        assert native == store.rows(conn.execute('MATCH (n:Function) RETURN n ORDER BY n.uid'))
        report['storage'] = {**inserted, 'payload_roundtrip': True, 'stored_frontend_query_pass': True,
                             'stored_response_query_pass': True, 'native_rows_unchanged': len(native), 'buffer_pool_mb': 1024}
    finally:
        conn.close(); db.close()
        if handle: handle.close()
    packed = compact(report)
    assert compact(expand(packed)) == packed
    (a.output / 'frontend-consumers.json').write_text(json.dumps(packed, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['counts', 'tests', 'storage']}))
