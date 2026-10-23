"""Version transitions must not promote historical records to current evidence."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from adapters.snapshot_refresh import Refresher, atomic_json
from adapters.snapshot_records import append_record, query_record, query_records, snapshot_basis
from tests.refresh_worker import synthetic_builder


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name); self.source = self.base/'source'; self.source.mkdir(); self.store = self.base/'store'
        self.git('init', '-q'); self.git('config', 'user.name', 'Record test')
        self.git('config', 'user.email', 'test@example.invalid'); self.git('config', 'core.autocrlf', 'false')
        self.config = {'version': 1, 'scope': {'include': ['*.ts']}, 'storage': 'json', 'deployment': {'services': []}}
        self.version = {'rules': 'synthetic_record_test'}
        self.save({'a.ts': 'first'})
        self.runner = Refresher(self.source, self.store, lambda: self.config, lambda: self.version, synthetic_builder)
        state = self.runner.run(); self.assertEqual(state['status'], 'up_to_date', state)
        self.basis = snapshot_basis(self.store)

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.source), *args], stderr=subprocess.PIPE)

    def save(self, files):
        for name, content in files.items(): (self.source/name).write_text(content, encoding='utf-8')
        self.git('add', '-A'); self.git('commit', '-qm', 'record fixture step')

    def submission(self, kind='verification'):
        return {'kind': kind, 'basis': deepcopy(self.basis),
                'provenance': {'evidence_kind': 'synthetic', 'source_ref': 'synthetic:p4/record-tests',
                               'producer': {'name': 'test_snapshot_records', 'version': '1'}},
                'payload': {'scenario': 'synthetic', 'outcome': 'passed', 'summary': 'fixture content',
                            'execution': {'build': 'synthetic', 'configuration': 'A', 'data': 'authored_fixture'}},
                'anchors': [{'label': 'entry', 'node_id': 'fixture:a.ts'}]}

    def test_all_kinds_retain_payload_basis_and_provenance_across_source_change(self):
        records = [append_record(self.store, self.submission(k)) for k in ('trace', 'summary', 'verification', 'asset_anchor')]
        originals = {(self.store/'records'/r['id']/'record.json'): r for r in records}
        self.save({'a.ts': 'changed behavior with same identity'}); self.runner.run()
        current = query_records(self.store)
        self.assertEqual(current['count'], 4)
        for item in current['items']:
            self.assertEqual(item['record']['basis'], self.basis)
            self.assertEqual(item['record']['payload']['outcome'], 'passed')
            self.assertEqual(item['record']['provenance']['evidence_kind'], 'synthetic')
            self.assertFalse(item['eligible_for_direct_overlay']); self.assertFalse(item['verification_carried_forward'])
            self.assertEqual(item['anchors'][0]['status'], 'candidate')
            self.assertEqual(item['applicability'], 'not_evaluated')
            old = query_record(self.store, item['record']['id'], snapshot_id=self.basis['id'])
            self.assertTrue(old['eligible_for_direct_overlay']); self.assertEqual(old['anchors'][0]['status'], 'mapped')
            self.assertEqual(old['requested_freshness'], 'historical_or_pending')
        for path, expected in originals.items(): self.assertEqual(json.loads(path.read_text(encoding='utf-8')), expected)
        self.assertEqual(query_records(self.store, include_history=False)['count'], 0)
        self.assertEqual(query_records(self.store, kind='trace')['count'], 1)

    def test_config_and_builder_versions_prevent_overlay_at_same_commit(self):
        record = append_record(self.store, self.submission('trace'))
        self.config['deployment'] = {'services': [{'id': 'another', 'consumer_paths': ['x'], 'provider_paths': ['y']}]}
        self.runner.run()
        result = query_record(self.store, record['id'])
        self.assertEqual(result['requested_basis']['source_commit'], self.basis['source_commit'])
        self.assertIn('config', result['version_differences']); self.assertFalse(result['eligible_for_direct_overlay'])
        self.version = {'rules': 'next_synthetic_version'}; self.runner.run()
        result = query_record(self.store, record['id'])
        self.assertIn('build_version', result['version_differences']); self.assertFalse(result['eligible_for_direct_overlay'])

    def test_late_submission_keeps_captured_basis_and_pending_snapshot_freshness(self):
        pending = self.submission()
        self.save({'a.ts': 'next'}); self.runner.run()
        record = append_record(self.store, pending)
        self.assertEqual(record['basis'], self.basis)
        self.assertFalse(query_record(self.store, record['id'])['eligible_for_direct_overlay'])
        self.basis = snapshot_basis(self.store); current = append_record(self.store, self.submission())
        self.save({'a.ts': 'unbuildable'})
        def broken(*args): raise ValueError('synthetic build failure')
        self.runner.builder = broken; self.runner.run()
        result = query_record(self.store, current['id'])
        self.assertTrue(result['eligible_for_direct_overlay'])
        self.assertEqual(result['requested_freshness'], 'historical_or_pending')

    def test_mismatched_or_unpublished_producer_basis_is_rejected(self):
        for key in ('source_commit', 'snapshot', 'config', 'build_version', 'id'):
            submission = self.submission(); submission['basis'][key] = 'wrong'
            with self.subTest(key=key), self.assertRaises((ValueError, LookupError)):
                append_record(self.store, submission)
        submission = self.submission(); del submission['basis']['config']
        with self.assertRaises(ValueError): append_record(self.store, submission)
        self.assertFalse((self.store/'records').exists())

    def test_rename_or_delete_never_falls_back_to_another_name(self):
        record = append_record(self.store, self.submission('asset_anchor'))
        self.git('mv', 'a.ts', 'renamed.ts'); self.save({'other.ts': 'same business name in another module'})
        self.runner.run()
        result = query_record(self.store, record['id'])
        self.assertEqual(result['anchors'][0]['status'], 'dangling')
        self.assertEqual(result['anchors'][0]['candidates'], [])
        self.assertFalse(result['verification_carried_forward'])

    def test_reused_id_with_changed_semantics_is_dangling(self):
        record = append_record(self.store, self.submission('asset_anchor'))
        self.save({'a.ts': 'renamed interface at same site'})
        def changed(source, request, output, log):
            result = synthetic_builder(source, request, output, log)
            path = output/'graph.json'; graph = json.loads(path.read_text(encoding='utf-8'))
            graph['nodes'][0]['name'] = 'new_interface'
            path.write_text(json.dumps(graph), encoding='utf-8'); return result
        self.runner.builder = changed; self.runner.run()
        self.assertEqual(query_record(self.store, record['id'])['anchors'][0]['status'], 'dangling')

    def test_multiple_exact_selectors_remain_ambiguous(self):
        record = append_record(self.store, self.submission('asset_anchor')); self.save({'a.ts': 'ambiguous declarations'})
        def ambiguous(source, request, output, log):
            result = synthetic_builder(source, request, output, log)
            path = output/'graph.json'; graph = json.loads(path.read_text(encoding='utf-8'))
            graph['nodes'].append({**graph['nodes'][0], 'id': 'other', 'line': 9})
            result['nodes'] += 1; path.write_text(json.dumps(graph), encoding='utf-8'); return result
        self.runner.builder = ambiguous; self.runner.run()
        anchor = query_record(self.store, record['id'])['anchors'][0]
        self.assertEqual(anchor['status'], 'ambiguous'); self.assertEqual(len(anchor['candidates']), 2)

    def test_unmapped_event_keeps_gap_even_when_id_appears_later(self):
        submission = self.submission('trace')
        submission['anchors'].append({'label': 'unobserved', 'node_id': 'fixture:b.ts', 'reason': 'not in sampled graph'})
        record = append_record(self.store, submission)
        self.save({'b.ts': 'now in graph'}); self.runner.run()
        self.assertEqual(query_record(self.store, record['id'])['anchors'][1]['status'], 'unmapped')
        self.assertEqual(query_record(self.store, record['id'])['anchors'][1]['candidates'], [])

    def test_failed_atomic_append_is_not_visible_and_next_append_succeeds(self):
        with patch('adapters.snapshot_refresh.os.replace', side_effect=OSError('interrupted record publication')):
            with self.assertRaises(OSError): append_record(self.store, self.submission())
        self.assertEqual(query_records(self.store)['count'], 0)
        record = append_record(self.store, self.submission())
        self.assertEqual(query_records(self.store)['count'], 1)
        self.assertEqual(query_records(self.store)['items'][0]['record'], record)

    def test_parallel_appends_preserve_all_records(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            records = list(pool.map(lambda _: append_record(self.store, self.submission()), range(8)))
        self.assertEqual({r['id'] for r in records}, {r['record']['id'] for r in query_records(self.store)['items']})

    def test_windows_reader_sharing_conflict_retries_atomic_publication(self):
        import os
        path = self.base/'atomic.json'; atomic_json(path, {'old': True})
        real_replace = os.replace; calls = []
        def sharing(source, target):
            calls.append(1)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), {'old': True})
            if len(calls) < 3:
                error = PermissionError('reader temporarily denies delete sharing'); error.winerror = 5
                raise error
            real_replace(source, target)
        with patch('adapters.snapshot_refresh.os.replace', side_effect=sharing), patch('adapters.snapshot_refresh.time.sleep'):
            atomic_json(path, {'new': True})
        self.assertEqual(len(calls), 3); self.assertEqual(json.loads(path.read_text(encoding='utf-8')), {'new': True})

    def test_persistent_windows_access_failure_preserves_previous_document(self):
        path = self.base/'atomic.json'; atomic_json(path, {'old': True})
        error = PermissionError('persistent access failure'); error.winerror = 5
        with patch('adapters.snapshot_refresh.os.replace', side_effect=error) as replace, patch('adapters.snapshot_refresh.time.sleep'):
            with self.assertRaises(PermissionError): atomic_json(path, {'new': True})
        self.assertEqual(replace.call_count, 10)
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')), {'old': True})

    def test_invalid_anchor_declarations_do_not_publish_records(self):
        for anchors in ([{'label': 'missing', 'node_id': 'does-not-exist'}],
                        [{'label': 'x', 'node_id': 'fixture:a.ts'}]*2):
            submission = self.submission(); submission['anchors'] = anchors
            with self.assertRaises(ValueError): append_record(self.store, submission)
        self.assertEqual(query_records(self.store)['count'], 0)

    def test_cli_captures_basis_appends_and_queries_same_record(self):
        script = Path(__file__).resolve().parents[1]/'scripts'/'snapshot_records.py'
        def cli(*args):
            return json.loads(subprocess.check_output([sys.executable, str(script), '--store', str(self.store), *args], text=True))
        self.assertEqual(cli('basis'), self.basis)
        path = self.base/'submission.json'; path.write_text(json.dumps(self.submission()), encoding='utf-8')
        record = cli('append', '--input', str(path))
        self.assertEqual(cli('query', '--id', record['id'])['record'], record)
        self.assertEqual(cli('query', '--kind', 'verification', '--only-snapshot')['count'], 1)


if __name__ == '__main__': unittest.main()
