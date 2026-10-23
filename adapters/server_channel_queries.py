"""Join accepted channel, scoped session storage, and response send evidence."""
from adapters.frontend_graph import key
from adapters.response_queries import explain_response
from adapters.transmission_queries import explain_transmission


def compatible(conditions):
    known = {}
    for c in conditions:
        if not isinstance(c, dict) or 'when' not in c: continue
        e = c.get('evidence', [{}])[0]
        identity = (c.get('source_symbol'), c.get('path', e.get('path')), c.get('line', e.get('line')), c.get('expression'))
        if identity in known and known[identity] != c['when']: return False
        known[identity] = c['when']
    return True


def origin_links(graph):
    flow = graph['server_channels']; result = []
    regs = {r['id']: r for r in flow['registrations']}
    getters = {g['id']: g for g in flow['member_getters']}
    instances = {o['id']: o for o in flow['source_instances']['objects']}
    for initial in flow['channel_initializers']:
        registration = regs.get(initial['origin']['registration'])
        if not registration: continue
        listeners = [l for l in flow['listeners'] if l['entry'] == registration['entry'] and
                     l['app'].get('instance') and l['app']['instance'] == registration['app'].get('instance') and
                     compatible(l['conditions'] + registration['conditions'])]
        for store in flow['object_stores']:
            if store['allocation'] != initial['allocation']: continue
            instance = instances.get(store['receiver_instance'])
            if not instance or instance['kind'] != 'static_local_object': continue
            for consumer in flow['member_consumers']:
                getter = getters.get(consumer['getter'])
                if not getter or (consumer['member'], consumer['receiver_instance']) != (store['member'], store['receiver_instance']): continue
                if getter['member'] != store['member'] or getter['source_symbol'] != consumer['getter_symbol']: continue
                result.append({'id': key('server-channel-origin', initial['id'], store['id'], consumer['id']),
                    'registration': registration, 'listen_candidates': listeners, 'channel_initialization': initial,
                    'store': store, 'getter': getter, 'consumer': consumer, 'manager_instance': instance,
                    'conditions': ['same_process_and_link_image', 'open_callback_and_store_executed',
                        'stored_session_not_replaced_or_removed_before_getter', 'session_and_channel_remain_live',
                        'selected_virtual_receiver_is_the_stored_allocation'],
                    'evidence': initial['evidence'] + store['evidence'] + consumer['evidence'], 'runtime_execution': 'unknown'})
    return result


def explain_server_channels(graph, *, provider=None, max_links=100):
    if max_links < 1: raise ValueError('max_links must be positive')
    origins = origin_links(graph); links = []; selected = set(); truncated = False
    if provider:
        responses = explain_response(graph, provider); transmissions = explain_transmission(graph, provider=provider, max_links=100000)
        truncated = responses['truncated'] or transmissions['truncated']
        for route in responses['routes']:
            for origin in origins:
                consumer = origin['consumer']; initial = origin['channel_initialization']
                if not any(s['call_site'] == consumer['call_site'] and s['caller'] == consumer['source_symbol'] and
                           s['callee'] in consumer['targets'] for s in route['steps']): continue
                choices = [t for t in transmissions['links'] if t['response_send_site']['call_site'] == route['steps'][0]['call_site'] and
                    t['serializer'] == route['serializer'] and t['response_object'] == route['object_root'] and
                    t['transmission']['receiver'].get('field') == initial['member']]
                if not choices: continue
                links.append({'origin_link': origin['id'], 'response_send_site': route['steps'][0],
                    'response_object': route['object_root'], 'serializer': route['serializer'], 'transmissions': choices,
                    'network_pairing': 'configured_service_candidate_with_source_server_channel_origin'})
                selected.add(origin['id'])
        origins = [o for o in origins if o['id'] in selected]
    flow = graph['server_channels']; entries = {o['registration']['entry'] for o in origins}
    return {'snapshot': graph['snapshot'], 'source_commit': graph['source_commit'], 'provider': provider,
        'status': 'conditional_server_channel_origin' if origins and (not provider or links) else 'unresolved',
        'origins': origins[:max_links], 'links': links[:max_links], 'total_origins': len(origins), 'total_links': len(links),
        'truncated': truncated or len(origins) > max_links or len(links) > max_links or
            any(d['kind'] in {'analysis_budget_exhausted', 'recursion_or_depth_limit', 'state_budget_exhausted'} for d in flow['diagnostics']),
        'gaps': [d for d in flow['diagnostics'] if d['entry'] in entries],
        'remaining': ['runtime_host_port_proxy_and_connection_correspondence', 'iframe_reply_wrapping_and_final_API_return',
                      'unresolved_encoding_and_queue_branches'], 'runtime_delivery': 'unknown', 'limits': flow['limits']}
