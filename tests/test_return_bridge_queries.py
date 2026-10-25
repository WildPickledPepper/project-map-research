import unittest
from unittest.mock import patch
from adapters.return_bridge_queries import project, wire_path, constant_test, evaluate_guard, dependency_path, explain_return_bridge, UNKNOWN


def path(root, selectors, **extra):
    return {'kind': 'input_path', 'root': root, 'path': selectors, 'transforms': [], 'gaps': [], **extra}


class ReturnBridgeQueryTests(unittest.TestCase):
    def test_frontend_loop_budget_is_visible_on_the_composite_return_query(self):
        graph={'snapshot':'v','source_commit':'v','return_flow':{'entries':[],'diagnostics':[],'limits':[]}}
        diagnostic={'kind':'loop_iteration_budget_exceeded','entry':'api'}
        with patch('adapters.return_bridge_queries.iframe_links', return_value=[{'api':'api','reply_send':{'entry':'reply'}}]), \
             patch('adapters.return_bridge_queries.explain_socket_receivers', return_value={'receivers':[],'truncated':False}), \
             patch('adapters.return_bridge_queries.explain_response', return_value={'truncated':False}), \
             patch('adapters.return_bridge_queries.explain_frontend', return_value={'status':'source_frontend_candidates',
                 'truncated':False,'extraction_truncated':True,'gaps':[diagnostic]}):
            result=explain_return_bridge(graph,'provider')
        self.assertTrue(result['truncated'])
        self.assertTrue(result['frontend_statuses'][0]['extraction_truncated'])
        self.assertEqual(result['gaps'][0]['kind'],'loop_iteration_budget_exceeded')

    def test_whole_object_consumption_cannot_substitute_a_sibling_for_the_requested_field(self):
        self.assertEqual(dependency_path([],['lines']),['lines'])
        self.assertIsNone(dependency_path(['limits'],['lines']))
        self.assertEqual(dependency_path(['lines','*','name'],['lines']),['lines','*','name'])
    def test_overwritten_input_selector_uses_new_source(self):
        v = path('old', [], overrides={'body': {'kind': 'constant', 'value': 4}})
        self.assertEqual(project(v, ['body']), [{'kind': 'constant', 'value': 4}])

    def test_tainted_or_unparsed_message_has_no_wire_projection(self):
        v = path('event', ['data', 'payload'])
        self.assertIsNone(wire_path(v, 'event'))
        v['transforms'] = [{'kind': 'JSON.parse', 'at_path': ['data']}]
        self.assertEqual(wire_path(v, 'event'), ['payload'])
        v['gaps'] = ['mutation']; self.assertIsNone(wire_path(v, 'event'))

    def test_json_dispatch_rejects_different_literal_tag(self):
        decoded = path('event', ['data', 'tag'], transforms=[{'kind': 'JSON.parse', 'at_path': ['data']}])
        test = {'kind': 'source_expression', 'operation': '===', 'inputs': [
            {'kind': 'alternatives', 'values': [decoded, path('event', ['data', 'tag'])]}, {'kind': 'constant', 'value': 'request'}]}
        payload = {'kind': 'object', 'fields': {'tag': {'kind': 'constant', 'value': 'other'}}}
        self.assertIs(constant_test(test, 'event', payload), False)

    def test_present_error_object_is_neither_null_nor_undefined(self):
        source = path('input', ['error'])
        test = {'kind': 'source_expression', 'operation': '&&', 'inputs': [
            {'kind': 'source_expression', 'operation': '!==', 'inputs': [source, {'kind': 'constant', 'value': None}]},
            {'kind': 'source_expression', 'operation': '!==', 'inputs': [source, {'kind': 'undefined'}]}]}
        self.assertIs(evaluate_guard(test, lambda _: [{'kind': 'object', 'fields': {}}]), True)
        self.assertIs(evaluate_guard(test, lambda _: [{'kind': 'undefined'}]), False)

    def test_opaque_guard_is_unknown(self):
        self.assertIs(evaluate_guard(path('runtime', []), lambda _: []), UNKNOWN)

    def test_missing_object_property_cannot_be_an_old_response(self):
        self.assertEqual(project({'kind': 'object', 'fields': {}}, ['body']), [{'kind': 'undefined'}])


if __name__ == '__main__': unittest.main()
