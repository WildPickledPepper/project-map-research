"""Trace typed JSON values through source wrappers to deferred socket sends.

Reuses the C++ extractor, source type candidates and lexical visibility. Native
models cover RapidJSON Writer/StringBuffer, standard accessors and uWS Loop /
WebSocket. Application functions, variables and capture names are source data.
"""
from copy import deepcopy
import json
import re

from adapters.cpp_data import arguments
from adapters.cpp_facts import declared_name
from adapters.cpp_library_types import LibraryTypes
from adapters.cpp_value_types import split_template
from adapters.frontend_graph import key
from adapters.syntax_supplement import identity, text, walk


def unique(items):
    return list({json.dumps(x, sort_keys=True): x for x in items}.values())


def value(kind='unknown', spelling='', **extra):
    return {'kind': kind, 'value_type': spelling, 'traces': [], **extra}


def parameter_spelling(node):
    qualifiers = [text(c) for c in node.named_children if c.type == 'type_qualifier']
    dec = node.child_by_field_name('declarator'); name = declared_name(node)
    suffix = dec.text[:name.start_byte-dec.start_byte].decode() if dec and name else ''
    return ' '.join(qualifiers + [text(node.child_by_field_name('type')), suffix]).strip()


class Transmission:
    def __init__(self, data, *, max_steps=12000, max_depth=12, max_states=64):
        if min(max_steps, max_depth, max_states) < 1: raise ValueError('Budgets must be positive')
        self.d = data; self.x = data.x; self.types = LibraryTypes(self.x)
        self.max_steps = max_steps; self.max_depth = max_depth; self.max_states = max_states
        self.sources = {}; self.sends = []; self.gaps = []; self.entries = []; self.steps = 0
        from adapters.cpp_encoding import EncodingBuffers
        self.encoding = EncodingBuffers(self)

    def evidence(self, info, node): return self.d.evidence(info['path'], node)

    def native(self, v, info):
        return self.types.resolve(v.get('value_type', ''), v.get('type_path', info['path']), v.get('type_scope', info['scope']))

    def owners(self, v, info):
        spelling = re.sub(r'\b(const|volatile)\b', '', v.get('value_type', '')).strip().strip('&* ')
        head, args = split_template(spelling)
        if head in {'std::shared_ptr', 'std::weak_ptr', 'std::unique_ptr'} and len(args) == 1: spelling = args[0]
        return self.x.resolve_type(spelling, v.get('type_path', info['path']), v.get('type_scope', info['scope']))['names']

    def target_candidates(self, node, uid, info, actuals=None, receiver=None):
        found = set(self.d.targets(node, uid, info)); fn = node.child_by_field_name('function')
        if receiver is not None and fn and fn.type == 'field_expression':
            for owner in self.owners(receiver, info):
                for group in self.x.members(owner, text(fn.child_by_field_name('field'))): found.update(group)
        result = []
        for target in sorted(found):
            f = self.x.functions_by_id[target]
            if not self.x.nodes[target]['definition'] or len(f['parameter_nodes']) != len(arguments(node)): continue
            compatible = True
            for a, p in zip(actuals or [], f['parameter_nodes']):
                expected = value(spelling=parameter_spelling(p), type_path=f['path'], type_scope=f['scope'])
                names, wanted = set(self.owners(a, info)), set(self.owners(expected, f))
                closure = set(names); pending = list(names)
                while pending:
                    for base in self.x.base_names.get(pending.pop(), []):
                        if base not in closure: closure.add(base); pending.append(base)
                if names and wanted and not closure & wanted: compatible = False
                first, second = self.native(a, info), self.native(expected, f)
                if first and second and not first & second and not (first & self.types.JSON and second & self.types.JSON): compatible = False
            if compatible: result.append(target)
        return result

    def step(self, v, kind, info, node, conditions=(), **extra):
        record = {'kind': kind, 'source_symbol': info['uid'], 'evidence': [self.evidence(info, node)], **extra}
        return {**v, 'traces': [{**t, 'steps': t['steps'] + [record],
                               'conditions': unique(t['conditions'] + list(conditions))} for t in v.get('traces', [])]}

    def gap(self, kind, info, node, context, **extra):
        self.gaps.append({'kind': kind, 'entry': context['entry'], 'source_symbol': info['uid'],
                          'evidence': [self.evidence(info, node)], **extra})

    def source(self, node, info, context, *, targets=(), parameter=None):
        site = 'cpp:' + identity(info['path'], 'call_site', node) if parameter is None else None
        sid = key('cpp-json-source', context['entry'], info['uid'], node.start_byte, context['calls'])
        record = {'id': sid, 'entry': context['entry'], 'source_symbol': info['uid'], 'source_site': site,
                  'targets': list(targets), 'parameter': parameter, 'evidence': [self.evidence(info, node)]}
        self.sources[sid] = record
        return [{'source': sid, 'steps': [], 'conditions': list(context['conditions'])}]

    def run_function(self, uid, actuals, receiver, context):
        info = {**self.x.functions_by_id[uid], 'uid': uid}
        if uid in context['active'] or len(context['active']) >= self.max_depth:
            self.gap('recursion_or_depth_limit', info, info['container'], context); return []
        context = {**context, 'active': context['active'] + [uid]}
        env = {'this': receiver or value('object', '::'.join(info['scope']), instance=key('this', context['entry']))}
        for i, p in enumerate(info['parameter_nodes']):
            typ = parameter_spelling(p); v = actuals[i] if i < len(actuals) else value(spelling=typ)
            if i >= len(actuals) and self.types.is_json(typ, info['path'], info['scope']):
                v['traces'] = self.source(p, info, context, parameter=i)
            v = {**v, 'value_type': typ, 'type_path': info['path'], 'type_scope': info['scope']}
            env[text(declared_name(p))] = self.step(v, 'parameter_binding', info, p, context['conditions'], parameter=i)
        returned = []
        self.statement(info['container'].child_by_field_name('body'), [{'env': env, 'conditions': context['conditions']}], info, context, returned)
        return returned

    def evaluate(self, node, state, info, context):
        self.steps += 1
        if self.steps > self.max_steps:
            if self.steps == self.max_steps + 1: self.gap('analysis_budget_exhausted', info, node or info['container'], context)
            return value(reason='analysis_budget_exhausted')
        if node is None: return value(reason='missing_expression')
        env = state['env']; conditions = state['conditions']; kind = node.type
        if kind in {'identifier', 'this'}:
            if text(node) in env: return env[text(node)]
            field = self.d.field(text(node), '::'.join(info['scope']))
            if field and env['this'].get('instance'):
                return value('object', field['type'], type_path=field['path'], type_scope=field['owner'].split('::'),
                             instance=key('member', env['this'].get('instance'), field['id']), field=field['id'])
            return value(reason='unresolved_identifier')
        if kind in {'string_literal', 'number_literal', 'true', 'false', 'null', 'qualified_identifier'}:
            return value('literal', 'std::string' if kind == 'string_literal' else '', literal=text(node))
        if kind in {'parenthesized_expression', 'pointer_expression', 'condition_clause'}:
            return self.evaluate(node.named_children[-1], state, info, context) if node.named_children else value()
        if kind == 'lambda_expression':
            captures = node.child_by_field_name('captures'); captured = {}; records = []
            # Deferred reference captures require lifetime/reaching-write analysis.
            if re.match(r'\[\s*[=&]', text(captures)):
                self.gap('default_lambda_capture_not_expanded', info, node, context); return value()
            previous = captures.start_byte + 1
            for item in captures.named_children:
                name = text(item); mode = 'reference' if b'&' in captures.text[previous-captures.start_byte:item.start_byte-captures.start_byte] else 'copy'
                if item.type == 'lambda_capture_initializer':
                    name = text(item.child_by_field_name('left')); v = self.evaluate(item.child_by_field_name('right'), state, info, context)
                else: v = env.get(name, value(reason='capture_binding_unresolved'))
                previous = item.end_byte
                if mode == 'reference':
                    self.gap('deferred_reference_capture_unresolved', info, item, context, capture=name)
                    v = value(reason='deferred_reference_capture_unresolved')
                captured[name] = self.step(deepcopy(v), 'lambda_capture', info, item, conditions, mode=mode, capture=name)
                records.append({'name': name, 'mode': mode, 'evidence': [self.evidence(info, item)]})
            return value('lambda', node=node, captured=captured, capture_records=records)
        if kind == 'field_expression':
            base = self.evaluate(node.child_by_field_name('argument'), state, info, context)
            fields = [self.d.field(text(node.child_by_field_name('field')), owner) for owner in self.owners(base, info)]
            fields = [f for f in fields if f]
            if len(fields) == 1:
                f = fields[0]; return value('object', f['type'], type_path=f['path'], type_scope=f['owner'].split('::'),
                                         instance=key('member', base.get('instance'), f['id']), field=f['id'])
            return value(reason='member_value_not_expanded')
        if kind == 'assignment_expression':
            left = node.child_by_field_name('left'); v = self.evaluate(node.child_by_field_name('right'), state, info, context)
            if left.type == 'identifier':
                if text(node.child_by_field_name('operator')) != '=': v = value(reason='compound_assignment_not_expanded')
                env[text(left)] = self.step(v, 'assignment', info, node, conditions)
            else:
                self.encoding.invalidate([env[text(n)] for n in walk(left) if n.type == 'identifier' and text(n) in env], node, info, context)
                self.gap('nonlocal_assignment_not_expanded', info, node, context)
            return v
        if kind != 'call_expression': return value(reason='expression_not_expanded:' + kind)
        fn = node.child_by_field_name('function'); spelling = text(fn); args = arguments(node)
        actuals = [self.evaluate(a, state, info, context) for a in args]
        if spelling in {'std::move', 'std::forward'} and len(actuals) == 1: return actuals[0]
        if fn and fn.type == 'field_expression':
            receiver = self.evaluate(fn.child_by_field_name('argument'), state, info, context)
            method = text(fn.child_by_field_name('field')); native = self.native(receiver, info)
        else: receiver = None; method = spelling; native = set()
        encoded = self.encoding.call(spelling, node, actuals, receiver, method, state, info, context)
        if encoded is not None: return encoded
        if receiver and method == 'value' and re.match(r'(?:const\s+)?std::optional\s*<', receiver['value_type']):
            return self.step({**receiver, 'value_type': split_template(receiver['value_type'].strip('& '))[1][0]}, 'optional_value', info, node, conditions)
        if receiver and method == 'has_value' and re.match(r'(?:const\s+)?std::optional\s*<', receiver['value_type']): return value('scalar', 'bool')
        if receiver and method in {'c_str', 'data'} and native & {'std::string', 'std::string_view'}:
            return self.step(receiver, 'string_view', info, node, conditions)
        if receiver and method == 'lock' and receiver['value_type'].startswith('std::weak_ptr<'):
            return {**receiver, 'value_type': receiver['value_type'].replace('std::weak_ptr<', 'std::shared_ptr<', 1)}
        if spelling == 'shared_from_this' and not args:
            # Require the standard CRTP base declaration, not the method name alone.
            owner = '::'.join(info['scope'])
            bases = [b for cid in self.x.classes.get(owner, []) for b in self.x.nodes[cid]['base_spellings']]
            if any(re.match(r'std::enable_shared_from_this\s*<', b) for b in bases): return env['this']
        if receiver and native & self.types.JSON and method == 'Accept' and len(actuals) == 1 and actuals[0]['kind'] == 'writer':
            buffer = actuals[0]['buffer']
            buffer['payload'] = self.step(receiver, 'rapidjson_accept', info, node, conditions)
            return value('scalar', 'bool')
        if receiver and receiver['kind'] == 'buffer' and method == 'GetString':
            return self.step({**receiver.get('payload', value(reason='buffer_has_no_json')), 'value_type': 'std::string'}, 'rapidjson_buffer_string', info, node, conditions)
        if receiver and receiver['kind'] == 'buffer' and method == 'Clear': receiver.pop('payload', None); return value()
        if receiver and 'uWS::Loop' in native and method == 'defer' and len(actuals) == 1 and actuals[0]['kind'] == 'lambda':
            callback = actuals[0]; captures = deepcopy(callback['captured'])
            captures.setdefault('this', value(reason='this_not_captured'))
            deferred = {'kind': 'deferred_execution', 'model': 'uWS::Loop::defer', 'evidence': [self.evidence(info, node)],
                        'captures': callback['capture_records'], 'condition': 'callback_invoked_by_event_loop'}
            ctx = {**context, 'deferred': context['deferred'] + [deferred]}
            self.statement(callback['node'].child_by_field_name('body'), [{'env': captures, 'conditions': conditions}], info, ctx, [])
            return value()
        if receiver and 'uWS::WebSocket' in native and method == 'send' and actuals:
            payload = self.step(actuals[0], 'socket_send_argument', info, node, conditions)
            self.sends.append({'id': key('cpp-transmission', context['entry'], info['uid'], node.start_byte, context['calls'], len(self.sends)),
                'entry': context['entry'], 'source_symbol': info['uid'], 'source_site': 'cpp:' + identity(info['path'], 'call_site', node),
                'transport': 'uWS::WebSocket::send', 'receiver': {k: v for k, v in receiver.items() if k != 'traces'},
                'opcode': actuals[1].get('literal') if len(actuals) > 1 else 'uWS::OpCode::BINARY',
                'traces': payload['traces'], 'conditions': conditions, 'deferred': context['deferred'],
                'call_chain': context['calls'], 'evidence': [self.evidence(info, node)], 'runtime_execution': 'unknown'})
            return value('scalar')
        targets = self.target_candidates(node, info['uid'], info, actuals, receiver)
        json_targets = [t for t in targets if self.types.is_json(self.x.functions_by_id[t]['return_type'],
                        self.x.functions_by_id[t]['path'], self.x.functions_by_id[t]['scope'])]
        if json_targets:
            f = self.x.functions_by_id[json_targets[0]]
            return value('json', f['return_type'], type_path=f['path'], type_scope=f['scope'],
                         traces=self.source(node, info, {**context, 'conditions': conditions}, targets=json_targets))
        tracked = [t for a in actuals for t in a.get('traces', [])]
        if targets and tracked:
            outputs = []
            for target in targets:
                frame = {'caller': info['uid'], 'callee': target, 'evidence': [self.evidence(info, node)]}
                ctx = {**context, 'calls': context['calls'] + [frame], 'conditions': conditions}
                outputs += self.run_function(target, actuals, receiver or env['this'], ctx)
            typ = self.x.functions_by_id[targets[0]]['return_type']
            traces = [t for out in outputs for t in out['traces']]
            if self.types.resolve(typ, self.x.functions_by_id[targets[0]]['path'], self.x.functions_by_id[targets[0]]['scope']) & {'std::string', 'std::string_view'} and any(not out['traces'] for out in outputs):
                self.gap('source_return_has_unlinked_alternative', info, node, context,
                         sources=sorted({t['source'] for t in tracked}), conditions=conditions,
                         alternatives=[out.get('return_conditions', []) for out in outputs if not out['traces']])
            result = self.step(value('returned', typ, traces=unique(traces)), 'source_call_return', info, node, conditions, targets=targets)
        else:
            if tracked: self.gap('unresolved_call_with_payload', info, node, context, sources=sorted({t['source'] for t in tracked}), conditions=conditions)
            result = value(reason='call_return_not_expanded')
        self.encoding.invalidate([*actuals, *([receiver] if receiver else [])], node, info, context)
        for arg in [*actuals, *([receiver] if receiver else [])]:
            buffer = arg.get('buffer') if arg['kind'] == 'writer' else arg if arg['kind'] == 'buffer' else None
            if buffer is not None and 'payload' in buffer:
                buffer.pop('payload')
                self.gap('unmodeled_buffer_effect', info, node, context)
        if receiver and native & self.types.JSON and receiver.get('traces'):
            receiver['traces'] = []
            self.gap('unmodeled_json_receiver_effect', info, node, context)
        # Side effects through mutable arguments cannot retain stale payload facts.
        for index, arg in enumerate(args):
            mutable = not targets or any(index < len(self.x.functions_by_id[t]['parameter_nodes']) and
                any(c in parameter_spelling(self.x.functions_by_id[t]['parameter_nodes'][index]) for c in '&*') and
                'const' not in parameter_spelling(self.x.functions_by_id[t]['parameter_nodes'][index]) for t in targets)
            if mutable and arg.type == 'identifier' and actuals[index].get('traces'):
                env[text(arg)] = value(reason='mutable_argument_effect_not_expanded')
                self.gap('mutable_argument_effect_not_expanded', info, arg, context)
        return result

    def declaration(self, node, state, info, context):
        typ = text(node.child_by_field_name('type')); name = text(declared_name(node)); dec = node.child_by_field_name('declarator')
        native = self.types.resolve(typ, info['path'], info['scope']); init = dec.child_by_field_name('value') if dec else None
        if native & {'rapidjson::StringBuffer', 'rapidjson::GenericStringBuffer'}:
            v = value('buffer', typ)
        elif native & {'rapidjson::Writer', 'rapidjson::PrettyWriter'}:
            params = dec.child_by_field_name('parameters') if dec else None
            args = list(init.named_children) if init and init.type == 'argument_list' else list(params.named_children) if params else []
            buffer = state['env'].get(text(args[0])) if len(args) == 1 else None
            v = value('writer', typ, buffer=buffer) if buffer and buffer['kind'] == 'buffer' else value(reason='writer_buffer_unresolved')
        else:
            if init and init.type == 'argument_list': init = init.named_children[0] if len(init.named_children) == 1 else None
            v = self.evaluate(init, state, info, context)
            v = self.step(v, 'local_binding', info, node, state['conditions'], binding=name)
            if typ != 'auto': v = {**v, 'value_type': typ, 'type_path': info['path'], 'type_scope': info['scope']}
            if dec and dec.type == 'init_declarator' and '&' in text(dec.child_by_field_name('declarator')) and init and init.type == 'identifier' and v.get('traces'):
                # Source reference aliases need a shared mutable cell model.
                state['env'][text(init)] = value(reason='reference_alias_not_expanded')
                v = value(reason='reference_alias_not_expanded')
                self.gap('reference_alias_not_expanded', info, node, context)
        state['env'][name] = v

    def statement(self, node, states, info, context, returned):
        if node is None: return states
        if self.steps > self.max_steps: return []
        if len(states) > self.max_states:
            self.gap('state_budget_exhausted', info, node, context); states = states[:self.max_states]
        kind = node.type
        if kind in {'compound_statement', 'else_clause', 'preproc_else'}:
            shadowed = {text(declared_name(c)) for c in node.named_children if c.type == 'declaration'} if kind == 'compound_statement' else set()
            # Preserve each incoming scope separately, including its local bindings.
            if shadowed and len(states) > 1:
                return [s for incoming in states for s in self.statement(node, [incoming], info, context, returned)]
            original = dict(states[0]['env']) if states else {}
            for child in node.named_children:
                states = self.statement(child, states, info, context, returned)
                if not states: break
            for state in states:
                for name in shadowed:
                    if name in original: state['env'][name] = original[name]
                    else: state['env'].pop(name, None)
            return states
        if kind in {'if_statement', 'preproc_if', 'preproc_ifdef'}:
            condition = node.child_by_field_name('condition') or node.child_by_field_name('name')
            yes = node.child_by_field_name('consequence'); no = node.child_by_field_name('alternative')
            preproc = kind.startswith('preproc_'); out = []
            for s in states:
                if not preproc: self.evaluate(condition, s, info, context)
                for when, body in [(True, yes), (False, no)]:
                    branch = deepcopy(s); branch['conditions'] = unique(s['conditions'] + [{'kind': 'preprocessor' if preproc else 'branch',
                        'expression': text(condition), 'when': when, 'source_symbol': info['uid'], 'evidence': [self.evidence(info, node)]}])
                    branches = [branch]
                    if preproc and when:
                        for child in node.named_children:
                            if child != condition and child != no: branches = self.statement(child, branches, info, context, returned)
                    else: branches = self.statement(body, branches, info, context, returned)
                    out += branches
            return out
        out = []
        for state in states:
            if kind == 'declaration': self.declaration(node, state, info, context)
            elif kind == 'expression_statement':
                for child in node.named_children: self.evaluate(child, state, info, context)
            elif kind == 'return_statement':
                v = self.evaluate(node.named_children[0], state, info, context) if node.named_children else value()
                returned.append({**self.step(v, 'return_value', info, node, state['conditions']), 'return_conditions': state['conditions']}); continue
            elif kind in {'comment', 'preproc_def', 'preproc_call'}: pass
            else:
                self.gap('statement_not_expanded', info, node, context, statement=kind)
                # Unmodeled control/effects end this path instead of retaining stale values.
                continue
            out.append(state)
        return out

    def build(self):
        for uid, f in self.x.functions_by_id.items():
            if not self.x.nodes[uid]['definition'] or self.types.is_json(f['return_type'], f['path'], f['scope']): continue
            parameter_seed = any(self.types.is_json(parameter_spelling(p), f['path'], f['scope']) for p in f['parameter_nodes'])
            call_seed = any(any(self.types.is_json(self.x.functions_by_id[t]['return_type'], self.x.functions_by_id[t]['path'],
                            self.x.functions_by_id[t]['scope']) for t in self.target_candidates(n, uid, f))
                            for n in walk(f['container']) if n.type == 'call_expression')
            if not parameter_seed and not call_seed: continue
            self.entries.append(uid); self.steps = 0
            self.run_function(uid, [], None, {'entry': uid, 'active': [], 'calls': [], 'conditions': [], 'deferred': []})
        return {'version': '0.2.0', 'entries': self.entries, 'sources': list(self.sources.values()), 'transmissions': self.sends,
                'diagnostics': unique(self.gaps), 'budgets': {'max_steps_per_entry': self.max_steps, 'max_depth': self.max_depth, 'max_states': self.max_states},
                'limits': ['source_type_candidates', 'explicit_copy_captures_only', 'conditional_payload_lineage',
                           'unmodeled_mutations_and_returns_remain_gaps', 'receiver_identity_is_source_context',
                           'endpoint_pairing_not_implemented', 'runtime_execution_and_delivery_not_observed']}
