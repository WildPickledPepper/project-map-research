"""Join object-scoped serializer routes to source JSON-to-socket traces."""
from adapters.response_queries import explain_response


def explain_transmission(graph, *, provider=None, entry=None, max_links=100):
    if max_links < 1: raise ValueError('max_links must be positive')
    flow = graph['cpp_transmission']; sources = {s['id']: s for s in flow['sources']}
    response = explain_response(graph, provider) if provider else None
    routes = response['routes'] if response else [None]
    links = []; selected = set()
    for send in flow['transmissions']:
        if entry and send['entry'] != entry: continue
        for trace in send['traces']:
            source = sources[trace['source']]
            for route in routes:
                if route is not None:
                    matches = [s for s in route['steps'] if source['source_site'] == s['call_site'] and
                               source['source_symbol'] == s['caller'] and s['callee'] in source['targets'] and
                               source['entry'] == s['caller']]
                    if not matches: continue
                selected.add(send['entry'])
                links.append({'json_source': source, 'transmission': {k: v for k, v in send.items() if k != 'traces'},
                              'lineage': trace,
                              'response_send_site': route['steps'][0] if route else None,
                              'serializer': route['serializer'] if route else None,
                              'response_object': route['object_root'] if route else None,
                              'conditions': route['conditions'] if route else [], 'runtime_delivery': 'unknown'})
    if entry: selected.add(entry)
    return {'snapshot': graph['snapshot'], 'source_commit': graph['source_commit'], 'provider': provider, 'entry': entry,
            'status': 'conditional_source_transmission' if links else 'unresolved',
            'links': links[:max_links], 'total_links': len(links),
            'truncated': len(links) > max_links or bool(response and response['truncated']),
            'gaps': [g for g in flow['diagnostics'] if g['entry'] in selected],
            'response_route_gaps': response['gaps'] if response else [],
            'remaining': ['socket_endpoint_correspondence', 'frontend_receive_and_iframe_reply_join',
                          'api_return_transformations', 'runtime_execution_and_delivery'],
            'limits': flow['limits']}
