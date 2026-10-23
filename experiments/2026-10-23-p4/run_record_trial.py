"""Exercise historical records against two real Insight snapshots using synthetic records."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.snapshot_refresh import read_snapshot, read_state
from adapters.snapshot_records import append_record, query_record, snapshot_basis


def run(store, output, before, after):
    output = Path(output).resolve()
    if output.is_relative_to(ROOT): raise ValueError('Keep raw record trial outputs outside Git')
    output.mkdir(parents=True, exist_ok=False)
    basis = snapshot_basis(store, before)
    graph = json.loads((Path(read_snapshot(store, before)['directory'])/'graph.json').read_text(encoding='utf-8'))
    # These names select experiment targets after extraction; they are not builder inputs.
    entry = next(n for n in graph['nodes'] if n['kind'] == 'callable' and n['name'] == 'getUnitFlows')
    registration = next(n for n in graph['nodes'] if n['kind'] == 'protocol_registration' and n['name'] == 'unit/flows')
    tool_commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    original_state = read_state(store); results = []
    for kind in ('trace', 'summary', 'verification', 'asset_anchor'):
        record = append_record(store, {'kind': kind, 'basis': basis,
            'provenance': {'evidence_kind': 'synthetic', 'source_ref': 'synthetic:p4/insight-version-transition',
                           'producer': {'name': 'run_record_trial', 'version': tool_commit}},
            'payload': {'scenario': 'synthetic_version_binding_probe', 'outcome': 'synthetic_pass',
                        'description': 'Envelope test on real static graphs; no product run or real historical asset'},
            'anchors': [{'label': 'client', 'node_id': entry['id']}, {'label': 'registration', 'node_id': registration['id']},
                        {'label': 'unmapped_event', 'reason': 'synthetic event without a source anchor'}]})
        old = query_record(store, record['id'], snapshot_id=before)
        new = query_record(store, record['id'], snapshot_id=after)
        statuses = {a['label']: a['status'] for a in new['anchors']}
        assert old['eligible_for_direct_overlay'] and old['version_relation'] == 'same_snapshot'
        assert not new['eligible_for_direct_overlay'] and not new['verification_carried_forward']
        assert old['record'] == new['record'] == record
        assert statuses == {'client': 'candidate', 'registration': 'dangling', 'unmapped_event': 'unmapped'}, statuses
        (output/(kind + '.json')).write_text(json.dumps({'original': old, 'requested': new}, ensure_ascii=False), encoding='utf-8')
        results.append({'kind': kind, 'id': record['id'], 'original_overlay': True, 'new_overlay': False,
                        'original_record_unchanged': True, 'new_anchor_statuses': statuses,
                        'verification_carried_forward': False})
    assert read_state(store) == original_state, 'Record append must not modify graph publication'
    report = {'evidence_kind': 'executed_record_envelope_test_on_real_Insight_graphs',
              'records_evidence_kind': 'synthetic', 'producer_commit': tool_commit,
              'before': {k: basis[k] for k in ('id', 'snapshot', 'source_commit', 'build_version')},
              'after': {k: snapshot_basis(store, after)[k] for k in ('id', 'snapshot', 'source_commit', 'build_version')},
              'results': results, 'graph_publication_unchanged': True,
              'scope': 'P4 version binding; real product runs and real external assets are not inputs',
              'file_hash_verification': 'not_run_per_user_preference'}
    (output/'record-trial.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'records': len(results), 'passed': True}))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('store', 'output'): ap.add_argument('--' + name, type=Path, required=True)
    for name in ('before', 'after'): ap.add_argument('--' + name, required=True)
    a = ap.parse_args(); run(a.store, a.output, a.before, a.after)
