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

    def test_rust_fact_and_process_boundary_survive_the_mixed_production_builder(self):
        from adapters.rust_project import available
        if not all(available(n) for n in ('cargo','rustc','rust-analyzer')):self.skipTest('Native Rust tools required')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';source.mkdir();output=root/'output';output.mkdir()
            files={'Cargo.toml':'[package]\nname="fixture"\nversion="0.1.0"\nedition="2021"\n',
                'src/lib.rs':'use std::process::Command;pub fn entry(){let _=Command::new("never-executed").arg("--port=1").spawn();}',
                'view.ts':'export function render(){return 1;}', 'service.cpp':'int handle(){return 1;}'}
            for path,body in files.items():
                target=source/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(body,encoding='utf-8')
            request={'source_commit':'authored-rust-mixed','snapshot':'authored-rust-mixed','input_paths':list(files),
                'config':normalize_config({'version':1,'scope':{'include':['*']},'storage':'json','deployment':{'version':1,'services':[]}}),
                'build_version':{'rules':'authored-fixture'}}
            with (output/'build.log').open('w',encoding='utf-8') as log:build(source,request,output,log,typescript=self.ts)
            graph=json.loads((output/'graph.json').read_text(encoding='utf-8'))
            self.assertTrue(any(n['kind']=='rust_boundary' and n['family']=='process_start' for n in graph['nodes']))
            self.assertTrue(any(e['kind']=='USES_COMMAND' for e in graph['edges']))
            self.assertEqual(next(r for r in graph['coverage'] if r['path']=='src/lib.rs')['status'],'parsed')
            self.assertIn('rust-analyzer',graph['extractors']['rust']['components'])

    def test_python_sources_and_owned_interface_join_enter_the_production_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';source.mkdir();output=root/'output';output.mkdir()
            files={'start.py':'''from aiohttp import web
from handlers import serve
app=web.Application()
app.router.add_get('/source',serve)
runner=web.AppRunner(app)
site=web.TCPSite(runner,'127.0.0.1',9100)
''','handlers.py':'async def serve(request): return request\n',
                'view.ts':'export function render(){return 1;}',
                'service.cpp':'int handle(){return 1;}' }
            for path,body in files.items():(source/path).write_text(body,encoding='utf-8')
            request={'source_commit':'synthetic-python-mixed','snapshot':'synthetic-python-mixed',
                'input_paths':list(files),'config':normalize_config({'version':1,'scope':{'include':['*']},'storage':'json','deployment':{'version':1,'services':[]}}),
                'build_version':{'rules':'authored-fixture'}}
            with (output/'build.log').open('w',encoding='utf-8') as log:build(source,request,output,log,typescript=self.ts)
            graph=json.loads((output/'graph.json').read_text(encoding='utf-8'))
            self.assertTrue(any(n['name']=='serve' and n.get('language')=='python' for n in graph['nodes']))
            self.assertTrue(any(e['kind']=='EXPOSES_ROUTE' for e in graph['edges']))
            self.assertTrue(any(e['kind']=='CAN_DISPATCH_TO' for e in graph['edges']))
            self.assertEqual({r['path']:r['status'] for r in graph['coverage'] if r['path'].endswith('.py')},
                             {'start.py':'parsed','handlers.py':'parsed'})
            self.assertEqual(graph['extractors']['python']['components']['jedi'],'0.19.2')

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
