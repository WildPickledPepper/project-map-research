"""Check the committed P5 acceptance bundle; raw runs are reproduced separately."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def read(name):
    return json.loads((HERE/'evidence'/(name+'.json')).read_text(encoding='utf-8'))


def main():
    boot, normal, late, parallel, fault, mapping = [read(n) for n in ('boot', 'normal', 'late', 'parallel', 'fault', 'mapping')]
    assert boot['status'] == normal['status'] == late['status'] == parallel['status'] == mapping['status'] == 'passed'
    assert len(normal['runs']) == len(late['runs']) == 3
    assert all(r['scenario_passed'] and r['capture_complete'] for r in normal['runs'])
    assert all(r['passed'] and r['capture_complete'] for r in late['runs'])
    assert len(parallel['requests']) == 2
    assert len({r['trace_id'] for r in parallel['requests']}) == 2
    assert len({r['slice_id'] for r in parallel['requests']}) == 2
    assert len(parallel['controls']['controls']) == 4
    assert all(c['passed'] and c['complete_chain_claim_rejected'] for c in parallel['controls']['controls'])
    assert fault['passed'] and fault['control_scenario_passed'] and not fault['fault_scenario_passed']
    assert fault['restoration']['late_scenario_and_correlation_passed']
    assert len(mapping['graphs']) == 2 and all(g['storage_roundtrip'] for g in mapping['graphs'])
    assert len({g['source_commit'] for g in mapping['graphs']}) == 2
    assert all(mapping['checks'].values())
    records = {r['label']: r for r in mapping['records']}
    assert set(records) == {'normal', 'late', 'parallel', 'fault_control', 'fault'}
    assert all(r['same_context_direct_overlay'] and r['anchors']['unmapped'] > 0 for r in records.values())
    assert records['normal']['stage_counts']['state.applied'] == 1
    assert records['late']['stage_counts']['response.discarded'] == 1
    assert not records['late']['stage_counts'].get('state.applied')
    assert records['fault']['stage_counts']['state.applied'] == 1 and not records['fault']['scenario_passed']
    assert records['fault']['source_commit'] == fault['source_commit']
    for name in ('normal', 'fault'):
        build = read('build-'+name)
        assert build['source_commit'] == records[name]['source_commit']
        assert build['file_hash_verification'] == 'not_run_per_user_preference'
    print('OK: P5 R01-R06 evidence; independent state failure, context isolation and unmapped events retained.')


if __name__ == '__main__': main()
