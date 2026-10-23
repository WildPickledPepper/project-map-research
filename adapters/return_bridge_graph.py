"""Persist return packaging and conditional links into the shared graph."""
from copy import deepcopy
from adapters.callback_queries import projections
from adapters.return_bridge_queries import iframe_links


def augment_returns(base, facts):
    if 'return_flow' in base: raise ValueError('Use a pre-return-bridge snapshot')
    graph = deepcopy(base); flow = deepcopy(facts['return_flow']); graph['return_flow'] = flow
    nodes = {n['id']: n for n in graph['nodes']}
    for n in facts['nodes']: nodes.setdefault(n['id'], n)
    edges = graph['edges']
    def node(r, kind):
        e = r['evidence'][0]
        if r['id'] in nodes: raise ValueError('Return node identity collision: ' + r['id'])
        nodes[r['id']] = {**r, 'kind': kind, 'name': kind, 'path': e['path'], 'line': e['line']}
    def edge(a, b, kind, r):
        if a not in nodes or b not in nodes: raise ValueError('Missing return edge endpoint')
        edges.append({'source': a, 'target': b, 'kind': kind, 'status': 'candidate',
            'conditions': r.get('conditions', []), 'evidence': r['evidence'], 'runtime_execution': 'unknown'})
    for group in ['boundaries', 'returns', 'callback_bindings', 'transmissions', 'window_listeners', 'handoffs']:
        for r in flow[group]: node(r, 'source_return_' + group)
    for r in flow['boundaries']:
        edge(r['target'], r['id'], 'SOURCE_CALL_RETURN_BOUNDARY', r)
        for delivery in graph['response_callbacks']['settlements']:
            registration = next((g for g in graph['response_callbacks']['registrations'] if delivery.get('registry_context') and
                g['id'] == delivery['registry_context']['registration'] and g['entry'] == r['target']), None)
            if registration: edge(delivery['id'], r['id'], 'PROMISE_DELIVERY_FEEDS_RETURN_BOUNDARY', r)
    boundary_ids = {b['id'] for b in flow['boundaries']}
    for r in flow['returns']:
        edge(r['source_symbol'], r['id'], 'RETURNS_SOURCE_VALUE', r)
        for p in projections(r['value']):
            if p['source']['root'] in boundary_ids: edge(p['source']['root'], r['id'], 'RETURN_VALUE_PROPAGATES', r)
    for r in flow['handoffs']:
        edge(r['listener'], r['id'], 'WINDOW_EVENT_FEEDS_HANDLER', r)
        edge(r['id'], r['target'], 'DISPATCHES_WINDOW_MESSAGE', r)
    added = set()
    for provider in sorted({m['provider'] for r in graph['protocol']['results'] for m in r['matches']}):
        for r in iframe_links(graph, provider):
            if r['id'] in added: continue
            added.add(r['id']); node(r, 'iframe_return_bridge')
            for field, kind in [('upstream_boundary','REPLY_USES_FULFILLED_VALUE'), ('reply_send','REPLY_TRANSPORT_FEEDS_API'),
                                ('client_handoff','REQUIRES_WINDOW_DISPATCH'), ('callback_binding','REQUIRES_FRAMEWORK_CALLBACK')]:
                edge(r[field]['id'], r['id'], kind, r)
            edge(r['id'], r['api'], 'RETURN_BRIDGE_FULFILLS_API', r)
    graph['nodes'] = list(nodes.values()); graph['snapshot'] = graph['source_commit'] + ':p3-data-v12'
    graph['extractors']['typescript_return_flow'] = 'typescript_return_flow/' + flow['version']
    graph['provenance']['return_base_snapshot'] = base['snapshot']; graph['diagnostics'] += flow['diagnostics']
    return graph
