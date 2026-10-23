"""Attach source JSON-to-send evidence to an existing, same-version graph."""
from copy import deepcopy


def augment_transmission(base, facts, flow, paths):
    if 'cpp_transmission' in base: raise ValueError('Rebuild from the pre-transmission snapshot')
    if not set(base['input_paths']) <= set(paths): raise ValueError('Transmission inputs must include base inputs')
    graph = deepcopy(base); nodes = {n['id']: n for n in graph['nodes']}
    for n in facts['nodes']: nodes.setdefault(n['id'], n)
    edges = graph['edges']; flow = deepcopy(flow)

    def add_node(record, kind, name):
        e = record['evidence'][0]
        nodes[record['id']] = {**record, 'kind': kind, 'name': name, 'path': e['path'], 'line': e['line']}

    def edge(a, b, kind, evidence, conditions=(), **extra):
        if a not in nodes or b not in nodes: raise ValueError('Missing transmission edge endpoint')
        edges.append({'source': a, 'target': b, 'kind': kind, 'status': 'candidate', 'evidence': evidence,
                      'conditions': list(conditions), 'runtime_execution': 'unknown', **extra})

    for source in flow['sources']:
        add_node(source, 'source_json_value', 'JSON return' if source['source_site'] else 'JSON parameter')
        edge(source['source_symbol'], source['id'], 'OBSERVES_JSON_VALUE', source['evidence'])
        for target in source['targets']: edge(target, source['id'], 'RETURNS_JSON_CANDIDATE', source['evidence'])
    for send in flow['transmissions']:
        add_node(send, 'source_cpp_transmission', send['transport'])
        edge(send['source_symbol'], send['id'], 'OBSERVES_CPP_TRANSMISSION', send['evidence'])
        for trace in send['traces']:
            evidence = [e for step in trace['steps'] for e in step['evidence']]
            edge(trace['source'], send['id'], 'JSON_VALUE_REACHES_SEND', evidence or send['evidence'], trace['conditions'],
                 steps=trace['steps'], deferred=send['deferred'], receiver=send['receiver'])
    graph['nodes'] = list(nodes.values()); graph['cpp_transmission'] = flow
    graph['input_paths'] = list(paths); graph['snapshot'] = graph['source_commit'] + ':p3-data-v9'
    graph['extractors']['cpp_transmission'] = 'cpp_transmission/' + flow['version']
    graph['provenance']['transmission_base_snapshot'] = base['snapshot']
    graph['provenance']['transmission_input_paths'] = list(paths)
    graph['diagnostics'] += flow['diagnostics']
    return graph
