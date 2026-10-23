"""Supplement CGC facts with declarations, lexical scopes and binding evidence.

Uses the existing Tree-sitter grammars. This module records source syntax; it
does not perform preprocessing, type checking, overload resolution or dispatch.
Caller/callee spellings are observations, never resolved call edges.
"""
from __future__ import annotations

import hashlib
from pathlib import PurePosixPath

VERSION = '0.1.0'
CPP_CONTAINERS = {'function_definition', 'field_declaration', 'declaration'}
CPP_SCOPES = {'namespace_definition', 'class_specifier', 'struct_specifier'}
TS_CLASSES = {'class_declaration', 'abstract_class_declaration', 'class'}
TS_FUNCTIONS = {'function_declaration', 'function_expression', 'generator_function_declaration',
                'method_definition', 'method_signature', 'abstract_method_signature', 'arrow_function'}
CPP_NAMES = {'identifier', 'field_identifier', 'qualified_identifier', 'destructor_name', 'operator_name', 'template_function'}


def walk(node):
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))


def text(node):
    return node.text.decode('utf-8') if node is not None else ''


def parents(node):
    current = node.parent
    while current is not None:
        yield current
        current = current.parent


def span(node):
    return {'line': node.start_point[0]+1, 'column': node.start_point[1]+1,
            'end_line': node.end_point[0]+1, 'end_column': node.end_point[1]+1,
            'start_byte': node.start_byte, 'end_byte': node.end_byte}


def identity(path, kind, node):
    value = f'{path}:{kind}:{node.start_byte}:{node.end_byte}'
    return hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]


def cpp_scope(node):
    parts = []
    for ancestor in reversed(list(parents(node))):
        if ancestor.type in CPP_SCOPES:
            name = text(ancestor.child_by_field_name('name'))
            parts.append(name or f'<anonymous@{ancestor.start_point[0]+1}>')
    return parts


def ts_name(node):
    named = node.child_by_field_name('name')
    if named is not None:
        return text(named)
    parent = node.parent
    if parent is not None and parent.type in {'variable_declarator', 'pair', 'public_field_definition'}:
        named = parent.child_by_field_name('name') or parent.child_by_field_name('key')
        if named is not None:
            return text(named)
    return f'<lambda@{node.start_point[0]+1}:{node.start_point[1]+1}>'


def ts_scope(node):
    parts = []
    for ancestor in reversed(list(parents(node))):
        if ancestor.type in TS_CLASSES or ancestor.type == 'internal_module':
            parts.append(text(ancestor.child_by_field_name('name')) or '<anonymous-class>')
        elif ancestor.type in TS_FUNCTIONS:
            parts.append(ts_name(ancestor))
    return parts


def cpp_callable(node):
    name = node.child_by_field_name('declarator')
    if name is None or name.type not in CPP_NAMES:
        return None
    owner = next((p for p in parents(node) if p.type in CPP_CONTAINERS | {'parameter_declaration','type_definition'}), None)
    if owner is None or owner.type not in CPP_CONTAINERS:
        return None
    # A function declarator inside a function pointer/type is not a declaration
    # of an invocable named method. Only follow its direct declarator chain.
    outer = owner.child_by_field_name('declarator')
    if outer is None:
        return None
    chain = outer
    while chain is not None and chain != node:
        if chain.type not in {'pointer_declarator', 'reference_declarator', 'attributed_declarator'}:
            return None
        chain = chain.child_by_field_name('declarator') or (chain.named_children[-1] if chain.named_children else None)
    if chain != node:
        return None
    spelling = text(name)
    scopes = cpp_scope(owner)
    prefix = '::'.join(scopes)
    if spelling.startswith('::'):
        qualified = spelling[2:]
    elif prefix and (spelling == prefix or spelling.startswith(prefix+'::')):
        qualified = spelling
    else:
        qualified = '::'.join(scopes+[spelling])
    body = owner.child_by_field_name('body')
    header_end = body.start_byte if body is not None else owner.end_byte
    # Preserve the spelling (including const, references and overload parameters).
    header = owner.text[:header_end-owner.start_byte].decode('utf-8').strip()
    tokens = [text(c) for c in owner.children if c.type not in {'comment'}]
    value = owner.child_by_field_name('default_value')
    pure = value is not None and text(value).strip() == '0'
    if not pure:
        pure = any(c.type == 'number_literal' and text(c) == '0' for c in owner.named_children) and any(c.type == '=' for c in owner.children)
    return owner, name, {'name': spelling.rsplit('::',1)[-1], 'qualified_name': qualified,
                        'scope': scopes, 'definition': owner.type == 'function_definition',
                        'parameters': text(node.child_by_field_name('parameters')),
                        'signature_spelling': header,
                        'return_type_spelling': text(owner.child_by_field_name('type')),
                        'virtual': 'virtual' in tokens, 'pure_virtual': pure}


