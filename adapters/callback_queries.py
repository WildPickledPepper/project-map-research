"""Explain registration, key selection, callback and Promise value projections."""


def projections(value, output_path=None):
    output_path = output_path or []
    if value['kind'] == 'input_path':
        decoders = value.get('transforms', [])
        wire = None
        if decoders:
            prefix = decoders[-1]['at_path']
            if value['path'][:len(prefix)] == prefix: wire = value['path'][len(prefix):]
        return [{'output_path': output_path, 'source': value, 'decoded_json_path': wire}]
    if value['kind'] == 'alternatives':
        return [p for child in value['values'] for p in projections(child, output_path)]
    if value['kind'] == 'object':
        return [p for name, child in value['fields'].items() for p in projections(child, output_path + [name])]
    return []


def explain_callbacks(graph, requester=None, receiver=None, max_deliveries=100):
    if max_deliveries < 0: raise ValueError('max_deliveries must be nonnegative')
    data = graph.get('response_callbacks', {})
    regs = {r['id']: r for r in data.get('registrations', []) if requester is None or r['entry'] == requester}
    lookups = {l['id']: l for l in data.get('lookups', [])}
    deliveries = []
    for s in data.get('settlements', []):
        context = s['registry_context']
        if not context or context['registration'] not in regs or (receiver is not None and s['entry'] != receiver): continue
        deliveries.append({'registration': regs[context['registration']], 'lookup': lookups[context['lookup']],
                           'settlement': s, 'projections': projections(s['value'])})
    registry_scopes = {(r['registry'], r['receiver_type']) for r in regs.values()}
    selected_lookups = [l for l in lookups.values() if (receiver is None or l['entry'] == receiver)
        and (requester is None or (l['registry'], l['receiver_type']) in registry_scopes)]
    used_lookups = {d['lookup']['id'] for d in deliveries}
    entries = {l['entry'] for l in selected_lookups} | {r['entry'] for r in regs.values()}
    gaps = [d for d in data.get('diagnostics', []) if d['entry'] in entries]
    return {'snapshot': graph['snapshot'], 'status': 'source_callback_candidates' if deliveries else 'not_extracted',
            'requester': requester, 'receiver': receiver, 'deliveries': deliveries[:max_deliveries],
            'registrations': list(regs.values()), 'unmatched_lookups': [l for l in selected_lookups if l['id'] not in used_lookups],
            'total_deliveries': len(deliveries), 'max_deliveries': max_deliveries, 'truncated': len(deliveries) > max_deliveries,
            'extraction_truncated': any(e['truncated'] for e in data.get('entries', []) if e['source_symbol'] in entries)
                or any(g['kind'] in {'step_limit', 'call_depth_limit'} for g in gaps),
            'gaps': gaps, 'limits': data.get('limits', []), 'runtime_execution': 'unknown',
            'transport_status': 'network_and_API_boundary_join_pending'}
