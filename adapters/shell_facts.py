"""Normalize command sites from the existing Bash grammar; no Shell evaluation."""
import importlib.metadata
from pathlib import Path

from adapters.snapshot_inputs import validate_path
from adapters.syntax_supplement import identity, span, text, walk

VERSION = 'bash_native_command_syntax/0.1.0'


def analyze(root, paths, parser):
    root = Path(root)
    nodes, edges, coverage, diagnostics = [], [], [], []
    for path in sorted(paths):
        validate_path(path)
        source = (root / path).read_bytes().replace(b'\r\n', b'\n')
        tree = parser.parse(source)
        module = 'bash-source-module:' + path
        nodes.append({'id': module, 'kind': 'code_module', 'path': path, 'line': 1,
                      'name': path, 'language': 'shell', 'evidence_kind': 'tree_sitter_bash_syntax'})
        for node in walk(tree.root_node):
            if node.type == 'command':
                name = node.child_by_field_name('name')
                if name is None:
                    continue
                uid = 'bash:' + identity(path, 'call_site', node)
                position = span(node)
                nodes.append({'id': uid, 'kind': 'call_site', 'path': path, **position,
                    'name': text(name), 'callee_spelling': text(name), 'language': 'shell',
                    'arguments_syntax': [{'native_kind': child.type, 'expression': text(child), **span(child)}
                                         for child in node.named_children if child != name],
                    'native_kind': 'command', 'evidence_kind': 'tree_sitter_bash_syntax',
                    'resolution': 'unresolved', 'reason': 'syntax_only_no_command_or_expansion_evaluation',
                    'runtime_execution': 'not_observed'})
                edges.append({'source': module, 'target': uid, 'kind': 'CONTAINS_CALL_SITE',
                    'status': 'source_relation', 'evidence': [{'path': path, 'line': position['line'],
                                                           'column': position['column']}],
                    'runtime_execution': 'not_observed'})
            elif node.type == 'ERROR' or node.is_missing:
                diagnostics.append({'path': path, 'kind': 'bash_syntax_error', **span(node),
                                    'native_kind': node.type})
        coverage.append({'path': path, 'status': 'syntax_errors' if tree.root_node.has_error else 'parsed',
                         'provider': 'tree_sitter_bash', 'adapter': VERSION})
    return {'nodes': nodes, 'edges': edges, 'coverage': coverage, 'diagnostics': diagnostics,
        'components': {'provider': 'tree_sitter_bash', 'adapter': VERSION,
            'tree_sitter_language_pack': importlib.metadata.version('tree-sitter-language-pack')},
        'limits': ['shell_command_sites_are_syntax_not_execution_or_resolved_process_targets']}
