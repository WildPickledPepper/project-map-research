"""Authored interchange cases for request/channel/event-parameter isolation."""
from copy import deepcopy
import sqlite3
import unittest

from adapters.socket_graph import augment_sockets
from adapters.socket_queries import explain_socket_receivers
from adapters.sqlite_fact_graph import _prepare, replace_snapshot
from tests.test_sqlite_fact_graph import read_graph


class SocketGraphTests(unittest.TestCase):
    def inputs(self):
        ev = [{'path': 'a.ts', 'line': 1, 'expression': 'source fixture'}]
        channel = {'kind': 'input_path', 'root': 'wire', 'path': [], 'receiver_type': 'Owner'}
        common = {'entry': 'request', 'evidence': ev, 'conditions': []}
        old_send = {**common, 'id': 'old-send', 'source_site': 'send-site', 'transport': 'WebSocket.send',
                    'promise_context': 'promise', 'receiver': channel,
                    'payload': {'kind': 'json_string', 'value': {'kind': 'object', 'fields': {'number': {'kind': 'constant', 'value': 1}}}}}
        reg = {**common, 'id': 'register', 'registry': 'callbacks', 'receiver_type': 'Owner', 'promises': ['promise'], 'key': {'kind': 'constant', 'value': 1}}
        lookup = {**common, 'id': 'lookup', 'entry': 'receive', 'registry': 'callbacks', 'receiver_type': 'Owner',
                  'key': {'kind': 'input_path', 'root': 'event', 'path': ['data', 'number'], 'transforms': [{'kind': 'JSON.parse', 'at_path': ['data']}]}}
        settlement = {**common, 'id': 'settle', 'entry': 'receive', 'promise': 'promise', 'mode': 'resolve',
                      'registry_context': {'registration': 'register', 'lookup': 'lookup', 'selectors': []}, 'value': {'kind': 'constant', 'value': 7}}
        callbacks = {'entries': [], 'transmissions': [old_send], 'registrations': [reg], 'lookups': [lookup], 'settlements': [settlement], 'diagnostics': []}
        sockets = {'version': '0.1.0', 'entries': [], 'diagnostics': [], 'limits': ['same_runtime_instance_required'],
                   'creations': [{**common, 'id': 'creation', 'transport': 'WebSocket'}],
                   'channel_bindings': [{**common, 'id': 'assignment', 'channel': channel, 'value': {'kind': 'native_socket', 'allocation': 'creation'}}],
                   'listener_bindings': [{**common, 'id': 'listener', 'channel': deepcopy(channel), 'action': 'install', 'callback': 'receive',
                       'event_parameter': 'event', 'this_binding': 'lexical', 'callback_receiver_type': 'Owner', 'superseded_by': []}],
                   'transmissions': [{**old_send, 'id': 'socket-send'}]}
        nodes = [{'id': n, 'kind': 'callable', 'name': n, 'path': 'a.ts', 'line': 1} for n in ['request', 'receive', 'lookup', 'old-send']]
        base = {'snapshot': 'source:base', 'source_commit': 'source', 'nodes': nodes, 'edges': [], 'response_callbacks': callbacks,
                'extractors': {}, 'provenance': {}, 'diagnostics': [], 'input_paths': ['a.ts']}
        return base, {'nodes': nodes, 'socket_flow': sockets}

    def test_positive_query_and_persistence(self):
        graph = augment_sockets(*self.inputs()); _prepare(graph)
        q = explain_socket_receivers(graph); self.assertEqual(q['total_receivers'], 1)
        r, = q['receivers']; self.assertEqual(len(r['native_creations']), 1); self.assertEqual(len(r['deliveries']), 1)
        with sqlite3.connect(':memory:') as conn:
            replace_snapshot(conn, graph); saved = read_graph(conn, graph['snapshot'])
        self.assertEqual(saved, graph); self.assertEqual(explain_socket_receivers(saved), q)
        self.assertTrue(any(e['kind'] == 'EVENT_PARAMETER_FEEDS_LOOKUP' for e in saved['edges']))

    def test_wrong_channel_receiver_or_event_parameter_disconnects(self):
        for name, new in [('channel', {'kind': 'input_path', 'root': 'other-wire', 'path': []}),
                          ('callback_receiver_type', 'Other'), ('event_parameter', 'another-event'), ('this_binding', 'event_target')]:
            base, facts = self.inputs(); facts['socket_flow']['listener_bindings'][0][name] = new
            self.assertFalse(explain_socket_receivers(augment_sockets(base, facts))['receivers'])

    def test_clear_supersession_and_missing_binding_disconnect(self):
        for mutation in ['clear', 'superseded', 'missing']:
            base, facts = self.inputs(); flow = facts['socket_flow']
            if mutation == 'clear': flow['listener_bindings'][0]['action'] = 'clear'
            elif mutation == 'superseded': flow['listener_bindings'][0]['superseded_by'] = ['later']
            else: flow['listener_bindings'] = []
            self.assertFalse(explain_socket_receivers(augment_sockets(base, facts))['receivers'])

    def test_incompatible_conditions_and_receiver_mutation_stay_unmatched(self):
        base, facts = self.inputs(); c = {'path': 'a.ts', 'line': 2, 'expression': 'flag', 'when': True}
        facts['socket_flow']['transmissions'][0]['conditions'] = [c]
        facts['socket_flow']['listener_bindings'][0]['conditions'] = [{**c, 'when': False}]
        self.assertFalse(explain_socket_receivers(augment_sockets(base, facts))['receivers'])
        base, facts = self.inputs(); facts['socket_flow']['listener_bindings'][0]['channel']['gaps'] = [{'kind': 'opaque_mutation'}]
        self.assertFalse(explain_socket_receivers(augment_sockets(base, facts))['receivers'])

    def test_filters_repeated_augmentation_and_callback_truncation(self):
        base, facts = self.inputs(); base['response_callbacks']['entries'] = [{'source_symbol': 'receive', 'truncated': True}]
        graph = augment_sockets(base, facts)
        self.assertTrue(explain_socket_receivers(graph)['truncated'])
        self.assertFalse(explain_socket_receivers(graph, requester='other')['receivers'])
        with self.assertRaises(ValueError): explain_socket_receivers(graph, max_links=0)
        with self.assertRaises(ValueError): augment_sockets(graph, facts)


if __name__ == '__main__': unittest.main()
