import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from adapters.snapshot_inputs import commit, export_inputs, normalize_config, select_inputs, validate_path


class SnapshotInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name); self.repo = self.base / 'repo'; self.repo.mkdir()
        self.git('init', '-q'); self.git('config', 'user.name', 'Snapshot test')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'core.autocrlf', 'false')
        self.config = {'version': 1, 'scope': {'include': ['*']}, 'deployment': {'services': []}, 'storage': 'json'}

    def git(self, *args, **kwargs):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], stderr=subprocess.PIPE, **kwargs)

    def save(self, files):
        for name, content in files.items():
            target = self.repo / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(content)
        self.git('add', '-A'); self.git('commit', '-qm', 'fixture')
        return commit(self.repo)

    def test_fixed_revision_ignores_later_commit_and_dirty_worktree(self):
        old = self.save({'src/a.ts': b'old\x00\n', 'src/b.ts': b'keep'})
        selected = select_inputs(self.repo, old, self.config)
        self.save({'src/a.ts': b'new', 'src/new.ts': b'added'})
        (self.repo/'src/b.ts').write_bytes(b'dirty')
        export_inputs(self.repo, selected, self.base/'export')
        self.assertEqual((self.base/'export/src/a.ts').read_bytes(), b'old\x00\n')
        self.assertEqual((self.base/'export/src/b.ts').read_bytes(), b'keep')
        self.assertFalse((self.base/'export/src/new.ts').exists())
        self.assertEqual(selected['source_commit'], old)
        self.assertFalse(selected['working_tree_included'])

    def test_git_archive_attributes_do_not_remove_or_substitute_source(self):
        original = b'$Format:%H$\r\n'
        self.save({'.gitattributes': b'a.ts export-ignore\nb.ts export-subst\n', 'a.ts': b'included', 'b.ts': original})
        selected = select_inputs(self.repo, 'HEAD', self.config)
        export_inputs(self.repo, selected, self.base/'export')
        self.assertEqual((self.base/'export/a.ts').read_bytes(), b'included')
        self.assertEqual((self.base/'export/b.ts').read_bytes(), original)

    def test_selection_observes_add_delete_rename_and_case_sensitive_globs(self):
        self.save({'src/old.ts': b'x', 'src/ignore.ts': b'x', 'other/a.ts': b'x', 'src/up.TS': b'x'})
        self.config['scope'] = {'include': ['src/*.ts'], 'exclude': ['src/ignore.ts']}
        before = select_inputs(self.repo, 'HEAD', self.config)
        self.assertEqual([f['path'] for f in before['files']], ['src/old.ts'])
        self.git('mv', 'src/old.ts', 'src/renamed.ts')
        self.save({'src/new/deep.ts': b'new'})
        after = select_inputs(self.repo, 'HEAD', self.config)
        self.assertEqual([f['path'] for f in after['files']], ['src/new/deep.ts', 'src/renamed.ts'])
        self.assertEqual(len(after['omitted']), 3)
        self.git('rm', 'src/renamed.ts'); self.git('commit', '-qm', 'remove')
        self.assertEqual([f['path'] for f in select_inputs(self.repo, 'HEAD', self.config)['files']], ['src/new/deep.ts'])

    def test_unsafe_and_nonportable_paths_rejected(self):
        for path in ['../a', '/a', 'C:/a', 'a\\b', 'a//b', './a', '.git/config', 'a/../b']:
            with self.subTest(path=path), self.assertRaises(ValueError): validate_path(path)

    def test_symlink_is_reported_without_following_it(self):
        self.save({'a.ts': b'ok', 'target': b'../outside'})
        blob = self.git('rev-parse', 'HEAD:target').decode().strip()
        self.git('update-index', '--add', '--cacheinfo', f'120000,{blob},link.ts')
        self.git('commit', '-qm', 'link')
        selected = select_inputs(self.repo, 'HEAD', self.config)
        self.assertIn({'path': 'link.ts', 'reason': 'unsupported_git_mode', 'mode': '120000'}, selected['omitted'])
        export_inputs(self.repo, selected, self.base/'export')
        self.assertFalse((self.base/'export/link.ts').exists())

    def test_configuration_is_detached_canonical_and_strict(self):
        self.config['scope']['include'] = ['z', 'a', 'z']
        result = normalize_config(self.config)
        self.assertEqual(result['scope']['include'], ['a', 'z'])
        self.config['scope']['include'].append('later')
        self.assertEqual(result['scope']['include'], ['a', 'z'])
        for patch in [{'storage': 'ignored'}, {'unknown': True}, {'scope': {'incldue': ['*']}}]:
            with self.subTest(patch=patch), self.assertRaises(ValueError): normalize_config({**self.config, **patch})

    def test_empty_scope_fails_and_export_cannot_overwrite_previous_snapshot(self):
        self.save({'a.ts': b'old'})
        with self.assertRaises(ValueError):
            select_inputs(self.repo, 'HEAD', {**self.config, 'scope': {'include': ['missing/*']}})
        selected = select_inputs(self.repo, 'HEAD', self.config)
        export_inputs(self.repo, selected, self.base/'export')
        with self.assertRaises(FileExistsError): export_inputs(self.repo, selected, self.base/'export')
        self.assertEqual((self.base/'export/a.ts').read_bytes(), b'old')


if __name__ == '__main__': unittest.main()
