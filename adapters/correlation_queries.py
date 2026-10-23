"""Compose request-key origins with scoped decoder/copy/serializer evidence."""
import json
from adapters.field_queries import explain_writes
from adapters.response_queries import explain_response


def alternatives(value):
    if value.get('kind') == 'alternatives':
        return [x for child in value['values'] for x in alternatives(child)]
    return [value]


def signature(value):
    if value.get('gaps') or value.get('overrides'): return None
    if value.get('kind') == 'constant': return ('constant', json.dumps(value['value'], sort_keys=True))
    if value.get('kind') == 'input_path':
        return ('input', value['root'], tuple(value['path']),
                tuple((t['kind'], tuple(t['at_path'])) for t in value.get('transforms', [])))
    return None


def fields(value, path=()):
    for v in alternatives(value):
        if v['kind'] == 'json_string': yield from fields(v['value'], path)
        elif v['kind'] == 'object':
            for name, child in v['fields'].items(): yield from fields(child, (*path, name))
        elif v['kind'] == 'input_path' and v.get('overrides'):
            for name, child in v['overrides'].items(): yield from fields(child, (*path, name))
        else: yield list(path), v


def consistent(conditions):
    known = {}
    for c in conditions:
        if not isinstance(c, dict) or 'when' not in c: continue
        identity = (c.get('path'), c.get('line'), c.get('expression'))
        if identity in known and known[identity] != c['when']: return False
        known[identity] = c['when']
    return True


def request_key_bindings(flow):
    found = {}
    for reg in flow.get('registrations', []):
        for sent in flow.get('transmissions', []):
            if sent['entry'] != reg['entry'] or sent.get('promise_context') not in reg['promises']: continue
            for wire, value in fields(sent['payload']):
                for key in alternatives(reg['key']):
                    identity = signature(key)
                    if identity is None or identity != signature(value): continue
                    conditions = reg['conditions'] + sent['conditions'] + key.get('conditions', []) + value.get('conditions', [])
                    if not consistent(conditions): continue
                    uid = (reg['id'], sent['id'], tuple(wire))
                    record = found.setdefault(uid, {'registration': reg['id'], 'transmission': sent['id'], 'entry': reg['entry'],
                        'promise': sent['promise_context'], 'wire_path': wire, 'matches': [],
                        'conditions': ['same_request_invocation', 'serialization_preserves_key_value'],
                        'evidence': reg['evidence'] + sent['evidence']})
                    match = {'registration_key': key, 'sent_value': value, 'conditions': conditions}
                    if match not in record['matches']: record['matches'].append(match)
    return list(found.values())


