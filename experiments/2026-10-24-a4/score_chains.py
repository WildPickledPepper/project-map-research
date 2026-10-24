"""Score frozen source references without changing graph extraction rules."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'experiments/2026-10-24-p7')]
from adapters.fact_queries import find_path
from adapters.data_graph import END_TO_END_KINDS
from adapters.protocol_graph import PROTOCOL_KINDS
from adapters.response_queries import explain_response
from adapters.return_bridge_queries import explain_return_bridge


def classify_outcome(consumers, pairs):
    correct = sum(p['correct'] for p in pairs)
    if any(not p['correct'] for p in pairs): return 'wrong_extra_connection'
    if correct == 1: return 'correct_unique_conditional'
    if correct > 1: return 'multiple_candidates'
    if consumers and all(c['status'] == 'unmatched' for c in consumers): return 'unmatched_expected_provider'
    return 'identified_unknown' if consumers else 'omission'


def provider_correct(case, provider, handlers):
    return provider['command'] == case['command'] and case['scope'] in provider['scope_values'] and any(
        n['path'] == case['handler_path'] and n['name'].endswith(case['handler_suffix']) for n in handlers)


def state_connected(case, states):
    return case['state'] is not None and any(n['path'] == case['consumer_path'] and n['name'] == case['state'] for n in states)


def run(graph_path, reference_path, output):
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    reference = json.loads(reference_path.read_text(encoding='utf-8'))
    graph = json.loads(graph_path.read_text(encoding='utf-8'))
    nodes = {n['id']: n for n in graph['nodes']}
    providers = {p['id']: p for p in graph['protocol']['providers']}
    rows = []
    def save():
        result = {'evidence_kind': 'executed_frozen_rule_held_out_chain_scoring', 'source_commit': graph['source_commit'],
            'snapshot': graph['snapshot'], 'build_version': graph['version']['build_version'],
            'reference_source': reference['source_commit'], 'reference_used_for_extraction': False,
            'protocol_commit': reference['protocol_commit'], 'cases': rows,
            'protocol_outcomes': dict(Counter(r['protocol_outcome'] for r in rows)),
            'counts': {'references': len(reference['cases']), 'scored': len(rows),
                'wrong_protocol_pairs': sum(r.get('wrong_pairs', 0) for r in rows),
                'correct_protocol_pairs': sum(r.get('correct_pairs', 0) for r in rows),
                'missing_expected_protocol_pairs': sum(r.get('correct_pairs', 0) == 0 for r in rows),
                'producer_forward_paths': sum(r.get('producer_forward', False) for r in rows),
                'producer_reverse_paths': sum(r.get('producer_reverse', False) for r in rows),
                'serialized_field_relations': sum(r.get('serialized_field_present', False) for r in rows),
                'return_state_relations': sum(r.get('expected_state_connected', False) for r in rows),
                'state_reference_denominator': sum(c['state'] is not None for c in reference['cases'])},
            'elapsed_seconds': round(time.perf_counter()-started, 4),
            'scope': 'source-rule holdout; existing whole-repository inputs were previously extracted; not strict blind or runtime validation',
            'file_hash_verification': 'not_run_per_user_preference'}
        (output/'first-results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        return result
    for case in reference['cases']:
        row = {'id': case['id'], 'api': case['api'], 'module': case['module'], 'expected_command': case['command'],
            'expected_handler': case['handler_suffix'], 'protocol_outcome': 'omission', 'correct_pairs': 0, 'wrong_pairs': 0}
        rows.append(row)
        try:
            def belongs(r):
                call = nodes.get(r['consumer'].removeprefix('protocol:'), {})
                exact_source = call.get('path') == case['api_path'] and call.get('line') == case.get('source_call_line')
                named_source = r['name'] == case['api'] and (nodes.get(r.get('message'), {}).get('path') == case['api_path'] or call.get('path') == case['api_path'])
                return exact_source or named_source
            consumers = [r for r in graph['protocol']['results'] if belongs(r)]
            row['export_alias_name_present'] = any(r['name'] == case['api'] for r in consumers)
            row['consumer_results'] = [{k: r[k] for k in ('consumer', 'name', 'message', 'status') if k in r} for r in consumers]
            actual = []
            selected = []
            for consumer in consumers:
                for match in consumer['matches']:
                    p = providers[match['provider']]
                    handlers = [nodes[uid] for uid in p['handler_methods']]
                    correct = provider_correct(case, p, handlers)
                    actual.append({'provider': p['id'], 'command': p['command'], 'scope': p['scope_values'],
                        'handlers': [{k: n[k] for k in ('id', 'name', 'path', 'line')} for n in handlers],
                        'correct': correct, 'conditions': match['conditions'], 'gaps': match['gaps']})
                    if correct: selected.append((consumer, p, handlers))
            row.update(actual_pairs=actual, correct_pairs=sum(x['correct'] for x in actual),
                wrong_pairs=sum(not x['correct'] for x in actual))
            row['protocol_outcome'] = classify_outcome(consumers, actual)
            row['gaps'] = []
            if not selected:
                row['gaps'].append('request_not_connected_to_expected_provider')
                save()
                continue
            consumer, provider, handlers = selected[0]
            message = consumer['message']
            starts = [e['source'] for e in graph['edges'] if e['target'] == message and e['kind'] == 'EMITS_MESSAGE']
            target = next(n['id'] for n in handlers if n['path'] == case['handler_path'] and n['name'].endswith(case['handler_suffix']))
            start = starts[0]
            forward = find_path(graph, start, target, PROTOCOL_KINDS, max_depth=12)
            reverse = find_path(graph, target, start, PROTOCOL_KINDS, reverse=True, max_depth=12)
            row.update(request_forward=forward['found'], request_reverse=reverse['found'])
            producers = [n for n in graph['nodes'] if n['kind'] == 'callable' and n.get('definition') and
                n['path'] == case['producer_path'] and n['name'].endswith(case['producer_suffix'])]
            production = []
            for producer in producers:
                f = find_path(graph, start, producer['id'], END_TO_END_KINDS | {'SOURCE_CALL_CANDIDATE'}, max_depth=32)
                r = find_path(graph, producer['id'], start, END_TO_END_KINDS | {'SOURCE_CALL_CANDIDATE'}, reverse=True, max_depth=32)
                production.append({'producer': {k: producer[k] for k in ('id', 'name', 'path', 'line')},
                    'forward': f['found'], 'reverse': r['found'],
                    'forward_depth_cut': f['depth_limit_reached'], 'reverse_depth_cut': r['depth_limit_reached']})
            row.update(producers=production, producer_forward=any(p['forward'] for p in production),
                producer_reverse=any(p['reverse'] for p in production))
            response = explain_response(graph, provider['id'])
            mappings = [m for route in response['routes'] for m in route['field_mappings']]
            row['serialized_field_present'] = any(case['field'][0] in m.get('wire_path', []) for m in mappings)
            returned = explain_return_bridge(graph, provider['id'], field_path=case['field'])
            writes = [item['write'] for link in returned['links'] for item in link['writes']]
            states = [nodes[w['state_node']] for w in writes]
            row['return_links'] = returned['total_links']
            row['states'] = [{k: n[k] for k in ('id', 'name', 'path', 'line')} for n in states]
            row['expected_state_connected'] = state_connected(case, states)
            row['consumer_contract'] = {'path': case['consumer_path'], 'symbol_or_handoff': case['consumer'],
                'expected_state': case['state'], 'status': 'connected_state' if row['expected_state_connected'] else
                'unresolved_expected_state' if case['state'] else 'helper_return_or_worker_handoff_not_scored_as_state'}
            row['query_truncated'] = response.get('truncated', False) or returned.get('truncated', False)
            row['return_gap_kinds'] = dict(Counter(g['kind'] for g in returned.get('gaps', [])))
            if not row['producer_forward']: row['gaps'].append('expected_producer_path_missing')
            if not row['serialized_field_present']: row['gaps'].append('expected_serialized_field_relation_missing')
            if not row['expected_state_connected']: row['gaps'].append('expected_frontend_consumer_not_fully_connected')
            if row['query_truncated']: row['gaps'].append('query_expansion_truncated')
        except Exception as exc:
            row['scoring_error'] = {'type': type(exc).__name__, 'message': str(exc)}
        save()
    result = save()
    print(json.dumps({'counts': result['counts'], 'protocol_outcomes': result['protocol_outcomes']}))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('graph', 'reference', 'output'): p.add_argument('--'+key, type=Path, required=True)
    a = p.parse_args()
    run(a.graph, a.reference, a.output)
