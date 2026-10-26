import json
from pathlib import Path
import tempfile
import unittest

from adapters.compilation_database import command_arguments, with_builtin_headers


class CompilationDatabaseTests(unittest.TestCase):
    def test_native_command_parser_preserves_quoted_paths_and_literal_shell_text(self):
        args = command_arguments('compiler.exe -DNAME="literal value" -c "source name.cpp" "$(do-not-run)"')
        self.assertEqual(args, ['compiler.exe', '-DNAME=literal value', '-c', 'source name.cpp', '$(do-not-run)'])

    def test_resource_headers_are_inserted_without_changing_product_flags_or_native_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); headers = root / 'clang builtin headers'; headers.mkdir()
            native = root / 'compile_commands.json'
            rows = [{'directory': str(root), 'file': str(root / 'source name.cpp'),
                     'arguments': ['compiler.exe', '-DFEATURE=1', '-std=c++17', '-c', 'source name.cpp']}]
            native.write_text(json.dumps(rows), encoding='utf-8')
            report = with_builtin_headers(native, root / 'adjusted', headers)
            actual = json.loads((root / 'adjusted/compile_commands.json').read_text())
            self.assertEqual(actual[0]['arguments'][3:], rows[0]['arguments'][1:])
            self.assertEqual(actual[0]['arguments'][1:3], ['-isystem', str(headers.resolve())])
            self.assertEqual(json.loads(native.read_text()), rows)
            self.assertFalse(report['source_database_modified'])
            self.assertFalse(report['command_text_executed'])

    def test_command_form_is_normalized_to_argument_array(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); headers = root / 'headers'; headers.mkdir()
            rows = [{'directory': str(root), 'file': 'file.cpp', 'command': 'c++ -c "file.cpp"'}]
            native = root / 'compile_commands.json'; native.write_text(json.dumps(rows))
            with_builtin_headers(native, root / 'adjusted', headers)
            row = json.loads((root / 'adjusted/compile_commands.json').read_text())[0]
            self.assertNotIn('command', row)
            self.assertEqual(row['arguments'][3:], ['-c', 'file.cpp'])


if __name__ == '__main__':
    unittest.main()
