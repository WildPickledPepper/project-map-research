from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import adapters.snapshot_refresh as refresh
from adapters.snapshot_inputs import commit
from tests.refresh_worker import VERSION, synthetic_builder


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name); self.source = self.base/'source'; self.source.mkdir()
        self.store = self.base/'store'
        self.git('init', '-q'); self.git('config', 'user.name', 'Refresh test')
        self.git('config', 'user.email', 'test@example.invalid'); self.git('config', 'core.autocrlf', 'false')
        self.config = {'version': 1, 'scope': {'include': ['*.ts']}, 'storage': 'json', 'deployment': {'services': []}}
        self.version = deepcopy(VERSION); self.events = []; self.calls = []
        self.write_commit({'a.ts': 'original'})

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.source), *args], stderr=subprocess.PIPE)

    def write_commit(self, files):
        for name, text in files.items():
            path = self.source/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text, encoding='utf-8')
        self.git('add', '-A'); self.git('commit', '-qm', 'change')
        return commit(self.source)

    def builder(self, source, request, output, log):
        self.calls.append(request['source_commit'])
        return synthetic_builder(source, request, output, log)

    def runner(self, builder=None):
        return refresh.Refresher(self.source, self.store, lambda: self.config, lambda: self.version,
                                 builder or self.builder, on_event=self.events.append)

    def graph(self, state=None):
        resolved = refresh.read_snapshot(self.store, state['last_success']['id'] if state else None)
        return json.loads((Path(resolved['directory'])/'graph.json').read_text(encoding='utf-8'))

    def test_first_publication_noop_and_committed_only_inputs(self):
        first = self.runner().run(); self.assertEqual(first['status'], 'up_to_date')
        (self.source/'a.ts').write_text('dirty and excluded', encoding='utf-8')
        second = self.runner().run()
        self.assertEqual(first['last_success'], second['last_success']); self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.graph()['nodes'][0]['content'], 'original')
        self.assertEqual(refresh.read_snapshot(self.store)['freshness'], 'current_at_observation')

    def test_automatic_scope_replans_new_modules_without_configuration_edits(self):
        self.config['scope'] = {'discovery': {}}
        first = self.runner().run()
        self.write_commit({'new/package.json':'{"name":"new"}', 'new/entry.ts':'export function added(){}',
                           'vendor/skip.ts':'third party', 'new/help.py':'def run(): return 1', 'new/later.rs':'fn main(){}'})
        second = self.runner().run()
        self.assertEqual(self.graph()['input_paths'], ['a.ts','new/entry.ts','new/help.py','new/package.json'])
        self.assertNotIn('new/later.rs',self.graph()['input_paths'])
        self.assertEqual(first['last_success']['config'], second['last_success']['config'])
        self.git('mv','new/entry.ts','new/renamed.ts');self.git('commit','-qm','rename')
        self.runner().run()
        self.assertIn('new/renamed.ts',self.graph()['input_paths'])
        self.assertNotIn('new/entry.ts',self.graph()['input_paths'])

    def test_scope_source_and_builder_configuration_changes_trigger_rebuild(self):
        self.runner().run(); old = commit(self.source)
        self.write_commit({'b.ts': 'second'}); self.runner().run()
        self.config['scope']['exclude'] = ['a.ts']; excluded = self.runner().run()
        self.assertEqual(self.graph()['input_paths'], ['b.ts'])
        self.config['deployment']['services'] = [{'id': 'new', 'consumer_paths': ['client'], 'provider_paths': ['server']}]
        configured = self.runner().run(); self.assertEqual(configured['last_success']['source_commit'], excluded['last_success']['source_commit'])
        self.version = {'rules': 'synthetic_next_version'}; versioned = self.runner().run()
        self.assertEqual(versioned['last_success']['build_version'], self.version)
        self.assertEqual(len(versioned['published']), 5); self.assertNotEqual(old, versioned['last_success']['source_commit'])

    def test_failed_builder_preserves_pointer_and_log_then_retries(self):
        before = self.runner().run(); self.write_commit({'a.ts': 'new'})
        def broken(source, request, output, log):
            synthetic_builder(source, request, output, log)
            raise RuntimeError('injected extraction failure')
        failed = self.runner(broken).run()
        self.assertEqual(failed['status'], 'failed'); self.assertEqual(failed['last_success'], before['last_success'])
        self.assertEqual(failed['published'], before['published'])
        self.assertIn('injected extraction failure', next((self.store/'staging').glob('*/build.log')).read_text(encoding='utf-8'))
        self.assertEqual(refresh.read_snapshot(self.store)['freshness'], 'historical_or_pending')
        recovered = self.runner().run(); self.assertEqual(recovered['status'], 'up_to_date')
        self.assertEqual(self.graph()['nodes'][0]['content'], 'new')
        self.assertEqual(self.graph(before)['nodes'][0]['content'], 'original')

    def test_invalid_graph_version_count_or_edges_never_publish(self):
        before = self.runner().run(); self.write_commit({'a.ts': 'new'})
        for corrupt in ['version', 'count', 'edge']:
            def broken(source, request, output, log):
                result = synthetic_builder(source, request, output, log)
                path = output/'graph.json'; graph = json.loads(path.read_text(encoding='utf-8'))
                if corrupt == 'version': graph['version']['source_commit'] = 'wrong'
                elif corrupt == 'count': result['nodes'] += 1
                else: graph['edges'] = [{'source': 'missing', 'target': 'missing', 'kind': 'CALLS', 'status': 'certain', 'evidence': []}]
                path.write_text(json.dumps(graph), encoding='utf-8')
                return result
            with self.subTest(corrupt=corrupt):
                state = self.runner(broken).run()
                self.assertEqual(state['status'], 'failed'); self.assertEqual(state['last_success'], before['last_success'])

    def test_builder_version_change_mid_build_discards_attempt(self):
        before = self.runner().run(); self.write_commit({'a.ts': 'new'})
        def changing(source, request, output, log):
            result = self.builder(source, request, output, log)
            self.version = {'rules': 'changed_mid_build'}
            return result
        failed = self.runner(changing).run()
        self.assertEqual(failed['status'], 'failed'); self.assertEqual(failed['last_success'], before['last_success'])
        self.assertIn('Builder version changed', failed['last_error']['message'])

    def test_two_commits_during_build_coalesce_to_latest_and_keep_first_input_fixed(self):
        original = commit(self.source); commits = []
        def advancing(source, request, output, log):
            result = self.builder(source, request, output, log)
            if request['source_commit'] == original:
                commits.append(self.write_commit({'a.ts': 'middle'}))
                commits.append(self.write_commit({'a.ts': 'latest'}))
                self.assertEqual((source/'a.ts').read_text(encoding='utf-8'), 'original')
            return result
        state = self.runner(advancing).run()
        self.assertEqual(state['status'], 'up_to_date'); self.assertEqual(self.calls, [original, commits[-1]])
        self.assertEqual(state['target']['source_commit'], commits[-1]); self.assertEqual(len(state['published']), 2)
        self.assertEqual([e['status'] for e in self.events if e['event'] == 'published'], ['pending', 'up_to_date'])

    def test_build_budget_persists_pending_target_for_next_run(self):
        old = commit(self.source)
        def advancing(source, request, output, log):
            result = self.builder(source, request, output, log)
            self.write_commit({'a.ts': 'new target'})
            return result
        pending = self.runner(advancing).run(max_builds=1)
        self.assertEqual(pending['status'], 'pending'); self.assertEqual(pending['last_success']['source_commit'], old)
        self.assertEqual(pending['target']['source_commit'], commit(self.source))
        final = self.runner().run(); self.assertEqual(final['status'], 'up_to_date')
        self.assertEqual(self.graph()['nodes'][0]['content'], 'new target')

    def test_lock_conflict_leaves_state_unchanged(self):
        self.runner().run(); original = (self.store/'state.json').read_bytes()
        with refresh.writer_lock(self.store):
            with self.assertRaises(refresh.RefreshBusy): self.runner().run()
        self.assertEqual((self.store/'state.json').read_bytes(), original)
        self.assertEqual(self.runner().run()['status'], 'up_to_date')

    def test_failure_after_directory_rename_does_not_publish_orphan(self):
        before = self.runner().run(); self.write_commit({'a.ts': 'new'})
        real_write = refresh.atomic_json
        def fail_pointer(path, value):
            if path.name == 'state.json' and value.get('last_success') and value['last_success'] != before['last_success']:
                raise OSError('injected state publication failure')
            return real_write(path, value)
        with patch.object(refresh, 'atomic_json', side_effect=fail_pointer): failed = self.runner().run()
        self.assertEqual(failed['last_success'], before['last_success']); self.assertEqual(failed['status'], 'failed')
        orphan = next(p.name for p in (self.store/'snapshots').iterdir() if p.name not in failed['published'])
        with self.assertRaises(LookupError): refresh.read_snapshot(self.store, orphan)
        self.assertEqual(self.runner().run()['status'], 'up_to_date')
        self.assertNotIn(orphan, refresh.read_state(self.store)['published'])

    def test_atomic_state_replace_failure_preserves_readable_old_document(self):
        path = self.base/'state.json'; refresh.atomic_json(path, {'old': True})
        with patch.object(refresh.os, 'replace', side_effect=OSError('cannot replace')):
            with self.assertRaises(OSError): refresh.atomic_json(path, {'new': True})
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')), {'old': True})
        self.assertFalse(list(self.base.glob('.*.tmp')))

    def test_bad_configuration_does_not_hide_old_snapshot_or_skip_fixed_target(self):
        before = self.runner().run(); self.write_commit({'a.ts': 'new'})
        self.config['unknown'] = True; failed = self.runner().run()
        self.assertEqual(failed['status'], 'failed'); self.assertEqual(failed['last_success'], before['last_success'])
        del self.config['unknown']; self.assertEqual(self.runner().run()['status'], 'up_to_date')
        self.assertEqual(self.graph()['nodes'][0]['content'], 'new')

    def test_process_kill_releases_lock_and_recovers_without_publishing_partial_graph(self):
        before = self.runner().run(); self.write_commit({'a.ts': 'interrupted target'})
        config = self.base/'config.json'; config.write_text(json.dumps(self.config), encoding='utf-8')
        ready = self.base/'ready'
        command = [sys.executable, str(Path(__file__).with_name('refresh_worker.py')),
                   '--source', str(self.source), '--store', str(self.store), '--config', str(config), '--ready', str(ready)]
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 10
            while not ready.exists() and proc.poll() is None and time.monotonic() < deadline: time.sleep(0.02)
            self.assertIsNone(proc.poll()); self.assertTrue(ready.exists())
            during = refresh.read_state(self.store); self.assertEqual(during['status'], 'building')
            self.assertEqual(during['last_success'], before['last_success'])
            with self.assertRaises(refresh.RefreshBusy): self.runner().run()
            self.write_commit({'a.ts': 'target committed before recovery'})
            proc.kill(); proc.wait(timeout=10)
            after = self.runner().run(); self.assertEqual(after['status'], 'up_to_date')
            self.assertEqual(self.graph()['nodes'][0]['content'], 'target committed before recovery')
            failure = json.loads((self.store/'attempts'/(during['current_attempt']['id']+'.json')).read_text(encoding='utf-8'))
            self.assertEqual(failure['outcome'], 'interrupted')
            self.assertNotIn(during['current_attempt']['id'], after['published'])
        finally:
            if proc.poll() is None: proc.kill(); proc.wait(timeout=10)
            proc.communicate(timeout=10)

    def test_store_cannot_be_reused_by_another_source(self):
        self.runner().run(); other = self.base/'other'; other.mkdir()
        wrong = refresh.Refresher(other, self.store, lambda: self.config, lambda: self.version, self.builder)
        with self.assertRaises(ValueError): wrong.run()

    def test_missing_published_graph_is_reported(self):
        state = self.runner().run()
        (self.store/'snapshots'/state['last_success']['id']/'graph.json').unlink()
        self.assertEqual(self.runner().run()['status'], 'failed')
        with self.assertRaises(ValueError): refresh.read_snapshot(self.store)


if __name__ == '__main__': unittest.main()
