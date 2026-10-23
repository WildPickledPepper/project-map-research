"""Authored interchange fixtures for callback storage and query isolation."""
import copy
import sqlite3
import unittest

from adapters.callback_graph import augment_callbacks
from adapters.callback_queries import explain_callbacks, projections
from adapters.sqlite_fact_graph import _prepare, replace_snapshot
from tests.test_sqlite_fact_graph import read_graph


class CallbackGraphTests(unittest.TestCase):
    def inputs(self):
        evidence = [{'path': 'a.ts', 'line': 1, 'expression': 'callback(message)'}]
        nodes = [{'id': n, 'kind': 'callable', 'name': n, 'path': 'a.ts', 'line': 1}
                 for n in ['send1', 'send2', 'receive1', 'receive2']]
        data = {k: [] for k in ['promises', 'registrations', 'lookups', 'settlements', 'deletions', 'entries', 'diagnostics']}
        data.update(version='0.1.0', limits=['equal_key_and_same_instance_required'])
        for i in [1, 2]:
            common = {'registry': f'map{i}', 'receiver_type': f'class{i}', 'conditions': [], 'evidence': evidence}
            data['promises'].append({'id': f'promise{i}', 'entry': f'send{i}', 'evidence': evidence})
            data['registrations'].append({**common, 'id': f'reg{i}', 'entry': f'send{i}', 'promises': [f'promise{i}']})
            data['lookups'].append({**common, 'id': f'lookup{i}', 'entry': f'receive{i}'})
            data['settlements'].append({'id': 'same-source-site', 'promise': f'promise{i}', 'entry': f'receive{i}',
                'mode': 'resolve', 'conditions': [{'kind': 'registered_value_selected'}], 'evidence': evidence,
                'registry_context': {'registration': f'reg{i}', 'lookup': f'lookup{i}', 'selectors': []},
                'value': {'kind': 'input_path', 'root': f'input{i}', 'path': ['data', 'body'],
                          'transforms': [{'kind': 'JSON.parse', 'at_path': ['data']}], 'evidence': evidence}})
        base = {'snapshot': 'source:p3-data-v6', 'source_commit': 'source', 'nodes': nodes, 'edges': [],
                'provenance': {}, 'extractors': {}, 'diagnostics': []}
        return base, {'nodes': nodes, 'response_flow': data}

    def test_requester_receiver_filters_and_decoded_projection(self):
        g = augment_callbacks(*self.inputs()); _prepare(g)
        q = explain_callbacks(g, requester='send1')
        self.assertEqual(q['total_deliveries'], 1)
        self.assertEqual(q['deliveries'][0]['projections'][0]['decoded_json_path'], ['body'])
        self.assertFalse(explain_callbacks(g, requester='send1', receiver='receive2')['deliveries'])
        self.assertEqual(explain_callbacks(g, receiver='receive1')['total_deliveries'], 1)
        self.assertTrue(explain_callbacks(g, max_deliveries=0)['truncated'])
        with self.assertRaises(ValueError): explain_callbacks(g, max_deliveries=-1)

    def test_cross_registry_and_cross_promise_joins_are_rejected(self):
        base, facts = self.inputs()
        bad = copy.deepcopy(facts); bad['response_flow']['settlements'][0]['registry_context']['lookup'] = 'lookup2'
        with self.assertRaises(ValueError): augment_callbacks(base, bad)
        bad = copy.deepcopy(facts); bad['response_flow']['settlements'][0]['promise'] = 'promise2'
        with self.assertRaises(ValueError): augment_callbacks(base, bad)

    def test_roundtrip_retains_callback_contexts(self):
        g = augment_callbacks(*self.inputs())
        with sqlite3.connect(':memory:') as conn:
            replace_snapshot(conn, g); saved = read_graph(conn, g['snapshot'])
        self.assertEqual(saved, g)
        self.assertEqual(explain_callbacks(saved), explain_callbacks(g))
        self.assertEqual(explain_callbacks(saved)['transport_status'], 'network_and_API_boundary_join_pending')

    def test_wrapped_errors_keep_output_field_and_undecoded_inputs(self):
        value = {'kind': 'object', 'fields': {'error': {'kind': 'input_path', 'root': 'event', 'path': ['data', 'error']}}}
        result = projections(value)
        self.assertEqual(result[0]['output_path'], ['error'])
        self.assertIsNone(result[0]['decoded_json_path'])


if __name__ == '__main__': unittest.main()