def extract(source: bytes, path: str, language: str, parser):
    """Return portable source facts using an injected, existing parser."""
    rel = PurePosixPath(path)
    if rel.is_absolute() or '..' in rel.parts or '\\' in path or ':' in path:
        raise ValueError('path must be repository-relative POSIX text')
    if language not in {'cpp', 'typescript', 'tsx'}:
        raise ValueError(f'Unsupported language: {language}')
    source = source.replace(b'\r\n', b'\n')
    source.decode('utf-8')
    tree = parser.parse(source)
    result = {'path': path, 'language': language, 'sha256_lf_utf8': hashlib.sha256(source).hexdigest(),
              'extractor': 'syntax_supplement', 'extractor_version': VERSION,
              'evidence_kind': 'source_syntax', 'symbols': [], 'calls': [], 'bindings': [],
              'diagnostics': [], 'limitations': ['preprocessing_not_evaluated', 'call_targets_not_resolved',
                                                'types_not_checked', 'binding_targets_not_resolved']}
    callables = []
    nodes = list(walk(tree.root_node))
    error_spans = [(n.start_byte,n.end_byte) for n in nodes if n.type == 'ERROR' or n.is_missing]
    def damaged(node):
        return node.has_error or any(start <= node.start_byte and node.end_byte <= end for start,end in error_spans)
    for node in nodes:
        if node.type == 'ERROR' or node.is_missing:
            result['diagnostics'].append({'kind': 'syntax_error' if node.type=='ERROR' else 'missing_token', **span(node)})
        value = None
        if language == 'cpp' and node.type == 'function_declarator':
            record = cpp_callable(node)
            if record is not None:
                container, named, value = record
            elif node.parent is not None and node.parent.type == 'parenthesized_declarator':
                result['diagnostics'].append({'kind':'unsupported_callable_declarator',**span(node)})
        elif language != 'cpp' and node.type in TS_FUNCTIONS:
            container = node
            named = node.child_by_field_name('name') or node
            name = ts_name(node)
            scope = ts_scope(node)
            parameters = node.child_by_field_name('parameters') or node.child_by_field_name('parameter')
            types = node.child_by_field_name('type_parameters')
            value = {'name':name,'qualified_name':'.'.join(scope+[name]),'scope':scope,
                     'definition':node.type not in {'method_signature','abstract_method_signature'},
                     'parameters':text(parameters),'type_parameters':text(types),
                     'return_type_spelling':text(node.child_by_field_name('return_type'))}
        if value is not None:
            if damaged(container):
                result['diagnostics'].append({'kind':'callable_in_error_region',**span(container)})
                continue
            value.update(id=identity(path,'callable',container), kind='callable', **span(named),
                         container_span=span(container), resolution='syntax_only')
            result['symbols'].append(value)
            callables.append((container.start_byte,container.end_byte,value['id'],value['qualified_name']))
    for node in nodes:
        if node.type in {'call_expression','new_expression'} and not damaged(node):
            callee = node.child_by_field_name('function') or node.child_by_field_name('constructor')
            args = node.child_by_field_name('arguments')
            enclosing = sorted((s for s in callables if s[0]<=node.start_byte and s[1]>=node.end_byte),key=lambda s:s[1]-s[0])
            result['calls'].append({'id':identity(path,'call_site',node),'callee_spelling':text(callee),
                                    'argument_spellings':[text(a) for a in args.named_children] if args is not None else [],
                                    'owner_id':enclosing[0][2] if enclosing else None,
                                    'owner_name':enclosing[0][3] if enclosing else None,
                                    'resolution':'unresolved','reason':'syntax_only_no_type_or_value_resolution',**span(node)})
        if language != 'cpp' and node.type == 'assignment_expression' and not damaged(node):
            left = node.child_by_field_name('left')
            right = node.child_by_field_name('right')
            if left is not None and left.type in {'member_expression','subscript_expression'}:
                result['bindings'].append({'id':identity(path,'property_assignment',node),
                    'left_spelling':text(left),'right_spelling':text(right),
                    'resolution':'syntax_only','execution_condition':'not_evaluated',**span(node)})
    return result
