"""Authored interchange fixtures test joins; real extraction is scored separately."""
import copy
import unittest
from unittest.mock import patch
from adapters.correlation_queries import request_key_bindings, explain_correlation


def source(root='counter'):
    return {'kind': 'input_path', 'root': root, 'path': [], 'transforms': [], 'conditions': [], 'gaps': []}


def fixture():
    evidence = [{'path': 'front.ts', 'line': 4}]
    reg = {'id': 'registration', 'entry': 'fetch', 'registry': 'map', 'receiver_type': 'Client',
           'promises': ['promise'], 'key': source(), 'conditions': [], 'evidence': evidence}
    send = {'id': 'sent', 'entry': 'fetch', 'promise_context': 'promise', 'transport': 'WebSocket.send',
            'payload': {'kind': 'json_string', 'value': {'kind': 'object', 'fields': {'ticket': source()}}},
            'conditions': [], 'evidence': evidence}
    lookup = {'id': 'lookup', 'entry': 'receive', 'registry': 'map', 'receiver_type': 'Client',
              'key': {**source('event'), 'path': ['data', 'replyToken'], 'transforms': [{'kind': 'JSON.parse', 'at_path': ['data']}]}}
    provider = {'id': 'provider', 'decoder_registration': {'functions': ['decode']}}
    message = {'id': 'message', 'path': 'front.ts', 'line': 4, 'flow_evidence': [
        {'kind': 'argument_transfer', 'target': {'path': 'front.ts', 'line': 1}},
        {'kind': 'platform_send', 'transport': 'WebSocket.send', 'path': 'front.ts', 'line': 4}]}
    effect = {'write': 'copy', 'root': 'response', 'selectors': ['member:reply'], 'operation': '=',
              'value_origins': [{'root': 'request', 'selectors': ['member:seq']}], 'offset': 10, 'call_chain': []}
    route = {'handler': 'handler', 'object_root': 'response', 'serializer': 'serializer', 'conditions': [],
             'production_links': [{'write': 'copy', 'wire_path': ['replyToken']}],
             'steps': [{'offset': 100, 'evidence': [{'path': 'server.cpp', 'line': 10}]}],
             'field_mappings': [{'wire_path': ['replyToken'], 'selectors': ['member:reply']}]}
    graph = {'snapshot': 'v8', 'nodes': [{'id': 'fetch', 'name': 'fetch', 'path': 'front.ts', 'line': 1}, message], 'edges': [],
        'protocol': {'providers': [provider], 'results': [{'message': 'message', 'matches': [{'provider': 'provider', 'conditions': []}]}]},
        'response_callbacks': {'registrations': [reg], 'transmissions': [send], 'lookups': [lookup],
            'settlements': [{'registry_context': {'registration': 'registration', 'lookup': 'lookup'}}]},
        'data': {'field_flow': {'roots': [{'id': 'request', 'kind': 'parameter', 'source_symbol': 'handler', 'mode': 'reference', 'type': {'names': ['Request']}}]},
            'summaries': [], 'response_routing': {'decoded_fields': [{'source_symbol': 'decode', 'owner_types': ['Request'], 'member': 'seq', 'wire_fields': ['ticket']}]}}}
    return graph, {'routes': [route], 'truncated': False}, {'effects': [effect], 'truncated': False}


class CorrelationTests(unittest.TestCase):
    def query(self, graph, response, effects, **options):
        with patch('adapters.correlation_queries.explain_response', return_value=response), patch('adapters.correlation_queries.explain_writes', return_value=effects):
            return explain_correlation(graph, 'provider', **options)

    def test_copy_connects_different_wire_names_by_source_origins(self):
        g, r, e = fixture(); q = self.query(g, r, e)
        self.assertEqual(q['total_links'], 1)
        self.assertEqual(q['links'][0]['request_key_binding']['wire_path'], ['ticket'])
        self.assertEqual(q['links'][0]['response_wire_path'], ['replyToken'])
        self.assertTrue(self.query(g, r, e, max_links=0)['truncated'])

    def test_other_request_invocation_and_unknown_mutation_do_not_match(self):
        g, _, _ = fixture(); f = g['response_callbacks']
        f['transmissions'][0]['promise_context'] = 'other'
        self.assertFalse(request_key_bindings(f))
        f['transmissions'][0]['promise_context'] = 'promise'; f['registrations'][0]['key']['gaps'] = [{'kind': 'unknown_mutation'}]
        self.assertFalse(request_key_bindings(f))

    def test_incompatible_branch_conditions_do_not_prove_a_shared_value(self):
        g, _, _ = fixture(); f = g['response_callbacks']; condition = {'path': 'a.ts', 'line': 1, 'expression': 'enabled', 'when': True}
        f['registrations'][0]['conditions'] = [condition]
        f['transmissions'][0]['conditions'] = [{**condition, 'when': False}]
        self.assertFalse(request_key_bindings(f))

    def test_known_later_write_blocks_stale_response_copy(self):
        g, r, e = fixture()
        e['effects'].append({**e['effects'][0], 'write': 'overwrite', 'offset': 20, 'value_origins': []})
        q = self.query(g, r, e); self.assertFalse(q['links'])
        self.assertEqual(q['gaps'][0]['kind'], 'later_field_write_blocks_key_copy')

    def test_shared_send_site_requires_provider_and_requester_path(self):
        g, r, e = fixture(); g['nodes'][1]['flow_evidence'][0]['target']['line'] = 77
        self.assertFalse(self.query(g, r, e)['links'])
        g, r, e = fixture(); g['protocol']['results'][0]['matches'][0]['provider'] = 'unrelated'
        self.assertFalse(self.query(g, r, e)['links'])

    def test_decoder_type_and_reachability_limit_correlation(self):
        g, r, e = fixture(); g['data']['response_routing']['decoded_fields'][0]['owner_types'] = ['Unrelated']
        self.assertFalse(self.query(g, r, e)['links'])
        g, r, e = fixture(); g['data']['response_routing']['decoded_fields'][0]['source_symbol'] = 'unreachable'
        self.assertFalse(self.query(g, r, e)['links'])

    def test_field_copy_and_wire_name_are_both_required(self):
        g, r, e = fixture(); e['effects'][0]['value_origins'][0]['selectors'] = ['member:different']
        self.assertFalse(self.query(g, r, e)['links'])

    def test_decoder_key_alternatives_are_not_a_nested_wire_path(self):
        g, r, e = fixture()
        payload = g['response_callbacks']['transmissions'][0]['payload']['value']
        payload['fields'] = {'ticket': {'kind': 'object', 'fields': {'nested': source()}}}
        g['data']['response_routing']['decoded_fields'][0]['wire_fields'] = ['ticket', 'nested']
        self.assertFalse(self.query(g, r, e)['links'])
        g, r, e = fixture(); g['data']['response_routing']['decoded_fields'][0]['wire_fields'] = ['different']
        self.assertFalse(self.query(g, r, e)['links'])


if __name__ == '__main__': unittest.main()
