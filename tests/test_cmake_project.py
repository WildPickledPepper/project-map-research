import os
import json
from pathlib import Path
import subprocess
import tempfile
import shutil
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

    def facts(self, *, config=None, source_commit='fixture'):
        paths = sorted(p.relative_to(self.source).as_posix() for p in self.source.rglob('*') if p.is_file())
        cpp = cpp_facts({p: (self.source / p).read_bytes() for p in paths if p.endswith('.cpp')}, self.parser)
        self.sequence += 1
        graph = extract(self.source, paths, source_commit=source_commit, output=self.base / ('analysis-' + str(self.sequence)),
                        config=config, source_facts=cpp)
        validate_graph({'snapshot': 'fixture', 'nodes': graph['nodes'] + cpp['nodes'], 'edges': graph['edges'] + cpp['edges']})
        return graph

    def test_successful_native_capture_replays_without_reconfiguring_source(self):
        revision='a'*40
        original=self.facts(source_commit=revision)
        capture=self.base/'analysis-1/0/0'
        (capture/'result.json').write_text(json.dumps({'source_commit':revision,'subdir':'recipes',
            'configuration':'Release','dependencies':[],'attempts':[{'id':'build','configured':True}]}))
        replay=self.facts(source_commit=revision,config={'version':1,'cmake':{
            'captures':[{'directory':str(capture),'source_commit':revision}]}})
        self.assertTrue(replay['contexts'][0]['capture_reused'])
        self.assertEqual({n['name'] for n in original['nodes'] if n['kind']=='build_target'},
                         {n['name'] for n in replay['nodes'] if n['kind']=='build_target'})
        self.assertFalse((self.base/'analysis-2/0/0/build').exists())
        self.assertFalse((self.base/'analysis-2/0/0/source').exists())
        with self.assertRaisesRegex(ValueError,'another source revision'):
            self.facts(source_commit='b'*40,config={'version':1,'cmake':{
                'captures':[{'directory':str(capture),'source_commit':revision}]}})

    def test_native_configuration_is_in_a_copy_and_entry_join_survives(self):
        graph = self.facts()
        self.assertEqual(graph['projects'], ['recipes'])
        self.assertEqual(graph['contexts'][0]['status'], 'configured')
        self.assertTrue(graph['contexts'][0]['compile_commands_available'])
        self.assertTrue(any(e['kind'] == 'EXECUTABLE_ENTRY_CANDIDATE' for e in graph['edges']))
        self.assertFalse((self.source / 'recipes/generated-on-configure.txt').exists())
        self.assertTrue(list((self.base / 'analysis-1').rglob('generated-on-configure.txt')))
        self.assertFalse([d for d in graph['diagnostics'] if d['required']])

    def test_multiple_native_variants_keep_artifacts_and_context_identities_separate(self):
        revision='a'*40
        script=self.source/'recipes/CMakeLists.txt'
        script.write_text(script.read_text()+'''\nif(SELECT_ALTERNATE)
set_target_properties(first PROPERTIES OUTPUT_NAME alternate)
endif()
''')
        self.facts(source_commit=revision)
        self.facts(source_commit=revision,config={'version':1,'cmake':{'arguments':['-DSELECT_ALTERNATE=ON']}})
        captures=[]
        for index,label in ((1,'baseline'),(2,'alternate')):
            capture=self.base/f'analysis-{index}/0/0'
            (capture/'result.json').write_text(json.dumps({'source_commit':revision,'subdir':'recipes',
                'configuration':'Release','dependencies':[],'attempts':[{'id':'build','configured':True}]}))
            captures.append({'directory':str(capture),'source_commit':revision,'context_key':label})
        graph=self.facts(source_commit=revision,config={'version':1,'cmake':{'captures':captures}})
        contexts={r['key'] for r in graph['contexts']}
        self.assertEqual(len(contexts),2)
        targets=[n for n in graph['nodes'] if n['kind']=='build_target']
        self.assertEqual(len(targets),2)
        self.assertEqual(len({n['id'] for n in graph['nodes']}),len(graph['nodes']))
        self.assertEqual(len({n['build_context'] for n in targets}),2)
        primary={e['target'] for e in graph['edges'] if e['kind']=='PRODUCES_ARTIFACT' and e.get('artifact_role')=='primary'}
        self.assertEqual({n['name'].removesuffix('.exe') for n in graph['nodes'] if n['id'] in primary},
                         {'first','alternate'})
        removed=self.facts(source_commit=revision,config={'version':1,'cmake':{'captures':captures[:1]}})
        self.assertEqual(len(removed['contexts']),1)
        self.assertFalse(any(n['name'].startswith('alternate') for n in removed['nodes']))
        without_labels=[{k:v for k,v in row.items() if k!='context_key'} for row in captures]
        with self.assertRaisesRegex(ValueError,'duplicate'):
            self.facts(source_commit=revision,config={'version':1,'cmake':{'captures':without_labels}})

    def test_portable_native_reply_replays_without_its_original_build_location(self):
        revision='a'*40
        self.facts(source_commit=revision)
        original=self.base/'analysis-1/0/0'
        capture=self.base/'portable'
        shutil.copytree(original/'build',capture/'build')
        receipt=json.loads((original/'receipt.json').read_text())
        (capture/'build/command.json').write_text(json.dumps(receipt['command']))
        (capture/'result.json').write_text(json.dumps({'source_commit':revision,'subdir':'recipes',
            'configuration':'Release','dependencies':[],'attempts':[{'id':'build','configured':True}]}))
        graph=self.facts(source_commit=revision,config={'version':1,'cmake':{
            'captures':[{'directory':str(capture),'source_commit':revision,'context_key':'portable'}]}})
        self.assertTrue(graph['contexts'][0]['capture_reused'])
        self.assertTrue(any(e['kind']=='EXECUTABLE_ENTRY_CANDIDATE' for e in graph['edges']))
        self.assertFalse((capture/'source').exists())

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
