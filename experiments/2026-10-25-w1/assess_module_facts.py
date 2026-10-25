"""Compare a published fact index with the independently frozen component scope.

This is an accounting and gap report, not a semantic correctness/recall score.
The frozen scope is evaluator input and never enters production extraction.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from projectmap.workspace import Workspace

LANGUAGES = {'typescript', 'tsx', 'javascript', 'cpp', 'python', 'rust', 'shell'}
BASE_KINDS = {'callable', 'type', 'call_site', 'value', 'binding', 'parameter', 'module_reference',
              'object_binding', 'object_path', 'field_write'}
NON_TEST_ROLES = {'first_party', 'build_support', 'deployment_support'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('trial', 'frozen-scope', 'output'): ap.add_argument('--' + name, type=Path, required=True)
    args = ap.parse_args()
    if args.output.exists(): ap.error('Choose a new output path')
    load = lambda p: json.loads(p.read_text(encoding='utf-8'))
    frozen = load(args.frozen_scope / 'reviewed-scope.json')
    inventory = load(args.frozen_scope / 'module-inventory.json')
    trial = load(args.trial / 'trial.json')
    workspace = Workspace(args.trial / 'workspace'); active = workspace.config['active']
    db = sqlite3.connect((workspace.directory / active['index']).as_uri() + '?mode=ro', uri=True)
    info = json.loads(db.execute('SELECT payload FROM pm_map_info').fetchone()[0]); snapshot = info['snapshot']
    assert trial['scope'] == 'repository' and trial['build']['status'] == 'ready'
    assert frozen['G01'] == 'passed'
    assert info['source_commit'] == frozen['source_commit'] == inventory['source_commit']
    modules = {m['id']: m for m in frozen['modules']}
    all_modules = {m['id']: m for m in inventory['modules']}
    files = {f['path']: f for f in inventory['files']}
    graph_files = {row['path']: row for (raw,) in db.execute('SELECT payload FROM pm_map_files') if (row := json.loads(raw))}
    assert set(graph_files) == set(files)
    ancestors = {}
    for identifier in all_modules:
        chain = []; here = identifier
        while here is not None:
            assert here not in chain, 'Cyclic scope ownership'
            chain.append(here); here = all_modules[here]['parent']
        ancestors[identifier] = chain
    owner = {p: next((m for m in ancestors[f['module']] if m in modules), None) for p, f in files.items()}
    node_counts = defaultdict(Counter)
    for path, kind, count in db.execute('SELECT path,kind,count(*) FROM pm_fact_nodes WHERE snapshot=? GROUP BY path,kind', (snapshot,)):
        if path in files: node_counts[path][kind] = count
    cross_out = defaultdict(Counter); cross_in = defaultdict(Counter)
    for source_path, target_path, kind, count in db.execute('''SELECT s.path,t.path,e.kind,count(*)
        FROM pm_fact_edges e JOIN pm_fact_nodes s ON s.snapshot=e.snapshot AND s.id=e.source
        JOIN pm_fact_nodes t ON t.snapshot=e.snapshot AND t.id=e.target
        WHERE e.snapshot=? GROUP BY s.path,t.path,e.kind''', (snapshot,)):
        source = owner.get(source_path); target = owner.get(target_path)
        if (source and target and source != target and files[source_path]['scope_role'] in NON_TEST_ROLES
                and files[target_path]['scope_role'] in NON_TEST_ROLES):
            cross_out[source][kind] += count; cross_in[target][kind] += count
    records = []
    for identifier, module in modules.items():
        direct = [p for p, f in files.items() if f['module'] == identifier]
        inclusive = [p for p, f in files.items() if identifier in ancestors[f['module']]]
        owned = [p for p in files if owner[p] == identifier]
        source = [p for p in owned if graph_files[p].get('language') in LANGUAGES]
        production = [p for p in source if files[p]['scope_role'] in NON_TEST_ROLES]
        counts = Counter()
        for p in owned: counts.update(node_counts[p])
        missing = [{'path': p, 'language': graph_files[p].get('language'), 'role': graph_files[p]['role'], 'audited_role': files[p]['scope_role'],
                    'input': graph_files[p]['graph_input'], 'coverage': graph_files[p].get('graph_coverage'),
                    'discovery_reason': graph_files[p].get('reason'), 'node_counts': dict(node_counts[p])}
                   for p in production if not (BASE_KINDS & node_counts[p].keys())]
        not_parsed = [{'path': p, 'language': graph_files[p].get('language'), 'role': graph_files[p]['role'], 'audited_role': files[p]['scope_role'],
                       'discovery_reason': graph_files[p].get('reason'), 'coverage': graph_files[p].get('graph_coverage')}
                      for p in production if (graph_files[p].get('graph_coverage') or {}).get('status') != 'parsed']
        flags = []
        if not production: flags.append('no_owned_non_test_program_source_identified')
        if production and not any(BASE_KINDS & node_counts[p].keys() for p in production): flags.append('no_owned_non_test_language_facts')
        if missing: flags.append('owned_non_test_source_without_base_facts_requires_review')
        if not_parsed: flags.append('owned_non_test_source_not_parsed_requires_review')
        if not cross_in[identifier]: flags.append('no_incoming_intercomponent_facts_requires_review')
        if not cross_out[identifier]: flags.append('no_outgoing_intercomponent_facts_requires_review')
        records.append({'id': identifier, 'role': module['role'], 'required_runtime_component': module['required_runtime_component'],
            'required_support_component': module['required_support_component'],
            'scope_counts': {'direct_files': len(direct), 'inclusive_files': len(inclusive),
                             'nearest_required_owner_files': len(owned), 'owned_program_sources': len(source),
                             'owned_non_test_program_sources': len(production)},
            'source_languages': dict(Counter(graph_files[p]['language'] for p in production)),
            'owned_node_counts': dict(counts), 'outgoing_edge_kinds': dict(cross_out[identifier]),
            'incoming_edge_kinds': dict(cross_in[identifier]),
            'sources_without_base_facts': missing, 'sources_not_parsed': not_parsed,
            'review_flags': flags, 'G02': 'pending_independent_semantic_review',
            'G03_G08': 'not_accepted_by_this_report'})
    checks = [
        {'id': 'same_pinned_source_and_published_snapshot', 'passed': snapshot == active['snapshot'] == trial['build']['snapshot']},
        {'id': 'all_frozen_required_components_reported', 'passed': {r['id'] for r in records} == set(modules)},
        {'id': 'all_frozen_tracked_files_accounted', 'passed': set(files) == set(graph_files)},
        {'id': 'unique_nearest_required_ownership', 'passed': sum(r['scope_counts']['nearest_required_owner_files'] for r in records) == sum(v is not None for v in owner.values())},
        {'id': 'cross_component_edge_counts_conserved', 'passed': sum(sum(v.values()) for v in cross_in.values()) == sum(sum(v.values()) for v in cross_out.values())},
        {'id': 'no_inherited_semantic_gate_pass', 'passed': all(r['G02'] != 'passed' for r in records)},
    ]
    result = {'schema': 'frozen-component-fact-audit/1', 'source_commit': info['source_commit'], 'snapshot': snapshot,
        'build_version': info['graph_version']['build_version'], 'index_counts': info['counts'],
        'scope_basis': {'rules_version': frozen['rules_version'], 'audit_version': frozen['audit_version'],
                        'required_components': len(modules), 'role': 'independent_evaluator_input_only'},
        'ownership': 'closest_required_ancestor_from_frozen_parent_graph; inclusive_counts_overlap; node_and_edge_counts_use_closest_owner',
        'non_test_source_and_intercomponent_edges': 'frozen_scope_role_first_party_build_support_or_deployment_support',
        'test_role_disagreements': [{'path': p, 'audited_role': f['scope_role'], 'discovery_role': graph_files[p]['role']}
            for p, f in files.items() if graph_files[p].get('language') in LANGUAGES and
            (f['scope_role'] == 'test') != (graph_files[p]['role'] == 'test')],
        'base_fact_kinds': sorted(BASE_KINDS), 'summary': {
            'required_runtime_components': sum(r['required_runtime_component'] for r in records),
            'required_support_components': sum(r['required_support_component'] for r in records),
            'review_flag_counts': dict(Counter(flag for r in records for flag in r['review_flags'])),
            'owned_non_test_sources_not_parsed': sum(len(r['sources_not_parsed']) for r in records),
            'owned_non_test_sources_without_base_facts': sum(len(r['sources_without_base_facts']) for r in records)},
        'modules': records, 'checks': checks, 'passed': all(r['passed'] for r in checks),
        'interpretation': 'accounting_and_review_queue_not_semantic_correctness_or_recall',
        'whole_G02_accepted': False, 'overall_technical_acceptance': False,
        'runtime_execution': False, 'historical_assets_enabled': False}
    db.close(); args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({'summary': result['summary'], 'checks': checks, 'passed': result['passed']}))
    if not result['passed']: raise SystemExit(1)


if __name__ == '__main__': main()
