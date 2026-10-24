"""Audit A3 against the existing A2 graph; uses known regressions and authored controls."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.project_map import Budget, ProjectMap, encoded
from adapters.protocol_graph import PROTOCOL_KINDS


def pages(call, **kwargs):
    items, cursor = [], None
    while True:
        result = call(cursor=cursor, **kwargs)
        if result.get('stop_reason') and not (result['stop_reason'] == 'output_budget' and result.get('next_cursor') and result['items']):
            raise AssertionError(result['stop_reason'])
        items.extend(result['items'])
        cursor = result['next_cursor']
        if not cursor:
            return items


def run(graph_path, index, source, output):
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    graph = json.loads(graph_path.read_text(encoding='utf-8'))
    q = ProjectMap(index, expected_snapshot=graph['snapshot'])
    checks, details = {}, {}
    def save(name, value):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    try:
        rows = q.db.execute('SELECT payload FROM pm_fact_nodes ORDER BY rowid')
        checks['all_node_payloads_equal'] = all(json.loads(row[0]) == node for row, node in zip(rows, graph['nodes']))
        rows = q.db.execute('SELECT payload FROM pm_fact_edges ORDER BY ordinal')
        checks['all_parallel_edge_payloads_equal'] = all(json.loads(row[0]) == edge for row, edge in zip(rows, graph['edges']))
        counts = q.info['counts']
        checks['all_counts_equal'] = counts['nodes'] == len(graph['nodes']) and counts['edges'] == len(graph['edges'])
        modules = pages(q.overview, limit=7)
        files = pages(q.files, limit=200)
        links = pages(q.links, limit=19)
        checks['automatic_module_file_input_counts'] = len(modules) == 29 and len(files) == 4855 and sum(f['graph_input'] for f in files) == 2310
        checks['module_links_have_source_status'] = bool(links) and all(x['status'] in {'candidate', 'conditional', 'source_fact', 'source_relation', 'static'} for x in links)
        save('overview.json', q.overview(limit=100))
        save('module-links.json', links)
        entries = pages(q.entries, limit=13)
        checks['all_entry_statuses_retained'] = [e['status'] for e in entries] == [e['status'] for e in graph['protocol']['results']]
        entry_rows = q.db.execute('SELECT payload FROM pm_map_entries ORDER BY rowid')
        checks['entry_payloads_equal'] = [json.loads(r[0]) for r in entry_rows] == graph['protocol']['results']
        provider_rows = q.db.execute('SELECT payload FROM pm_map_providers ORDER BY rowid')
        checks['provider_payloads_equal'] = [json.loads(r[0]) for r in provider_rows] == graph['protocol']['providers']
        assessed = []
        for e in entries:
            if e['node']:
                status = q.status(e['node'])
                near = q.neighbors(e['node'], limit=1)
                assessed.append(bool(status['items']) and status['file'] is not None and near['stop_reason'] is None)
        checks['every_entry_node_has_status_and_expansion'] = all(assessed)
        details['entries'] = {'total': len(entries), 'with_node': len(assessed),
            'statuses': dict(Counter(e['status'] for e in entries)), 'assessed': len(assessed)}
        save('entries.json', entries)
        expectations = json.loads((ROOT / 'experiments/2026-10-24-a2/evidence/chain-regression.json').read_text(encoding='utf-8'))
        witnesses = []
        for case in expectations['chains']:
            api = case['api']
            message = q.entries(api)['items'][0]['node']
            incoming = q.neighbors(message, 'in', ['EMITS_MESSAGE'])['items']
            assert len(incoming) == 1
            start = incoming[0]['source']
            target = case['handler'][0]['id']
            forward = q.walk(start, target=target, depth=8, kinds=PROTOCOL_KINDS)
            reverse = q.walk(target, target=start, direction='in', depth=8, kinds=PROTOCOL_KINDS)
            checks[api + '_bidirectional_witness'] = forward['found'] and reverse['found']
            edge_id = forward['items'][1]['ordinal']
            conditions = pages(q.detail, entity='edge', uid=edge_id, pointer='/conditions', limit=5)
            evidence = pages(q.detail, entity='edge', uid=edge_id, pointer='/evidence', limit=5)
            checks[api + '_conditions_and_evidence'] = bool(conditions) and bool(evidence)
            text = q.source(source, selector=start, context=2)
            checks[api + '_pinned_source'] = bool(text['items']) and not text['working_tree_read']
            save(api + '-forward.json', forward)
            save(api + '-reverse.json', reverse)
            save(api + '-source.json', text)
            witnesses.append({'api': api, 'start': start, 'target': target, 'edges': len(forward['items']),
                'conditions': len(conditions), 'evidence': len(evidence)})
        details['protocol_regressions'] = witnesses
        # Resource selection comes from a known A2 regression, rather than a new held-out case.
        resources = pages(q.search, text='CurveContainer', kind='storage_member', limit=50)
        checks['resource_search_and_reverse_expand'] = bool(resources) and any(
            q.neighbors(r['id'], 'in', limit=1)['items'] for r in resources)
        fields = pages(q.search, text='unitAllFlows', kind='api_result_field', limit=50)
        states = pages(q.search, kind='frontend_state_write', module='modules/timeline', limit=50)
        checks['field_and_state_discovery'] = bool(fields) and bool(states)
        details['field_resource_navigation'] = {'resources': len(resources), 'fields': len(fields), 'timeline_states': len(states)}
        q.budget = Budget(nodes=1)
        checks['node_budget_visible'] = q.walk(witnesses[0]['start'])['stop_reason'] == 'node_budget'
        q.budget = Budget(edges=1)
        checks['edge_budget_visible'] = q.walk(witnesses[0]['start'])['stop_reason'] == 'edge_budget'
        q.budget = Budget(seconds=1e-9)
        checks['wall_budget_visible'] = q.search()['stop_reason'] == 'wall_time_budget'
        q.budget = Budget(output_bytes=8192)
        output_limited = q.search(kind='callable', limit=200)
        checks['output_budget_visible'] = output_limited['stop_reason'] == 'output_budget' and len(encoded(output_limited).encode()) <= 8192
        q.budget = Budget()
        checks['unsupported_languages_visible'] = any(f.get('language') == 'python' and not f['graph_input'] for f in files)
        checks['no_runtime_or_assets_invented'] = q.info['runtime_execution'] == 'unknown_unless_linked_run' and q.info['assets']['status'] == 'not_connected'
        diagnostics = q.diagnostics(limit=3)
        checks['diagnostics_and_global_limits_readable'] = bool(diagnostics['items']) and counts['diagnostic_records'] > 0
        result = {'evidence_kind': 'executed_A3_full_graph_navigation_acceptance',
            'source_commit': graph['source_commit'], 'snapshot': graph['snapshot'],
            'navigation_version': q.info['navigation_version'], 'graph_version': graph['version'],
            'counts': counts, 'checks': checks, 'passed': all(checks.values()), 'details': details,
            'elapsed_seconds': round(time.perf_counter() - started, 4),
            'comparison': 'direct parsed JSON equality for every node, parallel edge, consumer and provider; no hash verification',
            'historical_validation_candidates': 'not_used',
            'scope': 'navigation fidelity and known A2 regressions; semantic extraction correctness remains A4'}
        save('validation.json', result)
        print(encoded({'passed': result['passed'], 'checks': len(checks), 'failed': [k for k, v in checks.items() if not v]}))
        return result
    finally:
        q.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('graph', 'index', 'source', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    sys.exit(0 if run(a.graph, a.index, a.source, a.output)['passed'] else 1)
