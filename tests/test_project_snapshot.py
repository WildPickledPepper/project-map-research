"""Exercise all extraction phases together on an authored cross-language fixture."""
import json
from functools import partial
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

    def test_default_rust_current_exe_chain_reaches_cmake_backend_entry(self):
        import os
        from adapters.rust_project import available
        from tests.test_cmake_file_api import CMAKE,NINJA
        from projectmap.workspace import Workspace
        if not (CMAKE and NINJA and all(available(n) for n in ('cargo','rustc','rust-analyzer'))):self.skipTest('Native Rust/CMake tools required')
        with tempfile.TemporaryDirectory(prefix='cross language process deployment ') as directory:
            root=Path(directory);source=root/'repository';source.mkdir();suffix='.exe' if os.name=='nt' else ''
            files={'Cargo.toml':'[package]\nname="neutral_frontend"\nversion="0.1.0"\nedition="2021"\n[[bin]]\nname="viewer-renamed"\npath="src/launcher.rs"\n',
                'src/launcher.rs':f'''fn main() {{
 let image=std::env::current_exe().unwrap();
 let child=image.parent().unwrap().join("assets").join("service").join("worker{suffix}");
 let _child=std::process::Command::new(child).spawn();
}}
''', 'compile/CMakeLists.txt':'cmake_minimum_required(VERSION 3.16)\nproject(Worker LANGUAGES CXX)\nadd_executable(worker_engine ../server/main.cpp)\nset_target_properties(worker_engine PROPERTIES OUTPUT_NAME "worker" RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/../native")\n',
                'server/main.cpp':'int main(){return 0;}\n', 'view.ts':'export function show(){return 1;}\n',
                'assemble.py':f'''import os,subprocess,shutil
ROOT=os.path.dirname(os.path.realpath(__file__))
os.putenv('CARGO_TARGET_DIR',os.path.join(ROOT,'rust-objects'))
subprocess.run(['cargo','build','--release'],cwd=ROOT)
shutil.copyfile(os.path.join(ROOT,'rust-objects','release','viewer-renamed{suffix}'),os.path.join(ROOT,'ship','desktop-viewer{suffix}'))
shutil.copyfile(os.path.join(ROOT,'native','worker{suffix}'),os.path.join(ROOT,'ship','assets','service','worker{suffix}'))
'''}
            for path,body in files.items():
                dest=source/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(body,encoding='utf-8')
            def git(*args):return subprocess.check_output(['git','-C',str(source),*args],stderr=subprocess.PIPE).decode().strip()
            git('init','-q');git('config','user.name','fixture');git('config','user.email','fixture@example.invalid')
            git('add','.');git('commit','-qm','authored cross language deployment')
            analysis=normalize_config({'version':1,'scope':{'include':['*']},'deployment':{},'storage':'json'})
            workspace=Workspace.create(root/'workspace',source,typescript=self.ts,analysis=analysis)
            result=workspace.update(builder=partial(build,typescript=self.ts),version={'rules':'authored-deployment-fixture'})
            self.assertEqual(result['status'],'ready',result)
            graph=json.loads(Path(workspace.config['active']['graph']).read_text(encoding='utf-8'))
            cpp=next(n for n in graph['nodes'] if n['path']=='server/main.cpp' and n['kind']=='callable' and n['name']=='main')
            rust=next(n for n in graph['nodes'] if n.get('language')=='rust' and n['kind']=='callable' and n['name']=='main')
            matched=[e for e in graph['edges'] if e['kind']=='RESOLVES_EXECUTABLE_TARGET_CANDIDATE']
            self.assertEqual(len(matched),1)
            provider=next(n for n in graph['nodes'] if n['id']==matched[0]['target']);self.assertEqual(provider['name'],'worker_engine')
            kinds=['OBSERVES_CALL','STATIC_CALL_TARGET','STATIC_CALL_CANDIDATE','DECLARES_BOUNDARY','COMMAND_PROGRAM',
                'PATH_VALUE_CANDIDATE','PATH_DEPLOYMENT_BINDING','RESOLVES_EXECUTABLE_TARGET_CANDIDATE','EXECUTABLE_ENTRY_CANDIDATE']
            for direction,start,end in [('out',rust['id'],cpp['id']),('in',cpp['id'],rust['id'])]:
                route=workspace.query('path',start=start,target=end,direction=direction,kinds=kinds,depth=18,nodes=500,edges=1000)
                self.assertTrue(route['found']);self.assertIsNone(route['stop_reason'])
            self.assertEqual(graph['executable_deployment']['counts']['artifact_matches'],1)
            self.assertTrue(all(e['runtime_execution']=='not_observed' for e in matched))
            self.assertIn('target_os_loader_accepts_provider_image',{c['kind'] for c in matched[0]['conditions']})
            self.assertEqual(workspace.query('source',start=cpp['id'])['path'],'server/main.cpp')
            self.assertEqual(git('status','--porcelain'),'')

    def test_native_cmake_target_and_entry_survive_workspace_build_and_bidirectional_query(self):
        from tests.test_cmake_file_api import CMAKE, NINJA
        if not (CMAKE and NINJA): self.skipTest('Native CMake and Ninja required')
        from projectmap.workspace import Workspace
        with tempfile.TemporaryDirectory(prefix='native build workspace ') as directory:
            root=Path(directory);source=root/'repository';source.mkdir()
            files={'compile/CMakeLists.txt':'cmake_minimum_required(VERSION 3.16)\nproject(Neutral LANGUAGES CXX)\nadd_subdirectory(third_party)\nadd_executable(service_app ../src/entry.cpp)\ntarget_link_libraries(service_app PRIVATE helper)\nset_target_properties(service_app PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/../native-output")\n',
                'compile/third_party/CMakeLists.txt':'add_library(helper STATIC ../../src/helper.cpp)\n',
                'src/helper.cpp':'int helper(){return 2;}\n',
                'src/entry.cpp':'int main(){return 0;}\n', 'client/view.ts':'export function show(){return 1;}\n',
                'assemble.py':'''import os,shutil
ROOT=os.path.dirname(os.path.realpath(__file__))
for item in os.listdir(os.path.join(ROOT,'native-output')):
 shutil.copyfile(os.path.join(ROOT,'native-output',item),os.path.join(ROOT,'stage',item))
shutil.copytree(os.path.join(ROOT,'stage'),os.path.join(ROOT,'ship'))
'''}
            for path,body in files.items():
                target=source/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(body,encoding='utf-8')
            def git(*args):return subprocess.check_output(['git','-C',str(source),*args],stderr=subprocess.PIPE).decode().strip()
            git('init','-q');git('config','user.name','fixture');git('config','user.email','fixture@example.invalid')
            git('add','.');git('commit','-qm','authored mixed native build');revision=git('rev-parse','HEAD')
            from projectmap.workspace import default_analysis
            analysis=default_analysis();analysis['build']={'version':1,'cmake':{'configurations':['Release']}}
            workspace=Workspace.create(root/'workspace',source,revision=revision,typescript=self.ts,analysis=analysis)
            built=workspace.update(builder=partial(build,typescript=self.ts),version={'rules':'authored-native-fixture'})
            self.assertEqual(built['status'],'ready')
            targets=workspace.query('search',text='service_app',kind='build_target')['items']
            entries=workspace.query('search',text='main',kind='callable')['items']
            self.assertEqual(len(targets),1);self.assertEqual(len(entries),1)
            for direction,start,target in [('out',targets[0],entries[0]),('in',entries[0],targets[0])]:
                path=workspace.query('path',start=start['id'],target=target['id'],direction=direction,
                    kinds=['EXECUTABLE_ENTRY_CANDIDATE'],depth=3,nodes=30,edges=30)
                self.assertTrue(path['found']);self.assertIsNone(path['stop_reason'])
                self.assertEqual(path['items'][0]['status'],'candidate')
            src=workspace.query('source',start=entries[0]['id'])
            self.assertEqual(src['source_commit'],revision);self.assertEqual(src['path'],'src/entry.cpp')
            graph=json.loads(Path(workspace.config['active']['graph']).read_text(encoding='utf-8'))
            self.assertEqual(graph['native_build']['contexts'][0]['status'],'configured')
            self.assertEqual(graph['native_build']['contexts'][0]['target_system']['status'],'available')
            self.assertIn('cmake',graph['extractors'])
            shipped=next(n for n in graph['nodes'] if n['kind']=='copied_artifact' and n['value']['segments'][0]=='ship')
            for direction,start,target in [('out',targets[0]['id'],shipped['id']),('in',shipped['id'],targets[0]['id'])]:
                route=workspace.query('path',start=start,target=target,direction=direction,
                    kinds=['PRODUCES_ARTIFACT','COPIES_ARTIFACT_TO'],depth=4,nodes=40,edges=40)
                self.assertTrue(route['found']);self.assertIsNone(route['stop_reason'])
                self.assertEqual(route['snapshot'],graph['snapshot'])
            proof=workspace.query('source',start=shipped['id'])
            self.assertEqual(proof['path'],'assemble.py');self.assertEqual(proof['source_commit'],revision)
            self.assertIn('artifact_copy_flow',graph['extractors'])
            self.assertEqual(git('status','--porcelain'),'')

    def test_rust_fact_and_process_boundary_survive_the_mixed_production_builder(self):
        from adapters.rust_project import available
        if not all(available(n) for n in ('cargo','rustc','rust-analyzer')):self.skipTest('Native Rust tools required')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';source.mkdir();output=root/'output';output.mkdir()
            files={'Cargo.toml':'[package]\nname="fixture"\nversion="0.1.0"\nedition="2021"\n',
                'src/lib.rs':'use std::{path::PathBuf,process::Command};pub fn entry(){let mut p=PathBuf::from("assets");for part in ["server","worker"]{p.push(part);}let _=Command::new(p).arg("--port=1").spawn();}',
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
            self.assertTrue(any(n['kind']=='path_value' and n['value']['relative_path']=='assets/server/worker' for n in graph['nodes']))
            self.assertTrue(any(e['kind']=='PATH_COMPONENT_SOURCE' for e in graph['edges']))

    def test_native_cargo_artifact_to_renamed_distribution_survives_workspace_queries_and_failed_refresh(self):
        import copy
        import os
        from adapters.cargo_native import capture
        from adapters.rust_project import available
        from adapters.snapshot_inputs import export_inputs,select_inputs
        from projectmap.workspace import Workspace
        from tests import test_cargo_file_api as fixtures
        if not all(available(n) for n in ('cargo','rustc','rust-analyzer')):self.skipTest('Native Rust tools required')
        with tempfile.TemporaryDirectory(prefix='cargo production workspace ') as directory:
            root=Path(directory);source=root/'repository';source.mkdir()
            files,env,manifest,name=fixtures.fixture_files();suffix='.exe' if os.name=='nt' else ''
            files['assemble.py']=f'''import os,shutil,subprocess
ROOT=os.path.dirname(os.path.realpath(__file__))
os.putenv('CARGO_TARGET_DIR',os.path.join(ROOT,'objects'))
subprocess.run(['cargo','build','--release'],cwd=ROOT)
shutil.copyfile(os.path.join(ROOT,'objects','release','{name}{suffix}'),os.path.join(ROOT,'ship','renamed-launcher{suffix}'))
'''
            files['view.ts']='export function show(){return 1;}\n'
            for path,body in files.items():
                dest=source/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(body,encoding='utf-8')
            def git(*args):return subprocess.check_output(['git','-C',str(source),*args],stderr=subprocess.PIPE).decode().strip()
            git('init','-q');git('config','user.name','fixture');git('config','user.email','fixture@example.invalid')
            git('config','core.autocrlf','false');git('add','.');git('commit','-qm','authored Cargo production input')
            revision=git('rev-parse','HEAD')
            analysis=normalize_config({'version':1,'scope':{'include':['*']},'deployment':{},'storage':'json'})
            selection=select_inputs(source,revision,analysis);export_inputs(source,selection,root/'export')
            native,receipt=capture(root/'export',list(files),output=root/'capture',source_commit=revision,expected_commit=revision,
                context_key='authored-release',manifest=manifest,target_directory='objects',environment=env)
            self.assertEqual(native['native_context']['status'],'built')
            analysis['build']={'version':1,'cargo':{'captures':[{'directory':str(root/'capture'),
                'source_commit':revision,'context_key':'authored-release'}]}}
            workspace=Workspace.create(root/'workspace',source,typescript=self.ts,analysis=analysis)
            result=workspace.update(builder=partial(build,typescript=self.ts),version={'rules':'authored-cargo-fixture'})
            self.assertEqual(result['status'],'ready',result)
            graph=json.loads(Path(workspace.config['active']['graph']).read_text(encoding='utf-8'))
            target=next(n for n in graph['nodes'] if n['kind']=='build_target' and n['name']==name)
            artifact=next(n for n in graph['nodes'] if n['kind']=='build_artifact' and n['native_executable'])
            shipped=[n for n in graph['nodes'] if n['kind']=='copied_artifact' and n['value']['relative_path']=='ship/renamed-launcher'+suffix]
            self.assertEqual(len(shipped),1)
            for direction,start,end in [('out',target['id'],shipped[0]['id']),('in',shipped[0]['id'],target['id'])]:
                route=workspace.query('path',start=start,target=end,direction=direction,
                    kinds=['PRODUCES_ARTIFACT','COPIES_ARTIFACT_TO'],depth=3,nodes=40,edges=40)
                self.assertTrue(route['found']);self.assertIsNone(route['stop_reason'])
                self.assertEqual([e['kind'] for e in route['items']],
                    ['PRODUCES_ARTIFACT','COPIES_ARTIFACT_TO'] if direction=='out' else ['COPIES_ARTIFACT_TO','PRODUCES_ARTIFACT'])
                self.assertEqual(route['source_commit'],revision)
            proof=workspace.query('source',start=target['id']);self.assertEqual(proof['path'],manifest)
            proof=workspace.query('source',start=shipped[0]['id']);self.assertEqual(proof['path'],'assemble.py')
            module=next(n for n in graph['nodes'] if n.get('syntax')=='source_file' and n['path']=='code/start.rs')
            self.assertTrue(workspace.query('path',start=target['id'],target=module['id'],kinds=['CARGO_TARGET_SOURCE'])['found'])
            self.assertEqual(artifact['materialization'],'reported_by_successful_native_build')
            binding=next(e for e in graph['edges'] if e['kind']=='REQUESTS_BUILD_CONTEXT_CANDIDATE')
            request=next(n for n in graph['nodes'] if n['id']==binding['source'])
            for direction,start,end in [('out',request['source_invocation'],shipped[0]['id']),('in',shipped[0]['id'],request['source_invocation'])]:
                route=workspace.query('path',start=start,target=end,direction=direction,kinds=['SOURCE_BUILD_REQUEST',
                    'REQUESTS_BUILD_CONTEXT_CANDIDATE','CONFIGURES_BUILD_TARGET','PRODUCES_ARTIFACT','COPIES_ARTIFACT_TO'],depth=6,nodes=60,edges=60)
                self.assertTrue(route['found']);self.assertIsNone(route['stop_reason'])
            self.assertEqual(request['request']['target_directory'],'objects')
            self.assertEqual(request['request']['target_directory_basis'],'source_environment')
            self.assertEqual(binding['status'],'conditional_candidate')
            self.assertTrue(any(c['kind']=='canonical_source_layout_required' for c in binding['conditions']))
            self.assertFalse(receipt['product_executable_run']);self.assertEqual(git('status','--porcelain'),'')
            # The same source builds a navigable output plan without any Cargo capture input.
            default_analysis=copy.deepcopy(analysis);del default_analysis['build']
            planned=Workspace.create(root/'declared-workspace',source,typescript=self.ts,analysis=default_analysis)
            built=planned.update(builder=partial(build,typescript=self.ts),version={'rules':'authored-cargo-declared-fixture'})
            self.assertEqual(built['status'],'ready',built)
            declared=json.loads(Path(planned.config['active']['graph']).read_text(encoding='utf-8'))
            product=next(n for n in declared['nodes'] if n['kind']=='copied_artifact')
            request=next(n for n in declared['nodes'] if n['kind']=='cargo_build_request')
            for direction,start,end in [('out',request['source_invocation'],product['id']),('in',product['id'],request['source_invocation'])]:
                route=planned.query('path',start=start,target=end,direction=direction,kinds=['SOURCE_BUILD_REQUEST',
                    'REQUESTS_BUILD_CONTEXT_CANDIDATE','CONFIGURES_BUILD_TARGET','PRODUCES_ARTIFACT','COPIES_ARTIFACT_TO'],depth=6,nodes=60,edges=60)
                self.assertTrue(route['found']);self.assertIsNone(route['stop_reason'])
            self.assertEqual(next(n for n in declared['nodes'] if n['kind']=='build_artifact')['materialization'],'expected_output_not_built')
            self.assertFalse(declared['cargo_declared_artifacts']['product_compiled'])
            self.assertEqual(git('status','--porcelain'),'')
            # A later source commit cannot reuse old native products. Keep the prior active graph queryable.
            active=copy.deepcopy(workspace.config['active']);(source/'new.py').write_text('value=1\n')
            git('add','.');git('commit','-qm','advance beyond native capture')
            failed=workspace.update(builder=partial(build,typescript=self.ts),version={'rules':'authored-cargo-fixture'})
            self.assertEqual(failed['status'],'failed',failed);self.assertTrue(failed['active_preserved'])
            self.assertEqual(workspace.status()['active'],active)
            self.assertTrue(workspace.query('search',text=name,kind='build_target',allow_stale=True)['items'])
            self.assertEqual(git('status','--porcelain'),'')

    def test_python_sources_and_owned_interface_join_enter_the_production_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';source.mkdir();output=root/'output';output.mkdir()
            files={'start.py':'''from aiohttp import web
from handlers import serve
import os,shutil,subprocess
os.putenv('BUILD_OUTPUT','objects')
subprocess.run(['cargo','build'],cwd='workspace')
shutil.copytree(os.path.join('native','payload'),os.path.join('package','resources'))
for name in os.listdir('native'):
 shutil.copyfile(os.path.join('native',name),os.path.join('package',name))
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
            self.assertTrue(any(n['kind']=='python_file_operation' and n['destination_semantics']==['directory_root'] for n in graph['nodes']))
            self.assertTrue(any(n['kind']=='path_value' and n.get('language')=='python' and n['value']['relative_path']=='native/payload' for n in graph['nodes']))
            self.assertTrue(any(e['kind']=='FILE_SOURCE' for e in graph['edges']))
            self.assertTrue(any(n['kind']=='file_operation_context' for n in graph['nodes']))
            self.assertTrue(any(e['kind']=='CONTEXT_PATH_VALUE' for e in graph['edges']))
            self.assertTrue(any(n['kind']=='path_value' and n['value']['resolution']=='pattern' for n in graph['nodes']))
            self.assertTrue(any(n['kind']=='path_iteration' for n in graph['nodes']))
            self.assertTrue(any(n['kind']=='python_process_invocation' for n in graph['nodes']))
            self.assertTrue(any(e['kind']=='PROCESS_ENVIRONMENT_EFFECT' for e in graph['edges']))
            self.assertTrue(any(e['kind']=='PROCESS_BOUNDARY' for e in graph['edges']))

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
