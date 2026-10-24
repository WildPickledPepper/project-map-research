"""Query source consumers on one side of an explicit API fulfillment boundary."""


def overlap(requested, actual):
    return all(a == b or '*' in (a, b) for a, b in zip(requested, actual))


def explain_frontend(graph, api=None, entry=None, field_path=None, state=None, max_writes=200):
    if max_writes < 0:
        raise ValueError('max_writes must be nonnegative')
    if field_path is not None and (not isinstance(field_path, list) or not all(isinstance(p, str) for p in field_path)):
        raise ValueError('field_path must be a list of selectors')
    data = graph.get('frontend', {})
    calls = [c for c in data.get('api_calls', []) if (api is None or c['api'] == api)
             and (entry is None or c['entry'] == entry)]
    contexts = {c['request_context'] for c in calls}
    writes = []
    consumers = []
    if state is None:
        for consumer in data.get('consumptions', []):
            deps = [d for d in consumer['value_dependencies'] if d['request_context'] in contexts
                    and (field_path is None or overlap(field_path, d['path']))]
            if deps: consumers.append({**consumer, 'matching_dependencies': deps})
    for write in data.get('state_writes', []):
        if state is not None and write['state_node'] != state:
            continue
        deps = [d for d in write['value_dependencies'] if d['request_context'] in contexts
                and (field_path is None or overlap(field_path, d['path']))]
        continuations = [c for c in write['continuation_apis'] if c in contexts]
        if deps or (field_path is None and continuations):
            writes.append({**write, 'matching_dependencies': deps,
                           'matching_continuations': continuations,
                           'relationship': 'value_dependency_candidate' if deps else 'fulfillment_continuation'})
    if state is not None or field_path is not None:
        used = {d['request_context'] for w in writes for d in w['matching_dependencies']}
        used.update(d['request_context'] for c in consumers for d in c['matching_dependencies'])
        if field_path is None:
            used.update(c for w in writes for c in w['matching_continuations'])
        calls = [c for c in calls if c['request_context'] in used]
    selected_entries = {c['entry'] for c in calls}
    return {'status': 'source_frontend_candidates' if calls else 'not_extracted',
            'snapshot': graph['snapshot'], 'api': api, 'entry': entry, 'field_path': field_path,
            'state': state, 'api_calls': calls, 'writes': writes[:max_writes], 'consumers': consumers[:max_writes],
            'total_writes': len(writes), 'total_consumers': len(consumers), 'max_writes': max_writes, 'truncated': len(writes) > max_writes or len(consumers) > max_writes,
            'gaps': [d for d in data.get('diagnostics', []) if d['entry'] in selected_entries],
            'extraction_truncated': any(e['truncated'] for e in data.get('entries', []) if e['source_symbol'] in selected_entries),
            'transport_status': 'pending_transport_join', 'runtime_execution': 'unknown',
            'limits': data.get('limits', [])}
