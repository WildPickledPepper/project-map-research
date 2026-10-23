import json
import unittest
from adapters.chain_queries import evidence_in, explain_chain


class ChainQueryTests(unittest.TestCase):
    def test_evidence_order_survives_storage_key_normalization(self):
        source = {'lookup': {'evidence': [{'path': 'second.cpp', 'line': 4}]},
                  'entry': {'evidence': [{'path': 'first.ts', 'line': 2, 'expression': 'call()'}]},
                  'uses': [{'path': 'a.cpp', 'line': 8}, {'path': 'a.cpp', 'line': 3}]}
        self.assertEqual(list(evidence_in(source)), list(evidence_in(json.loads(json.dumps(source, sort_keys=True)))))

    def test_field_query_requires_explicit_selectors(self):
        for path in [None, [], 'field', [3]]:
            with self.assertRaises(ValueError): explain_chain({}, 'provider', path)


if __name__ == '__main__': unittest.main()
