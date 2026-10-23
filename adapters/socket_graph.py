"""Persist socket construction and receive bindings alongside earlier facts."""
from copy import deepcopy

from adapters.frontend_graph import key
from adapters.socket_queries import channel_identity, receiver_links


def augment_sockets(base, facts):
    if 'socket_flow' in base: raise ValueError('Use the pre-socket-binding graph')
    graph = deepcopy(base); flow = deepcopy(facts['socket_flow']); graph['socket_flow'] = flow
    nodes = {n['id']: n for n in graph['nodes']}
    for n in facts['nodes']: nodes.setdefault(n['id'], n)
    edges = graph['edges']

    def node(record, kind, name):
        e = record['evidence'][0]
        nodes[record['id']] = {**record, 'kind': kind, 'name': name, 'path': e['path'], 'line': e['line']}

    def edge(a, b, kind, record, **extra):
        if a not in nodes or b not in nodes: raise ValueError('Missing socket relation endpoint')
        edges.append({'source': a, 'target': b, 'kind': kind, 'status': 'candidate', 'evidence': record['evidence'],
                      'conditions': record.get('conditions', []), 'runtime_execution': 'unknown', **extra})

    def channel(record, value):
        identity = channel_identity(value)
        if not identity: return None
        uid = key('source-socket-channel', identity)
        node({'id': uid, 'identity': [list(v) if isinstance(v, tuple) else v for v in identity], 'evidence': record['evidence']}, 'source_socket_channel', 'WebSocket channel')
        return uid

    for group, kind in [('creations', 'source_socket_creation'), ('channel_bindings', 'source_socket_assignment'),
                        ('listener_bindings', 'source_socket_listener'), ('transmissions', 'source_socket_send')]:
        for r in flow[group]:
            node(r, kind, kind); edge(r['entry'], r['id'], 'OBSERVES_' + kind.upper(), r)
            if group == 'channel_bindings':
                ch = channel(r, r['channel'])
                if ch: edge(r['id'], ch, 'ASSIGNS_SOCKET_CHANNEL', r)
                if r['value']['kind'] == 'native_socket': edge(r['value']['allocation'], r['id'], 'SOCKET_CREATION_ASSIGNED', r)
            elif group == 'listener_bindings':
                ch = channel(r, r['channel'])
                if ch: edge(ch, r['id'], 'SETS_SOCKET_MESSAGE_HANDLER', r)
                if r['callback']: edge(r['id'], r['callback'], 'INSTALLS_MESSAGE_CALLBACK', r, superseded_by=r['superseded_by'])
            elif group == 'transmissions':
                ch = channel(r, r['receiver'])
                if ch: edge(r['id'], ch, 'SENDS_ON_SOCKET_CHANNEL', r)
    for link in receiver_links(graph):
        node(link, 'socket_receiver_link', 'request channel to response lookup')
        edge(link['request_send']['id'], link['id'], 'REQUEST_CHANNEL_SELECTS_RECEIVER', link)
        edge(link['listener']['id'], link['id'], 'REQUIRES_SOCKET_HANDLER_BINDING', link)
        for lookup in {d['lookup']['id'] for d in link['deliveries']}: edge(link['id'], lookup, 'EVENT_PARAMETER_FEEDS_LOOKUP', link)
    graph['nodes'] = list(nodes.values()); graph['snapshot'] = graph['source_commit'] + ':p3-data-v10'
    graph['extractors']['typescript_socket_flow'] = 'typescript_socket_flow/' + flow['version']
    graph['provenance']['socket_base_snapshot'] = base['snapshot']; graph['diagnostics'] += flow['diagnostics']
    return graph
