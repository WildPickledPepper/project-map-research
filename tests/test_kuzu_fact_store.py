"""Exercise snapshot isolation, failure recovery and native graph preservation."""
import copy
import os
from pathlib import Path
import tempfile
import unittest

_dll = os.add_dll_directory(os.environ['PROJECT_MAP_DLL_DIR']) if os.name == 'nt' and os.environ.get('PROJECT_MAP_DLL_DIR') else None
import kuzu

from adapters.kuzu_fact_store import delete_snapshot, prepare, replace_snapshot, rows


def fixture(commit='a'*40):
    return {'source_commit':commit,'manifest_sha256':'b'*64,'extractor_version':'0.1.0',
            'records':[{'path':"src/quote's.ts",'sha256_lf_utf8':'c'*64,'evidence_kind':'source_syntax',
                        'symbols':[{'id':'method','line':1,'qualified_name':'Client.fetch'}],
                        'calls':[{'id':'call','line':2,'owner_id':'method','resolution':'unresolved',
                                  'callee_spelling':"service.get('item')"}],
                        'bindings':[]}]}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = kuzu.Database(str(self.root/'graph.kuzu'),buffer_pool_size=64*1024*1024)
        self.conn = kuzu.Connection(self.db)
        self.conn.execute('CREATE NODE TABLE Function(uid STRING,path STRING,line_number INT64,PRIMARY KEY(uid))')
        self.conn.execute('CREATE (:Function {uid:$id,path:$path,line_number:1})',
                          {'id':'native','path':(self.root/"src/quote's.ts").as_posix()})

    def tearDown(self):
        self.conn.close()
        self.db.close()
        self.temp.cleanup()

    def count(self,label):
        return rows(self.conn.execute(f'MATCH (n:{label}) RETURN count(n) AS n'))[0]['n']

    def test_roundtrip_keeps_evidence_direction_and_quotes(self):
        report = replace_snapshot(self.conn,fixture(),self.root)
        self.assertEqual(report['native_refinements'],1)
        result = rows(self.conn.execute('MATCH (a:PMFact)-[r:PMSyntaxEdge]->(b:PMFact) RETURN a.qualified_name AS owner,r.kind AS kind,b.payload AS payload'))
        self.assertEqual(result[0]['owner'],'Client.fetch')
        self.assertEqual(result[0]['kind'],'OBSERVES_CALL')
        self.assertIn("service.get('item')",result[0]['payload'])
        self.assertIn('unresolved',result[0]['payload'])

    def test_replace_removes_old_facts_and_is_idempotent(self):
        facts = fixture()
        first = replace_snapshot(self.conn,facts,self.root)
        again = replace_snapshot(self.conn,facts,self.root)
        self.assertEqual(first,again)
        self.assertEqual(self.count('PMFact'),2)
        facts['records'][0]['calls'] = []
        replace_snapshot(self.conn,facts,self.root)
        self.assertEqual(self.count('PMFact'),1)
        self.assertEqual(rows(self.conn.execute('MATCH ()-[r:PMSyntaxEdge]->() RETURN count(r) AS n'))[0]['n'],0)

    def test_delete_keeps_other_snapshot_and_native_graph(self):
        first = replace_snapshot(self.conn,fixture(),self.root)
        second = replace_snapshot(self.conn,fixture('d'*40),self.root)
        delete_snapshot(self.conn,first['snapshot'])
        self.assertEqual(self.count('PMFact'),2)
        self.assertEqual(self.count('Function'),1)
        result = rows(self.conn.execute('MATCH (:Function)-[r:PMRefines]->() RETURN r.snapshot AS snapshot'))
        self.assertEqual(result,[{'snapshot':second['snapshot']}])

    def test_failure_after_delete_rolls_back_previous_snapshot(self):
        facts = fixture()
        replace_snapshot(self.conn,facts,self.root)
        real = self.conn
        class FailOnInsert:
            def execute(self,query,*args):
                if query.startswith('UNWIND $items AS item CREATE'):
                    raise RuntimeError('injected write failure')
                return real.execute(query,*args)
        with self.assertRaisesRegex(RuntimeError,'injected'):
            replace_snapshot(FailOnInsert(),facts,self.root)
        self.assertEqual(self.count('PMFact'),2)
        self.assertEqual(rows(self.conn.execute('MATCH ()-[r:PMRefines]->() RETURN count(r) AS n'))[0]['n'],1)

    def test_bad_inputs_leave_saved_snapshot_unchanged(self):
        original = fixture()
        replace_snapshot(self.conn,original,self.root)
        invalid = []
        duplicate = copy.deepcopy(original)
        duplicate['records'][0]['calls'][0]['id'] = 'method'
        invalid.append(duplicate)
        absent = copy.deepcopy(original)
        absent['records'][0]['calls'][0]['owner_id'] = 'absent'
        invalid.append(absent)
        resolved = copy.deepcopy(original)
        resolved['records'][0]['calls'][0]['resolution'] = 'resolved'
        invalid.append(resolved)
        for facts in invalid:
            with self.subTest(facts=facts), self.assertRaises(ValueError):
                replace_snapshot(self.conn,facts,self.root)
            self.assertEqual(self.count('PMFact'),2)

    def test_same_line_ambiguity_is_reported_without_merge(self):
        facts = fixture()
        facts['records'][0]['symbols'].append({'id':'other','line':1,'qualified_name':'Client.fetch.callback'})
        report = replace_snapshot(self.conn,facts,self.root)
        self.assertEqual(report['native_refinements'],0)
        self.assertEqual(report['ambiguous_native_refinements'][0]['supplement_count'],2)

    def test_snapshot_identity_includes_extractor_and_manifest(self):
        facts = fixture()
        base = prepare(facts)[0]
        facts['extractor_version'] = '0.2.0'
        self.assertNotEqual(prepare(facts)[0],base)
        facts = fixture()
        facts['manifest_sha256'] = 'e'*64
        self.assertNotEqual(prepare(facts)[0],base)


if __name__ == '__main__':
    unittest.main()
