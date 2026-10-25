import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from adapters.cmake_file_api import analyze, link_source_symbols,target_system,NativeContextError
from adapters.cpp_facts import analyze as cpp_facts
from adapters.sqlite_fact_graph import validate_graph


CMAKE = os.environ.get('PROJECT_MAP_CMAKE') or shutil.which('cmake')
NINJA = os.environ.get('PROJECT_MAP_NINJA') or shutil.which('ninja')


class NativeSystemRecordTests(unittest.TestCase):
    def record(self,body):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        root=Path(directory.name);path=root/'CMakeFiles/3.31.6/CMakeSystem.cmake';path.parent.mkdir(parents=True);path.write_text(body)
        return root

    def body(self,name='Windows',processor='AMD64',host='Windows',cross='FALSE'):
        return f'''set(CMAKE_SYSTEM_NAME "{name}")
set(CMAKE_SYSTEM_PROCESSOR "{processor}")
set(CMAKE_HOST_SYSTEM_NAME "{host}")
set(CMAKE_HOST_SYSTEM_PROCESSOR "host-processor")
set(CMAKE_CROSSCOMPILING "{cross}")
'''

    def test_target_host_and_declared_processor_remain_distinct(self):
        row=target_system(self.record(self.body('Linux','aarch64','Windows','TRUE')),'3.31.6')
        self.assertEqual((row['name'],row['host_name'],row['declared_processor']),('Linux','Windows','aarch64'))
        self.assertEqual(row['target_path_style'],'posix');self.assertEqual(row['host_path_style'],'windows');self.assertTrue(row['cross_compiling'])
        self.assertEqual(row['processor_interpretation'],'cmake_system_processor_not_verified_compiler_architecture')

    def test_missing_ambiguous_dynamic_and_unknown_boolean_are_rejected(self):
        for body in (self.body().replace('set(CMAKE_SYSTEM_NAME "Windows")',''),self.body()+'set(CMAKE_SYSTEM_NAME "Linux")\n',
                     self.body('${runtime}'),self.body(cross='MAYBE')):
            with self.subTest(body=body),self.assertRaises(NativeContextError):target_system(self.record(body),'3.31.6')

    def test_unknown_system_name_is_recorded_without_inventing_path_style(self):
        row=target_system(self.record(self.body('Generic','riscv64','Linux','TRUE')),'3.31.6')
        self.assertEqual(row['name'],'Generic');self.assertIsNone(row['target_path_style'])

    def test_version_path_and_missing_file_are_rejected(self):
        root=self.record(self.body())
        for version in ('../../outside','9.9.9'):
            with self.subTest(version=version),self.assertRaises(NativeContextError):target_system(root,version)


