"""Check process-evidence joins and the identities they must not invent."""
from copy import deepcopy
import unittest

from adapters.native_process_sites import augment, project
from adapters.sqlite_fact_graph import validate_graph


REVISION = 'a' * 40


def fixture(prefix='ops'):
    provenance = {'provider': 'codebase-memory-mcp', 'version': '0.12.1', 'source_commit': REVISION}
    nodes = [
        {'id': 'docker', 'kind': 'code_module', 'path': prefix + '/Dockerfile', 'line': 1, 'name': 'image'},
        {'id': 'shell', 'kind': 'code_module', 'path': prefix + '/launch.sh', 'line': 1, 'name': 'launch'},
        {'id': 'task', 'kind': 'code_module', 'path': prefix + '/task.sh', 'line': 1, 'name': 'task'},
        {'id': 'command', 'kind': 'call_site', 'language': 'shell', 'path': prefix + '/launch.sh',
         'line': 4, 'name': 'sh'},
        {'id': 'owner', 'kind': 'callable', 'path': prefix + '/start.py', 'line': 1, 'name': 'start'},
        {'id': 'bound', 'kind': 'python_boundary', 'path': prefix + '/start.py', 'line': 6,
         'name': 'sp.Popen', 'call': 'call:1', 'api_candidates': ['subprocess.Popen']},
        {'id': 'description', 'kind': 'process', 'path': '', 'line': 0, 'name': '<dynamic>'},
    ]
    edges = []
    for identifier, source, target, line, api, program in [
            (1, 'docker', 'shell', 9, 'dockerfile', '/launch.sh'),
            (2, 'shell', 'task', 4, 'shell', 'task.sh'),
            (3, 'owner', 'description', 6, 'subprocess.Popen', '<dynamic>')]:
        edges.append({'source': source, 'target': target, 'kind': 'CBM_SPAWNS', 'status': 'candidate',
                      'native_id': identifier, 'provenance': provenance,
                      'evidence': [{'path': next(n['path'] for n in nodes if n['id']==source), 'line': line}],
                      'native_properties': {'line': line, 'api': api, 'program': program}})
    return nodes, edges


class NativeProcessSitesTests(unittest.TestCase):
    def test_two_layouts_connect_shell_call_to_native_source_target(self):
        for prefix in ('ops', 'new/packages/service'):
            nodes, edges = fixture(prefix)
            result = project(nodes, edges, source_commit=REVISION)
            adjacency = {}
            for e in result['edges']:
                adjacency.setdefault(e['source'], []).append(e['target'])
            self.assertTrue(any('task' in adjacency.get(site, []) for site in adjacency['command']))
            self.assertEqual(result['summary']['counts']['sites'], 3)
            self.assertEqual({n['path'] for n in result['nodes']},
                             {prefix + '/' + name for name in ('Dockerfile', 'launch.sh', 'start.py')})
            self.assertTrue(all(e['status'] == 'candidate' for e in result['edges']))

    def test_program_description_does_not_join_two_process_instances(self):
        nodes, edges = fixture()
        other = deepcopy(nodes[-2]); other.update(id='other', path='other/start.py')
        nodes.append(other)
        edges.append({**edges[-1], 'native_id': 4})
        result = project(nodes, edges, source_commit=REVISION)
        self.assertEqual(len([n for n in result['nodes'] if n['native_target'] == 'description']), 2)
        self.assertFalse(any(e['target'] == 'description' for e in result['edges']))
        self.assertFalse(any(e['source'] == 'other' for e in result['edges']))
        self.assertEqual(result['summary']['counts']['unresolved_dynamic_program'], 2)

    def test_two_same_api_calls_on_one_line_are_ambiguous(self):
        nodes, edges = fixture()
        nodes.append({**nodes[-2], 'id': 'second', 'call': 'call:2'})
        result = project(nodes, edges, source_commit=REVISION)
        python = next(n for n in result['nodes'] if n['path'].endswith('.py'))
        self.assertEqual(python['anchor_status'], 'ambiguous_source_calls')
        self.assertFalse(any(e['source'] in {'bound', 'second'} for e in result['edges']))

    def test_same_line_wrong_bound_api_is_not_an_anchor(self):
        nodes, edges = fixture(); nodes[-2]['api_candidates'] = ['subprocess.run']
        result = project(nodes, edges, source_commit=REVISION)
        self.assertFalse(any(e['source'] == 'bound' for e in result['edges']))

    def test_rust_command_constructor_is_not_reported_as_process_start(self):
        nodes, edges = fixture()
        nodes[-2].update(kind='rust_boundary', api_declarations=[{'canonical': 'std::process::Command::new'}])
        edges[-1]['native_properties']['api'] = 'std::process::Command::new'
        result = project(nodes, edges, source_commit=REVISION)
        python = next(n for n in result['nodes'] if n['path'].endswith('.py'))
        self.assertEqual(python['operation'], 'command_construction')
        self.assertTrue(any(e['source'] == 'bound' for e in result['edges']))

    def test_wrong_revision_and_duplicate_native_identity_rejected(self):
        nodes, edges = fixture()
        with self.assertRaisesRegex(ValueError, 'another source revision'):
            project(nodes, edges, source_commit='b' * 40)
        with self.assertRaisesRegex(ValueError, 'Duplicate native'):
            project(nodes, edges + [edges[0]], source_commit=REVISION)

    def test_augmented_graph_remains_valid_and_does_not_overwrite_native_edges(self):
        nodes, edges = fixture(); original = deepcopy(edges)
        graph = {'snapshot': 'fixture', 'source_commit': REVISION, 'nodes': nodes,
                 'edges': edges, 'diagnostics': []}
        augment(graph); validate_graph(graph)
        self.assertEqual(graph['edges'][:3], original)
        with self.assertRaisesRegex(ValueError, 'already projected'):
            augment(graph)


if __name__ == '__main__':
    unittest.main()
