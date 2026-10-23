"""Execution context and missing mappings must survive graph projection."""
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'experiments/2026-10-24-p5'))
from runtime_records import append_runtime, query_runtime, validate_context
from adapters.snapshot_refresh import Refresher
from adapters.snapshot_records import snapshot_basis
from tests.refresh_worker import synthetic_builder


class RuntimeRecordsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.source = Path(temp.name)/'source'; self.source.mkdir()
        self.store = Path(temp.name)/'store'
        self.git('init', '-q'); self.git('config', 'user.name', 'Runtime fixture')
        self.git('config', 'user.email', 'test@example.invalid')
        (self.source/'a.ts').write_text('a', encoding='utf-8')
        (self.source/'b.ts').write_text('b', encoding='utf-8')
        self.git('add', '.'); self.git('commit', '-qm', 'synthetic graph')
        self.config = {'version': 1, 'scope': {'include': ['*.ts']}, 'storage': 'json', 'deployment': {'services': []}}
        self.runner = Refresher(self.source, self.store, lambda: self.config,
                               lambda: {'rules': 'synthetic'}, synthetic_builder)
        self.runner.run(); self.basis = snapshot_basis(self.store)
        commit = self.basis['source_commit']
        self.context = {'source_commit': commit, 'build': {'source_commit': commit,
                        'components': [{'source_commit': commit, 'log_ref': 'synthetic:build'}]},
                        'runtime_config': {'strict': True}, 'data': {'fixture': 'synthetic'},
                        'scenario': {'name': 'synthetic'}}
        self.events = [{'id': 'event:1', 'stage': 'captured', 'observation': {'value': 3}},
                       {'id': 'event:2', 'stage': 'outside_source', 'observation': {'value': 9}}]
        self.rules = [{'stage': 'captured', 'role': 'hook',
                       'selector': {'kind': 'synthetic_file', 'name': 'a.ts'}}]

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.source), *args], stderr=subprocess.PIPE)

    def append(self):
        return append_runtime(self.store, self.basis, self.context, self.events, [], self.rules,
            {'evidence_kind': 'synthetic', 'source_ref': 'synthetic:runtime-test',
             'producer': {'name': 'test', 'version': '1'}}, {'scenario_passed': False}, [])

    def query(self, record, context=None, snapshot=None):
        return query_runtime(self.store, record['id'], snapshot_id=snapshot or self.basis['id'],
                             context=self.context if context is None else context)

    def test_same_context_preserves_unmapped_event_and_failed_assertion(self):
        record = self.append(); result = self.query(record)
        self.assertTrue(result['eligible_for_direct_overlay'])
        self.assertEqual([a['status'] for a in record['anchors']], ['mapped', 'unmapped'])
        self.assertEqual(record['payload']['events'], self.events)
        self.assertFalse(record['payload']['outcome']['scenario_passed'])
        self.assertFalse(result['verification_carried_forward'])
        self.assertEqual(record['payload']['static_context']['execution_status'], 'not_inferred_from_static_edges')

    def test_each_execution_context_difference_blocks_direct_overlay(self):
        record = self.append()
        for key in self.context:
            changed = deepcopy(self.context)
            changed[key] = 'another' if key == 'source_commit' else {'different': True}
            with self.subTest(key=key):
                result = self.query(record, changed)
                self.assertFalse(result['eligible_for_direct_overlay'])
                self.assertEqual(result['runtime_context_differences'], [key])

    def test_new_source_and_graph_configuration_do_not_inherit_execution(self):
        record = self.append()
        (self.source/'a.ts').write_text('changed', encoding='utf-8')
        self.git('add', '.'); self.git('commit', '-qm', 'next synthetic source')
        self.runner.run(); next_basis = snapshot_basis(self.store)
        result = self.query(record, snapshot=next_basis['id'])
        self.assertFalse(result['eligible_for_direct_overlay'])
        self.assertIn('source_commit', result['version_differences'])
        self.config['scope']['exclude'] = ['b.ts']; self.runner.run()
        result = self.query(record, snapshot=snapshot_basis(self.store)['id'])
        self.assertIn('config', result['version_differences'])
        self.assertFalse(result['eligible_for_direct_overlay'])
        self.assertTrue(self.query(record)['eligible_for_direct_overlay'])

    def test_ambiguous_selector_keeps_candidates_without_choosing(self):
        self.rules[0]['selector'].pop('name')
        record = self.append(); mapping = record['payload']['mappings'][0]
        self.assertEqual(mapping['reason'], 'ambiguous_source_selector')
        self.assertEqual(len(mapping['candidates']), 2)
        self.assertEqual(record['anchors'][0]['status'], 'unmapped')

    def test_incompatible_build_or_source_cannot_be_attached_to_graph(self):
        for field in ('source_commit', 'build'):
            context = deepcopy(self.context)
            if field == 'source_commit': context[field] = 'wrong'
            else: context[field]['source_commit'] = 'wrong'
            with self.assertRaises(ValueError): validate_context(context, self.basis)
        self.context['build']['components'][0]['source_commit'] = 'older'
        with self.assertRaisesRegex(ValueError, 'scoped equivalence'): self.append()

    def test_context_cannot_be_omitted_and_duplicate_event_ids_are_rejected(self):
        record = self.append()
        with self.assertRaises(ValueError): self.query(record, {})
        self.events.append(deepcopy(self.events[0]))
        with self.assertRaisesRegex(ValueError, 'Duplicate'): self.append()


if __name__ == '__main__': unittest.main()
