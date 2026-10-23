import copy
import os
from pathlib import Path
import tempfile
import unittest

DLL_HANDLE=os.add_dll_directory(os.environ['PROJECT_MAP_DLL_DIR']) if os.name=='nt' and os.environ.get('PROJECT_MAP_DLL_DIR') else None
import kuzu
from adapters.kuzu_fact_graph import replace_snapshot,delete_snapshot,read_snapshot,rows


def fixture(snapshot='v1'):
    return {'snapshot':snapshot,'metadata':{'中文':'条件'},'nodes':[
        {'id':i,'kind':'callable','path':'a.cpp','line':1,'name':i} for i in ('a','b')],
        'edges':[{'source':'a','target':'b','kind':'CANDIDATE','status':'candidate',
                  'condition':x,'evidence':[{'path':'a.cpp','line':1}]} for x in ('db','text')]}


class KuzuGraphTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=kuzu.Database(str(Path(self.tmp.name)/'graph'),buffer_pool_size=64*1024*1024)
        self.conn=kuzu.Connection(self.db)
        self.conn.execute('CREATE NODE TABLE Native(id STRING, PRIMARY KEY(id))')
        self.conn.execute("CREATE (:Native {id:'original'})")

    def tearDown(self):
        self.conn.close();self.db.close();self.tmp.cleanup()

    def test_full_roundtrip_parallel_edges_and_reverse_query(self):
        g=fixture();replace_snapshot(self.conn,g)
        self.assertEqual(read_snapshot(self.conn,'v1'),g)
        r=rows(self.conn.execute("MATCH (a:PMGraphNode)-[e:PMGraphEdge]->(b:PMGraphNode) WHERE b.id='b' AND b.snapshot='v1' RETURN a.id AS id,e.payload AS payload"))
        self.assertEqual(len(r),2);self.assertEqual({x['id'] for x in r},{'a'})

    def test_replace_delete_preserves_other_snapshot_and_native(self):
        replace_snapshot(self.conn,fixture());replace_snapshot(self.conn,fixture('v2'))
        short=fixture();short['edges']=[]
        replace_snapshot(self.conn,short)
        self.assertEqual(read_snapshot(self.conn,'v1'),short)
        delete_snapshot(self.conn,'v1')
        self.assertIsNone(read_snapshot(self.conn,'v1'))
        self.assertEqual(read_snapshot(self.conn,'v2'),fixture('v2'))
        self.assertEqual(rows(self.conn.execute('MATCH (n:Native) RETURN n.id AS id')),[{'id':'original'}])

    def test_invalid_endpoints_and_duplicate_ids_leave_snapshot(self):
        replace_snapshot(self.conn,fixture())
        for mode in ('missing','duplicate'):
            bad=fixture()
            if mode=='missing':bad['edges'][0]['target']='absent'
            else:bad['nodes'].append(copy.deepcopy(bad['nodes'][0]))
            with self.assertRaises(ValueError):replace_snapshot(self.conn,bad)
        self.assertEqual(read_snapshot(self.conn,'v1'),fixture())

    def test_mid_write_error_rolls_back_deleted_snapshot(self):
        replace_snapshot(self.conn,fixture())
        class FailOnInsert:
            def execute(inner,query,*args):
                if query.startswith('UNWIND'):raise RuntimeError('injected failure')
                return self.conn.execute(query,*args)
        with self.assertRaisesRegex(RuntimeError,'injected'):replace_snapshot(FailOnInsert(),fixture())
        self.assertEqual(read_snapshot(self.conn,'v1'),fixture())

    def test_commit_error_is_preserved_when_engine_already_aborted(self):
        replace_snapshot(self.conn,fixture())
        class AbortAtCommit:
            def execute(inner,query,*args):
                if query=='COMMIT':
                    self.conn.execute('ROLLBACK')
                    raise RuntimeError('injected commit allocation failure')
                return self.conn.execute(query,*args)
        for operation in [lambda:replace_snapshot(AbortAtCommit(),fixture()),
                          lambda:delete_snapshot(AbortAtCommit(),'v1')]:
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(RuntimeError,'commit allocation') as raised:operation()
                self.assertIn('Rollback also failed',raised.exception.__notes__[0])
                self.assertEqual(read_snapshot(self.conn,'v1'),fixture())


if __name__=='__main__':unittest.main()
