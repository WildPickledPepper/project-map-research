"""Persist deferred callback selections without collapsing request contexts."""
from copy import deepcopy
from adapters.frontend_graph import key
from adapters.correlation_queries import request_key_bindings


def augment_callbacks(base, facts):
    graph = deepcopy(base); flow = deepcopy(facts['response_flow'])
    nodes = {n['id']: n for n in graph['nodes']}
    for n in facts['nodes']: nodes.setdefault(n['id'], n)
    edges = graph['edges']

    def node(uid, kind, record, name):
        e = record['evidence'][0]
        nodes[uid] = {**record, 'id': uid, 'kind': kind, 'name': name, 'path': e['path'], 'line': e['line']}

    def edge(a, b, kind, record, conditions=None):
        if a not in nodes or b not in nodes: raise ValueError('Missing callback relation endpoint')
        edges.append({'source': a, 'target': b, 'kind': kind, 'status': 'candidate',
                      'evidence': record['evidence'], 'conditions': record.get('conditions', []) if conditions is None else conditions,
                      'runtime_execution': 'unknown'})

    for p in flow['promises']:
        node(p['id'], 'source_promise', p, 'Promise')
        edge(p['entry'], p['id'], 'CREATES_SOURCE_PROMISE', p)
    regs = {r['id']: r for r in flow['registrations']}
    lookups = {r['id']: r for r in flow['lookups']}
    for records, kind in [(flow['registrations'], 'callback_registration'), (flow['lookups'], 'callback_lookup'),
                          (flow['deletions'], 'callback_deletion')]:
        for r in records:
            mid = key('callback-registry', r['registry'], r['receiver_type'])
            node(mid, 'callback_registry', r, r['registry'])
            node(r['id'], kind, r, kind)
            edge(r['entry'], r['id'], 'OBSERVES_' + kind.upper(), r)
            edge(r['id'], mid, 'USES_CALLBACK_REGISTRY', r)
            for pid in r.get('promises', []): edge(r['id'], pid, 'RETAINS_PROMISE_RESOLVER', r)
    for index, s in enumerate(flow['settlements']):
        s['source_site'] = s['id']
        s['id'] = key('promise-settlement', s['entry'], s['id'], s['promise'], index)
        node(s['id'], 'promise_settlement', s, s['mode'])
        edge(s['entry'], s['id'], 'OBSERVES_PROMISE_SETTLEMENT', s)
        edge(s['id'], s['promise'], 'RESOLVES_PROMISE' if s['mode'] == 'resolve' else 'REJECTS_PROMISE', s)
        context = s['registry_context']
        if context:
            r, lookup = regs[context['registration']], lookups[context['lookup']]
            if (r['registry'], r['receiver_type']) != (lookup['registry'], lookup['receiver_type']):
                raise ValueError('Callback join crosses registry scope')
            if s['promise'] not in r['promises']: raise ValueError('Resolver belongs to another registration')
            edge(r['id'], lookup['id'], 'CANDIDATE_REGISTRY_VALUE', s)
            edge(lookup['id'], s['id'], 'SELECTED_CALLBACK_SETTLES', s)
    for t in flow.get('transmissions', []):
        node(t['id'], 'source_transmission', t, t['transport'])
        edge(t['entry'], t['id'], 'OBSERVES_TRANSMISSION', t)
    for update in flow.get('counter_updates', []):
        node(update['id'], 'source_counter_update', update, update['operation'])
        edge(update['entry'], update['id'], 'OBSERVES_COUNTER_UPDATE', update)
    flow['request_key_bindings'] = request_key_bindings(flow)
    for binding in flow['request_key_bindings']:
        uid = key('request-key-binding', binding['registration'], binding['transmission'], binding['wire_path'])
        node(uid, 'request_key_binding', binding, '/'.join(binding['wire_path']))
        edge(binding['registration'], uid, 'USES_SENT_KEY_SOURCE', binding)
        edge(uid, binding['transmission'], 'KEY_FIELD_IN_TRANSMISSION', binding)
    graph['nodes'] = list(nodes.values()); graph['response_callbacks'] = flow
    graph['snapshot'] = graph['source_commit'] + (':p3-data-v8' if flow['version'] != '0.1.0' else ':p3-data-v7')
    graph['provenance']['callback_base_snapshot'] = base['snapshot']
    graph['extractors']['typescript_response_flow'] = 'typescript_response_flow/' + flow['version']
    graph['diagnostics'] += flow['diagnostics']
    return graph
