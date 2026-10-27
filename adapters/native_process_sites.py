"""Attach native CBM process evidence to existing source-bound API sites.

This adapter consumes provider facts. It neither evaluates commands nor resolves
program names. In particular, CBM's shared Process nodes describe programs, not
process instances, and Rust Command::new constructs a command without starting it.
"""
from collections import Counter, defaultdict
from urllib.parse import quote


VERSION = 'native_process_site_bridge/0.1.0'


def _api_matches(node, api):
    if node['kind'] == 'python_boundary':
        return api in node.get('api_candidates', [])
    if node['kind'] == 'rust_boundary':
        return any(api == item.get('canonical') for item in node.get('api_declarations', []))
    return node['kind'] == 'call_site' and node.get('language') == 'shell' and api == 'shell'


def project(nodes, edges, *, source_commit):
    """Project supplied facts; callers may select them from an existing index."""
    by_id = {n['id']: n for n in nodes}
    anchors = defaultdict(list)
    for node in by_id.values():
        if (node['kind'] in {'python_boundary', 'rust_boundary'} or
                node['kind'] == 'call_site' and node.get('language') == 'shell'):
            anchors[(node['path'], node['line'])].append(node)
    added, links, diagnostics, counts = [], [], [], Counter()
    seen = set()
    for edge in edges:
        if edge['kind'] != 'CBM_SPAWNS':
            continue
        provenance = edge.get('provenance', {})
        if provenance.get('source_commit') != source_commit:
            raise ValueError('Process evidence belongs to another source revision')
        if provenance.get('provider') != 'codebase-memory-mcp':
            raise ValueError('Expected native CBM process evidence')
        caller, target = by_id[edge['source']], by_id[edge['target']]
        properties = edge.get('native_properties', {})
        line, api = properties.get('line'), properties.get('api')
        if not caller['path'] or type(line) is not int or line <= 0 or not api:
            diagnostics.append({'kind': 'native_process_site_gap', 'reason': 'missing_source_site',
                                'native_edge': edge.get('native_id'), 'path': caller['path']})
            counts['missing_source_site'] += 1
            continue
        native_key = (edge['source'], edge['target'], edge.get('native_id'))
        if native_key in seen:
            raise ValueError('Duplicate native process edge identity')
        seen.add(native_key)
        uid = 'native-process-site:' + ':'.join(quote(str(v), safe='') for v in native_key)
        operation = 'command_construction' if api == 'std::process::Command::new' else 'process_start_candidate'
        candidates = [n for n in anchors[(caller['path'], line)] if _api_matches(n, api)]
        # Distinct calls on one line cannot be distinguished by CBM's line-only
        # location. Do not connect them all, even if their API names agree.
        calls = {n.get('call', n['id']) for n in candidates}
        matched = candidates if len(calls) == 1 else []
        status = ('matched_source_call' if matched else 'ambiguous_source_calls' if calls
                  else 'no_source_api_anchor')
        if target.get('path'):
            counterpart = 'native_source_target_candidate'
        elif properties.get('program') in {None, '', '<dynamic>'}:
            counterpart = 'unresolved_dynamic_program'
        else:
            counterpart = 'external_or_unbound_program'
        row = {'id': uid, 'kind': 'native_process_site', 'path': caller['path'], 'line': line,
               'name': str(properties.get('program') or api), 'api': api, 'operation': operation,
               'native_edge': edge.get('native_id'), 'native_caller': caller['id'],
               'native_target': target['id'], 'native_properties': properties,
               'provenance': provenance, 'source_commit': source_commit,
               'anchor_status': status, 'counterpart_status': counterpart,
               'source_calls': sorted(calls), 'runtime_execution': 'not_observed',
               'instance_identity': 'not_established'}
        added.append(row)
        counts['sites'] += 1
        counts[operation] += 1
        counts[status] += 1
        counts[counterpart] += 1
        common = {'status': 'candidate', 'evidence': [{'path': caller['path'], 'line': line}],
                  'provenance': provenance, 'native_edge': edge.get('native_id'),
                  'runtime_execution': 'not_observed', 'instance_identity': 'not_established'}
        links.append({'source': caller['id'], 'target': uid, 'kind': 'HAS_NATIVE_PROCESS_SITE', **common})
        for anchor in matched:
            links.append({'source': anchor['id'], 'target': uid, 'kind': 'HAS_NATIVE_PROCESS_EVIDENCE',
                          **common, 'analysis_contexts': anchor.get('analysis_contexts', []),
                          'conditions': anchor.get('conditions', []),
                          'basis': 'same_source_path_line_and_bound_library_api_unique_call'})
        if target.get('path'):
            links.append({'source': uid, 'target': target['id'], 'kind': 'MAY_EXECUTE_SOURCE_MODULE',
                          **common, 'basis': 'native_cbm_source_target_no_program_name_join'})
        # A source-less Process node can be shared by unrelated spawn sites.
        # Retain its ID as evidence metadata, without adding an instance edge.
        if not matched or not target.get('path'):
            diagnostics.append({'kind': 'native_process_site_gap', 'path': caller['path'], 'line': line,
                                'source': uid, 'anchor_status': status, 'counterpart_status': counterpart,
                                'reason': 'source_anchor_or_executable_counterpart_unresolved'})
    return {'nodes': added, 'edges': links, 'diagnostics': diagnostics,
            'summary': {'adapter': VERSION, 'counts': dict(counts),
                        'limits': ['native_candidates_are_not_execution_evidence',
                                   'shared_program_descriptions_are_not_process_instances',
                                   'unmatched_native_sites_do_not_establish_boundary_completeness']}}


def augment(graph):
    if 'native_process_sites' in graph:
        raise ValueError('Native process sites already projected')
    result = project(graph['nodes'], graph['edges'], source_commit=graph['source_commit'])
    for key in ('nodes', 'edges', 'diagnostics'):
        graph[key].extend(result[key])
    graph['native_process_sites'] = result['summary']
    graph.setdefault('extractors', {})['native_process_sites'] = VERSION
    return graph
