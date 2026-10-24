"""Build and audit the repaired full graph's existing SQLite navigation index."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.project_map import build_index, ProjectMap
from adapters.protocol_graph import PROTOCOL_KINDS
from adapters.repository_discovery import discover


def run(graph_path, source, old_index, output):
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    graph = json.loads(graph_path.read_text(encoding='utf-8'))
    discovery = discover(source, graph['source_commit'])
    index = output/'map.sqlite'
    build_index(graph, discovery, index, navigation_version={'schema':'project-map/1','experiment':'A4 repair',
                'rules_commit':graph['version']['build_version']['rules_commit']})
    q, old = ProjectMap(index), ProjectMap(old_index)
    checks, samples = {}, {}
    try:
        counts = q.info['counts']
        checks['all_node_counts_equal'] = q.db.execute('SELECT count(*) FROM pm_fact_nodes').fetchone()[0] == len(graph['nodes'])
        checks['all_edge_counts_equal'] = q.db.execute('SELECT count(*) FROM pm_fact_edges').fetchone()[0] == len(graph['edges'])
        checks['all_node_payloads_equal'] = all(json.loads(row[0])==node for row,node in zip(
            q.db.execute('SELECT payload FROM pm_fact_nodes ORDER BY rowid'),graph['nodes']))
        checks['all_parallel_edge_payloads_equal'] = all(json.loads(row[0])==edge for row,edge in zip(
            q.db.execute('SELECT payload FROM pm_fact_edges ORDER BY ordinal'),graph['edges']))
        checks['all_protocol_entry_payloads_equal'] = [json.loads(r[0]) for r in q.db.execute('SELECT payload FROM pm_map_entries ORDER BY rowid')] == graph['protocol']['results']
        checks['all_provider_payloads_equal'] = [json.loads(r[0]) for r in q.db.execute('SELECT payload FROM pm_map_providers ORDER BY rowid')] == graph['protocol']['providers']
        checks['automatic_product_counts'] = counts['modules']==31 and counts['input_files']==2315 and counts['tracked_files']==4860
        checks['correct_source_commit'] = q.info['source_commit']==graph['source_commit']
        checks['new_direct_consumer_found'] = any(e['status']=='matched_conditional' for e in q.entries('renamedEntry')['items'])
        checks['deleted_provider_invalidates_direct_consumer'] = bool(q.entries('retiredEntry')['items']) and all(e['status']=='unmatched' for e in q.entries('retiredEntry')['items'])
        checks['removed_paths_absent'] = q.db.execute("SELECT count(*) FROM pm_fact_nodes WHERE path IN ('a4_server/protocol.cpp','a4_server/obsolete.cpp')").fetchone()[0]==0
        checks['deleted_provider_absent'] = not q.providers('a4/retired')['items']
        checks['renamed_provider_present'] = bool(q.providers('a4/final')['items'])
        cursor = old.search(limit=1)['next_cursor']
        try:
            q.search(cursor=cursor); checks['old_cursor_rejected']=False
        except ValueError: checks['old_cursor_rejected']=True
        checks['old_snapshot_readable'] = bool(old.entries('getUnitFlows')['items'])
        for name in ['queryIterations','queryStages','queryOperatorCategory','queryOperatorComputeUnit','getBlocksGraphData','getLeaksAllocationsData','getTraceData','getNumaOverview','getBasicInfo']:
            result = q.entries(name)
            samples[name]=result
            checks[name+'_matched_visible'] = result['stop_reason'] is None and any(e['status']=='matched_conditional' for e in result['items'])
        provider = next(p for p in graph['protocol']['providers'] if p['command']=='a4/final')
        entry = q.entries('renamedEntry')['items'][0]
        start = q.neighbors(entry['node'],'in',['EMITS_MESSAGE'])['items'][0]['source']
        target = provider['handler_methods'][0]
        forward = q.walk(start,target=target,depth=8,kinds=PROTOCOL_KINDS)
        reverse = q.walk(target,target=start,direction='in',depth=8,kinds=PROTOCOL_KINDS)
        checks['direct_protocol_bidirectional_navigation'] = forward['found'] and reverse['found']
        samples['direct_forward'],samples['direct_reverse']=forward,reverse
        pinned = q.source(source,selector=start,context=1)
        checks['pinned_committed_source_readable'] = bool(pinned['items']) and not pinned['working_tree_read']
        result = {'evidence_kind':'executed_repaired_full_graph_navigation_fidelity',
            'source_commit':graph['source_commit'],'snapshot':graph['snapshot'],'build_version':graph['version']['build_version'],
            'checks':checks,'passed':all(checks.values()),'counts':counts,'index_bytes':index.stat().st_size,
            'protocol_status_records':dict(Counter(r['status'] for r in graph['protocol']['results'])),
            'unique_consumer_identities':len({r['consumer'] for r in graph['protocol']['results']}),
            'elapsed_seconds':round(time.perf_counter()-started,4),'file_hash_verification':'not_run_per_user_preference'}
        for name,value in [('result.json',result),('query-samples.json',samples)]:
            (output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'passed':result['passed'],'checks':checks,'counts':counts}))
        return result
    finally: q.close(); old.close()


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('graph','source','old-index','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();run(a.graph.resolve(),a.source.resolve(),a.old_index.resolve(),a.output.resolve())