@unittest.skipUnless(CMAKE and NINJA, 'Native CMake and Ninja required')
class CMakeFileApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='native cmake facts ')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.base = Path(cls.temporary.name); cls.repository = cls.base / 'repository'
        cls.project = cls.repository / 'recipes/native'; cls.project.mkdir(parents=True)
        cls.code = {'code/entry.cpp': 'namespace other{int main(){return 2;}} int main(){return 0;}\n',
                    'code/decoy.cpp': 'int main(){return 1;}\n',
                    'code/helper.cpp': 'int helper(){return 3;}\n',
                    'code/extra.cpp': 'int extra(){return 4;}\n'}
        for path, source in cls.code.items():
            target = cls.repository / path; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source, encoding='utf-8')
        cls.outside = cls.base / 'outside.cpp'; cls.outside.write_text('int outside(){return 8;}\n')
        (cls.project / 'CMakeLists.txt').write_text('''cmake_minimum_required(VERSION 3.16)
project(UnrelatedLayout LANGUAGES CXX)
option(WITH_EXTRA "Extra input" OFF)
add_library(helper STATIC ../../code/helper.cpp)
function(register_tool name input directory)
  add_executable(${name} ${input})
  set_target_properties(${name} PROPERTIES OUTPUT_NAME worker RUNTIME_OUTPUT_DIRECTORY "${directory}")
endfunction()
register_tool(alpha ../../code/entry.cpp "${CMAKE_BINARY_DIR}/service")
register_tool(beta ../../code/decoy.cpp "${CMAKE_BINARY_DIR}/decoy")
target_link_libraries(alpha PRIVATE helper)
if(WITH_EXTRA)
  target_sources(alpha PRIVATE ../../code/extra.cpp)
  target_compile_definitions(alpha PRIVATE EXTRA_ENABLED=1)
endif()
file(WRITE "${CMAKE_BINARY_DIR}/generated.cpp" "int generated(){return 7;}\\n")
set_source_files_properties("${CMAKE_BINARY_DIR}/generated.cpp" PROPERTIES GENERATED TRUE)
target_sources(alpha PRIVATE "${CMAKE_BINARY_DIR}/generated.cpp")
add_library(external_library STATIC "''' + cls.outside.as_posix() + '''")
''', encoding='utf-8')
        cls.builds = {}
        for label, configuration, enabled in [('release', 'Release', 'OFF'), ('debug', 'Debug', 'ON')]:
            build = cls.base / label; query = build / '.cmake/api/v1/query/client-project-map'
            query.mkdir(parents=True)
            for name in ('codemodel-v2', 'cache-v2', 'toolchains-v1', 'cmakeFiles-v1'): (query / name).touch()
            result = subprocess.run([CMAKE, '-S', str(cls.project), '-B', str(build), '-G', 'Ninja',
                '-DCMAKE_MAKE_PROGRAM=' + str(NINJA), '-DCMAKE_BUILD_TYPE=' + configuration,
                '-DWITH_EXTRA=' + enabled], capture_output=True, text=True, timeout=90)
            if result.returncode: raise RuntimeError(result.stdout + result.stderr)
            cls.builds[label] = build
        import tree_sitter_language_pack as pack
        if os.environ.get('PROJECT_MAP_PARSER_CACHE'):
            pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))
        cls.source_facts = cpp_facts({p: s.encode() for p, s in cls.code.items()}, pack.get_parser('cpp'))

    def graph(self, label='release', **overrides):
        args = {'context_key': 'native/' + label, 'source_commit': 'fixture-revision',
                'expected_commit': 'fixture-revision', 'selected_paths': list(self.code), 'configure_returncode': 0}
        args.update(overrides)
        graph = analyze(self.builds[label], self.repository, **args)
        validate_graph({'snapshot': 'native-cmake-fixture', **graph})
        return graph

    def pairs(self, graph, kind):
        nodes = {n['id']: n for n in graph['nodes']}
        return [(nodes[e['source']], nodes[e['target']], e) for e in graph['edges'] if e['kind'] == kind]

    def test_same_basename_artifacts_have_separate_full_path_identity(self):
        graph = self.graph(); self.assertEqual(graph['native_context']['status'], 'configured')
        pairs = self.pairs(graph, 'PRODUCES_ARTIFACT')
        primary = [(a, b) for a, b, e in pairs if e['artifact_role'] == 'primary' and a['target_type'] == 'EXECUTABLE']
        self.assertEqual({a['name'] for a, _ in primary}, {'alpha', 'beta'})
        self.assertEqual(len({b['name'] for _, b in primary}), 1)
        self.assertEqual(len({b['id'] for _, b in primary}), 2)
        self.assertEqual({Path(b['location']['path']).parent.as_posix() for _, b in primary}, {'service', 'decoy'})
        self.assertTrue(all(b['path'] == '@build/' + b['location']['path'] for _, b in primary))
        self.assertTrue(all(a['name'] not in b['name'] for a, b in primary))

    def test_live_native_system_is_bound_to_configuration_not_artifact_filename(self):
        graph=self.graph();context=next(n for n in graph['nodes'] if n['kind']=='build_configuration')
        system=context['target_system']
        self.assertEqual(system['status'],'available');self.assertEqual(system,graph['native_context']['target_system'])
        self.assertEqual(system['host_path_style'],'windows' if os.name=='nt' else 'posix')
        self.assertEqual(system['target_path_style'],system['host_path_style'])
        self.assertEqual(system['file'],'CMakeFiles/'+context['cmake_version']+'/CMakeSystem.cmake')

    def test_source_and_dependency_membership_use_native_target_ids(self):
        graph = self.graph()
        self.assertEqual({(a['name'], b['name']) for a, b, _ in self.pairs(graph, 'LINKS_BUILD_TARGET')}, {('alpha', 'helper')})
        owned = {(a['name'], b['path']) for a, b, _ in self.pairs(graph, 'COMPILES_SOURCE') if b['selected_source']}
        self.assertIn(('alpha', 'code/entry.cpp'), owned)
        self.assertNotIn(('alpha', 'code/decoy.cpp'), owned)
        self.assertIn(('beta', 'code/decoy.cpp'), owned)
        declaration = next(n['declaration'] for n in graph['nodes'] if n['kind'] == 'build_target' and n['name'] == 'alpha')
        self.assertTrue({'add_executable', 'register_tool'} <= {r.get('command') for r in declaration})
        self.assertTrue(all(r['path'] == 'recipes/native/CMakeLists.txt' for r in declaration))

    def test_configuration_conditions_and_ids_do_not_collapse(self):
        release = self.graph(); debug = self.graph('debug')
        self.assertFalse({n['id'] for n in release['nodes']} & {n['id'] for n in debug['nodes']})
        self.assertFalse(any(n['kind'] == 'build_source' and n['path'] == 'code/extra.cpp' for n in release['nodes']))
        extra = next(n for n in debug['nodes'] if n['kind'] == 'build_source' and n['path'] == 'code/extra.cpp')
        definition = next(d for d in extra['compile_group']['definitions'] if d['define'] == 'EXTRA_ENABLED=1')
        self.assertTrue(any(r.get('command') == 'target_compile_definitions' for r in definition['declaration']))
        context = next(n for n in debug['nodes'] if n['kind'] == 'build_configuration')
        self.assertEqual(context['configuration'], 'Debug')
        self.assertIn({'name': 'WITH_EXTRA', 'type': 'BOOL', 'value': 'ON'}, context['cache_options'])

    def test_entry_join_is_per_native_input_and_keeps_preprocessor_uncertainty(self):
        graph = self.graph(); edges = link_source_symbols(graph, self.source_facts)
        combined = {'snapshot': 'joined', 'nodes': graph['nodes'] + self.source_facts['nodes'], 'edges': graph['edges'] + edges}
        validate_graph(combined)
        pairs = self.pairs(combined, 'EXECUTABLE_ENTRY_CANDIDATE')
        self.assertEqual({(a['name'], b['name'], b['path']) for a, b, _ in pairs},
                         {('alpha', 'main', 'code/entry.cpp'), ('beta', 'main', 'code/decoy.cpp')})
        self.assertTrue(all(e['status'] == 'candidate' and e['condition'] == 'source_preprocessor_and_link_selection_not_proven' for _, _, e in pairs))
        self.assertFalse(any(b['name'] == 'other::main' for _, b, _ in pairs))

    def test_unselected_generated_and_external_sources_are_explicit(self):
        graph = self.graph(); outside = [n for n in graph['nodes'] if n['kind'] == 'build_source' and not n['selected_source']]
        self.assertEqual({n['location']['root'] for n in outside}, {'build', 'external'})
        self.assertTrue(any(n['generated'] for n in outside))
        self.assertTrue(all(d['required'] for d in graph['diagnostics']))
        self.assertFalse({n['id'] for n in outside} & {e['source'] for e in link_source_symbols(graph, self.source_facts)})

    def test_declared_dependency_scope_does_not_demand_all_dependency_internals(self):
        graph = self.graph(selected_paths=['code/entry.cpp', 'code/decoy.cpp'], dependency_prefixes=['code/helper.cpp'])
        dependency = next(n for n in graph['nodes'] if n['kind'] == 'build_source' and n['path'] == 'code/helper.cpp')
        self.assertTrue(dependency['dependency_source']); self.assertFalse(dependency['selected_source'])
        diagnostic = next(d for d in graph['diagnostics'] if d.get('path') == 'code/helper.cpp')
        self.assertFalse(diagnostic['required'])

    def test_wrong_source_and_failed_reconfigure_reject_previous_success(self):
        for override in ({'source_commit': 'other-revision'}, {'configure_returncode': 1}):
            graph = self.graph(**override)
            self.assertFalse(graph['nodes']); self.assertFalse(graph['edges'])
            self.assertEqual(graph['native_context']['status'], 'unavailable')
            self.assertTrue(graph['diagnostics'][0]['required'])

    def test_published_directory_copy_requires_matching_recorded_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);copied_build=root/'build';copied_source=root/'repository'
            shutil.copytree(self.builds['release'],copied_build);shutil.copytree(self.repository,copied_source)
            args={'context_key':'relocated/release','source_commit':'fixture-revision','expected_commit':'fixture-revision',
                  'selected_paths':list(self.code),'configure_returncode':0}
            rejected=analyze(copied_build,copied_source,**args)
            self.assertEqual(rejected['native_context']['status'],'unavailable')
            graph=analyze(copied_build,copied_source,recorded_build_root=self.builds['release'],recorded_repository_root=self.repository,**args)
            validate_graph({'snapshot':'relocated-native',**graph})
            self.assertEqual(graph['native_context']['status'],'configured')
            self.assertTrue(graph['native_context']['relocation']['build_root_relocated'])
            self.assertEqual(graph['native_context']['target_system']['status'],'available')
            self.assertEqual({n['location']['path'] for n in graph['nodes'] if n['kind']=='build_artifact'},
                             {n['location']['path'] for n in self.graph()['nodes'] if n['kind']=='build_artifact'})
            for patch in ({'recorded_build_root':self.base/'wrong','recorded_repository_root':self.repository},
                          {'recorded_build_root':self.builds['release']}):
                self.assertEqual(analyze(copied_build,copied_source,**patch,**args)['native_context']['status'],'unavailable')

    def test_wrong_export_missing_index_and_reply_escape_are_required_gaps(self):
        for directory, index_name in [(self.base / 'missing', None), (self.builds['release'], '../../outside.json')]:
            graph = analyze(directory, self.repository, context_key='unavailable', source_commit='revision',
                expected_commit='revision', selected_paths=[], configure_returncode=0, index_name=index_name)
            self.assertFalse(graph['nodes']); self.assertTrue(graph['diagnostics'][0]['required'])
        graph = analyze(self.builds['release'], self.base / 'wrong-export', context_key='unavailable',
            source_commit='revision', expected_commit='revision', selected_paths=[], configure_returncode=0)
        self.assertFalse(graph['nodes']); self.assertTrue(graph['diagnostics'][0]['required'])


if __name__ == '__main__': unittest.main()
