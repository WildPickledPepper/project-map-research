"""Compose source iframe packaging, keyed delivery and API value projections."""
from copy import deepcopy
import json

from adapters.callback_queries import explain_callbacks, projections
from adapters.correlation_queries import request_key_bindings, signature
from adapters.frontend_graph import key
from adapters.frontend_queries import explain_frontend, overlap
from adapters.response_queries import explain_response
from adapters.socket_queries import explain_socket_receivers


def alternatives(v):
    if v.get('kind') == 'alternatives': return [x for a in v['values'] for x in alternatives(a)]
    return [v]


def project(value, path):
    result = []
    for v in alternatives(value):
        if not path: result.append(v); continue
        if v.get('kind') == 'object': result += project(v['fields'].get(path[0], {'kind': 'undefined'}), path[1:])
        elif v.get('kind') == 'input_path':
            if path[0] in v.get('overrides', {}): result += project(v['overrides'][path[0]], path[1:])
            else: result.append({**v, 'path': v['path'] + path, 'overrides': {}})
    return result


def clean(v):
    return v.get('kind') == 'input_path' and not v.get('gaps') and not v.get('overrides')


def wire_path(v, event_parameter):
    if not clean(v) or v['root'] != event_parameter: return None
    transforms = v.get('transforms', [])
    if len(transforms) != 1 or transforms[0]['kind'] != 'JSON.parse': return None
    prefix = transforms[0]['at_path']
    return v['path'][len(prefix):] if v['path'][:len(prefix)] == prefix else None


def through_handoff(handoff, template, suffix=()):
    if template.get('kind') == 'alternatives': return [v for t in template['values'] for v in through_handoff(handoff, t, suffix)]
    if not clean(template) or template['root'] not in handoff['target_parameters']: return []
    index = handoff['target_parameters'].index(template['root'])
    if index >= len(handoff['arguments']): return []
    return project(handoff['arguments'][index], template['path'] + list(suffix))


def constant_test(test, event_parameter, payload):
    values = []
    choices = alternatives(test)
    if any(wire_path(v, event_parameter) is not None for v in choices):
        choices = [v for v in choices if not (v.get('kind') == 'input_path' and v['root'] == event_parameter and not v.get('transforms'))]
    for v in choices:
        if v.get('kind') == 'constant': values.append(v['value']); continue
        path = wire_path(v, event_parameter)
        if path is not None:
            selected = project(payload, path)
            if not selected or any(x.get('kind') != 'constant' for x in selected): return None
            values += [x['value'] for x in selected]; continue
        if v.get('kind') == 'source_expression' and v['operation'] in {'===', '!=='}:
            left, right = [constant_test(x, event_parameter, payload) for x in v['inputs']]
            if left is None or right is None: return None
            values.append((left == right) == (v['operation'] == '===')); continue
        return None
    return values[0] if values and all(type(v) == type(values[0]) and v == values[0] for v in values) else None


UNKNOWN, UNDEFINED, OBJECT = object(), object(), object()


def evaluate_guard(test, resolve):
    out = []
    for v in alternatives(test):
        kind = v.get('kind')
        if kind == 'constant': out.append(v['value'])
        elif kind == 'undefined': out.append(UNDEFINED)
        elif kind == 'object': out.append(OBJECT)
        elif kind == 'input_path':
            selected = resolve(v)
            if not selected: return UNKNOWN
            out += [evaluate_guard(s, lambda _: []) for s in selected]
        elif kind == 'source_expression' and len(v['inputs']) == 2:
            a, b = [evaluate_guard(x, resolve) for x in v['inputs']]; op = v['operation']
            if a is UNKNOWN or b is UNKNOWN: return UNKNOWN
            if op in {'===', '!=='}:
                if a is OBJECT and b is OBJECT: return UNKNOWN
                out.append(((type(a) == type(b) and a == b) if a not in (OBJECT, UNDEFINED) and b not in (OBJECT, UNDEFINED) else a is b) == (op == '==='))
            elif op in {'&&', '||'}:
                truth = a is not UNDEFINED and a is not None and bool(a)
                out.append((b if truth else a) if op == '&&' else (a if truth else b))
            else: return UNKNOWN
        else: return UNKNOWN
    return out[0] if out and all(type(v) == type(out[0]) and v == out[0] for v in out) else UNKNOWN


def substitute(value, root, replacement):
    if value.get('kind') == 'input_path' and value['root'] == root:
        values = project(replacement, value['path'])
        return {'kind': 'alternatives', 'values': values} if len(values) != 1 else values[0]
    if value.get('kind') == 'object': return {**value, 'fields': {k: substitute(v, root, replacement) for k, v in value['fields'].items()}}
    if value.get('kind') == 'alternatives': return {**value, 'values': [substitute(v, root, replacement) for v in value['values']]}
    return value


