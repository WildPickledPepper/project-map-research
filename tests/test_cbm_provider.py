"""Check provider identity/precision at the SQLite interoperability boundary."""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from adapters.cbm_provider import read_native
from adapters.sqlite_fact_graph import validate_graph


class CbmProviderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = Path(self.temporary.name) / 'native.db'
        with closing(sqlite3.connect(self.database)) as db, db:
            db.executescript('''CREATE TABLE nodes(id INTEGER PRIMARY KEY, project TEXT,
                label TEXT, name TEXT, qualified_name TEXT, file_path TEXT,
                start_line INTEGER, end_line INTEGER, properties TEXT);
                CREATE TABLE edges(id INTEGER PRIMARY KEY, project TEXT,
                source_id INTEGER, target_id INTEGER, type TEXT, properties TEXT);''')

    def node(self, identifier, *, project='fixture', path='worker.py', label='Function',
             name='same', qualified='scope.same'):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?,?)',
                       (identifier, project, label, name, qualified, path, 3, 5, '{}'))

    def edge(self, source, target, *, project='fixture', kind='CALLS'):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('INSERT INTO edges(project,source_id,target_id,type,properties) VALUES (?,?,?,?,?)',
                       (project, source, target, kind, json.dumps({'confidence': 1.0, 'line': 4})))

    def read(self, paths=('worker.py',)):
        return read_native(self.database, project='fixture', paths=paths,
                           source_commit='a' * 40, provider_version='0.12.1')

    def test_same_name_and_qualified_name_do_not_merge_native_instances(self):
        self.node(1); self.node(2)
        self.edge(1, 2)
        facts = self.read()
        self.assertEqual(len({n['id'] for n in facts['nodes']}), 2)
        self.assertNotEqual(facts['edges'][0]['source'], facts['edges'][0]['target'])

    def test_native_confidence_is_not_upgraded_to_precise_or_runtime_edge(self):
        self.node(1); self.node(2); self.edge(1, 2)
        facts = self.read()
        edge = facts['edges'][0]
        self.assertEqual(edge['status'], 'candidate')
        self.assertEqual(edge['native_properties']['confidence'], 1.0)
        self.assertEqual(edge['runtime_execution'], 'not_observed')
        self.assertEqual(edge['evidence'][0], {'path': 'worker.py', 'line': 4})
        validate_graph({'snapshot': 'fixture', **facts})

    def test_other_project_outside_input_and_dangling_edges_are_not_imported(self):
        self.node(1); self.node(2, project='other')
        self.node(3, path='vendor/worker.py')
        self.edge(1, 2); self.edge(1, 3); self.edge(1, 99)
        facts = self.read()
        self.assertEqual([n['native_id'] for n in facts['nodes']], [1])
        self.assertEqual(facts['edges'], [])
        self.assertEqual(len(facts['diagnostics']), 1)

    def test_source_less_resource_preserves_native_identity_without_invented_path(self):
        self.node(1)
        self.node(2, path='', label='Process', qualified='__process__worker')
        self.edge(1, 2, kind='SPAWNS')
        facts = self.read()
        self.assertEqual(facts['nodes'][1]['path'], '')
        self.assertEqual(facts['nodes'][1]['kind'], 'process')
        self.assertEqual(facts['edges'][0]['kind'], 'CBM_SPAWNS')

    def test_unsafe_selected_path_is_rejected_before_reading(self):
        with self.assertRaises(ValueError):
            self.read(paths=('../outside.py',))

    def test_native_partial_and_directory_exclusion_survive_module_presence(self):
        self.node(1, label='Module')
        with closing(sqlite3.connect(self.database)) as db, db:
            db.executescript('''CREATE TABLE index_coverage(project TEXT, rel_path TEXT,
                kind TEXT, detail TEXT);''')
            db.executemany('INSERT INTO index_coverage VALUES (?,?,?,?)', [
                ('fixture', 'worker.py', 'parse_partial', '3-3'),
                ('fixture', 'build', 'not_indexed_dir', 'excluded subtree')])
        facts = self.read(paths=('worker.py', 'build/launch.sh'))
        by_path = {r['path']: r for r in facts['coverage']}
        self.assertEqual(by_path['worker.py']['status'], 'provider_partial')
        self.assertEqual(by_path['build/launch.sh']['status'], 'provider_excluded')
        self.assertEqual(by_path['worker.py']['native_coverage'][0]['detail'], '3-3')


if __name__ == '__main__':
    unittest.main()
