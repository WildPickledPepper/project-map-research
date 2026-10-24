import importlib
import unittest

evaluation = importlib.import_module('experiments.2026-10-24-a4.score_chains')


class A4EvaluationTests(unittest.TestCase):
    def test_unknown_unmatched_and_omitted_are_distinct(self):
        self.assertEqual(evaluation.classify_outcome([], []), 'omission')
        self.assertEqual(evaluation.classify_outcome([{'status': 'unknown'}], []), 'identified_unknown')
        self.assertEqual(evaluation.classify_outcome([{'status': 'unmatched'}], []), 'unmatched_expected_provider')

    def test_correct_path_does_not_hide_extra_wrong_connection(self):
        self.assertEqual(evaluation.classify_outcome([{'status': 'ambiguous'}], [{'correct': True}, {'correct': False}]), 'wrong_extra_connection')

    def test_same_name_in_other_handler_file_is_not_a_correct_pair(self):
        case = {'command': 'read', 'scope': 'one', 'handler_path': 'one/handler.cpp', 'handler_suffix': 'Work::run'}
        provider = {'command': 'read', 'scope_values': ['one']}
        self.assertFalse(evaluation.provider_correct(case, provider, [{'name': 'Other::Work::run', 'path': 'other/handler.cpp'}]))
        self.assertTrue(evaluation.provider_correct(case, provider, [{'name': 'One::Work::run', 'path': 'one/handler.cpp'}]))

    def test_same_command_in_other_scope_is_not_a_correct_pair(self):
        case = {'command': 'read', 'scope': 'one', 'handler_path': 'one/handler.cpp', 'handler_suffix': 'Work::run'}
        self.assertFalse(evaluation.provider_correct(case, {'command': 'read', 'scope_values': ['two']},
            [{'name': 'One::Work::run', 'path': 'one/handler.cpp'}]))

    def test_unrelated_state_with_same_name_is_not_return_chain_evidence(self):
        case = {'state': 'items', 'consumer_path': 'ui/expected.tsx'}
        self.assertFalse(evaluation.state_connected(case, [{'name': 'items', 'path': 'ui/unrelated.tsx'}]))
        self.assertTrue(evaluation.state_connected(case, [{'name': 'items', 'path': 'ui/expected.tsx'}]))


if __name__ == '__main__': unittest.main()