def delivery_allowed(flow, bridge, socket_value):
    handoff = bridge['client_handoff']
    listener = next(l for l in flow['window_listeners'] if l['id'] == handoff['listener'])
    payload = substitute(bridge['reply_send']['payload']['value'], bridge['upstream_boundary']['id'], socket_value)
    def resolve(v):
        return [x for p in through_handoff(handoff, v) if wire_path(p, listener['event_parameter']) is not None
                for x in project(payload, wire_path(p, listener['event_parameter']))]
    for condition in bridge['client_delivery']['settlement']['conditions']:
        if 'when' not in condition: continue
        tests = [g['test'] for g in flow.get('guard_tests', []) if g['source_symbol'] == handoff['target'] and
                 (g['path'], g['line'], g['expression']) == (condition.get('path'), condition.get('line'), condition.get('expression'))]
        if any(isinstance(result := evaluate_guard(t, resolve), bool) and result != condition['when'] for t in tests): return False
    return True


def accepts(handoff, listener, payload):
    for condition in handoff['conditions']:
        result = constant_test(condition.get('test', {}), listener['event_parameter'], payload)
        if isinstance(result, bool) and result != condition.get('when', result): return False
    return True


def message_apis(graph, provider):
    matched = {r['message']: r for r in graph['protocol']['results'] if any(m['provider'] == provider for m in r['matches'])}
    return {e['source']: e for e in graph['edges'] if e['kind'] == 'EMITS_MESSAGE' and e['target'] in matched}


def iframe_links(graph, provider):
    flow = graph['return_flow']; boundaries = {b['id']: b for b in flow['boundaries']}
    listeners = {l['id']: l for l in flow['window_listeners'] if l['callback'] and not l['superseded_by']}
    callbacks = explain_callbacks(graph, max_deliveries=100000)['deliveries']; apis = message_apis(graph, provider)
    old_sends = {s['id']: s for s in graph['response_callbacks']['transmissions']}
    bindings = request_key_bindings(graph['response_callbacks']); found = {}
    for returned in flow['returns']:
        api = returned['source_symbol']
        if api not in apis or returned['entry'] != api: continue
        for api_value in alternatives(returned['value']):
            if not clean(api_value) or api_value['root'] not in boundaries: continue
            boundary = boundaries[api_value['root']]
            for delivery in callbacks:
                if delivery['registration']['entry'] != boundary['target'] or delivery['settlement']['mode'] != 'resolve': continue
                for outgoing in bindings:
                    if outgoing['registration'] != delivery['registration']['id'] or old_sends[outgoing['transmission']]['transport'] != 'window.postMessage': continue
                    requests = [s for s in flow['transmissions'] if s['entry'] == outgoing['entry'] and
                                s['source_site'] == old_sends[outgoing['transmission']]['source_site'] and s['payload']['kind'] == 'json_string']
                    for client_handoff in flow['handoffs']:
                        client_listener = listeners.get(client_handoff['listener'])
                        if not client_listener or client_listener['entry'] != api or client_handoff['target'] != delivery['settlement']['entry']: continue
                        if client_handoff['receiver_type'] != delivery['registration']['receiver_type']: continue
                        keys = [wire_path(v, client_listener['event_parameter']) for v in through_handoff(client_handoff, delivery['lookup']['key'])]
                        outputs = [wire_path(v, client_listener['event_parameter']) for v in through_handoff(client_handoff, delivery['settlement']['value'], api_value['path'])]
                        for reply in flow['transmissions']:
                            if reply['transport'] != 'window.postMessage' or reply['payload']['kind'] != 'json_string': continue
                            registration = next((b for b in flow['callback_bindings'] if b['entry'] == reply['entry'] and
                                any(e.get('kind') == 'callback_registration' and e['path'] == b['evidence'][0]['path'] and e['line'] == b['evidence'][0]['line'] for e in apis[api]['evidence'])), None)
                            if not registration: continue
                            for payload in alternatives(reply['payload']['value']):
                                if not accepts(client_handoff, client_listener, payload): continue
                                for server_handoff in flow['handoffs']:
                                    server_listener = listeners.get(server_handoff['listener'])
                                    if not server_listener or server_handoff['target'] != reply['entry'] or server_handoff['receiver_type'] != registration['receiver_type']: continue
                                    for request in requests:
                                        request_payload = request['payload']['value']
                                        if not accepts(server_handoff, server_listener, request_payload): continue
                                        # The returned number must copy the incoming request's wire key.
                                        preserved = [v for kp in keys if kp is not None for t in project(payload, kp)
                                            for v in through_handoff(server_handoff, t) if wire_path(v, server_listener['event_parameter']) == outgoing['wire_path']]
                                        request_keys = project(request_payload, outgoing['wire_path'])
                                        if not preserved or not any(signature(v) == signature(m['registration_key']) for v in request_keys for m in outgoing['matches']): continue
                                        # Reply destination is selected from a request field populated with window.name.
                                        destination = [v for s in reply['receiver'].get('selections', []) for v in through_handoff(server_handoff, s['key'])]
                                        routes = [v for d in destination if wire_path(d, server_listener['event_parameter']) is not None
                                            for v in project(request_payload, wire_path(d, server_listener['event_parameter']))
                                            if clean(v) and v['path'] == ['name'] and v['root'] == request['receiver'].get('root')]
                                        if not routes: continue
                                        for output in outputs:
                                            if output is None: continue
                                            for value in project(payload, output):
                                                source = boundaries.get(value.get('root'))
                                                if not clean(value) or not source or source['entry'] != reply['entry']: continue
                                                uid = key('iframe-return-link', api, outgoing['registration'], reply['id'], source['id'], value['path'])
                                                result = found.setdefault(uid, {'id': uid, 'api': api, 'api_return': returned,
                                                    'api_boundary': boundary, 'upstream_boundary': source, 'upstream_projection': value,
                                                    'request_key_binding': outgoing, 'client_delivery': delivery, 'callback_binding': registration,
                                                    'server_handoff': server_handoff, 'client_handoff': client_handoff,
                                                    'request_send': request, 'reply_send': reply, 'reply_value_path': output, 'source_window_name': routes,
                                                    'alternatives': [], 'evidence': returned['evidence'] + reply['evidence'],
                                                    'conditions': ['same_client_instance_and_live_registry_key', 'registered_framework_callback_is_active',
                                                        'parent_and_named_child_windows_match_deployment', 'target_origin_allows_message',
                                                        'window_handlers_remain_active', 'source_guards_and_fulfillment_path_selected'], 'runtime_delivery': 'unknown'})
                                                candidate = {'payload': payload, 'preserved_key': preserved, 'source_projection': value}
                                                if candidate not in result['alternatives']: result['alternatives'].append(candidate)
    return list(found.values())


