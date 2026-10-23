"""Add API-result consumers, keeping the transport boundary explicit."""
from copy import deepcopy
import json


def key(prefix, *parts):
    return prefix + ':' + json.dumps(parts, ensure_ascii=False, separators=(',', ':'))


def augment_frontend(base, facts):
    graph = deepcopy(base)
    flow = deepcopy(facts['data_flow'])
    nodes = {n['id']: n for n in graph['nodes']}
    for n in facts['nodes']:
        nodes.setdefault(n['id'], n)
    edges = graph['edges']

    def node(uid, kind, name, source_evidence, **extra):
        nodes[uid] = {'id': uid, 'kind': kind, 'name': name,
                      'path': source_evidence[0]['path'], 'line': source_evidence[0]['line'], **extra}

    def edge(a, b, kind, evidence, conditions=(), **extra):
        if a not in nodes or b not in nodes:
            raise ValueError('Frontend relation references a missing symbol')
        edges.append({'source': a, 'target': b, 'kind': kind, 'status': 'candidate',
                      'evidence': evidence, 'conditions': list(conditions),
                      'runtime_execution': 'unknown', **extra})

    requests = {c['request_context']: c for c in flow['api_calls']}
    for context, call in requests.items():
        uid = key('api-result', context)
        call['result_node'] = uid
        node(uid, 'api_result_boundary', context, call['evidence'], **call,
             transport_status='pending_transport_join')
        edge(call['api'], uid, 'DECLARES_API_RESULT_BOUNDARY', call['evidence'])
        edge(call['entry'], uid, 'REQUESTS_API_RESULT', call['evidence'])

    def field(dep):
        call = requests[dep['request_context']]
        if call['api'] != dep['api'] or call['api_call'] != dep['api_call']:
            raise ValueError('Response dependency belongs to a different request')
        uid = key('result-field', dep['request_context'], dep['path'])
        if uid not in nodes:
            node(uid, 'api_result_field', '/'.join(dep['path']), dep['evidence'],
                 api=dep['api'], request_context=dep['request_context'], selectors=dep['path'])
            edge(call['result_node'], uid, 'HAS_RESULT_FIELD', dep['evidence'])
        return uid

    for index, read in enumerate(flow['field_reads']):
        uid = key('frontend-read', read['entry'], read['id'], index)
        read['source_site'] = read['id']; read['id'] = uid
        node(uid, 'frontend_field_read', '/'.join(read['response']['path']), read['evidence'], **read)
        edge(field(read['response']), uid, 'READ_RESULT_FIELD', read['evidence'], read['conditions'])
        edge(read['source_symbol'], uid, 'OBSERVES_RESULT_READ', read['evidence'], read['conditions'])

    for index, write in enumerate(flow['state_writes']):
        uid = key('frontend-write', write['entry'], write['id'], index)
        write['source_site'] = write['id']; write['id'] = uid
        target = write['target']
        sid = key('frontend-state', write['entry'], target['root'], target['path'])
        write['state_node'] = sid
        node(sid, 'frontend_state_path', '/'.join(target['path']), write['evidence'],
             entry=write['entry'], root=target['root'], selectors=target['path'],
             identity_scope='entry_parameter_in_one_invocation')
        node(uid, 'frontend_state_write', '/'.join(target['path']), write['evidence'], **write)
        edge(write['source_symbol'], uid, 'OBSERVES_FRONTEND_WRITE', write['evidence'], write['conditions'])
        edge(uid, sid, 'WRITES_FRONTEND_STATE', write['evidence'], write['conditions'])
        for dep in write['value_dependencies']:
            edge(field(dep), uid, 'VALUE_MAY_REACH_STATE_WRITE', dep['evidence'] + write['evidence'],
                 write['conditions'] + dep.get('conditions', []), gaps=dep.get('gaps', []),
                 call_chain=write['call_chain'])
        for context in write['continuation_apis']:
            edge(requests[context]['result_node'], uid, 'FULFILLMENT_PRECEDES_STATE_WRITE',
                 write['evidence'], write['conditions'])

    graph['nodes'] = list(nodes.values())
    graph['frontend'] = flow
    graph['snapshot'] = graph['source_commit'] + ':p3-data-v6'
    graph['provenance']['frontend_base_snapshot'] = base['snapshot']
    graph['extractors']['typescript_data_flow'] = 'typescript_data_flow/' + flow['version']
    graph['diagnostics'] += flow['diagnostics']
    return graph
