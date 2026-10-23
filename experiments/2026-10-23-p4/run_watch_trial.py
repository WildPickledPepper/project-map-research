"""Exercise the production watcher on a private Insight checkout.

Expected application names belong to this scorer. Extractors receive source,
scope, deployment and tool versions, without expected answers.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT/'experiments/2026-10-23-p3'))
from adapters.snapshot_inputs import commit, git, normalize_config
from adapters.snapshot_refresh import atomic_json, read_snapshot, read_state
from run_combined import assess

REVISION = 'd4e8d1cf9f90208bcbe5371c127088f6fd66c688'
HEADER = 'server/src/modules/defs/ProtocolDefs.h'


def run(source, output, config_path, typescript, python_log):
    source = source.resolve(); output = output.resolve()
    if output.is_relative_to(ROOT) or output.is_relative_to(source): raise ValueError('Keep experiment outputs outside repositories')
    output.mkdir(parents=True, exist_ok=False)
    checkout = output/'source'; store = output/'store'; config_file = output/'config.json'
    subprocess.run(['git', 'clone', '--quiet', '--shared', '--no-checkout', str(source), str(checkout)], check=True)
    git(checkout, 'checkout', '--quiet', '--detach', REVISION)
    git(checkout, 'config', 'user.name', 'Project Map Experiment')
    git(checkout, 'config', 'user.email', 'research@example.invalid')
    config = normalize_config(json.loads(config_path.read_text(encoding='utf-8')))
    assert config['storage'] == 'kuzu'
    atomic_json(config_file, config)
    command = [sys.executable, str(ROOT/'scripts/refresh_project_map.py'), '--source', str(checkout), '--store', str(store),
               '--config', str(config_file), '--typescript', str(typescript.resolve()), '--watch', '--interval', '0.25']
    log = (output/'watcher.log').open('w', encoding='utf-8')
    proc = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)

    def wait_for(predicate, description, seconds=900):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f'Watcher exited with {proc.returncode}; see {output / "watcher.log"}')
            state = read_state(store)
            if state and predicate(state): return state
            time.sleep(0.1)
        raise TimeoutError('Watcher did not reach ' + description)

    try:
        first = wait_for(lambda s: s['status'] == 'building', 'initial build')
        assert first['current_attempt']['source_commit'] == REVISION
        print('Initial Insight build is running; commit two changes in the private checkout', flush=True)
        (checkout/'p4-watch-trial.txt').write_text('Authored automatic refresh experiment.\n', encoding='utf-8')
        git(checkout, 'add', '--', 'p4-watch-trial.txt'); git(checkout, 'commit', '-qm', 'Fixture: first commit during extraction')
        middle = commit(checkout)
        path = checkout/HEADER; data = path.read_bytes(); old = b'"unit/flows"'; new = b'"unit/flows/p4-probe"'
        assert data.count(old) == 1
        path.write_bytes(data.replace(old, new))
        git(checkout, 'add', '--', HEADER); git(checkout, 'commit', '-qm', 'Fixture: change provider identity while client stays unchanged')
        target = commit(checkout)
        during = read_state(store)
        assert during['status'] == 'building' and during['current_attempt']['source_commit'] == REVISION
        assert not during['last_success']
        (output/'source-changes.patch').write_bytes(git(checkout, 'diff', '--binary', '--unified=0', REVISION, target))
        print('Both commits arrived during the original build; waiting for automatic catch-up', flush=True)
        final = wait_for(lambda s: s['status'] == 'up_to_date' and s['last_success']['source_commit'] == target, 'latest committed source')
        assert len(final['published']) == 2
        old_snapshot = read_snapshot(store, final['published'][0]); new_snapshot = read_snapshot(store)
        assert old_snapshot['receipt']['source_commit'] == REVISION
        assert old_snapshot['freshness'] == 'historical_or_pending'
        assert new_snapshot['receipt']['source_commit'] == target and new_snapshot['freshness'] == 'current_at_observation'
        old_graph = json.loads((Path(old_snapshot['directory'])/'graph.json').read_text(encoding='utf-8'))
        old_checks = assess(old_graph)
        new_graph = json.loads((Path(new_snapshot['directory'])/'graph.json').read_text(encoding='utf-8'))
        requests = [r for r in new_graph['protocol']['results'] if r['name'] == 'getUnitFlows']
        assert requests and all(not r['matches'] for r in requests)
        assert any(p['command'] == 'unit/flows/p4-probe' for p in new_graph['protocol']['providers'])
        assert not any(p['command'] == 'unit/flows' for p in new_graph['protocol']['providers'])
        assert git(checkout, 'diff', '--name-only', middle, target).decode().splitlines() == [HEADER]
        print('Latest graph published; checking malformed-config recovery with the last successful graph retained', flush=True)
        bad = output/'bad-config.tmp'; bad.write_text('{', encoding='utf-8'); bad.replace(config_file)
        failed = wait_for(lambda s: s['status'] == 'failed', 'configuration failure', seconds=30)
        assert failed['last_success'] == final['last_success'] and failed['published'] == final['published']
        assert read_snapshot(store)['freshness'] == 'historical_or_pending'
        atomic_json(config_file, config)
        recovered = wait_for(lambda s: s['status'] == 'up_to_date', 'configuration recovery', seconds=30)
        assert recovered['last_success'] == final['last_success'] and recovered['published'] == final['published']
        tests = python_log.read_text(encoding='utf-8'); assert re.search(r'\nOK\s*$', tests)
        report = {'evidence_kind': 'executed_production_watch_cli_on_private_Insight_checkout',
            'source_base': REVISION, 'source_intermediate': middle, 'source_target': target,
            'rules_version': new_snapshot['receipt']['build_version'],
            'published': [{'id': item['receipt']['id'], 'source_commit': item['receipt']['source_commit'],
                           'snapshot': item['receipt']['snapshot'], 'result': item['receipt']['result']} for item in [old_snapshot, new_snapshot]],
            'checks': {'two_commits_during_initial_build': True, 'intermediate_coalesced_to_latest': True,
                       'baseline_D01_D05': old_checks['gates'], 'provider_constant_change_recomputed_unchanged_client': True,
                       'old_snapshot_retains_original_version': True, 'malformed_config_preserves_last_success': True,
                       'config_recovery_without_duplicate_snapshot': True, 'both_kuzu_roundtrips': all(
                           item['receipt']['result']['storage_roundtrip'] for item in [old_snapshot, new_snapshot])},
            'changed_identity': {'before': 'unit/flows', 'after': 'unit/flows/p4-probe', 'path': HEADER},
            'final_client_result': [{'name': r['name'], 'status': r['status'], 'matches': len(r['matches'])} for r in requests],
            'tests': {'python': int(re.search(r'Ran (\d+) tests', tests)[1]), 'passed': True},
            'scope': '154 configured source paths; private source mutation; static graph, not product execution',
            'P4_remaining': ['versioned non-graph evidence and summary access; historical asset selector migration checks'],
            'incremental': 'disabled', 'file_hash_verification': 'not_run_per_user_preference'}
        atomic_json(output/'watch-trial.json', report)
        print(json.dumps({'checks': report['checks'], 'published': report['published']}), flush=True)
        return report
    finally:
        if proc.poll() is None: proc.terminate(); proc.wait(timeout=10)
        log.close()


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ['source', 'output', 'config', 'typescript', 'python-log']: ap.add_argument('--'+name, type=Path, required=True)
    a = ap.parse_args(); run(a.source, a.output, a.config, a.typescript, a.python_log)
