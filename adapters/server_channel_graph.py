"""Persist server registration, channel initialization and scoped session joins."""
from copy import deepcopy

from adapters.server_channel_queries import origin_links


def augment_server_channels(base, facts, flow, paths):
    if 'server_channels' in base: raise ValueError('Use a pre-server-channel graph')
    if not set(base['input_paths']) <= set(paths): raise ValueError('Inputs must include base inputs')
    graph = deepcopy(base); graph['server_channels'] = deepcopy(flow)
    nodes = {n['id']: n for n in graph['nodes']}; edges = graph['edges']
    for n in facts['nodes']: nodes.setdefault(n['id'], n)
    def node(r, kind):
        e = r['evidence'][0]
        nodes[r['id']] = {**r, 'kind': kind, 'name': kind, 'path': e['path'], 'line': e['line']}
    def edge(a, b, kind, r):
        if a not in nodes or b not in nodes: raise ValueError('Missing server channel endpoint')
        edges.append({'source': a, 'target': b, 'kind': kind, 'status': 'candidate',
            'conditions': r.get('conditions', []), 'evidence': r['evidence'], 'runtime_execution': 'unknown'})
    for o in flow['source_instances']['objects']: nodes.setdefault(o['id'], o)
    for group in ['registrations', 'listeners', 'allocations', 'channel_initializers', 'object_stores', 'member_getters', 'member_consumers']:
        for r in flow[group]:
            node(r, 'server_' + group.rstrip('s'))
            if 'member_record' in r and r['member'] not in nodes: node(r['member_record'], 'source_member_storage')
    for r in flow['registrations']: edge(r['source_symbol'], r['id'], 'REGISTERS_NATIVE_SERVER_BEHAVIOR', r)
    for r in flow['listeners']: edge(r['source_symbol'], r['id'], 'OBSERVES_SERVER_LISTEN', r)
    for r in flow['channel_initializers']:
        edge(r['origin']['registration'], r['id'], 'ACCEPTED_CHANNEL_INITIALIZES_SESSION', r)
        edge(r['allocation'], r['id'], 'ALLOCATED_SESSION_RECEIVES_CHANNEL', r)
        edge(r['id'], r['member'], 'INITIALIZES_SESSION_CHANNEL_MEMBER', r)
    for r in flow['object_stores']:
        edge(r['allocation'], r['id'], 'STORES_ALLOCATED_OBJECT', r)
        edge(r['id'], r['member'], 'WRITES_SESSION_STORAGE', r)
    for r in flow['member_getters']: edge(r['member'], r['id'], 'RETURNS_STORED_MEMBER', r)
    for r in flow['member_consumers']:
        edge(r['getter'], r['id'], 'MEMBER_GETTER_FEEDS_RECEIVER', r)
        edge(r['id'], r['call_site'], 'STORED_MEMBER_USED_AT_CALL', r)
    for r in origin_links(graph):
        node(r, 'server_channel_origin_link')
        edge(r['channel_initialization']['id'], r['id'], 'ACCEPTED_CHANNEL_HAS_STORED_SESSION', r)
        edge(r['store']['id'], r['id'], 'REQUIRES_SESSION_STORE', r)
        edge(r['id'], r['consumer']['id'], 'STORED_SESSION_REACHES_CONSUMER', r)
    graph['nodes'] = list(nodes.values()); graph['input_paths'] = list(paths)
    graph['snapshot'] = graph['source_commit'] + ':p3-data-v11'
    graph['extractors']['cpp_socket_origin'] = 'cpp_socket_origin/' + flow['version']
    graph['provenance']['server_channel_base_snapshot'] = base['snapshot']
    graph['diagnostics'] += flow['diagnostics']
    return graph
