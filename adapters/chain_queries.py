"""One evidence ledger for protocol, producer, transport and consumer queries."""
import json

from adapters.data_graph import END_TO_END_KINDS
from adapters.data_queries import explain_receiver
from adapters.fact_queries import find_path
from adapters.response_queries import explain_response
from adapters.return_bridge_queries import explain_return_bridge
from adapters.server_channel_queries import explain_server_channels
from adapters.socket_queries import explain_socket_receivers
from adapters.transmission_queries import explain_transmission


def evidence_in(value):
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and isinstance(value.get('line'), int):
            yield {k: value[k] for k in ['path', 'line', 'column', 'expression', 'kind'] if k in value}
        for k in sorted(value):
            if k != 'path': yield from evidence_in(value[k])
    elif isinstance(value, list):
        for v in value: yield from evidence_in(v)


def explain_chain(graph, provider, field_path, *, include_details=False):
    if not isinstance(field_path, list) or not field_path or not all(isinstance(x, str) for x in field_path):
        raise ValueError('Provide a nonempty array of field selectors')
    returned = explain_return_bridge(graph, provider, field_path=field_path)
    response = explain_response(graph, provider)
    sent = explain_transmission(graph, provider=provider)
    sockets = explain_socket_receivers(graph, provider=provider)
    server = explain_server_channels(graph, provider=provider)
    nodes = {n['id']: n for n in graph['nodes']}
    ledger = []; evidence = {}; indexes = {}; gaps = []; used_nodes = set()

    def refs(items):
        ids = []
        for e in evidence_in(items):
            k = json.dumps(e, ensure_ascii=False, sort_keys=True)
            if k not in indexes:
                eid = 'e' + str(len(indexes) + 1); indexes[k] = eid; evidence[eid] = e
            if indexes[k] not in ids: ids.append(indexes[k])
        return ids

    def add(stage, kind, source, target, origins, conditions=(), **extra):
        used_nodes.update(i for i in [source, target] if i in nodes)
        ledger.append({'stage': stage, 'kind': kind, 'source': source, 'target': target,
            'status': 'source_candidate', 'evidence': refs(origins), 'conditions': list(conditions), **extra})

    apis = sorted({b['api'] for b in returned['bridges']})
    if not apis:
        messages = {r['message'] for r in graph['protocol']['results'] if any(m['provider'] == provider for m in r['matches'])}
        apis = sorted({e['source'] for e in graph['edges'] if e['kind'] == 'EMITS_MESSAGE' and e['target'] in messages})
    handlers = sorted({r['handler'] for r in response['routes']})
    request_paths = [find_path(graph, api, handler, END_TO_END_KINDS, max_depth=16) for api in apis for handler in handlers]
    for p in request_paths:
        for edge in p['edges']:
            add('request', edge['kind'], edge['source'], edge['target'], edge['evidence'], edge.get('conditions', []))

    # The field's production call chain selects producer entry candidates.
    productions = {p['write'] + json.dumps(p['production_calls'], sort_keys=True): p for link in returned['links']
                   for w in link['writes'] for m in w['value_mappings'] for p in m['production']}
    calls = {p['production_calls'][0]['call_site']: p['production_calls'][0] for p in productions.values() if p['production_calls']}
    receivers = {site: explain_receiver(graph, site) for site in sorted(calls)}
    candidates = sorted({p['production_calls'][0]['callee'] for p in productions.values() if p['production_calls']})
    database_paths = []
    for candidate in candidates:
        for api in apis:
            forward = find_path(graph, api, candidate, END_TO_END_KINDS, max_depth=16)
            reverse = find_path(graph, candidate, api, END_TO_END_KINDS, reverse=True, max_depth=16)
            database_paths.append({'api': api, 'candidate': candidate, 'forward': forward, 'reverse': reverse})
            for edge in forward['edges']:
                add('database', edge['kind'], edge['source'], edge['target'], edge['evidence'], edge.get('conditions', []))
    for site, receiver in receivers.items():
        for factory in receiver['factory_candidates']:
            add('database_selection', 'FACTORY_AND_STATE_DEPENDENCY', site, factory['allocation']['id'], factory,
                receiver['remaining_conditions'], allocation=factory['allocation']['type_spelling'])
    for p in productions.values():
        add('production', 'FIELD_PRODUCTION_CALL_CHAIN', p['writer'], p['write'], p, p['conditions'],
            wire_path=p['wire_path'], calls=p['production_calls'])
    for route in response['routes']:
        for step in route['steps']:
            add('response_object', step['kind'], step['caller'], step['callee'], step['evidence'], step.get('conditions', []), call_site=step['call_site'])
        for mapping in route['field_mappings']:
            if any(f == mapping for l in returned['links'] for w in l['writes'] for m in w['value_mappings'] for f in m['fields']):
                add('serialization', mapping['relation'], route['object_root'], route['serializer'], mapping['evidence'], mapping['conditions'],
                    wire_path=mapping['wire_path'], selectors=mapping['selectors'])
    for link in sent['links']:
        for step in link['lineage']['steps']:
            add('response_transport', step['kind'], link['json_source']['id'], link['transmission']['id'], step['evidence'],
                link['lineage']['conditions'], model=step.get('model'), response_send_site=link['response_send_site']['call_site'])
    for origin in server['origins']:
        add('server_connection', 'ACCEPTED_CHANNEL_SESSION_SOURCE', origin['registration']['id'], origin['id'], origin, origin.get('conditions', []))
    for receiver in sockets['receivers']:
        add('socket_delivery', 'REQUEST_CHANNEL_TO_RESPONSE_LISTENER', receiver['request_send']['id'], receiver['listener']['id'], receiver, receiver['conditions'])
    for bridge in returned['bridges']:
        add('iframe_reply', 'KEYED_WINDOW_REPLY_TO_API', bridge['upstream_boundary']['id'], bridge['api'], bridge, bridge['conditions'],
            reply_projection=bridge['reply_value_path'], api_projection=bridge['api_return']['value'].get('path'))
    states = set()
    for link in returned['links']:
        for item in link['writes']:
            w = item['write']; states.add(w['state_node'])
            add('frontend_state', 'RETURN_FIELD_TO_STATE', link['response_send_site']['call_site'], w['state_node'], item,
                link['conditions'] + w.get('conditions', []),
                api_dependencies=[{k: d[k] for k in ['api', 'api_call', 'request_context', 'path', 'gaps'] if k in d}
                                  for d in w['matching_dependencies']], relationship=w['relationship'])
    for c in graph.get('source_conditions', {}).get('guards', []):
        constant = next(k for k in graph['source_conditions']['constants'] if k['id'] == c['constant'])
        add('source_conditions', 'CONST_MEMBER_GUARD', c['constant'], c['id'], [c, constant], constant['conditions'],
            value=c['value'], branches=c['branches'], resolution=c['status'])
    sections = {'returns': returned, 'response': response, 'transmission': sent, 'sockets': sockets, 'server': server}
    for stage, result in sections.items():
        for gap in result.get('gaps', []):
            gaps.append({'stage': stage, 'kind': gap['kind'], 'evidence': refs(gap),
                'detail': {k: v for k, v in gap.items() if k != 'evidence'}})
    reverse_states = {state: explain_return_bridge(graph, provider, state=state, field_path=field_path)['total_links'] for state in sorted(states)}
    truncated = any(q.get('truncated') for q in sections.values()) or any(q['truncated'] for q in receivers.values())
    truncated |= any(p['depth_limit_reached'] for p in request_paths)
    truncated |= any(p[d]['depth_limit_reached'] for p in database_paths for d in ['forward', 'reverse'])
    connected = bool(returned['links'] and database_paths and server['origins'] and sent['links'] and request_paths)
    connected &= all(p['found'] for p in request_paths) and all(p[d]['found'] for p in database_paths for d in ['forward', 'reverse'])
    ledger = list({json.dumps(r, sort_keys=True): r for r in ledger}.values())
    result = {'schema_version': 'source-chain/0.1', 'snapshot': graph['snapshot'], 'source_commit': graph['source_commit'],
        'provider': provider, 'field_path': field_path, 'status': 'conditional_source_chain' if connected else 'unresolved',
        'coverage': {'input_files': len(graph['input_paths']), 'extractors': graph['extractors'], 'whole_repository': False},
        'summary': {'apis': apis, 'handlers': handlers, 'producer_candidates': candidates,
            'response_exits': returned['total_links'], 'transmission_paths': sent['total_links'], 'states': sorted(states),
            'reverse_states': reverse_states, 'database_reverse_paths': sum(p['reverse']['found'] for p in database_paths)},
        'nodes': {i: {k: nodes[i][k] for k in ['id', 'kind', 'name', 'path', 'line'] if k in nodes[i]} for i in sorted(used_nodes)},
        'relations': ledger, 'evidence': evidence, 'gaps': gaps, 'truncated': truncated,
        'conditions': ['source_branches_and_candidate_implementations_selected', 'request_and_response_keys_still_live',
            'configured_service_and_parent_child_windows_match', 'channel_and_session_lifetimes_valid',
            'encoding_calls_succeed_without_loss', 'no_intervening_unmodeled_mutations'],
        'unexpanded': ['request_network_buffer_framing_and_worker_schedule', 'full_path_constraint_satisfiability',
            'encoding_detection_algorithm_and_external_api_failures', 'whole_repository_consumers_outside_input'],
        'runtime_observation': 'not_executed_in_P3'}
    if include_details:
        result['details'] = {**sections, 'receivers': receivers, 'request_paths': request_paths, 'database_paths': database_paths}
    return result
