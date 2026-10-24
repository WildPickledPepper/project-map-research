"""Exercise all extraction phases together on an authored cross-language fixture."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from adapters.snapshot_inputs import normalize_config
from scripts.build_project_snapshot import build
from tests.test_cpp_protocol import SOURCE


class FullSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.ts = Path(subprocess.check_output(['node', '-p', 'require.resolve("typescript")'],
                                                  stderr=subprocess.PIPE, text=True).strip())
        except (OSError, subprocess.CalledProcessError):
            raise unittest.SkipTest('Install the pinned TypeScript dependency before the full builder test')

    def test_complete_rebuild_recomputes_cross_file_protocol_matching(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root/'source'; source.mkdir()
            (source/'server').mkdir(); (source/'client').mkdir()
            (source/'server/main.cpp').write_text(SOURCE, encoding='utf-8')
            client = '''declare const channel:WebSocket; declare const b:{invoke:(x:string)=>void};
                function make(){return (label:string)=>channel.send(JSON.stringify({wireTag:label,space:'north'}));}
                b.invoke=make(); export function entry(){b.invoke('alpha/read');}'''
            (source/'client/main.ts').write_text(client, encoding='utf-8')
            config = normalize_config({'version': 1, 'scope': {'include': ['*']}, 'storage': 'json',
                'deployment': {'services': [{'id': 'fixture', 'consumer_paths': ['client'], 'provider_paths': ['server']}]}})
            graphs = []
            for index in range(2):
                output = root/str(index); output.mkdir()
                request = {'source_commit': 'authored-fixture-'+str(index), 'snapshot': 'fixture-'+str(index),
                           'input_paths': ['client/main.ts', 'server/main.cpp'], 'config': config,
                           'build_version': {'rules': 'synthetic_test_input'}}
                with (output/'build.log').open('w', encoding='utf-8') as log:
                    result = build(source, request, output, log, typescript=self.ts)
                graph = json.loads((output/'graph.json').read_text(encoding='utf-8'))
                self.assertEqual(graph['version'], {k: request[k] for k in ['source_commit', 'snapshot', 'config', 'build_version']})
                self.assertEqual(result['files'], 2)
                self.assertEqual(graph['provenance']['update_mode'], 'full_rebuild')
                self.assertEqual(graph['provenance']['trigger'], 'caller')
                self.assertFalse(result['storage_roundtrip'])
                phase_input=json.loads((output/'phase-input.json').read_text(encoding='utf-8'))
                self.assertEqual(phase_input['project_map_phase'],'return')
                self.assertNotIn('nodes',phase_input)
                self.assertEqual(phase_input['apiEntries'],graph['frontend']['api_symbols'])
                self.assertEqual(set(phase_input['boundarySymbols']),
                                 {r['entry'] for r in graph['response_callbacks']['registrations']})
                graphs.append(graph)
                # Only the provider changes. The unchanged consumer must lose its old match.
                (source/'server/main.cpp').write_text(SOURCE.replace('alpha/read', 'beta/read'), encoding='utf-8')
            matches = lambda graph: [e for e in graph['edges'] if e['kind'] == 'MATCHES_REGISTERED_PROTOCOL']
            self.assertTrue(matches(graphs[0]))
            self.assertFalse(matches(graphs[1]))
            self.assertEqual((source/'client/main.ts').read_text(encoding='utf-8'), client)
            self.assertTrue(matches(json.loads((root/'0/graph.json').read_text(encoding='utf-8'))))


if __name__ == '__main__': unittest.main()
