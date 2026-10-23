import sqlite3
import unittest

from adapters.cpp_data import DataExtractor
from adapters.cpp_transmission import Transmission
from adapters.transmission_graph import augment_transmission
from adapters.transmission_queries import explain_transmission
from adapters.sqlite_fact_graph import replace_snapshot, _prepare
from tests.test_sqlite_fact_graph import read_graph
import tests.test_cpp_data as data_tests


class TransmissionGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): data_tests.CppDataTests.setUpClass(); cls.parser = data_tests.CppDataTests.parser

    def graph(self):
        code = 'using J=rapidjson::Document;void emit(const J& j,uWS::WebSocket<false,true,int>* s){rapidjson::StringBuffer b;rapidjson::Writer<rapidjson::StringBuffer> w(b);j.Accept(w);s->send(b.GetString());s->send(b.GetString());}'
        d = DataExtractor({'a.cpp': code.encode()}, self.parser)
        base = {'source_commit': 'source', 'snapshot': 'source:base', 'nodes': [], 'edges': [],
                'input_paths': ['a.cpp'], 'extractors': {}, 'provenance': {}, 'diagnostics': []}
        return augment_transmission(base, d.facts, Transmission(d).build(), ['a.cpp'])

    def test_query_and_roundtrip_preserve_conditional_lineage(self):
        g = self.graph(); _prepare(g)
        q = explain_transmission(g); self.assertEqual(q['total_links'], 2)
        self.assertTrue(all(t['runtime_delivery'] == 'unknown' for t in q['links']))
        with sqlite3.connect(':memory:') as conn:
            replace_snapshot(conn, g); saved = read_graph(conn, g['snapshot'])
        self.assertEqual(saved, g); self.assertEqual(explain_transmission(saved), q)
        self.assertEqual(sum(e['kind'] == 'JSON_VALUE_REACHES_SEND' for e in g['edges']), 2)

    def test_entry_filter_budget_and_zero_links_are_explicit(self):
        g = self.graph(); self.assertFalse(explain_transmission(g, entry='unknown')['links'])
        q = explain_transmission(g, max_links=1); self.assertTrue(q['truncated']); self.assertEqual(len(q['links']), 1)
        with self.assertRaises(ValueError): explain_transmission(g, max_links=0)

    def test_reapplying_extension_is_rejected(self):
        with self.assertRaises(ValueError): augment_transmission(self.graph(), {'nodes': []}, {}, ['a.cpp'])


if __name__ == '__main__': unittest.main()
