"""Verify streamed and in-memory graph validation/indexing retain identical facts."""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from adapters.graph_document import GraphDocument
from adapters.sqlite_fact_graph import validate_graph
from adapters.project_map import build_index


class GraphDocumentTests(unittest.TestCase):
    def graph(self):
        return {'snapshot':'s','source_commit':'c'*40,'input_paths':['src/a.rs'],
            'nodes':[{'id':'one','kind':'value','name':'one','path':'src/a.rs','line':1,
                      'numbers':[2**100,.25,{'float':.5}]}],
            'edges':[{'source':'one','target':'one','kind':'COPY','status':'candidate','evidence':[]}],
            'coverage':[{'path':'src/a.rs','status':'parsed'}],'diagnostics':[]}

    def test_lossless_numbers_metadata_and_public_index(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);raw=self.graph();path=root/'graph.json';path.write_text(json.dumps(raw))
            streamed=GraphDocument(path);validate_graph(streamed)
            self.assertEqual(list(streamed['nodes']),raw['nodes'])
            self.assertEqual(len(streamed['edges']),1)
            discovery={'source_commit':'c'*40,'files':[{'path':'src/a.rs','module':'src','eligible':True,'status':'pending'}],
                       'modules':[{'path':'src'}]}
            for name,graph in [('ordinary',raw),('streamed',streamed)]:
                build_index(graph,discovery,root/(name+'.sqlite'))
            with closing(sqlite3.connect(root/'ordinary.sqlite')) as a,closing(sqlite3.connect(root/'streamed.sqlite')) as b:
                for table in ('pm_fact_nodes','pm_fact_edges','pm_map_files','pm_map_modules'):
                    self.assertEqual(a.execute('SELECT * FROM '+table).fetchall(),b.execute('SELECT * FROM '+table).fetchall())

    def test_invalid_endpoints_and_duplicate_ids_still_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'graph.json'
            raw=self.graph();raw['edges'][0]['target']='missing';path.write_text(json.dumps(raw))
            with self.assertRaisesRegex(ValueError,'endpoints'):validate_graph(GraphDocument(path))
            raw=self.graph();raw['nodes']*=2;path.write_text(json.dumps(raw))
            with self.assertRaisesRegex(ValueError,'duplicate node'):validate_graph(GraphDocument(path))

    def test_changed_document_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'graph.json';path.write_text(json.dumps(self.graph()))
            graph=GraphDocument(path);path.write_text('{}')
            with self.assertRaisesRegex(ValueError,'changed'):list(graph['nodes'])


if __name__=='__main__':unittest.main()
