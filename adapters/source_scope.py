"""Entry and configuration declarations for scope review, without target inference."""
import ast
import json
from pathlib import PurePosixPath
import re


def python_scope(text, path):
    entries, options, diagnostics = [], [], []
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        return entries, options, [{'path': path, 'line': error.lineno, 'reason': 'python_scope_syntax_error'}]
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            guard = (isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq)
                     and len(test.comparators) == 1 and
                     ((isinstance(test.left, ast.Name) and test.left.id == '__name__' and
                       isinstance(test.comparators[0], ast.Constant) and test.comparators[0].value == '__main__') or
                      (isinstance(test.comparators[0], ast.Name) and test.comparators[0].id == '__name__' and
                       isinstance(test.left, ast.Constant) and test.left.value == '__main__')))
            if guard:
                entries.append({'path': path, 'line': node.lineno, 'kind': 'python_main_guard',
                                'condition': ast.unparse(test), 'origin': 'python_ast'})
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'add_argument':
            names = [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
            if not names:
                continue
            declarations = {}
            for keyword in node.keywords:
                if keyword.arg in {'default', 'choices', 'required', 'action', 'type', 'nargs'}:
                    try:
                        value = ast.literal_eval(keyword.value)
                        json.dumps(value, allow_nan=False)
                        declarations[keyword.arg] = {'literal': value}
                    except (ValueError, TypeError):
                        declarations[keyword.arg] = {'expression': ast.unparse(keyword.value), 'resolution': 'not_evaluated'}
            options.append({'path': path, 'line': node.lineno, 'kind': 'cli_option_declaration_candidate',
                            'names': names, 'declarations': declarations, 'receiver': ast.unparse(node.func.value),
                            'origin': 'python_ast', 'receiver_type_proven': False})
    return entries, options, diagnostics


def source_scope(text, path, language):
    if language == 'python':
        return python_scope(text, path)
    entries, options = [], []
    if language in {'rust', 'cpp', 'c'}:
        pattern = r'^\s*(?:pub\s+)?fn\s+main\s*\(' if language == 'rust' else r'^\s*(?:int|void)\s+main\s*\('
        for line, body in enumerate(text.splitlines(), 1):
            if re.search(pattern, body):
                entries.append({'path': path, 'line': line, 'kind': language + '_main_declaration_candidate',
                                'origin': 'source_declaration_pattern', 'build_conditions': 'requires_build_context'})
    if language in {'shell', 'powershell', 'batch'}:
        entries.append({'path': path, 'line': 1, 'kind': 'script_execution_candidate',
                        'origin': 'tracked_script_source', 'invocation': 'requires_consumer_review'})
    return entries, options, []


def script_role_evidence(texts):
    """Recognize directly named npm script files; keep provenance and avoid executing shell."""
    found = {}
    for path, text in texts.items():
        if PurePosixPath(path).name != 'package.json':
            continue
        try:
            scripts = json.loads(text).get('scripts', {})
        except (ValueError, AttributeError):
            continue
        if not isinstance(scripts, dict):
            continue
        for name, command in scripts.items():
            if not isinstance(command, str) or not re.match(r'^(?:build|bundle|compile|pack|sync|lint|format|prepare|prepack|postpack|prepublishOnly)(?:[:_-]|$)', name):
                continue
            for match in re.finditer(r'\b(?:node|ts-node|tsx)\s+(?:[\'"]([^\'"]+)[\'"]|([^\s;&|]+))', command):
                spelling = match[1] or match[2]
                if spelling.startswith('-') or '\\' in spelling:
                    continue
                parts = [part for part in (*PurePosixPath(path).parent.parts, *PurePosixPath(spelling).parts) if part != '.']
                if '..' in parts:
                    continue
                target = '/'.join(parts)
                if target in texts:
                    found.setdefault(target, []).append({'path': path, 'script': name, 'command': command,
                                                         'kind': 'npm_script_file_reference'})
    return found
