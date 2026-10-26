"""Ensure native captures cannot silently change source/configuration or precision."""
import json
from pathlib import Path
import tempfile
import unittest

from adapters.native_provider_graph import augment, configuration, merge, read_capture
from adapters.repository_discovery import manifest_kind
from adapters.build_configuration import configuration as build_configuration


class NativeProviderGraphTests(unittest.TestCase):
    def facts(self):
        return {'nodes': [{'id': 'native:1', 'kind': 'type', 'path': 'model.hpp', 'line': 1,
                           'name': 'Model'}], 'edges': [], 'diagnostics': [],
                'coverage': [{'path': 'model.hpp', 'status': 'parsed'}], 'limits': [],
                'components': {'provider': 'clangd', 'source_commit': 'c' * 40, 'context': 'release'}}

    def test_stale_source_and_wrong_compile_context_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'facts.json').write_text(json.dumps(self.facts()))
            capture = {'provider': 'clangd', 'directory': str(root), 'source_commit': 'c' * 40,
                       'context_key': 'release'}
            with self.assertRaisesRegex(ValueError, 'another source revision'):
                read_capture(capture, paths=['model.hpp'], source_commit='d' * 40)
            with self.assertRaisesRegex(ValueError, 'another compile context'):
                read_capture({**capture, 'context_key': 'debug'}, paths=['model.hpp'], source_commit='c' * 40)
            self.assertEqual(len(read_capture(capture, paths=['model.hpp'], source_commit='c' * 40)['nodes']), 1)

    def test_capture_filters_to_current_selected_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'facts.json').write_text(json.dumps(self.facts()))
            capture = {'provider': 'clangd', 'directory': str(root), 'source_commit': 'c' * 40,
                       'context_key': 'release'}
            facts = read_capture(capture, paths=['other.hpp'], source_commit='c' * 40)
            self.assertEqual(facts['nodes'], []); self.assertEqual(facts['coverage'], [])

    def test_error_context_does_not_turn_native_lookup_into_precise_edge(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); facts = self.facts()
            facts['coverage'][0]['status'] = 'parsed_with_diagnostics'
            facts['edges'] = [{'source':'native:1','target':'native:1','kind':'CLANGD_REFERS_TO_DECLARATION',
                              'status':'static_declaration','evidence':[]}]
            (root / 'facts.json').write_text(json.dumps(facts))
            capture={'provider':'clangd','directory':str(root),'source_commit':'c'*40,'context_key':'release'}
            actual=read_capture(capture,paths=['model.hpp'],source_commit='c'*40)
            self.assertEqual(actual['edges'][0]['status'],'candidate')
            self.assertEqual(actual['nodes'][0]['semantic_context_status'],'parsed_with_diagnostics')

    def test_semantic_provider_status_preserves_existing_parser_status_and_native_evidence(self):
        graph = {'input_paths': ['model.hpp'], 'nodes': [], 'edges': [], 'limits': [], 'diagnostics': [],
                 'coverage': [{'path': 'model.hpp', 'status': 'syntax_errors'}]}
        facts = self.facts(); merge(graph, facts, provider='clangd', context='release')
        self.assertEqual(graph['coverage'][0]['status'], 'parsed')
        self.assertEqual(graph['coverage'][0]['source_parser_status'], 'syntax_errors')
        self.assertEqual(graph['coverage'][0]['providers'], facts['coverage'])
        with self.assertRaisesRegex(ValueError, 'identity collision'):
            merge(graph, facts, provider='clangd', context='release')

    def test_native_header_capture_preserves_standalone_diagnostics_and_rejects_wrong_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); facts=self.facts();facts['components']['provider']='libclang'
            facts['nodes'][0]['id']='libclang:header:1'
            facts['coverage'][0]['translation_units']=[{'translation_unit':'consumer.cpp','status':'parsed','errors':0}]
            (root/'facts.json').write_text(json.dumps(facts))
            capture={'provider':'libclang','directory':str(root),'source_commit':'c'*40,'context_key':'release'}
            result=read_capture(capture,paths=['model.hpp'],source_commit='c'*40)
            graph={'input_paths':['model.hpp'],'nodes':[],'edges':[],'limits':[],'diagnostics':[],
                   'coverage':[{'path':'model.hpp','status':'parsed_with_diagnostics',
                     'native_semantic_status':'parsed_with_diagnostics','providers':[{'provider':'clangd','status':'parsed_with_diagnostics'}]}]}
            merge(graph,result,provider='libclang',context='release')
            row=graph['coverage'][0]
            self.assertEqual(row['status'],'parsed')
            self.assertEqual(row['standalone_native_semantic_status'],'parsed_with_diagnostics')
            self.assertEqual(row['providers'][0]['status'],'parsed_with_diagnostics')
            self.assertEqual(row['translation_unit_semantics']['translation_units'][0]['errors'],0)
            with self.assertRaisesRegex(ValueError,'wrong provider'):
                read_capture({**capture,'provider':'clangd'},paths=['model.hpp'],source_commit='c'*40)

    def test_outside_source_is_not_accepted_by_merge(self):
        graph = {'input_paths': ['other.hpp'], 'nodes': [], 'edges': [], 'limits': [], 'diagnostics': [], 'coverage': []}
        with self.assertRaisesRegex(ValueError, 'escaped'):
            merge(graph, self.facts(), provider='clangd', context='release')

    def test_native_provider_configuration_passes_through_existing_build_config(self):
        config = build_configuration({'version': 1, 'cmake': {}, 'providers': {'cbm': {'enabled': False}}})
        self.assertFalse(config['providers']['cbm']['enabled'])
        with self.assertRaises(ValueError):
            configuration({'cbm': {'enabled': 'true'}})
        with self.assertRaises(ValueError):
            configuration({'captures': [{'provider': 'unknown'}]})

    def test_rust_svf_capture_does_not_hide_missing_cpp_native_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);facts=self.facts();facts['components']['provider']='svf'
            facts['nodes'][0].update(path='app.rs',language='rust');facts['coverage'][0]['path']='app.rs'
            (root/'facts.json').write_text(json.dumps(facts))
            graph={'input_paths':['app.rs','model.cpp'],'source_commit':'c'*40,'nodes':[],
                'edges':[],'limits':[],'diagnostics':[],'coverage':[]}
            augment(graph,root=root,output=root/'output',config={
                'cbm':{'enabled':False},'clangd':{'enabled':False},'libclang':{'enabled':False},
                'rapx':{'enabled':False},'captures':[{'provider':'svf','directory':str(root.resolve()),
                'source_commit':'c'*40,'context_key':'release'}]})
            self.assertTrue(any(d.get('provider')=='svf' and d.get('language')=='cpp'
                                and d['affected_paths']==['model.cpp'] for d in graph['diagnostics']))

    def test_standard_container_and_yaml_names_are_project_independent(self):
        for name in ('ops/Dockerfile', 'bundle/Dockerfile.debug', 'service.custom.Dockerfile',
                     'configuration/renamed.yaml', 'deployment/other.yml'):
            self.assertEqual(manifest_kind(name), 'native_boundary')


if __name__ == '__main__':
    unittest.main()
