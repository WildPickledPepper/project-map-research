"""Link a request's native channel to its installed response lookup callback."""
from adapters.callback_queries import explain_callbacks
from adapters.correlation_queries import consistent, explain_correlation, request_key_bindings
from adapters.frontend_graph import key
from adapters.transmission_queries import explain_transmission


def channel_identity(value):
    if value.get('gaps') or value.get('transforms'): return None
    if value.get('kind') == 'input_path': return ('input', value['root'], tuple(value['path']))
    if value.get('kind') == 'native_socket': return ('allocation', value['allocation'])
    return None


def receiver_links(graph, requester=None):
    sockets = graph['socket_flow']; callbacks = graph['response_callbacks']
    sends = {s['id']: s for s in callbacks['transmissions']}; regs = {r['id']: r for r in callbacks['registrations']}
    creations = {s['id']: s for s in sockets['creations']}
    deliveries = explain_callbacks(graph, requester=requester, max_deliveries=100000)['deliveries']
    result = []
    for binding in request_key_bindings(callbacks):
        old_send = sends[binding['transmission']]; reg = regs[binding['registration']]
        if old_send['transport'] != 'WebSocket.send' or requester and reg['entry'] != requester: continue
        for sent in sockets['transmissions']:
            identity = channel_identity(sent['receiver'])
            if not identity or identity != channel_identity(old_send['receiver']): continue
            if sent['source_site'] != old_send['source_site'] or sent['entry'] != old_send['entry']: continue
            for listener in sockets['listener_bindings']:
                if listener['action'] != 'install' or listener['superseded_by'] or channel_identity(listener['channel']) != identity: continue
                if listener['this_binding'] not in {'lexical', 'bound'} or listener['callback_receiver_type'] != reg['receiver_type']: continue
                if not consistent(sent['conditions'] + listener['conditions'] + reg['conditions']): continue
                selected = []
                for delivery in deliveries:
                    lookup = delivery['lookup']; event_key = lookup['key']; context = delivery['settlement']['registry_context']
                    if context['registration'] != reg['id'] or lookup['entry'] != listener['callback']: continue
                    if event_key.get('kind') != 'input_path' or event_key.get('gaps') or event_key['root'] != listener['event_parameter']: continue
                    transforms = event_key.get('transforms', [])
                    if not transforms or transforms[-1]['kind'] != 'JSON.parse' or transforms[-1]['at_path'] != ['data']: continue
                    selected.append(delivery)
                if not selected: continue
                assignments = [a for a in sockets['channel_bindings'] if channel_identity(a['channel']) == identity]
                choices = [creations[a['value']['allocation']] for a in assignments if a['value']['kind'] == 'native_socket' and a['value']['allocation'] in creations]
                if identity[0] == 'allocation' and identity[1] in creations: choices.append(creations[identity[1]])
                choices = list({c['id']: c for c in choices}.values())
                result.append({'id': key('socket-receiver-link', binding['registration'], sent['id'], listener['id']),
                    'request_key_binding': binding, 'request_send': old_send, 'socket_send': sent, 'listener': listener,
                    'native_creations': choices, 'channel_assignments': assignments,
                    'unresolved_channel_assignments': [a for a in assignments if a['value']['kind'] != 'native_socket'],
                    'deliveries': selected, 'conditions': ['same_runtime_channel_and_owner_instance', 'native_WebSocket_branch_selected',
                        'listener_installation_executed_and_remains_active', 'message_dispatches_to_recorded_event_parameter',
                        'registration_key_matches_response_key_and_remains_live'],
                    'evidence': sent['evidence'] + listener['evidence'], 'runtime_delivery': 'unknown'})
    return result


def explain_socket_receivers(graph, *, provider=None, requester=None, max_links=100):
    if max_links < 1: raise ValueError('max_links must be positive')
    receivers = receiver_links(graph, requester); backend = []; upstream_truncated = False
    if provider:
        keys = explain_correlation(graph, provider); sends = explain_transmission(graph, provider=provider)
        upstream_truncated = keys['truncated'] or sends['truncated']
        used = set()
        for correlation in keys['links']:
            for receiver in receivers:
                if correlation['request_key_binding'] != receiver['request_key_binding']: continue
                if not any(d['lookup']['id'] == correlation['response_lookup']['id'] for d in receiver['deliveries']): continue
                choices = [s for s in sends['links'] if s['response_send_site']['call_site'] == correlation['response_send_site']['call_site'] and
                           s['serializer'] == correlation['serializer'] and s['response_object'] == correlation['copy_effect']['root']]
                if not choices: continue
                backend.append({'receiver_link': receiver['id'], 'key_correlation': correlation, 'cpp_transmissions': choices,
                                'network_pairing': 'configured_service_candidate_server_channel_origin_pending'})
                used.add(receiver['id'])
        receivers = [r for r in receivers if r['id'] in used]
    entries = {r['listener']['entry'] for r in receivers} | {r['socket_send']['entry'] for r in receivers}
    entries |= {c['entry'] for r in receivers for c in r['native_creations']}
    callback_entries = {d['lookup']['entry'] for r in receivers for d in r['deliveries']} | {r['request_key_binding']['entry'] for r in receivers}
    return {'snapshot': graph['snapshot'], 'source_commit': graph['source_commit'], 'provider': provider, 'requester': requester,
            'status': 'conditional_source_socket_receiver' if receivers else 'unresolved',
            'receivers': receivers[:max_links], 'backend_links': backend[:max_links],
            'total_receivers': len(receivers), 'total_backend_links': len(backend),
            'truncated': upstream_truncated or len(receivers) > max_links or len(backend) > max_links or
                         any(e['truncated'] for e in graph['socket_flow']['entries'] if e['source_symbol'] in entries) or
                         any(e['truncated'] for e in graph['response_callbacks']['entries'] if e['source_symbol'] in callback_entries),
            'gaps': [d for d in graph['socket_flow']['diagnostics'] if d['entry'] in entries],
            'remaining': ['server_accept_session_channel_origin', 'runtime_host_port_proxy_and_connection_correspondence',
                          'iframe_reply_wrapping_and_final_API_return', 'unresolved_encoding_and_queue_branches'],
            'runtime_delivery': 'unknown', 'limits': graph['socket_flow']['limits']}
