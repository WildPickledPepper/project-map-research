"""Replay native process evidence without loading the full exported graph."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.native_process_sites import augment
from adapters.project_map import ProjectMap, build_index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    destination = args.output.resolve()
    if destination.is_relative_to(ROOT) or destination.exists():
        parser.error('Use a new output outside the research checkout')
    destination.mkdir(parents=True)
    started = time.monotonic()
    db = sqlite3.connect(args.index.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        db.execute('PRAGMA query_only=ON')
        db.execute('PRAGMA cache_size=-8192')
        db.set_progress_handler(lambda: int(time.monotonic() - started > 60), 10000)
        info = json.loads(db.execute('SELECT payload FROM pm_map_info').fetchone()[0])
        if info['source_commit'] != args.revision:
            raise ValueError('Wrong source revision')
        snapshot = info['snapshot']
        files = [json.loads(r[0]) for r in db.execute('SELECT payload FROM pm_map_files ORDER BY path')]
        nodes = {}
        for kind in ('python_boundary', 'rust_boundary'):
            for (payload,) in db.execute('SELECT payload FROM pm_fact_nodes WHERE snapshot=? AND kind=?',
                                        (snapshot, kind)):
                node = json.loads(payload)
                nodes[node['id']] = node
        for file in files:
            if file.get('language') == 'shell':
                for (payload,) in db.execute(
                        "SELECT payload FROM pm_fact_nodes WHERE snapshot=? AND path=? AND kind='call_site'",
                        (snapshot, file['path'])):
                    node = json.loads(payload)
                    nodes[node['id']] = node
        edges = [json.loads(r[0]) for r in db.execute(
            "SELECT payload FROM pm_fact_edges WHERE snapshot=? AND kind='CBM_SPAWNS'", (snapshot,))]
        for edge in edges:
            for uid in (edge['source'], edge['target']):
                if uid not in nodes:
                    nodes[uid] = json.loads(db.execute(
                        'SELECT payload FROM pm_fact_nodes WHERE snapshot=? AND id=?', (snapshot, uid)).fetchone()[0])
        discovery = {'source_commit': args.revision,
                     'files': files,
                     'modules': [json.loads(r[0]) for r in db.execute('SELECT payload FROM pm_map_modules ORDER BY path')],
                     'provenance': {'input': 'existing_committed_source_navigation_index'}}
    finally:
        db.close()
    selected = sorted({n['path'] for n in nodes.values() if n['path']})
    native_edge_count = len(edges)
    graph = {'snapshot': snapshot + ':native-process-site-replay', 'source_commit': args.revision,
             'input_paths': selected, 'nodes': list(nodes.values()), 'edges': edges, 'diagnostics': [],
             'coverage': [{'path': path, 'status': 'selected_facts_not_full_file_analysis'} for path in selected],
             'limits': ['selected_process_evidence_replay_not_a_full_map_rebuild']}
    augment(graph)
    (destination / 'graph.json').write_text(json.dumps(graph, ensure_ascii=False), encoding='utf-8')
    build_index(graph, discovery, destination / 'navigation.sqlite')
    checks = []
    query = ProjectMap(destination / 'navigation.sqlite', expected_snapshot=graph['snapshot'])
    try:
        for edge in graph['edges']:
            if edge['kind'] != 'MAY_EXECUTE_SOURCE_MODULE':
                continue
            forward = query.walk(edge['source'], target=edge['target'], depth=1, kinds=[edge['kind']])
            reverse = query.walk(edge['target'], target=edge['source'], depth=1, direction='in', kinds=[edge['kind']])
            checks.append({'case': 'native_source_counterpart_bidirectional', 'source': edge['source'],
                           'target': edge['target'], 'passed': forward['found'] and reverse['found']})
            for anchor in graph['edges']:
                if anchor['kind'] != 'HAS_NATIVE_PROCESS_EVIDENCE' or anchor['target'] != edge['source']:
                    continue
                kinds = ['HAS_NATIVE_PROCESS_EVIDENCE', 'MAY_EXECUTE_SOURCE_MODULE']
                forward = query.walk(anchor['source'], target=edge['target'], depth=2, kinds=kinds)
                reverse = query.walk(edge['target'], target=anchor['source'], depth=2, direction='in', kinds=kinds)
                checks.append({'case': 'source_call_to_native_target_bidirectional',
                               'source': anchor['source'], 'target': edge['target'],
                               'passed': forward['found'] and reverse['found']})
        sites = [n for n in graph['nodes'] if n['kind'] == 'native_process_site']
        checks.append({'case': 'every_supplied_native_spawn_accounted', 'passed': len(sites) == native_edge_count})
        descriptions = {n['native_target'] for n in sites if n['counterpart_status'] != 'native_source_target_candidate'}
        checks.append({'case': 'no_new_instance_edge_to_shared_program_descriptions',
                       'passed': not any(e['target'] in descriptions for e in graph['edges'] if e['kind'] != 'CBM_SPAWNS')})
    finally:
        query.close()
    owners = {r['path']: r['module'] for r in discovery['files']}
    result = {'schema': 'native-process-bridge-replay/1', 'source_commit': args.revision,
              'baseline_snapshot': snapshot, 'summary': graph['native_process_sites'],
              'selected_counts': {'nodes': len(graph['nodes']), 'edges': len(graph['edges'])},
              'sites_by_structural_module': dict(Counter(owners[n['path']] for n in sites)),
              'seconds': round(time.monotonic() - started, 3), 'checks': checks,
              'passed': all(c['passed'] for c in checks), 'default_whole_map_updated': False,
              'G03_G04_accepted': False,
              'limits': ['native_spawn_count_is_not_all_boundary_signal_coverage',
                         'legacy_native_edges_still_include_shared_program_description_targets']}
    (destination / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
