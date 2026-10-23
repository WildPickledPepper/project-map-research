"""Commit-driven refresh with real extractors on an authored protocol fixture."""
from functools import partial
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest

from adapters.snapshot_inputs import commit, normalize_config
from adapters.snapshot_refresh import Refresher, atomic_json, read_snapshot, read_state
from scripts.build_project_snapshot import build
from tests.test_cpp_protocol import SOURCE

CLIENT = '''declare const channel:WebSocket; declare const b:{invoke:(x:string)=>void};
function make(){return (label:string)=>channel.send(JSON.stringify({wireTag:label,space:'north'}));}
b.invoke=make(); export function entry(){b.invoke('alpha/read');}'''
SERVER = '#include "keys.h"\n' + SOURCE.replace('const std::string ACTION="alpha/read";', '')


class AutomaticGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.ts = Path(subprocess.check_output(['node', '-p', 'require.resolve("typescript")'],
                                                  stderr=subprocess.PIPE, text=True).strip())
        except (OSError, subprocess.CalledProcessError): raise unittest.SkipTest('Install pinned TypeScript for real extraction')

    def test_watcher_tracks_cross_file_identity_registration_consumer_and_configuration_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); source = base/'source'; source.mkdir(); store = base/'store'
            git = lambda *args: subprocess.check_output(['git', '-C', str(source), *args], stderr=subprocess.PIPE)
            git('init', '-q'); git('config', 'user.name', 'Watcher test'); git('config', 'user.email', 'test@example.invalid')
            git('config', 'core.autocrlf', 'false')

            def save(files):
                for name, content in files.items():
                    path = source/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content, encoding='utf-8')
                git('add', '-A'); git('commit', '-qm', 'fixture step')
                return commit(source)

            initial = save({'server/keys.h': 'const std::string ACTION="alpha/read";', 'server/main.cpp': SERVER, 'client/api.ts': CLIENT})
            config = {'version': 1, 'scope': {'include': ['*']}, 'storage': 'json', 'deployment': {'services': [
                {'id': 'fixture', 'consumer_paths': ['client'], 'provider_paths': ['server']}]}}
            config_file = base/'config.json'; atomic_json(config_file, config)
            errors = []; stop = threading.Event()
            runner = Refresher(source, store, lambda: json.loads(config_file.read_text(encoding='utf-8')),
                              lambda: {'rules': 'synthetic_version_for_authored_fixture'}, partial(build, typescript=self.ts))

            def watch():
                try:
                    while not stop.is_set(): runner.run(); stop.wait(0.1)
                except BaseException as error: errors.append(error)

            worker = threading.Thread(target=watch, daemon=True); worker.start()

            def await_graph(revision):
                deadline = time.monotonic() + 40; state = None
                while time.monotonic() < deadline:
                    if errors: raise errors[0]
                    state = read_state(store)
                    if (state and state['status'] == 'up_to_date' and state['last_success']['source_commit'] == revision
                            and state['last_success']['config'] == normalize_config(config)):
                        resolved = read_snapshot(store)
                        graph = json.loads((Path(resolved['directory'])/'graph.json').read_text(encoding='utf-8'))
                        return state, graph
                    stop.wait(0.05)
                self.fail('Automatic refresh did not reach target: ' + repr(state))

            matches = lambda graph: {r['name'] for r in graph['protocol']['results'] if r['status'] == 'matched_conditional'}
            try:
                before, graph = await_graph(initial); self.assertIn('entry', matches(graph))
                revision = save({'server/keys.h': 'const std::string ACTION="beta/read";'})
                _, graph = await_graph(revision); self.assertFalse(matches(graph))
                self.assertEqual((source/'client/api.ts').read_text(encoding='utf-8'), CLIENT)

                client = CLIENT.replace('alpha/read', 'beta/read')
                revision = save({'client/api.ts': client, 'client/second.ts': client.replace('entry()', 'anotherEntry()')})
                _, graph = await_graph(revision); self.assertTrue({'entry', 'anotherEntry'} <= matches(graph))

                registration = 'entries.emplace(ACTION,std::make_unique<SpecificWork>());'
                implementation = 'struct SpecificWork:AbstractWork { ~SpecificWork() override=default; bool execute(Record& r) override {return true;} };'
                self.assertIn(implementation, SERVER)
                revision = save({'server/main.cpp': SERVER.replace(registration, '').replace(implementation, '')})
                _, graph = await_graph(revision); self.assertFalse(matches(graph))
                self.assertFalse(graph['protocol']['providers'])
                self.assertFalse(any(e['kind'] == 'RESOLVES_HANDLER' for e in graph['edges']))
                self.assertFalse(any(n['name'] == 'SpecificWork::execute' for n in graph['nodes']))

                git('rm', 'client/second.ts')
                revision = save({'server/main.cpp': SERVER})
                _, graph = await_graph(revision); self.assertIn('entry', matches(graph)); self.assertNotIn('anotherEntry', matches(graph))
                self.assertFalse(any(n['path'] == 'client/second.ts' for n in graph['nodes']))

                old_handlers = {n['id'] for n in graph['nodes'] if n['name'] == 'SpecificWork::execute'}
                git('mv', 'server/main.cpp', 'server/renamed.cpp')
                revision = save({'server/renamed.cpp': SERVER.replace('SpecificWork', 'NewWork'),
                                 'client/api.ts': client.replace('entry()', 'renamedEntry()'),
                                 'server/unrelated.cpp': 'struct Record; namespace Other {struct SpecificWork {bool execute(Record& r){return false;}};} '})
                _, graph = await_graph(revision); self.assertIn('renamedEntry', matches(graph)); self.assertNotIn('entry', matches(graph))
                self.assertTrue(old_handlers); self.assertFalse(old_handlers & {n['id'] for n in graph['nodes']})
                self.assertFalse(any(n['path'] == 'server/main.cpp' for n in graph['nodes']))
                names = {n['id']: n['name'] for n in graph['nodes']}
                self.assertIn('Other::SpecificWork::execute', names.values())
                self.assertEqual({names[h] for p in graph['protocol']['providers'] for h in p['handler_methods']}, {'NewWork::execute'})

                config['deployment']['services'] = [
                    {'id': 'client_service', 'consumer_paths': ['client'], 'provider_paths': ['unrelated']},
                    {'id': 'server_service', 'consumer_paths': ['unrelated'], 'provider_paths': ['server']}]
                atomic_json(config_file, config)
                changed, graph = await_graph(revision); self.assertFalse(matches(graph))
                self.assertEqual(changed['last_success']['source_commit'], revision)
                old = read_snapshot(store, before['last_success']['id'])
                self.assertEqual(old['receipt']['source_commit'], initial)
                self.assertEqual(old['freshness'], 'historical_or_pending')
                self.assertIn('entry', matches(json.loads((Path(old['directory'])/'graph.json').read_text(encoding='utf-8'))))
            finally:
                stop.set(); worker.join(timeout=30)
                self.assertFalse(worker.is_alive(), 'Watcher did not stop after its current build')
                self.assertFalse(errors)


if __name__ == '__main__': unittest.main()
