"""File-local C++ syntax facts for A1, reusing the existing supplement."""
import re
from adapters.syntax_supplement import extract, cpp_scope, span, text, walk

REGISTRATION = re.compile(r'(register|subscribe|addEventListener|(?:^|[.:>])(on|set|emplace|insert)$)', re.I)


def cpp_facts(raw, path, parser):
    raw = raw.replace(b'\r\n', b'\n'); raw.decode('utf-8')
    tree = parser.parse(raw)
    facts = extract(raw, path, 'cpp', parser, tree=tree, record_hash=False)
    types, imports, resources, entries = [], [], [], []
    for node in walk(tree.root_node):
        if node.has_error: continue
        if node.type in {'class_specifier', 'struct_specifier', 'enum_specifier'}:
            name = text(node.child_by_field_name('name'))
            types.append({'name': name, 'qualified_name': '::'.join(cpp_scope(node) + [name]),
                          'kind': node.type, **span(node)})
        elif node.type == 'preproc_include':
            imports.append({'expression': text(node.child_by_field_name('path')), **span(node)})
        elif node.type == 'field_declaration' and not any(x.type == 'function_declarator' for x in walk(node)):
            resources.append({'kind': 'member_declaration_candidate', 'scope': cpp_scope(node),
                              'expression': text(node)[:500], 'expression_truncated': len(text(node)) > 500, **span(node)})
    for call in facts['calls']:
        args = call['argument_spellings']; callee = call['callee_spelling']
        call['spellings_truncated'] = len(callee) > 500 or any(len(a) > 500 for a in args)
        call['callee_spelling'] = callee[:500]; call['argument_spellings'] = [a[:500] for a in args]
    for symbol in facts['symbols']:
        if symbol['name'] in {'main', 'wmain', 'WinMain'}:
            entries.append({'kind': 'conventional_entry_candidate', 'symbol': symbol['id'], 'line': symbol['line']})
    facts.update(types=types, imports=imports, resources=resources, entries=entries,
        interfaces=[s for s in facts['symbols'] if not s['definition'] or s.get('virtual')],
        registrations=[{'kind': 'registration_call_candidate', 'call': c['id'], 'line': c['line'],
                        'callee': c['callee_spelling'], 'resolution': 'unresolved',
                        'basis': 'ast_call_with_generic_spelling_hint'} for c in facts['calls'] if REGISTRATION.search(c['callee_spelling'])])
    facts['status'] = 'syntax_errors' if any(d['kind'] in {'syntax_error', 'missing_token'} for d in facts['diagnostics']) else 'parsed'
    facts['limits'] = facts.pop('limitations') + ['registration_hints_not_proven_registrations',
                    'member_declarations_not_runtime_resources', 'compile_context_not_applied']
    return facts
