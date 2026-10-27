"""Account for frozen source signals against existing semantic/provider facts.

This is an evaluation ledger, not a production extractor or recall proof. A
source-line observation does not establish a unique call or runtime identity.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


FAMILIES = {
    'process_start': {'process_start', 'command_constructor'},
    'process_stop': {'process_stop', 'process_wait'},
    'webview_load': {'frontend_loader', 'webview_builder'},
}
STOP_CALL = re.compile(r'(?:^|\.)(kill|terminate|wait|join)$')
NON_PROCESS_APIS = {'os.path.join', 'posixpath.join', 'ntpath.join', 'str.join'}


def inspect_signal(signal, nodes):
    family = signal['family']
    boundaries = [n for n in nodes if n['kind'] in {'python_boundary', 'rust_boundary'}
                  and n.get('family') in FAMILIES[family]]
    native = [n for n in nodes if n['kind'] == 'native_process_site' and family == 'process_start']
    observations = boundaries + native
    status = 'source_boundary_observed_counterpart_unverified' if observations else 'no_semantic_boundary_observation'
    proof = []
    if family == 'process_stop' and not observations:
        operations = [n for n in nodes if n['kind'] == 'call_site' and n.get('language') == 'python'
                      and STOP_CALL.search(n['name'])]
        for node in operations:
            inference = node.get('inference', [])
            apis = {item.get('qualified_name') for item in inference}
            if (apis and apis <= NON_PROCESS_APIS and all(
                    item.get('origin_scope') == 'external_or_builtin' and not item.get('input') for item in inference)):
                proof.append({'id': node['id'], 'apis': sorted(apis), 'basis': 'existing_jedi_external_api_inference'})
        if operations and len(proof) == len(operations):
            status = 'lexical_candidate_has_only_non_process_api_observations'
    return {'id': signal['id'], 'family': family, 'module': signal['module'],
            'path': signal['evidence']['path'], 'line': signal['evidence']['line'],
            'status': status, 'observation_ids': sorted(n['id'] for n in observations),
            'non_process_api_observations': proof,
            'call_identity': 'source_line_coincidence_only_not_unique_identity',
            'counterpart_accepted': False, 'runtime_execution': 'not_observed'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inventory', type=Path, required=True)
    p.add_argument('--index', type=Path, required=True)
    p.add_argument('--process-replay', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    destination = args.output.resolve()
    if destination.is_relative_to(ROOT) or destination.exists():
        p.error('Use a new output outside the research checkout')
    destination.mkdir(parents=True)
    inventory = json.loads(args.inventory.read_text(encoding='utf-8'))
    replay = json.loads((args.process_replay / 'graph.json').read_text(encoding='utf-8'))
    db = sqlite3.connect(args.index.resolve().as_uri() + '?mode=ro', uri=True)
    started = time.monotonic()
    db.set_progress_handler(lambda: int(time.monotonic() - started > 60), 10000)
    try:
        info = json.loads(db.execute('SELECT payload FROM pm_map_info').fetchone()[0])
        if info['source_commit'] != inventory['source_commit'] or info['source_commit'] != replay['source_commit']:
            raise ValueError('Source revision mismatch')
        snapshot = info['snapshot']
        selected = [r for r in inventory['boundaries'] if r['family'] in FAMILIES]
        wanted = {(r['evidence']['path'], r['evidence']['line']) for r in selected}
        by_site = defaultdict(list)
        wanted_lines = defaultdict(set)
        for path, line in wanted:
            wanted_lines[path].add(line)
        for path in sorted({key[0] for key in wanted}):
            calls, boundaries = {}, []
            for (payload,) in db.execute('''SELECT payload FROM pm_fact_nodes WHERE snapshot=? AND path=?
                    AND kind IN ('python_boundary','rust_boundary','call_site')''', (snapshot, path)):
                node = json.loads(payload)
                if node['kind'] == 'call_site':
                    calls[node['id']] = node
                else:
                    boundaries.append(node)
                if (path, node['line']) in wanted:
                    by_site[(path, node['line'])].append(node)
            for node in boundaries:
                call = calls.get(node['call'], {})
                end_line = call.get('end_line', call.get('line', node['line']) + call.get('expression', '').count('\n'))
                for line in wanted_lines[path]:
                    if node['line'] < line <= end_line:
                        by_site[(path, line)].append(node)
        for node in replay['nodes']:
            if node['kind'] == 'native_process_site':
                by_site[(node['path'], node['line'])].append(node)
    finally:
        db.close()
    rows = [inspect_signal(r, by_site[(r['evidence']['path'], r['evidence']['line'])]) for r in selected]
    native_sites = [n for n in replay['nodes'] if n['kind'] == 'native_process_site']
    extras = [{'path': n['path'], 'line': n['line'], 'operation': n['operation'], 'native_edge': n['native_edge'],
               'anchor_status': n['anchor_status'], 'counterpart_status': n['counterpart_status']}
              for n in native_sites if (n['path'], n['line']) not in wanted]
    by_family = {family: dict(Counter(r['status'] for r in rows if r['family'] == family)) for family in FAMILIES}
    output = {'schema': 'startup-boundary-signal-audit/1', 'source_commit': info['source_commit'],
              'baseline_snapshot': snapshot, 'origin': 'frozen_lexical_signals_vs_existing_semantic_observations',
              'families': by_family, 'selected_signals': len(rows), 'rows': rows,
              'native_sites_outside_selected_lexical_signals': extras,
              'seconds': round(time.monotonic() - started, 3), 'G03_G04_accepted': False,
              'limits': ['all_signal_rows_retained_including_non_process_api_observations',
                         'line_coincidence_does_not_establish_matching_call_identity',
                         'native_extras_extend_discovery_not_a_new_complete_denominator',
                         'build_container_and_shell_inventory_not_exhausted_by_these_three_lexical_families']}
    (destination / 'audit.json').write_text(json.dumps(output, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in output.items() if k not in {'rows','native_sites_outside_selected_lexical_signals'}}))


if __name__ == '__main__':
    main()
