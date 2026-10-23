import json
import unittest
import importlib
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

    def test_evidence_pack_keeps_index_and_symbolic_references(self):
        pack = importlib.import_module('experiments.2026-10-23-p3.run_response_routing')
        original = {'chain': {'evidence': {'e1': {'path': 'a.cpp', 'line': 3}},
                             'relations': [{'evidence': ['e1']}]},
                    'source_step': {'evidence': [{'path': 'a.cpp', 'line': 3}]}}
        unpacked = pack.expand(pack.compact(original))
        self.assertEqual(unpacked, original)


if __name__ == '__main__': unittest.main()
