"""Explain const bool member guards using declarations and source constructors."""
from adapters.cpp_facts import declared_name
from adapters.frontend_graph import key
from adapters.syntax_supplement import cpp_scope, text, walk


def extract_conditions(data):
    x = data.x; constants = {}; guards = []
    for field in data.fields.values():
        if field['type'] != 'bool': continue
        declarations=field.get('declarations',[])
        if any(d['conditions'] for d in declarations):
            if not all('const' in d['qualifiers'] for d in declarations):continue
            constants[field['id']]={'id':key('const-member-value',field['id']),'field':field,'value':None,'default_value':None,
                'status':'configuration_dependent','constructors':[],'missing_constructors':[],'evidence':field['evidence'],
                'conditions':['member_declaration_requires_selected_preprocessor_context']}
            continue
        node = next((n for n in walk(x.units[field['path']]['tree'].root_node)
                     if n.type == 'field_declaration' and n.start_point[0] + 1 == field['line']
                     and text(declared_name(n)) == field['name']), None)
        if node is None or 'const' not in [text(c) for c in node.named_children if c.type == 'type_qualifier']: continue
        default = node.child_by_field_name('default_value')
        if default is None or default.type not in {'true', 'false'}: continue
        owner = field['owner']; leaf = owner.rsplit('::', 1)[-1]
        ctors = [(uid, f) for uid, f in x.functions_by_id.items() if not f['return_type'] and
                 (f['signature'][0] == owner + '::' + leaf or
                  f['signature'][0] == leaf and '::'.join(cpp_scope(f['container'])) == owner)]
        definitions = [(u, f) for u, f in ctors if x.nodes[u]['definition']]
        missing = [u for u, f in ctors if not any(d['signature'][1:] == f['signature'][1:] for _, d in definitions)]
        values = []; evidence = list(field['evidence'])
        for uid, f in definitions:
            chosen = default
            for c in f['container'].named_children:
                if c.type != 'field_initializer_list': continue
                for init in c.named_children:
                    if init.type != 'field_initializer' or not init.named_children: continue
                    name = text(init.named_children[0])
                    if name == leaf: chosen = None  # Delegation requires a constructor call graph.
                    if name == field['name']:
                        args = next((a for a in init.named_children if a.type in {'argument_list', 'initializer_list'}), None)
                        chosen = args.named_children[0] if args is not None and len(args.named_children) == 1 else None
                        evidence.append(data.evidence(f['path'], init))
            values.append(chosen.type == 'true' if chosen is not None and chosen.type in {'true', 'false'} else None)
            evidence.append(data.evidence(f['path'], f['container']))
        resolved = bool(values) and not missing and all(v is not None and v == values[0] for v in values)
        constants[field['id']] = {'id': key('const-member-value', field['id']), 'field': field,
            'value': values[0] if resolved else None, 'default_value': default.type == 'true',
            'status': 'source_const_member' if resolved else 'constructor_dependent',
            'constructors': [u for u, _ in definitions], 'missing_constructors': missing,
            'evidence': evidence, 'conditions': ['all_relevant_constructor_definitions_in_input', 'defined_cpp_behavior']}
    for uid, info in x.functions_by_id.items():
        if not x.nodes[uid]['definition']: continue
        for node in walk(info['container']):
            if node.type not in {'if_statement', 'while_statement'}: continue
            expr = node.child_by_field_name('condition'); negated = False
            while expr is not None and expr.type in {'condition_clause', 'parenthesized_expression'}:
                expr = expr.named_children[-1] if expr.named_children else None
            if expr is not None and expr.type == 'unary_expression' and text(expr.child_by_field_name('operator')) == '!':
                negated = True; expr = expr.child_by_field_name('argument')
            field = data.receiver_field(expr, uid, info)
            constant = constants.get(field['id']) if field else None
            if not constant: continue
            known = constant['status'] == 'source_const_member'
            guards.append({'id': key('const-member-guard', uid, node.start_byte), 'source_symbol': uid,
                'constant': constant['id'], 'kind': node.type, 'expression': text(node.child_by_field_name('condition')),
                'value': (not constant['value'] if negated else constant['value']) if known else None,
                'status': constant['status'], 'evidence': [data.evidence(info['path'], node)],
                'branches': [{'when': b, 'reachable': b == (not constant['value'] if negated else constant['value']) if known else None}
                             for b in [True, False]]})
    return {'version': '0.1.0', 'constants': list(constants.values()), 'guards': guards}
