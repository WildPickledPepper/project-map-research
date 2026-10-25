import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from adapters.cmake_project import configuration, extract, roots
from adapters.cpp_facts import analyze as cpp_facts
from adapters.sqlite_fact_graph import validate_graph
from tests.test_cmake_file_api import CMAKE, NINJA


class CMakeConfigurationTests(unittest.TestCase):
    def test_root_discovery_has_no_project_name_or_layout_assumptions(self):
        self.assertEqual(roots(['unknown/tree/CMakeLists.txt', 'unknown/tree/lib/CMakeLists.txt',
                                'other/CMakeLists.txt', 'other/sub/CMakeLists.txt']), ['other', 'unknown/tree'])
        self.assertEqual(roots(['CMakeLists.txt', 'x/y/CMakeLists.txt']), ['.'])

    def test_strict_versioned_context_configuration(self):
        self.assertEqual(configuration()['cmake']['configurations'], ['Release'])
        for patch in [{'version': 2}, {'version': 1, 'unknown': True},
            {'version': 1, 'cmake': {'enabled': 'yes'}}, {'version': 1, 'cmake': {'timeout_seconds': False}},
            {'version': 1, 'cmake': {'arguments': ['-Soutside']}},
            {'version': 1, 'cmake': {'arguments': ['-DCMAKE_BUILD_TYPE=Debug']}},
            {'version': 1, 'cmake': {'dependencies': [{'kind': 'git', 'destination': '../outside', 'repository': 'repo', 'revision': 'a' * 40}]}},
            {'version': 1, 'cmake': {'dependencies': [{'kind': 'git', 'destination': 'dep', 'repository': 'repo', 'revision': 'main'}]}}]:
            with self.subTest(patch=patch), self.assertRaises(ValueError): configuration(patch)


