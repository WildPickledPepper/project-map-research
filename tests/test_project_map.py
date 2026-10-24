import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from adapters.project_map import Budget, ProjectMap, build_index, encoded


def fixture():
    nodes = [{'id': uid, 'kind': kind, 'name': name, 'path': path, 'line': 2,
        'definition': True} for uid, kind, name, path in [
        ('api', 'callable', 'fetch', 'ui/a.ts'), ('message', 'protocol_message', 'request', 'ui/a.ts'),
        ('handler', 'callable', 'handle', 'server/a.cpp'), ('resource', 'storage_member', 'cache', 'server/a.cpp')]]
    nodes[1]['resolution'] = 'unknown'
    edges = [{'source': a, 'target': b, 'kind': k, 'status': 'conditional',
        'evidence': [{'path': 'server/a.cpp', 'line': 2}], 'conditions': ['service_selected']}
        for a, b, k in [('api', 'message', 'EMITS_MESSAGE'), ('message', 'handler', 'RESOLVES_HANDLER'),
            ('handler', 'resource', 'WRITES'), ('handler', 'resource', 'READS'), ('resource', 'handler', 'CYCLE')]]
    graph = {'source_commit': 'commit', 'snapshot': 'one', 'version': {'rules': 'frozen'}, 'nodes': nodes, 'edges': edges,
        'input_paths': ['ui/a.ts', 'server/a.cpp'], 'coverage': [{'path': p, 'status': 'parsed'} for p in ['ui/a.ts', 'server/a.cpp']],
        'diagnostics': [{'path': 'server/a.cpp', 'kind': 'missing_compile_context'}], 'limits': ['runtime_not_observed'],
        'protocol': {'results': [{'message': 'message', 'name': 'fetch', 'status': 'matched_conditional',
            'matches': [{'provider': 'p', 'conditions': ['service_selected']}]},
            {'name': 'dynamic', 'status': 'unknown_callable', 'matches': []}]}}
    files = [{'path': p, 'module': p.split('/')[0], 'status': 'pending', 'eligible': True, 'bytes': 60,
        'role': 'product', 'task': 'source', 'language': 'typescript' if p.endswith('ts') else 'cpp'}
        for p in graph['input_paths']]
    files.append({'path': 'tools/a.py', 'module': 'tools', 'status': 'excluded', 'eligible': False,
        'reason': 'unsupported_language', 'bytes': 40, 'language': 'python'})
    discovery = {'source_commit': 'commit', 'files': files,
        'modules': [{'path': p, 'files': 1, 'origin': 'nearest_tracked_manifest_or_top_level'} for p in ['ui', 'server', 'tools']]}
    return graph, discovery


class ProjectMapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / 'map.sqlite'
        self.graph, self.discovery = fixture()
        build_index(self.graph, self.discovery, self.path)
        self.q = ProjectMap(self.path)

    def tearDown(self):
        self.q.close()
        self.temp.cleanup()

    def test_lossless_nodes_parallel_edges_and_readonly(self):
        for i, node in enumerate(self.graph['nodes']):
            row = self.q.db.execute('SELECT payload FROM pm_fact_nodes WHERE id=?', (node['id'],)).fetchone()
            self.assertEqual(json.loads(row[0]), node)
        rows = self.q.db.execute('SELECT payload FROM pm_fact_edges ORDER BY ordinal')
        self.assertEqual([json.loads(r[0]) for r in rows], self.graph['edges'])
        with self.assertRaises(sqlite3.OperationalError):
            self.q.db.execute('DELETE FROM pm_fact_nodes')

    def test_keyset_pages_and_query_snapshot_binding(self):
        first = self.q.search(limit=1)
        cursor, ids = first['next_cursor'], [first['items'][0]['id']]
        while cursor:
            page = self.q.search(limit=1, cursor=cursor)
            ids += [n['id'] for n in page['items']]
            cursor = page['next_cursor']
        self.assertEqual(ids, [n['id'] for n in self.graph['nodes']])
        with self.assertRaises(ValueError): self.q.search('changed', cursor=first['next_cursor'])
        self.q.info['snapshot'] = 'other'
        with self.assertRaises(ValueError): self.q.search(cursor=first['next_cursor'])

    def test_all_structural_modules_and_unexpanded_language(self):
        self.assertEqual(len(self.q.overview()['items']), 3)
        self.assertEqual(self.q.files('tools')['items'][0]['reason'], 'unsupported_language')
        groups = self.q.links()['items']
        self.assertTrue(any(g['source'] == 'ui' and g['target'] == 'server' for g in groups))
        self.assertEqual(self.q.search(kind='storage_member')['items'][0]['id'], 'resource')

    def test_any_entry_status_and_unknown_retained(self):
        rows = self.q.entries()['items']
        self.assertEqual(rows[1]['status'], 'unknown_callable')
        self.assertIsNone(rows[1]['node'])
        r = self.q.status('fetch')
        self.assertEqual(r['file']['graph_coverage']['status'], 'parsed')
        self.assertEqual(r['runtime_execution'], 'unknown_unless_linked_run')
        self.assertEqual(self.q.diagnostics('server/a.cpp')['items'][0]['kind'], 'missing_compile_context')

    def test_forward_reverse_witness_cycle_and_kinds(self):
        r = self.q.walk('fetch', target='handle', depth=4)
        self.assertTrue(r['found'])
        self.assertEqual([e['kind'] for e in r['items']], ['EMITS_MESSAGE', 'RESOLVES_HANDLER'])
        self.assertTrue(self.q.walk('handler', target='api', direction='in')['found'])
        self.assertFalse(self.q.walk('api', target='handler', kinds=['READS'])['found'])
        self.assertLessEqual(self.q.walk('api', depth=16)['visited_nodes'], 4)

    def test_node_edge_and_depth_stops_are_separate(self):
        self.q.budget = Budget(nodes=1)
        self.assertEqual(self.q.walk('api')['stop_reason'], 'node_budget')
        self.q.budget = Budget(edges=1)
        self.assertEqual(self.q.walk('api')['stop_reason'], 'edge_budget')
        self.q.budget = Budget()
        self.assertTrue(self.q.walk('api', depth=0)['depth_scope_reached'])
        self.assertEqual(self.q.walk('api', depth=0)['missing_relation_meaning'], 'unknown')

    def test_wall_budget_does_not_become_no_results(self):
        self.q.budget = Budget(seconds=0.000000001)
        r = self.q.search()
        self.assertEqual(r['stop_reason'], 'wall_time_budget')
        self.assertFalse(r['page_complete'])

    def test_neighbor_paging_and_full_condition_evidence_navigation(self):
        r = self.q.neighbors('handler', limit=1)
        self.assertEqual(r['items'][0]['evidence_count'], 1)
        self.assertEqual(r['items'][0]['condition_count'], 1)
        second = self.q.neighbors('handler', limit=1, cursor=r['next_cursor'])
        self.assertNotEqual(r['items'][0]['edge_id'], second['items'][0]['edge_id'])
        details = self.q.detail('edge', 1, '/conditions')
        self.assertEqual(details['items'][0]['value'], 'service_selected')
        self.assertEqual(self.q.detail('edge', 1, '/evidence')['items'][0]['value']['line'], 2)
        self.assertEqual(self.q.detail('node', 'message', '/resolution')['items'][0]['pointer'], '/resolution')

    def test_output_limits_and_large_nested_values_can_be_expanded(self):
        self.q.close()
        self.graph['nodes'][0]['nested'] = [{'text': 'z' * 6000}, {'done': True}]
        build_index(self.graph, self.discovery, self.path)
        self.q = ProjectMap(self.path, budget=Budget(output_bytes=4096))
        r = self.q.detail('node', 'api')
        self.assertLessEqual(len(encoded(r).encode()), 4096)
        self.assertTrue(next(x for x in r['items'] if x['key'] == 'nested')['value_truncated'])
        r = self.q.detail('node', 'api', '/nested/1/done')
        self.assertIs(r['items'][0]['value'], True)

    def test_failed_rebuild_keeps_previous_index(self):
        self.q.close()
        self.graph['edges'][0]['target'] = 'missing'
        with self.assertRaises(ValueError): build_index(self.graph, self.discovery, self.path)
        self.q = ProjectMap(self.path)
        self.assertTrue(self.q.walk('api', target='handler')['found'])
        self.assertFalse(list(self.root.glob('*.building')))

    def test_wrong_source_or_snapshot_is_rejected(self):
        self.discovery['source_commit'] = 'other'
        with self.assertRaises(ValueError): build_index(self.graph, self.discovery, self.root / 'other.sqlite')
        with self.assertRaises(ValueError): ProjectMap(self.path, expected_snapshot='other')
        with self.assertRaises(ValueError): self.q.source(self.root, path='../secret', line=1)

    def test_source_reads_pinned_commit_even_with_dirty_worktree(self):
        source = self.root / 'repo'
        source.mkdir()
        def git(*args):
            return subprocess.check_output(['git', '-C', str(source), *args], stderr=subprocess.PIPE).decode().strip()
        git('init')
        git('config', 'user.name', 'Test')
        git('config', 'user.email', 'test@example.invalid')
        (source / 'ui').mkdir()
        (source / 'ui/a.ts').write_text('first\nPINNED\nthird\n', encoding='utf-8')
        git('add', '.')
        git('commit', '-m', 'fixture')
        self.q.info['source_commit'] = git('rev-parse', 'HEAD')
        (source / 'ui/a.ts').write_text('WORKTREE SECRET', encoding='utf-8')
        r = self.q.source(source, selector='api', context=0)
        self.assertEqual(r['items'], [{'line': 2, 'text': 'PINNED'}])
        self.assertFalse(r['working_tree_read'])


if __name__ == '__main__': unittest.main()
