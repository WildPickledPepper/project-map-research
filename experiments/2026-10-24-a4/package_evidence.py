"""Package A4 results while retaining negative findings and first-run mistakes."""
import argparse
import json
from pathlib import Path
import re
import sys
import subprocess

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.project_map import ProjectMap


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def package(results, output):
    output.mkdir(parents=True, exist_ok=True)
    def save(name, value):
        text = json.dumps(value, ensure_ascii=False, indent=2)+'\n'
        if re.search(r'[A-Za-z]:[\\/](?:Users|workspace)[\\/]', text):
            raise ValueError('Workspace path in public evidence: '+name)
        (output/name).write_text(text, encoding='utf-8')
    mappings = {'first-chain-results-raw.json': 'a4-heldout-first-01/first-results.json',
        'reviewed-chain-results.json': 'a4-heldout-reviewed-02/first-results.json',
        'history.json': 'a4-history-first-02/history.json', 'history-pair.json': 'a4-history-pair-01/result.json',
        'source-updates.json': 'a4-product-02/preparation.json', 'update-controls.json': 'a4-updates-first-01/result.json',
        'updated-map.json': 'a4-map-update-first-01/result.json', 'rebuild.json': 'a4-comparison-01/comparison.json',
        'comparison-cost.json': 'a4-comparison-01/cost.json',
        'publication-validation.json': 'a4-publication-first-01/result.json',
        'known-regression.json': 'a4-known-regression-final-02/queries/validation.json',
        'index.json': 'a4-index-first.json'}
    for name, path in mappings.items(): save(name, read(results/path))
    builds = [read(results/name/'result.json') for name in ('a4-full-first-01', 'a4-full-rebuild-01')]
    save('full-builds.json', {'evidence_kind': 'executed_full_scope_builds_on_updated_product_copy', 'runs': builds})
    py = (results/'a4-python-tests.txt').read_text(encoding='utf-8')
    ts = (results/'a4-typescript-tests.txt').read_text(encoding='utf-8')
    count = re.search(r'Ran (\d+) tests in ([0-9.]+)s', py)
    assert count and py.rstrip().endswith('OK') and '# fail 0' in ts
    save('tests.json', {'evidence_kind': 'executed_complete_local_test_suites',
        'python': {'passed': int(count[1]), 'seconds': float(count[2]), 'failures': 0},
        'typescript': {'passed': int(re.search(r'# tests (\d+)', ts)[1]), 'failures': 0},
        'new_evaluation_negative_controls': 5})
    first_preparation = read(results/'a4-product-01/preparation.json')
    save('first-failures.json', {'evidence_kind': 'retained_executed_first_attempts_and_methodology_corrections', 'items': [
        {'stage': 'product_copy_preparation', 'unintended_changed_paths': sum(not p.startswith('a4_') for p in first_preparation['changed_paths']),
            'issue': 'checkout inherited autocrlf before it was disabled; staging all paths recorded line-ending changes',
            'treatment': 'first copy excluded before product extraction; new copy disables conversion at checkout, stages only authored paths and asserts exact five-file scope'},
        {'stage': 'historical_source_read', 'record': 10, 'issue': 'older blob absent from the local partial clone',
            'treatment': 'fetch needed historical objects in the isolated A4 clone; original source checkout unchanged'},
        {'stage': 'first_reference_and_scoring', 'original_correct_protocol_pairs': 2,
            'issues': ['cluster UI group was incorrectly used as backend protocol scope',
                'export-name-only selection missed the returned anonymous callback', 'unmatched rows were initially grouped under identified_unknown'],
            'treatment': 'retain original reference and results; source-reviewed reference uses actual module constant and source call coordinates; extraction rules unchanged'},
        {'stage': 'legacy_regression_overview_adapter', 'failed_attempts': 2,
            'issue': 'automatic discovery uses files/manifests while legacy renderer expects file_count/metadata/dependencies',
            'treatment': 'adapt only the report inventory fields; final 19 known-chain checks pass'},
        {'stage': 'reviewed_reference_preparation', 'issue': 'one command literal occurs in two exported functions in the same source file',
            'treatment': 'choose the source call inside the selected API declaration; rejected input attempt produced no graph score'}]})
    reference = read(Path(__file__).parent/'reference-reviewed.json')
    phase = read(results/'a4-full-first-01/build/typescript_protocol_flow.cjs.json')
    checkpoint = read(results/'a4-full-first-01/build/protocol-checkpoint.json')
    details = []
    for case in reference['cases']:
        consumers = [c for c in phase['protocol']['consumers'] if c['path'] == case['api_path'] and c['line'] == case['source_call_line']]
        providers = [p for p in checkpoint['protocol']['providers'] if p['command'] == case['command']]
        details.append({'id': case['id'], 'source_call': {'path': case['api_path'], 'line': case['source_call_line']},
            'source_consumers': [{'name': c['name'], 'status': c['status'],
                'socket_payloads': [{k: v for k, v in b.get('payload', {}).get('fields', {}).items() if k in {'command', 'moduleName'}}
                    for b in c['boundaries'] if b['transport'] == 'socket']} for c in consumers],
            'provider_candidates_for_source_command': len(providers),
            'provider_paths': [p['path'] for p in providers]})
    q = ProjectMap(results/'a4-navigation-first-01/map.sqlite')
    try:
        path = 'modules/operator/src/components/operator/DetailChart.tsx'
        states = [dict(r) for r in q.db.execute('''SELECT kind,name,path,line FROM pm_fact_nodes WHERE path=?
            AND kind IN ('frontend_state_path','frontend_state_write','frontend_field_read','api_result_field') ORDER BY rowid''', (path,))]
    finally:
        q.close()
    save('gap-evidence.json', {'evidence_kind': 'executed_phase_and_index_inspection', 'request_records': details,
        'operator_frontend_facts': states,
        'interpretation': ['debounced iteration command/module values remain unknown',
            'group request exists under an anonymous callback identity', 'two templated MemScope request registrations produce no provider candidates',
            'operator response reads and reset writes exist; expected mapped-data state writes are not linked',
            'compute-unit serialized field relation missing in the response query'],
        'cause_scope': 'these are observed facts; exact missing semantic models require separate focused controls'})
    reviewed = read(output/'reviewed-chain-results.json')
    controls = read(output/'update-controls.json')
    updated = read(output/'updated-map.json')
    rebuilt = read(output/'rebuild.json')
    known = read(output/'known-regression.json')
    history = read(output/'history.json')
    pair = read(output/'history-pair.json')
    baseline = 'b85ba0cb3cfc0d89856ce7fed63ca28da705c215'
    implementation_delta = subprocess.check_output(['git', '-C', str(ROOT), 'diff', '--name-only', baseline, '--',
        'adapters', 'scripts', 'experiments/2026-10-24-p7', 'requirements-*.txt', 'package*.json'], text=True).splitlines()
    delivery = {'frozen_source_references_present': len(reference['cases']) == 6,
        'all_six_cases_scored_without_script_error': reviewed['counts']['scored'] == 6 and not any(c.get('scoring_error') for c in reviewed['cases']),
        'all_twelve_history_records_audited': history['counts']['denominator'] == 12,
        'historical_changed_source_pair_extracted': pair['passed'],
        'real_refresh_update_controls_pass': controls['passed'], 'updated_full_map_identity_checks_pass': updated['update_fidelity_passed'],
        'both_complete_builds_succeeded': all(b['status'] == 'passed' for b in builds),
        'complete_rebuild_equal': rebuilt['equal'], 'known_regressions_pass': known['passed'],
        'no_extraction_rules_changed': not implementation_delta and all(b['source_commit'] == rebuilt['source_commit'] for b in builds) and rebuilt['build_versions'][0] == rebuilt['build_versions'][1]}
    gates = {'all_six_expected_protocol_pairs_recovered': reviewed['counts']['correct_protocol_pairs'] == 6 and reviewed['counts']['wrong_protocol_pairs'] == 0,
        'expected_named_frontend_states_connected': reviewed['counts']['return_state_relations'] == reviewed['counts']['state_reference_denominator'],
        'direct_socket_protocol_consumers_visible': updated['protocol_discovery_passed'],
        'update_fidelity': updated['update_fidelity_passed'] and controls['passed'],
        'reproducible_full_build': rebuilt['equal'], 'known_chain_regression': known['passed']}
    save('evaluation.json', {'evidence_kind': 'A4_evaluation_delivery_and_tool_acceptance_separated',
        'protocol_commit': '379da8d', 'initial_reference_commit': 'bd5d2a8',
        'tool_baseline': 'b85ba0cb3cfc0d89856ce7fed63ca28da705c215',
        'extraction_changes_since_A2': [], 'implementation_path_delta_since_frozen_baseline': implementation_delta,
        'A3_only_implementation_additions': ['adapters/project_map.py', 'scripts/project_map.py', 'scripts/render_project_map.py'],
        'evaluation_complete': all(delivery.values()), 'delivery_checks': delivery,
        'tool_acceptance_passed': all(gates.values()), 'tool_gates': gates,
        'reviewed_counts': reviewed['counts'], 'initial_reference_corrected_after_first_output': True,
        'original_first_output_retained': True, 'extraction_rules_adapted_to_validation': False,
        'runtime_reproduction_count': 0, 'historical_full_repository_bad_fixed_graph_pairs': 0,
        'historical_two_file_cpp_fact_pairs': 1,
        'conclusion': 'A4 evaluation complete; current tool fails new-module connection and direct-transport discovery acceptance',
        'file_hash_verification': 'not_run_per_user_preference'})
    print(json.dumps({'evaluation_complete': all(delivery.values()), 'tool_acceptance_passed': all(gates.values()),
        'reviewed_counts': reviewed['counts']}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results', type=Path, required=True)
    p.add_argument('--output', type=Path, default=Path(__file__).parent/'evidence')
    a = p.parse_args()
    package(a.results, a.output)