@unittest.skipUnless(CMAKE and NINJA, 'Native CMake and Ninja required')
class CMakeProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cmake configure copy '); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name); self.source = self.base / 'committed'; self.source.mkdir()
        self.write('recipes/CMakeLists.txt', '''cmake_minimum_required(VERSION 3.16)
project(Independent LANGUAGES CXX)
file(WRITE "${CMAKE_SOURCE_DIR}/generated-on-configure.txt" "copy only")
add_executable(first ../programs/entry.cpp)
''')
        self.write('programs/entry.cpp', 'int main(){return 0;}\n')
        import tree_sitter_language_pack as pack
        if os.environ.get('PROJECT_MAP_PARSER_CACHE'): pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))
        self.parser = pack.get_parser('cpp'); self.sequence = 0

    def write(self, name, text):
        path = self.source / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text, encoding='utf-8')

    def facts(self, *, config=None):
        paths = sorted(p.relative_to(self.source).as_posix() for p in self.source.rglob('*') if p.is_file())
        cpp = cpp_facts({p: (self.source / p).read_bytes() for p in paths if p.endswith('.cpp')}, self.parser)
        self.sequence += 1
        graph = extract(self.source, paths, source_commit='fixture', output=self.base / ('analysis-' + str(self.sequence)),
                        config=config, source_facts=cpp)
        validate_graph({'snapshot': 'fixture', 'nodes': graph['nodes'] + cpp['nodes'], 'edges': graph['edges'] + cpp['edges']})
        return graph

    def test_native_configuration_is_in_a_copy_and_entry_join_survives(self):
        graph = self.facts()
        self.assertEqual(graph['projects'], ['recipes'])
        self.assertEqual(graph['contexts'][0]['status'], 'configured')
        self.assertTrue(graph['contexts'][0]['compile_commands_available'])
        self.assertTrue(any(e['kind'] == 'EXECUTABLE_ENTRY_CANDIDATE' for e in graph['edges']))
        self.assertFalse((self.source / 'recipes/generated-on-configure.txt').exists())
        self.assertTrue(list((self.base / 'analysis-1').rglob('generated-on-configure.txt')))
        self.assertFalse([d for d in graph['diagnostics'] if d['required']])

    def test_target_add_rename_delete_rebuild_has_no_old_target_or_artifact(self):
        first = self.facts()
        self.write('programs/another.cpp', 'int main(){return 1;}\n')
        script = self.source / 'recipes/CMakeLists.txt'; original = script.read_text()
        script.write_text(original + 'add_executable(second ../programs/another.cpp)\n')
        added = self.facts()
        script.write_text(original.replace('first ', 'renamed '))
        renamed = self.facts()
        names = lambda g: {n['name'] for n in g['nodes'] if n['kind'] == 'build_target'}
        self.assertEqual(names(first), {'first'}); self.assertEqual(names(added), {'first', 'second'})
        self.assertEqual(names(renamed), {'renamed'})
        artifacts = [n['name'] for n in renamed['nodes'] if n['kind'] == 'build_artifact']
        self.assertTrue(all('first' not in n and 'second' not in n for n in artifacts))

    def test_two_real_configs_and_explicitly_disabled_context(self):
        graph = self.facts(config={'version': 1, 'cmake': {'configurations': ['Release', 'Debug']}})
        self.assertEqual({r['configuration'] for r in graph['contexts']}, {'Release', 'Debug'})
        self.assertEqual(len([n for n in graph['nodes'] if n['kind'] == 'build_configuration']), 2)
        disabled = self.facts(config={'version': 1, 'cmake': {'enabled': False}})
        self.assertFalse(disabled['nodes']); self.assertTrue(disabled['diagnostics'][0]['required'])
        self.assertEqual(disabled['contexts'][0]['status'], 'unavailable')

    def test_dependency_failure_and_source_overwrite_are_required_gaps(self):
        missing = self.source / 'recipes/CMakeLists.txt'; missing.write_text(missing.read_text() + 'add_subdirectory(required_dependency)\n')
        graph = self.facts()
        self.assertFalse(graph['nodes']); self.assertTrue(graph['diagnostics'][0]['required'])
        self.assertEqual(graph['contexts'][0]['configure_returncode'], 1)
        graph = self.facts(config={'version': 1, 'cmake': {'dependencies': [{'kind': 'file',
            'destination': 'programs/entry.cpp', 'path': str(self.source / 'programs/entry.cpp'),
            'origin': 'authored-source-cache', 'version': '1'}]}})
        self.assertFalse(graph['nodes']); self.assertTrue(graph['diagnostics'][0]['required'])
        self.assertIn('replace selected source', graph['diagnostics'][0]['reason'])

    def test_fixed_git_dependency_is_exported_without_modifying_its_checkout(self):
        dep = self.base / 'dependency'; dep.mkdir()
        (dep / 'CMakeLists.txt').write_text('add_library(helper STATIC helper.cpp)\n')
        (dep / 'helper.cpp').write_text('int helper(){return 3;}\n')
        def git(*args): return subprocess.check_output(['git', '-C', str(dep), *args], stderr=subprocess.PIPE).decode().strip()
        git('init', '-q'); git('config', 'user.name', 'fixture'); git('config', 'user.email', 'fixture@example.invalid')
        git('add', '.'); git('commit', '-qm', 'authored dependency'); revision = git('rev-parse', 'HEAD')
        script = self.source / 'recipes/CMakeLists.txt'; script.write_text(script.read_text() + 'add_subdirectory(dependency)\ntarget_link_libraries(first PRIVATE helper)\n')
        graph = self.facts(config={'version': 1, 'cmake': {'dependencies': [{'kind': 'git',
            'destination': 'recipes/dependency', 'repository': str(dep), 'revision': revision}]}})
        self.assertEqual(graph['contexts'][0]['status'], 'configured')
        self.assertTrue(any(n['kind'] == 'build_source' and n['dependency_source'] for n in graph['nodes']))
        self.assertFalse([d for d in graph['diagnostics'] if d['required']])
        self.assertEqual(git('status', '--porcelain'), '')


if __name__ == '__main__': unittest.main()