def explain_return_bridge(graph, provider, *, field_path=None, state=None, max_links=100):
    if max_links < 1: raise ValueError('max_links must be positive')
    bridges = iframe_links(graph, provider); sockets = explain_socket_receivers(graph, provider=provider, max_links=100000)
    routes = explain_response(graph, provider); links = []; used = set()
    for bridge in bridges:
        frontend = explain_frontend(graph, api=bridge['api'], field_path=field_path, state=state)
        for receiver in sockets['receivers']:
            for delivery in receiver['deliveries']:
                if delivery['registration']['entry'] != bridge['upstream_boundary']['target'] or delivery['settlement']['mode'] != 'resolve': continue
                if not delivery_allowed(graph['return_flow'], bridge, delivery['settlement']['value']): continue
                for value in project(delivery['settlement']['value'], bridge['upstream_projection']['path']):
                    for projection in projections(value):
                        wire = projection['decoded_json_path']
                        if wire is None or projection['source'].get('gaps'): continue
                        for backend in sockets['backend_links']:
                            if backend['receiver_link'] != receiver['id']: continue
                            correlation = backend['key_correlation']
                            for route in routes['routes']:
                                if route['steps'][0]['call_site'] != correlation['response_send_site']['call_site'] or route['serializer'] != correlation['serializer']: continue
                                writes = []
                                for write in frontend['writes']:
                                    mappings = []
                                    for dep in write['matching_dependencies']:
                                        prefix = projection['output_path']
                                        if dep['path'][:len(prefix)] != prefix: continue
                                        selected_wire = wire + dep['path'][len(prefix):]
                                        fields = [f for f in route['field_mappings'] if overlap(selected_wire, f['wire_path'])]
                                        production = [p for p in route['production_links'] if overlap(selected_wire, p['wire_path'])]
                                        if fields: mappings.append({'consumer_dependency': dep, 'wire_path': selected_wire, 'fields': fields, 'production': production})
                                    if mappings or field_path is None and write['relationship'] == 'fulfillment_continuation' and write['matching_continuations']:
                                        writes.append({'write': write, 'value_mappings': mappings})
                                if not writes: continue
                                uid = key('return-to-state', bridge['id'], delivery['settlement']['id'], route['steps'][0]['call_site'], projection['output_path'], wire)
                                links.append({'id': uid, 'bridge': bridge['id'], 'receiver': receiver['id'], 'socket_delivery': delivery,
                                    'response_send_site': route['steps'][0], 'wire_to_api': projection, 'writes': writes,
                                    'conditions': route['conditions'] + bridge['conditions'], 'runtime_delivery': 'unknown'})
                                used.add(bridge['id'])
    entries = {b['api'] for b in bridges} | {b['reply_send']['entry'] for b in bridges}
    return {'snapshot': graph['snapshot'], 'source_commit': graph['source_commit'], 'provider': provider,
        'status': 'conditional_return_to_frontend_state' if links else 'unresolved', 'bridges': bridges[:max_links], 'links': links[:max_links],
        'total_bridges': len(bridges), 'total_links': len(links), 'field_path': field_path, 'state': state,
        'truncated': len(bridges) > max_links or len(links) > max_links or sockets['truncated'] or routes['truncated'] or
            any(e['truncated'] for e in graph['return_flow']['entries'] if e['source_symbol'] in entries),
        'gaps': [g for g in graph['return_flow']['diagnostics'] if g['entry'] in entries],
        'remaining': ['unresolved_encoding_and_queue_branches', 'runtime_connection_lifetime_and_value_assertions'],
        'runtime_delivery': 'unknown', 'limits': graph['return_flow']['limits']}
