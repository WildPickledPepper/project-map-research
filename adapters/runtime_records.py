"""Bind observed events to an extracted graph and an explicit execution context.

Selectors describe capture hooks, not graph edges. Request links remain runtime
identity links. Static neighbors retain their source evidence and are not marked
executed merely because an observed node touches them.
"""
from copy import deepcopy
import json
from pathlib import Path

from adapters.snapshot_refresh import read_snapshot
from adapters.snapshot_records import append_record, query_record


CONTEXT_KEYS = {'source_commit', 'build', 'runtime_config', 'data', 'scenario'}


def validate_context(context, basis):
    if set(context) != CONTEXT_KEYS:
        raise ValueError('Complete source/build/config/data/scenario context is required')
    if context['source_commit'] != basis['source_commit']:
        raise ValueError('Runtime source differs from graph source')
    for field in CONTEXT_KEYS - {'source_commit'}:
        if not isinstance(context[field], dict) or not context[field]:
            raise ValueError('Empty execution context: ' + field)
    build = context['build']
    if build.get('source_commit') != context['source_commit'] or not build.get('components'):
        raise ValueError('Build receipt does not bind the runtime source')
    for component in build['components']:
        if not component.get('source_commit') or not component.get('log_ref'):
            raise ValueError('Component source and build log are required')
        if component['source_commit'] != context['source_commit']:
            eq = component.get('source_equivalence', {})
            if (eq.get('against_commit') != context['source_commit'] or not eq.get('scope') or
                    eq.get('changed_paths') != [] or eq.get('method') != 'git_diff_name_only'):
                raise ValueError('Component was built from a different source without scoped equivalence')


def select_nodes(nodes, rule):
    selector = rule.get('selector', {})
    if not selector or 'kind' not in selector:
        raise ValueError('Mapping rules require an explicit node kind')
    result = []
    for node in nodes:
        if not all(node.get(k) == v for k, v in selector.items()):
            continue
        if 'first_argument' in rule and (not node.get('arguments') or
                node['arguments'][0] != rule['first_argument']):
            continue
        result.append(node)
    return result


def append_runtime(store, basis, context, events, links, rules, provenance, outcome, diagnostics):
    validate_context(context, basis)
    if len({e['id'] for e in events}) != len(events):
        raise ValueError('Duplicate runtime event identity')
    resolved = read_snapshot(store, basis['id'])
    graph = json.loads((Path(resolved['directory'])/'graph.json').read_text(encoding='utf-8'))
    anchors, mappings, observed_node_ids = [], [], set()
    for event in events:
        matches = [r for r in rules if r['stage'] == event['stage'] and
                   all(event['observation'].get(k) == v for k, v in r.get('when', {}).items())]
        if not matches:
            label = event['id'] + ':unmapped'
            reason = 'No source selector for this observed capture point'
            anchors.append({'label': label, 'reason': reason})
            mappings.append({'event_id': event['id'], 'label': label, 'status': 'unmapped', 'reason': reason})
        for rule in matches:
            label = event['id'] + ':' + rule['role']
            candidates = select_nodes(graph['nodes'], rule)
            mapped = {'event_id': event['id'], 'label': label, 'role': rule['role'],
                      'rule': rule, 'candidates': [n['id'] for n in candidates]}
            if len(candidates) == 1:
                node = candidates[0]
                anchors.append({'label': label, 'node_id': node['id']})
                mapped.update(status='mapped', node={k: node[k] for k in ('id', 'kind', 'path', 'name', 'line') if k in node})
                observed_node_ids.add(node['id'])
            else:
                reason = 'selector_not_found' if not candidates else 'ambiguous_source_selector'
                anchors.append({'label': label, 'reason': reason})
                mapped.update(status='unmapped', reason=reason)
            mappings.append(mapped)
    # Preserve source graph relationships as context; do not relabel them runtime calls.
    context_edges = [edge for edge in graph['edges'] if
                     edge.get('source') in observed_node_ids or edge.get('target') in observed_node_ids]
    payload = {'execution_context': context, 'events': events, 'links': links,
               'mapping_rules_kind': 'declared_capture_adapter_applied_after_graph_extraction',
               'mappings': mappings, 'outcome': outcome, 'diagnostics': diagnostics,
               'static_context': {'edges': context_edges, 'execution_status': 'not_inferred_from_static_edges'},
               'path_difference_policy': 'scenario_assertions_determine_outcome; path_difference_alone_is_not_a_bug',
               'unobserved_execution': 'unknown_from_this_capture'}
    return append_record(store, {'kind': 'trace', 'basis': basis, 'provenance': provenance,
                                 'payload': payload, 'anchors': anchors})


def query_runtime(store, record_id, *, snapshot_id, context):
    result = query_record(store, record_id, snapshot_id=snapshot_id)
    recorded = result['record']['payload']['execution_context']
    if not isinstance(context, dict) or set(context) != CONTEXT_KEYS:
        raise ValueError('Explicit target execution context is required')
    differences = sorted(k for k in CONTEXT_KEYS if context[k] != recorded[k])
    result['runtime_context_differences'] = differences
    result['graph_eligible_for_direct_overlay'] = result['eligible_for_direct_overlay']
    result['eligible_for_direct_overlay'] = result['eligible_for_direct_overlay'] and not differences
    result['target_execution_context'] = deepcopy(context)
    return result
