"""Execute D01-D05 together on the same generated graph and stored snapshot."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.chain_queries import explain_chain
from adapters import kuzu_fact_graph as store
from run_selection import assess as assess_selection
from run_return_bridge import assess as assess_return
from run_response_routing import compact, expand


def assess(graph):
    selection = assess_selection(graph); returns = assess_return(graph)
    provider = returns['query']['provider']; chain = explain_chain(graph, provider, ['unitAllFlows'])
    assert chain['status'] == 'conditional_source_chain' and not chain['truncated']
    summary = chain['summary']; nodes = {n['id']: n for n in graph['nodes']}
    assert [nodes[a]['name'] for a in summary['apis']] == ['getUnitFlows']
    assert {nodes[a]['name'] for a in summary['producer_candidates']} == {
        'Dic::Module::Timeline::TextTraceDatabase::QueryUnitFlows', 'Dic::Module::FullDb::DbTraceDataBase::QueryUnitFlows'}
    assert summary['response_exits'] == 4 and summary['transmission_paths'] == 16
    assert len(summary['states']) == 2 and set(summary['reverse_states'].values()) == {4}
    assert summary['database_reverse_paths'] == 2
    stages = Counter(r['stage'] for r in chain['relations'])
    assert set(stages) == {'request', 'database', 'database_selection', 'production', 'response_object', 'serialization',
        'response_transport', 'server_connection', 'socket_delivery', 'iframe_reply', 'frontend_state', 'source_conditions'}
    assert stages['production'] == 7 and stages['database_selection'] == 3
    paths = set(graph['input_paths'])
    assert all(r['evidence'] and all(e in chain['evidence'] for e in r['evidence']) for r in chain['relations'])
    assert all(e['path'] in paths and e['line'] > 0 for e in chain['evidence'].values())
    encoded = [r for r in chain['relations'] if r['kind'] == 'win32_encoding_output']
    assert {r['model'] for r in encoded} == {'MultiByteToWideChar', 'WideCharToMultiByte'}
    assert all(any(c.get('kind') == 'library_precondition' for c in r['conditions'] if isinstance(c, dict)) for r in encoded)
    guards = graph['source_conditions']['guards']; assert len(guards) == 3 and all(g['value'] is False for g in guards)
    queue, = graph['source_conditions']['constants']; assert queue['field']['name'] == 'useResponseQueue'
    assert queue['status'] == 'source_const_member' and not queue['missing_constructors']
    assert chain['gaps'] and chain['unexpanded'] and chain['runtime_observation'] == 'not_executed_in_P3'
    negatives = {}
    original_edges = graph['edges']
    try:
        graph['edges'] = [e for e in original_edges if e['kind'] != 'MATCHES_REGISTERED_PROTOCOL']
        disconnected = explain_chain(graph, provider, ['unitAllFlows'])
        assert disconnected['status'] == 'unresolved' and disconnected['summary']['database_reverse_paths'] == 0
        negatives['deleted_protocol_bridge_breaks_combined_chain'] = True
    finally: graph['edges'] = original_edges
    unrelated = explain_chain(graph, provider, ['nonexistent_response_field'])
    assert unrelated['status'] == 'unresolved' and not unrelated['summary']['states']
    negatives['unrelated_field_has_no_state_or_producer_claim'] = True
    return {'evidence_kind': 'executed_combined_source_queries_and_storage', 'source_commit': graph['source_commit'],
        'snapshot': graph['snapshot'], 'phase_status': 'P3_complete_selected_source_scope',
        'gates': {k: 'pass' for k in ['D01', 'D02', 'D03', 'D04', 'D05']},
        'scope': '154 selected source files; conditional static relations, candidates and explicit unexpanded internals',
        'counts': {'files': len(graph['input_paths']), 'nodes': len(graph['nodes']), 'edges': len(graph['edges']),
                   'chain_relations': len(chain['relations']), 'source_evidence': len(chain['evidence'])},
        'chain': chain, 'stages': dict(stages),
        'selection': {k: selection[k] for k in ['database_paths', 'factory_conditions', 'instance', 'instance_paths', 'receiver_runtime_conditions']},
        'return_checks': {k: returns[k] for k in ['reverse_queries', 'negative_checks', 'all_return_summary']},
        'negative_checks': negatives,
        'remaining_phases': ['P4_versioned_refresh', 'P5_actual_runtime', 'P6_external_history_assets', 'P7_reuse_and_project_map'],
        'file_hash_verification': 'not_run_per_user_preference'}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ['graph', 'cgc-db', 'output', 'python-log', 'typescript-log']: ap.add_argument('--' + name, type=Path, required=True)
    a = ap.parse_args()
    if a.output.resolve().is_relative_to(ROOT): raise ValueError('Keep database outside Git')
    a.output.mkdir(parents=True, exist_ok=False)
    graph = json.loads(a.graph.read_text(encoding='utf-8')); report = assess(graph)
    report['rules_revision'] = subprocess.check_output(['git', 'log', '-1', '--format=%H', '--', 'adapters', 'scripts/build_chain_closure_graph.py'], cwd=ROOT, text=True).strip()
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
        print('Persist final P3 snapshot and rerun D01-D05 together', flush=True)
        inserted = store.replace_snapshot(conn, graph); saved = store.read_snapshot(conn, graph['snapshot'])
        assert saved == graph and assess(saved) == assess(graph)
        assert native == store.rows(conn.execute('MATCH (n:Function) RETURN n ORDER BY n.uid'))
        report['storage'] = {**inserted, 'payload_roundtrip': True, 'combined_gates_pass': True, 'native_rows_unchanged': len(native)}
    finally:
        conn.close(); db.close()
        if handle: handle.close()
    packed = compact(report); assert compact(expand(packed)) == packed
    assert expand(packed)['chain'] == report['chain']
    (a.output/'combined.json').write_text(json.dumps(packed, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['gates', 'counts', 'tests', 'storage']}))