def explain_correlation(graph, provider_id, max_links=100):
    if max_links < 0: raise ValueError('max_links must be nonnegative')
    provider = next(p for p in graph['protocol']['providers'] if p['id'] == provider_id)
    nodes = {n['id']: n for n in graph['nodes']}; flow = graph['response_callbacks']
    regs = {r['id']: r for r in flow['registrations']}; sends = {t['id']: t for t in flow.get('transmissions', [])}
    lookup_by_id = {l['id']: l for l in flow['lookups']}
    result = explain_response(graph, provider_id)
    messages = [(nodes[r['message']], match) for r in graph['protocol']['results'] for match in r['matches'] if match['provider'] == provider_id]
    roots = {r['id']: r for r in graph['data']['field_flow']['roots']}
    callees = {s['source_symbol']: {t for c in s['calls'] for t in c['targets']} for s in graph['data']['summaries']}
    reachable = set(); pending = list(provider['decoder_registration']['functions'])
    while pending:
        uid = pending.pop()
        if uid not in reachable: reachable.add(uid); pending.extend(callees.get(uid, []))
    bases = {}
    for e in graph['edges']:
        if e['kind'] == 'INHERITS': bases.setdefault(nodes[e['source']]['name'], set()).add(nodes[e['target']]['name'])

    def types(typ):
        while typ.get('name') in {'std::unique_ptr', 'std::shared_ptr'} and typ.get('arguments'): typ = typ['arguments'][0]
        found = set(typ.get('names', [])); todo = list(found)
        while todo:
            for parent in bases.get(todo.pop(), ()):
                if parent not in found: found.add(parent); todo.append(parent)
        return found

    def position(effect):
        return tuple(c.get('offset', -1) for c in effect['call_chain']) + (effect.get('offset', -1),)

    def overlaps(a, b): return a[:len(b)] == b or b[:len(a)] == a

    effects = {}; links = []; gaps = []
    for binding in request_key_bindings(flow):
        reg, sent = regs[binding['registration']], sends[binding['transmission']]
        requester = nodes[reg['entry']]
        scoped_messages = []
        for message, match in messages:
            at = sent['evidence'][0]
            if (message['path'], message['line']) != (at['path'], at['line']): continue
            events = message.get('flow_evidence', [])
            def transport(kind): return 'socket' if kind == 'WebSocket.send' else kind
            if not any(e.get('kind') == 'platform_send' and transport(e.get('transport')) == transport(sent['transport']) and
                       (e['path'], e['line']) == (at['path'], at['line']) for e in events): continue
            if not any(e.get('kind') == 'argument_transfer' and
                       (e.get('target', {}).get('path'), e.get('target', {}).get('line')) == (requester['path'], requester['line']) for e in events): continue
            scoped_messages.append((message, match))
        for settlement in flow['settlements']:
            context = settlement['registry_context']
            if not context or context['registration'] != reg['id']: continue
            lookup = lookup_by_id[context['lookup']]
            for key in alternatives(lookup['key']):
                transforms = key.get('transforms', [])
                if key.get('kind') != 'input_path' or not transforms or key.get('gaps'): continue
                prefix = transforms[-1]['at_path']
                if key['path'][:len(prefix)] != prefix: continue
                response_wire = key['path'][len(prefix):]
                for route in result['routes']:
                    handler = route['handler']
                    if handler not in effects: effects[handler] = explain_writes(graph, handler)
                    candidates = effects[handler]['effects']
                    if effects[handler]['truncated']: gaps.append({'kind': 'field_query_truncated', 'handler': handler})
                    for production in route['production_links']:
                        if production['wire_path'] != response_wire: continue
                        for effect in candidates:
                            if effect['write'] != production['write'] or effect['root'] != route['object_root']: continue
                            if effect['operation'] != '=' or len(effect['value_origins']) != 1 or not effect['value_origins'][0]: continue
                            origin = effect['value_origins'][0]; root = roots[origin['root']]
                            if root['kind'] != 'parameter' or root['source_symbol'] != handler: continue
                            before_send = route['steps'][0]['offset']
                            later = [e for e in candidates if e['root'] == effect['root'] and overlaps(e['selectors'], effect['selectors'])
                                     and position(e) > position(effect) and position(e)[0] < before_send]
                            if later:
                                gaps.append({'kind': 'later_field_write_blocks_key_copy', 'write': effect['write'], 'later': [e['write'] for e in later]}); continue
                            deref = ['pointee'] if root['mode'] == 'pointer' or root['type'].get('name') in {'std::unique_ptr', 'std::shared_ptr'} else []
                            for decoder in graph['data']['response_routing']['decoded_fields']:
                                if decoder['source_symbol'] not in reachable or not types(root['type']) & set(decoder['owner_types']): continue
                                if origin['selectors'] != deref + ['member:' + decoder['member']]: continue
                                if decoder['wire_fields'] != binding['wire_path']: continue
                                for message, match in scoped_messages:
                                    record = {'message': message['id'], 'provider': provider_id, 'request_key_binding': binding,
                                        'response_lookup': lookup, 'request_decoder': decoder, 'copy_effect': effect,
                                        'response_wire_path': response_wire, 'response_field_mapping': [m for m in route['field_mappings'] if m['wire_path'] == response_wire],
                                        'response_send_site': route['steps'][0], 'serializer': route['serializer'],
                                        'conditions': match['conditions'] + route['conditions'] + ['response_transport_pending', 'same_request_response_exchange'],
                                        'runtime_delivery': 'unknown'}
                                    if record not in links: links.append(record)
    return {'snapshot': graph['snapshot'], 'provider': provider_id, 'links': links[:max_links], 'total_links': len(links),
            'truncated': len(links) > max_links or result['truncated'] or any(r['truncated'] for r in effects.values()),
            'max_links': max_links, 'gaps': gaps, 'status': 'source_key_copy_candidates' if links else 'not_extracted',
            'remaining': ['C++ response transmission', 'endpoint and runtime instance correspondence',
                          'iframe response wrapping and final API return', 'conditional queue path'], 'runtime_delivery': 'unknown'}
