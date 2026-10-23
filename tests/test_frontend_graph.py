import sqlite3
import unittest

from adapters.frontend_graph import augment_frontend
from adapters.frontend_queries import explain_frontend
from adapters import sqlite_fact_graph as store
from tests.test_sqlite_fact_graph import read_graph


class FrontendGraphTests(unittest.TestCase):
    def graph(self):
        evidence = [{'path': 'a.ts', 'line': 2, 'expression': 'state.rows = r.rows'}]
        nodes = [{'id': uid, 'kind': 'callable', 'name': uid, 'path': 'a.ts', 'line': 1}
                 for uid in ['api1', 'api2', 'entry1', 'entry2']]
        base = {'snapshot': 'v:p3-data-v5', 'source_commit': 'v', 'nodes': nodes,
                'edges': [], 'provenance': {}, 'extractors': {}, 'diagnostics': []}
        calls, reads, writes = [], [], []
        for i in [1, 2]:
            api, entry, context = f'api{i}', f'entry{i}', f'request{i}'
            call = {'api': api, 'entry': entry, 'api_call': f'call{i}', 'request_context': context, 'evidence': evidence}
            dep = {k: call[k] for k in ['api', 'api_call', 'request_context', 'evidence']}
            dep.update(path=['rows'], conditions=[], gaps=[])
            calls.append(call)
            writes.append({'id': 'same-source-site', 'entry': entry, 'source_symbol': entry,
                           'target': {'root': 'state', 'path': ['view']}, 'operation': '=',
                           'value_dependencies': [dep], 'continuation_apis': [context],
                           'conditions': [], 'call_chain': [], 'evidence': evidence})
            writes.append({**writes[-1], 'id': 'refresh', 'target': {'root': 'state', 'path': ['refresh']},
                           'value_dependencies': []})
        flow = {'version': '0.1.0', 'api_calls': calls, 'field_reads': reads, 'state_writes': writes,
                'entries': [], 'diagnostics': [], 'limits': ['pending_transport_join']}
        return augment_frontend(base, {'nodes': nodes, 'data_flow': flow})

    def test_api_and_state_identity_are_scoped(self):
        g = self.graph()
        result = explain_frontend(g, api='api1')
        self.assertEqual(len(result['writes']), 2)
        self.assertEqual({w['entry'] for w in result['writes']}, {'entry1'})
        state = result['writes'][0]['state_node']
        reverse = explain_frontend(g, state=state)
        self.assertEqual(len(reverse['writes']), 1)
        self.assertEqual([c['api'] for c in reverse['api_calls']], ['api1'])
        self.assertEqual(reverse['writes'][0]['matching_dependencies'][0]['api'], 'api1')
        self.assertFalse(explain_frontend(g, api='api2', state=state)['writes'])

    def test_field_query_excludes_continuation_only_updates(self):
        g = self.graph()
        result = explain_frontend(g, api='api1', field_path=['rows', '*', 'name'])
        self.assertEqual(len(result['writes']), 1)
        self.assertEqual(result['writes'][0]['relationship'], 'value_dependency_candidate')
        self.assertFalse(explain_frontend(g, api='api1', field_path=['other'])['writes'])
        self.assertTrue(explain_frontend(g, api='api1', max_writes=0)['truncated'])
        with self.assertRaises(ValueError): explain_frontend(g, max_writes=-1)

    def test_persisted_graph_retains_queries_and_distinct_relation_kinds(self):
        g = self.graph()
        store._prepare(g)
        with sqlite3.connect(':memory:') as conn:
            store.replace_snapshot(conn, g)
            saved = read_graph(conn, g['snapshot'])
        self.assertEqual(saved, g)
        self.assertEqual(explain_frontend(saved, api='api1'), explain_frontend(g, api='api1'))
        kinds = {e['kind'] for e in g['edges']}
        self.assertIn('VALUE_MAY_REACH_STATE_WRITE', kinds)
        self.assertIn('FULFILLMENT_PRECEDES_STATE_WRITE', kinds)
        self.assertEqual(explain_frontend(saved)['transport_status'], 'pending_transport_join')

    def test_inconsistent_request_reference_is_rejected(self):
        g = self.graph()
        flow = g['frontend']
        flow['state_writes'][0]['value_dependencies'][0]['api'] = 'api2'
        with self.assertRaises(ValueError): augment_frontend(g, {'nodes': [], 'data_flow': flow})


if __name__ == '__main__': unittest.main()
