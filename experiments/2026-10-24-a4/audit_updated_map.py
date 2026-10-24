"""Distinguish input/symbol update success from missed protocol consumers."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.project_map import ProjectMap


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('index', 'old-index', 'preparation', 'output'): p.add_argument('--'+key, type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    q, old = ProjectMap(a.index), ProjectMap(a.old_index)
    preparation = json.loads(a.preparation.read_text(encoding='utf-8'))
    checks, capability_checks = {}, {}
    try:
        checks['updated_commit_matches'] = q.info['source_commit'] == preparation['final_revision']
        checks['all_five_new_inputs_present'] = len(q.files('a4_client', limit=100)['items']) == 3 and len(q.files('a4_server', limit=100)['items']) == 2
        checks['module_and_input_denominators_updated'] = q.info['counts']['modules'] == 31 and q.info['counts']['input_files'] == 2315 and q.info['counts']['tracked_files'] == 4860
        symbols = q.search('renamedEntry', kind='callable', module='a4_client')['items']
        checks['renamed_source_symbol_present'] = bool(symbols)
        checks['deleted_or_renamed_provider_paths_absent'] = q.db.execute("SELECT count(*) FROM pm_fact_nodes WHERE path IN ('a4_server/protocol.cpp','a4_server/obsolete.cpp')").fetchone()[0] == 0
        checks['renamed_provider_identity_present'] = bool(q.providers('a4/final')['items'])
        checks['deleted_provider_identity_absent'] = not q.providers('a4/retired')['items']
        old_cursor = old.search(limit=1)['next_cursor']
        try:
            q.search(cursor=old_cursor)
            checks['old_cursor_rejected'] = False
        except ValueError:
            checks['old_cursor_rejected'] = True
        checks['old_snapshot_still_readable'] = old.info['source_commit'] == preparation['base'] and bool(old.entries('getUnitFlows')['items'])
        entries = q.entries('renamedEntry')['items']
        retired = q.entries('retiredEntry')['items']
        capability_checks['new_direct_socket_consumer_discovered'] = bool(entries)
        capability_checks['retired_direct_socket_consumer_reported_unmatched'] = bool(retired) and all(e['status'] == 'unmatched' for e in retired)
        sockets = q.search(kind='source_socket_send', module='a4_client', limit=100)['items']
        result = {'evidence_kind': 'executed_full_product_update_and_navigation_queries',
            'source_commit': q.info['source_commit'], 'snapshot': q.info['snapshot'], 'counts': q.info['counts'],
            'checks': checks, 'update_fidelity_passed': all(checks.values()),
            'protocol_discovery_checks': capability_checks, 'protocol_discovery_passed': all(capability_checks.values()),
            'direct_socket_sends_found': sockets, 'new_protocol_entries': entries, 'retired_protocol_entries': retired,
            'gap': 'socket facts exist but direct exported sends are not seeded as protocol consumers',
            'file_hash_verification': 'not_run_per_user_preference'}
        (a.output/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(json.dumps({'updates': checks, 'discovery': capability_checks, 'socket_sends': len(sockets)}))
    finally:
        q.close(); old.close()
