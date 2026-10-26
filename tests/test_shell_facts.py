from pathlib import Path
import tempfile
import unittest

from adapters.shell_facts import analyze


class ShellFactsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        import tree_sitter_language_pack as pack
        if os.environ.get('PROJECT_MAP_PARSER_CACHE'):
            pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))
        cls.parser=pack.get_parser('bash')

    def test_commands_assignments_substitution_and_literal_decoys(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'setup.sh').write_text('''# fake_command --never
tool="not_a_command"
DEBIAN_FRONTEND=noninteractive apt-get install -y tcl
"$tool" "$(date +%s)"
cat <<'END'
fake_heredoc_command --never
END
''',encoding='utf-8')
            graph=analyze(root,['setup.sh'],self.parser)
            commands=[n for n in graph['nodes'] if n['kind']=='call_site']
            self.assertEqual([n['name'] for n in commands],['apt-get','"$tool"','date','cat'])
            self.assertEqual(len({n['id'] for n in commands}),4)
            self.assertTrue(all(n['resolution']=='unresolved' for n in commands))
            self.assertEqual(graph['coverage'][0]['status'],'parsed')
            self.assertEqual({e['target'] for e in graph['edges']},{n['id'] for n in commands})
            self.assertTrue(any(a['native_kind']=='variable_assignment' for a in commands[0]['arguments_syntax']))

    def test_same_spelling_in_two_paths_and_invalid_input_stay_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ('one.sh','two.sh'):(root/name).write_text('echo hello\n',encoding='utf-8')
            (root/'bad.sh').write_text('if then\n',encoding='utf-8')
            graph=analyze(root,['one.sh','two.sh','bad.sh'],self.parser)
            sites=[n for n in graph['nodes'] if n['kind']=='call_site' and n['path']!='bad.sh']
            self.assertEqual(len({n['id'] for n in sites}),2)
            self.assertEqual(next(r['status'] for r in graph['coverage'] if r['path']=='bad.sh'),'syntax_errors')
            self.assertTrue(graph['diagnostics'])
