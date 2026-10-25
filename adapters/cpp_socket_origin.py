"""Recover accepted-channel construction and scoped session storage from source.

Reuses the C++ type/instance extractors and bounded transmission interpreter.
Only uWS behavior fields and std binding/allocation APIs are library models.
"""
from copy import deepcopy
import re

from adapters.cpp_data import arguments, enclosing_function
from adapters.cpp_facts import declared_name
from adapters.cpp_control import predicates
from adapters.cpp_instances import extract_instances
from adapters.cpp_protocol import ProtocolExtractor, make_type
from adapters.cpp_transmission import Transmission, parameter_spelling, unique, value
from adapters.cpp_value_types import split_template
from adapters.frontend_graph import key
from adapters.syntax_supplement import cpp_scope, identity, text, walk


class SocketOrigins(Transmission):
    APPS = {'uWS::App', 'uWS::SSLApp', 'uWS::TemplatedApp'}
    BEHAVIORS = {'uWS::App::WebSocketBehavior', 'uWS::SSLApp::WebSocketBehavior'}

    def __init__(self, data, **budgets):
        super().__init__(data, **budgets)
        self.protocol = ProtocolExtractor(None, None, extractor=self.x, facts=data.facts, value_types=data.types)
        self.instances = extract_instances(data); self.accessors = {a['source_symbol']: a for a in self.instances['accessors']}
        self.registrations = []; self.listeners = []; self.allocations = []; self.channel_initializers = []; self.stores = []

    def own_field(self, node, info):
        if node is None: return None
        if node.type == 'field_expression' and text(node.child_by_field_name('argument')) != 'this': return None
        return self.d.receiver_field(node, info['uid'], info)

    def native(self, v, info):
        spelling = re.sub(r'\b(const|volatile)\b', '', v.get('value_type', '')).strip().strip('&* ')
        head, args = split_template(spelling)
        if head in {'std::unique_ptr', 'std::shared_ptr'} and len(args) == 1: spelling = args[0]
        return self.types.resolve(spelling, v.get('type_path', info['path']), v.get('type_scope', info['scope']))

    @staticmethod
    def describe(v):
        keys = {'kind', 'value_type', 'type_path', 'type_scope', 'instance', 'field', 'allocation', 'literal',
                'origin', 'targets', 'member_function', 'arguments', 'receiver', 'reason', 'evidence', 'return_conditions'}
        return {k: deepcopy(x) for k, x in v.items() if k in keys}

    @staticmethod
    def method(fn):
        return text(fn.child_by_field_name('field')).split('<', 1)[0] if fn and fn.type == 'field_expression' else None

    def visible_definition(self, uid, path):
        info = self.x.functions_by_id[uid]; visible = self.x.visibility.get(path, {path})
        return any(self.x.functions_by_id[d]['path'] in visible for d in self.x.functions[info['signature']])

    def argument_is_mutable(self, fn, index, targets, info):
        candidates = [self.x.functions_by_id[t] for t in targets]
        if not candidates and fn and fn.type in {'identifier', 'qualified_identifier'}:
            for q in self.protocol.qnames(text(fn), info['path'], info['scope'], self.protocol.functions):
                candidates += [f for u, f in self.protocol.functions[q] if self.visible_definition(u, info['path'])]
        spellings = []
        for f in candidates:
            parameter_list = f['node'].child_by_field_name('parameters')
            params = [p for p in parameter_list.named_children if p.type in {'parameter_declaration', 'optional_parameter_declaration',
                      'variadic_parameter_declaration'}] if parameter_list else f['parameter_nodes']
            if index < len(params): spellings.append(parameter_spelling(params[index]))
            elif params and '...' in text(params[-1]): spellings.append(parameter_spelling(params[-1]))
            else: return True
        # A value parameter cannot rebind the caller's variable. Object lifetime
        # and pointee mutations still remain runtime conditions in the result.
        return not spellings or any('&' in p and 'const' not in p for p in spellings)

    def bind_callback(self, node, state, info, context):
        args = arguments(node)
        if not args: return value(reason='empty_bind')
        spelling = text(args[0]).lstrip('& '); targets = []
        for name in self.protocol.qnames(spelling, info['path'], info['scope'], self.protocol.functions):
            targets += [uid for uid, _ in self.protocol.functions[name] if self.visible_definition(uid, info['path'])]
        bound = []
        for arg in args[1:]:
            placeholder = re.fullmatch(r'std::placeholders::_(\d+)', text(arg))
            bound.append({'kind': 'placeholder', 'index': int(placeholder[1]) - 1} if placeholder else self.describe(self.evaluate(arg, state, info, context)))
        return value('bound_callback', targets=sorted(set(targets)), arguments=bound, evidence=[self.evidence(info, node)])

    def open_callback(self, registration, callback, info, context):
        if callback.get('kind') != 'bound_callback':
            self.gap('open_callback_not_expanded', info, info['container'], context, registration=registration['id']); return
        for target in callback['targets']:
            callee = self.x.functions_by_id[target]; owner = '::'.join(callee['scope'])
            member = owner in self.x.classes; bound = callback['arguments']
            receiver = bound[0] if member and bound else None; bound = bound[1:] if member else bound
            if len(bound) != len(callee['parameter_nodes']): continue
            if member and (not receiver or owner not in self.owners(receiver, info)):
                self.gap('bound_receiver_type_unresolved', info, info['container'], context, callback=target); continue
            actuals = []; origins = []
            for index, (arg, param) in enumerate(zip(bound, callee['parameter_nodes'])):
                if arg['kind'] == 'placeholder' and arg['index'] == 0:
                    typ = parameter_spelling(param)
                    if 'uWS::WebSocket' not in self.native(value(spelling=typ), callee):
                        actuals.append(value(reason='accepted_channel_parameter_type_unresolved')); continue
                    origin = {'registration': registration['id'], 'callback': target, 'parameter': index,
                              'event_argument': 0, 'evidence': callback['evidence'] + [self.evidence(callee, param)]}
                    origins.append(origin)
                    actuals.append(value('accepted_channel', typ, origin=origin, evidence=origin['evidence']))
                elif arg['kind'] == 'placeholder': actuals.append(value(reason='open_event_argument_absent'))
                else: actuals.append(deepcopy(arg))
            if not origins: continue
            frame = {'caller': info['uid'], 'callee': target, 'kind': 'uWS_open_callback', 'evidence': callback['evidence']}
            condition = {'kind': 'native_open_callback', 'registration': registration['id'], 'callback': target,
                         'meaning': 'accepted_channel_delivered_to_bound_placeholder'}
            ctx = {**context, 'conditions': registration['conditions'] + [condition], 'calls': context['calls'] + [frame]}
            self.run_function(target, actuals, receiver, ctx)

    def construct(self, node, typ, actuals, state, info, context):
        aid = key('cpp-source-allocation', context['entry'], info['uid'], node.start_byte, context['calls'], len(self.allocations))
        native = self.native(value(spelling=typ), info)
        record = {'id': aid, 'entry': context['entry'], 'source_symbol': info['uid'], 'type': typ,
                  'conditions': state['conditions'], 'evidence': [self.evidence(info, node)]}
        self.allocations.append(record)
        result = value('app' if native & self.APPS else 'source_allocation', typ, instance=aid, allocation=aid,
                       type_path=info['path'], type_scope=info['scope'], evidence=record['evidence'])
        if not any(a.get('origin') for a in actuals): return result
        owners = self.x.resolve_type(typ, info['path'], info['scope'])['names']
        for owner in owners:
            constructors = list(self.d.functions.get(owner + '::' + owner.rsplit('::', 1)[-1], []))
            # Inline constructor declarators can be identifiers rather than
            # field_identifiers. Recover their class from lexical source scope.
            constructors += [(u, f) for u, f in self.x.functions_by_id.items() if self.x.nodes[u]['definition'] and
                not f['return_type'] and f['signature'][0] == owner.rsplit('::', 1)[-1] and
                '::'.join(cpp_scope(f['container'])) == owner]
            for uid, constructor in constructors:
                if len(constructor['parameter_nodes']) != len(actuals) or not self.visible_definition(uid, info['path']): continue
                if uid in context['active'] or len(context['active']) >= self.max_depth:
                    self.gap('recursion_or_depth_limit', info, node, context); continue
                if any(a.get('origin') and 'uWS::WebSocket' not in self.native(value(spelling=parameter_spelling(p)), constructor)
                       for a, p in zip(actuals, constructor['parameter_nodes'])): continue
                ctor = {**constructor, 'uid': uid, 'scope': owner.split('::')}; env = {'this': result}; bindings = {}
                for index, (p, arg) in enumerate(zip(ctor['parameter_nodes'], actuals)):
                    env[text(declared_name(p))] = {**arg, 'value_type': parameter_spelling(p), 'parameter_index': index,
                                                  'type_path': ctor['path'], 'type_scope': ctor['scope']}
                for init in ctor['container'].named_children:
                    if init.type != 'field_initializer_list': continue
                    for field_init in init.named_children:
                        if field_init.type != 'field_initializer' or not field_init.named_children: continue
                        name = text(field_init.named_children[0]); field = self.d.field(name, owner,path=ctor['path'])
                        argv = next((c for c in field_init.named_children if c.type in {'argument_list', 'initializer_list'}), None)
                        if not field or not argv or len(argv.named_children) != 1: continue
                        val = self.evaluate(argv.named_children[0], {'env': env, 'conditions': state['conditions']}, ctor, context)
                        env['@field:' + field['id']] = val; bindings[name] = (field, field_init)
                frame = {'caller': info['uid'], 'callee': uid, 'kind': 'constructor_argument_transfer', 'evidence': record['evidence']}
                ctx = {**context, 'conditions': state['conditions'], 'active': context['active'] + [uid], 'calls': context['calls'] + [frame]}
                states = self.statement(ctor['container'].child_by_field_name('body'), [{'env': env, 'conditions': state['conditions']}], ctor, ctx, [])
                for current in states:
                    for name, (field, field_init) in bindings.items():
                        val = current['env'].get('@field:' + field['id'], {})
                        if not val.get('origin') or 'uWS::WebSocket' not in self.native(value(spelling=field['type'], type_path=field['path'], type_scope=field['owner'].split('::')), ctor): continue
                        self.channel_initializers.append({'id': key('accepted-channel-member', aid, uid, field['id'], len(self.channel_initializers)),
                            'entry': context['entry'], 'allocation': aid, 'constructed_type': owner, 'constructor': uid,
                            'member': field['id'], 'member_record': field, 'origin': val['origin'],
                            'parameter': val.get('parameter_index'), 'conditions': current['conditions'],
                            'evidence': record['evidence'] + [self.evidence(ctor, field_init)], 'call_chain': ctx['calls']})
        return result

    def evaluate(self, node, state, info, context):
        if node is None or self.steps > self.max_steps: return super().evaluate(node, state, info, context)
        self.steps += 1
        field = self.own_field(node, info)
        if field and '@field:' + field['id'] in state['env']: return state['env']['@field:' + field['id']]
        if node.type == 'lambda_expression':
            return value('source_callback', reason='lambda_callback_not_expanded', evidence=[self.evidence(info, node)])
        if node.type == 'initializer_list':
            fields = {}
            for pair in node.named_children:
                if pair.type != 'initializer_pair': continue
                designator = text(pair.child_by_field_name('designator')).lstrip('.')
                fields[designator] = self.evaluate(pair.child_by_field_name('value'), state, info, context)
            return value('designated_fields', fields=fields, evidence=[self.evidence(info, node)])
        if node.type == 'assignment_expression':
            left = node.child_by_field_name('left'); field = self.own_field(left, info)
            if left.type == 'field_expression' and not field:
                receiver = self.evaluate(left.child_by_field_name('argument'), state, info, context)
                if receiver.get('kind') in {'behavior', 'designated_fields'}:
                    val = self.evaluate(node.child_by_field_name('right'), state, info, context)
                    if text(node.child_by_field_name('operator')) != '=': val = value(reason='compound_behavior_assignment')
                    receiver['fields'][text(left.child_by_field_name('field'))] = val
                    return val
            if field:
                val = self.evaluate(node.child_by_field_name('right'), state, info, context)
                if text(node.child_by_field_name('operator')) != '=': val = value(reason='compound_member_assignment_not_expanded')
                state['env']['@field:' + field['id']] = val
                if val.get('allocation') and val['kind'] == 'source_allocation':
                    self.stores.append({'id': key('allocated-object-store', context['entry'], info['uid'], node.start_byte, val['allocation'], len(self.stores)),
                        'entry': context['entry'], 'source_symbol': info['uid'], 'member': field['id'], 'member_record': field,
                        'receiver_instance': state['env']['this'].get('instance'), 'allocation': val['allocation'],
                        'conditions': state['conditions'], 'evidence': [self.evidence(info, node)], 'call_chain': context['calls']})
                return val
        if node.type != 'call_expression': return super().evaluate(node, state, info, context)
        fn = node.child_by_field_name('function'); spelling = text(fn); args = arguments(node); method = self.method(fn)
        if spelling == 'std::bind': return self.bind_callback(node, state, info, context)
        typ = make_type(node)
        if typ: return self.construct(node, typ, [self.evaluate(a, state, info, context) for a in args], state, info, context)
        actuals = [self.evaluate(a, state, info, context) for a in args]
        if spelling in {'std::move', 'std::forward'} and len(actuals) == 1: return actuals[0]
        receiver = self.evaluate(fn.child_by_field_name('argument'), state, info, context) if method else None
        native = self.native(receiver, info) if receiver else set()
        if native & self.APPS and method in {'ws', 'listen'}:
            values = actuals
            record = {'id': key('server-' + method, context['entry'], info['uid'], node.start_byte, len(self.registrations) + len(self.listeners)),
                'entry': context['entry'], 'source_symbol': info['uid'], 'app': self.describe(receiver),
                'conditions': state['conditions'], 'evidence': [self.evidence(info, node)], 'call_chain': context['calls']}
            if method == 'listen':
                record['arguments'] = [self.describe(v) for v in values]; self.listeners.append(record)
            elif len(values) == 2:
                choices = values[1].get('alternatives', [values[1]])
                for behavior in choices:
                    if behavior['kind'] != 'behavior':
                        self.gap('websocket_behavior_unresolved', info, node, context); continue
                    selected = {k: self.describe(v) for k, v in behavior['fields'].items() if k in {'open', 'message', 'close'}}
                    registration = {**record, 'id': record['id'] + ':' + str(len(self.registrations)), 'route': self.describe(values[0]),
                        'callbacks': selected, 'behavior_evidence': behavior.get('evidence', []),
                        'conditions': unique(state['conditions'] + behavior.get('return_conditions', []))}
                    self.registrations.append(registration)
                    self.open_callback(registration, selected.get('open', {}), info, context)
            return receiver
        targets = self.target_candidates(node, info['uid'], info, actuals, receiver)
        if targets and all(t in self.accessors for t in targets):
            choices = {self.accessors[t]['instance'] for t in targets}
            if len(choices) == 1:
                f = self.x.functions_by_id[targets[0]]
                return value('object', f['return_type'], type_path=f['path'], type_scope=f['scope'], instance=choices.pop())
        behavior_targets = [t for t in targets if self.native(value(spelling=self.x.functions_by_id[t]['return_type']), self.x.functions_by_id[t]) & self.BEHAVIORS]
        if behavior_targets or targets and any(a.get('allocation') or a.get('origin') for a in actuals):
            outputs = []
            for target in behavior_targets or targets:
                frame = {'caller': info['uid'], 'callee': target, 'evidence': [self.evidence(info, node)]}
                outputs += self.run_function(target, actuals, receiver or state['env']['this'],
                    {**context, 'conditions': state['conditions'], 'calls': context['calls'] + [frame]})
            for index, (arg, actual) in enumerate(zip(args, actuals)):
                if arg.type == 'identifier' and (actual.get('origin') or actual.get('allocation')) and self.argument_is_mutable(fn, index, targets, info):
                    state['env'][text(arg)] = value(reason='reference_effect_not_transferred')
                    self.gap('reference_effect_not_transferred', info, node, context)
            if outputs:
                return outputs[0] if len(outputs) == 1 else value('alternatives', alternatives=outputs)
            return value(reason='void_or_unresolved_source_return')
        # A call whose implementation was not interpreted must not keep a stale
        # mutable behavior, channel reference, or source allocation argument.
        for index, (arg, actual) in enumerate(zip(args, actuals)):
            tracked = actual.get('kind') in {'behavior', 'designated_fields'} or actual.get('origin') or actual.get('allocation')
            mutable = self.argument_is_mutable(fn, index, targets, info)
            if tracked and mutable and arg.type == 'identifier':
                state['env'][text(arg)] = value(reason='unexpanded_mutable_argument')
                self.gap('unexpanded_mutable_argument', info, node, context)
        return value(reason='call_return_not_expanded')

    def declaration(self, node, state, info, context):
        typ = text(node.child_by_field_name('type'))
        if self.native(value(spelling=typ), info) & self.BEHAVIORS:
            dec = node.child_by_field_name('declarator'); init = dec.child_by_field_name('value') if dec else None
            v = self.evaluate(init, state, info, context)
            if v['kind'] == 'designated_fields' or init is None:
                v = {**v, 'kind': 'behavior', 'value_type': typ, 'fields': v.get('fields', {})}
            state['env'][text(declared_name(node))] = deepcopy(v); return
        super().declaration(node, state, info, context)
        name = text(declared_name(node)); v = state['env'].get(name, {})
        if v.get('kind') == 'behavior' and '&' not in text(node.child_by_field_name('declarator')):
            state['env'][name] = deepcopy(v)

    def getters(self):
        result = []
        for uid, info in self.x.functions_by_id.items():
            if not self.x.nodes[uid]['definition']: continue
            for ret in walk(info['container']):
                if ret.type != 'return_statement' or not ret.named_children or enclosing_function(ret) != info['container']: continue
                node = ret.named_children[0]
                smart_get = node.type == 'call_expression' and self.method(node.child_by_field_name('function')) == 'get' and not arguments(node)
                if smart_get:
                    node = node.child_by_field_name('function').child_by_field_name('argument')
                field = self.own_field(node, {**info, 'uid': uid})
                if not field: continue
                if smart_get and split_template(field['type'])[0] not in {'std::shared_ptr', 'std::unique_ptr'}: continue
                result.append({'id': key('member-getter', uid, ret.start_byte), 'source_symbol': uid,
                    'member': field['id'], 'member_record': field, 'conditions': predicates(ret), 'evidence': [self.evidence(info, ret)]})
        return result

    def member_consumers(self, getters):
        by_target = {}
        for getter in getters: by_target.setdefault(getter['source_symbol'], []).append(getter)
        contexts = {c['call_site']: c for c in self.instances['calls']}; result = []
        for uid, info in self.x.functions_by_id.items():
            if not self.x.nodes[uid]['definition']: continue
            for call in walk(info['container']):
                if call.type != 'call_expression' or enclosing_function(call) != info['container']: continue
                fn = call.child_by_field_name('function')
                if not fn or fn.type != 'field_expression': continue
                receiver = fn.child_by_field_name('argument'); init = receiver
                if receiver.type == 'identifier': init = self.protocol.local_initializer(text(receiver), receiver, info)
                if init is None or init.type != 'call_expression': continue
                if receiver.type == 'identifier':
                    mutators = [n for n in walk(info['container']) if n.type == 'call_expression' and init.end_byte <= n.start_byte < call.start_byte and
                        any(text(a).lstrip('& ') == text(receiver) and self.argument_is_mutable(n.child_by_field_name('function'), i,
                            self.d.targets(n, uid, info), info) for i, a in enumerate(arguments(n)))]
                    if mutators: continue
                site = 'cpp:' + identity(info['path'], 'call_site', init)
                for target in self.d.targets(init, uid, info):
                    for getter in by_target.get(target, []):
                        field = getter['member_record']
                        declared_receiver = value(spelling=field['type'], type_path=field['path'], type_scope=field['owner'].split('::'))
                        candidates = set(self.d.targets(call, uid, info))
                        for owner in self.owners(declared_receiver, info):
                            for group in self.x.members(owner, text(fn.child_by_field_name('field'))): candidates.update(group)
                        changed = True
                        while changed:
                            previous = len(candidates)
                            for edge in self.d.facts['edges']:
                                if edge['kind'] in {'OVERRIDE_CANDIDATE', 'DECLARES_DEFINITION'} and edge['source'] in candidates:
                                    candidates.add(edge['target'])
                            changed = len(candidates) != previous
                        candidates = sorted(t for t in candidates if self.x.nodes[t]['definition'] and
                            len(self.x.functions_by_id[t]['parameter_nodes']) == len(arguments(call)))
                        for instance in contexts.get(site, {}).get('instances', []):
                            result.append({'id': key('stored-member-consumer', uid, call.start_byte, getter['id'], instance),
                                'source_symbol': uid, 'call_site': 'cpp:' + identity(info['path'], 'call_site', call),
                                'targets': candidates, 'getter': getter['id'], 'getter_symbol': target,
                                'member': getter['member'], 'receiver_instance': instance,
                                'conditions': predicates(call), 'evidence': [self.evidence(info, init), self.evidence(info, call)]})
        return result

    def build(self):
        for uid, f in self.x.functions_by_id.items():
            if not self.x.nodes[uid]['definition']: continue
            if not any(n.type == 'call_expression' and self.method(n.child_by_field_name('function')) in {'ws', 'listen'} for n in walk(f['container'])): continue
            self.entries.append(uid); self.steps = 0
            self.run_function(uid, [], None, {'entry': uid, 'active': [], 'calls': [], 'conditions': [], 'deferred': []})
        getters = self.getters()
        return {'version': '0.1.0', 'entries': self.entries, 'registrations': self.registrations, 'listeners': self.listeners,
                'allocations': self.allocations, 'channel_initializers': self.channel_initializers, 'object_stores': self.stores,
                'member_getters': getters, 'member_consumers': self.member_consumers(getters),
                'source_instances': self.instances, 'diagnostics': unique(self.gaps),
                'budgets': {'max_steps_per_entry': self.max_steps, 'max_depth': self.max_depth, 'max_states': self.max_states},
                'limits': ['source_type_and_constructor_candidates', 'std_bind_open_callbacks', 'same_runtime_app_and_accepted_session_required',
                           'stored_object_lifetime_and_replacement_not_solved', 'unsupported_callbacks_and_control_flow_keep_unknown',
                           'actual_listening_and_network_connection_not_observed']}
