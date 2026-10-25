"""Evaluate generated scope against separately authored committed-source references.

This research-only evaluator never supplies module names to the production generator.
"""
import argparse
from collections import Counter
import json
from pathlib import Path, PurePosixPath
import re
import subprocess


def git(source, *args):
    return subprocess.check_output(['git', '-C', str(source), *args])


def verify(source, inventory, reference):
    documents = {name: json.loads((inventory / (name + '.json')).read_text(encoding='utf-8'))
                 for name in ('module-inventory', 'boundary-inventory', 'mechanism-matrix',
                              'runtime-modes', 'coverage-baseline')}
    revision = reference['source_commit']
    paths = set(git(source, 'ls-tree', '-r', '--name-only', '-z', revision).decode().split('\0')) - {''}
    checks = []

    def check(name, condition, detail=None):
        checks.append({'id': name, 'passed': bool(condition), 'detail': detail})

    def text(path):
        return git(source, 'show', revision + ':' + path).decode('utf-8')

    def source_evidence(spec):
        if spec.get('kind') == 'directory':
            found = sorted(p for p in paths if p.startswith(spec['path'] + '/'))
            return {'path': spec['path'], 'tracked_descendants': len(found), 'present': bool(found)}
        found = [n for n, line in enumerate(text(spec['path']).splitlines(), 1)
                 if spec['contains'] in line] if spec['path'] in paths else []
        return {'path': spec['path'], 'contains': spec['contains'], 'lines': found, 'present': bool(found)}

    files = documents['module-inventory']['files']
    modules = {m['id']: m for m in documents['module-inventory']['modules']}
    counts = Counter(f['path'] for f in files)
    check('all_committed_paths_exactly_once', set(counts) == paths and all(n == 1 for n in counts.values()),
          {'expected': len(paths), 'actual': len(files), 'missing': sorted(paths - set(counts)),
           'extra': sorted(set(counts) - paths)})
    check('all_documents_same_source_and_rules', all(d['source_commit'] == revision and
          d['rules_version'] == documents['coverage-baseline']['rules_version'] for d in documents.values()))
    check('all_files_have_owner_and_scan_state', all(f['module'] in modules and f['scope_scan'] for f in files))
    check('no_working_tree_or_semantic_completion_claim', all(not d['working_tree_included'] and
          not d['semantic_graph_produced'] for d in documents.values()))
    check('all_required_scopes_discovered', set(reference['required_scopes']) <= set(modules),
          {'missing': sorted(set(reference['required_scopes']) - set(modules))})

    # Enumerate source families independently of the generator's module logic.
    group_results = []
    code_suffixes = {'.cpp', '.h', '.hpp', '.py', '.rs', '.ts', '.tsx', '.js', '.mjs', '.cjs', '.sh'}
    for group in reference['group_checks']:
        prefix = group['path'] + '/'
        if group['selector'] == 'direct_child_workspace_packages':
            members = [group['path'] + '/' + m for m in
                       re.findall(r"^\s*-\s*['\"]([^'\"]+)['\"]", text(group['evidence']['path']), re.M)]
        elif group['selector'] == 'direct_child_source_directories':
            members = sorted({prefix + p[len(prefix):].split('/')[0] for p in paths if
                              p.startswith(prefix) and '/' in p[len(prefix):] and
                              PurePosixPath(p).suffix.lower() in code_suffixes})
        else:
            raise ValueError('Unknown independent group selector: ' + group['selector'])
        missing = sorted(set(members) - set(modules))
        evidence = source_evidence(group['evidence'])
        check('source_group.' + group['id'], members and not missing and evidence['present'],
              {'members': members, 'missing': missing, 'evidence': evidence})
        group_results.append({'id': group['id'], 'members': members})

    anchors = {}
    for spec in reference['source_anchors']:
        evidence = source_evidence(spec)
        anchors[spec['id']] = evidence
        check('source_anchor.' + spec['id'], evidence['present'], evidence)

    required_modes = []
    for spec in reference['runtime_mode_obligations']:
        valid = spec['module'] in modules and all(anchors[a]['present'] for a in spec['anchors'])
        check('mode_reference.' + spec['id'], valid)
        required_modes.append({**spec, 'origin': 'manual_independent_source_review',
                               'evidence': [anchors[a] for a in spec['anchors']],
                               'execution_status': 'not_executed', 'acceptance_gate': 'G06'})

    matrix = documents['mechanism-matrix']
    pairs = Counter((r['module'], r['mechanism']) for r in matrix['items'])
    check('all_modules_eighteen_mechanisms', len(matrix['mechanisms']) == 18 and
          set(pairs) == {(m, family) for m in modules for family in matrix['mechanisms']} and
          all(n == 1 for n in pairs.values()))
    check('no_signal_remains_unknown', all(r['applicability'] != 'not_applicable' and
          r['status'] == 'not_accepted' for r in matrix['items']))
    missing=set(documents['coverage-baseline']['whole_project_languages_missing'])
    partial={lang for m in modules.values() for lang,state in m['semantic_support'].items()
             if state=='preexisting_partial_not_accepted_for_module' and m['gate_status']['G02']=='not_executed'}
    check('required_language_gaps_remain_visible', set(reference['mandatory_language_gaps']) <= missing|partial)
    boundaries = documents['boundary-inventory']['boundaries']
    check('signals_are_candidates_with_unresolved_counterparts', all(b['module'] in modules and
          b['counterpart'] is None and b['resolution'] == 'not_semantically_extracted' for b in boundaries))
    check('candidate_ids_unique', len({b['id'] for b in boundaries}) == len(boundaries))
    check('no_historical_asset_input_or_overall_pass', not documents['coverage-baseline']['historical_assets_enabled']
          and documents['coverage-baseline']['overall_technical_acceptance'] == 'not_passed')

    obligations = []
    for module in modules.values():
        if not (module['required_runtime_review'] or module.get('required_support_review')):
            continue
        for gate, work in [('G02', 'semantic_facts_and_independent_language_reference'),
                           ('G03', 'boundary_identities_counterparts_conditions_and_negative_cases'),
                           ('G04', 'upstream_downstream_connections_or_audited_independence'),
                           ('G05', 'resource_ownership_and_all_applicable_mechanisms'),
                           ('G06', 'actual_consumer_scenario_and_independent_assertions'),
                           ('G07', 'new_rename_delete_and_configuration_change_refresh'),
                           ('G08', 'installed_tool_search_expansion_and_source_navigation')]:
            obligations.append({'id': gate + ':' + module['id'], 'module': module['id'], 'gate': gate,
                                'work': work, 'status': 'not_executed'})

    unresolved = [
        'module role/responsibility and resource ownership review is incomplete',
        'independent interface references and negative cases for every boundary family are incomplete',
        'build-context mode combinations and data-tool scenarios require source review',
        'semantic boundary identities are not frozen by lexical candidate counts',
    ]
    return {'schema': 'independent-scope-review/1', 'source_commit': revision,
            'rules_version': documents['coverage-baseline']['rules_version'],
            'reference_origin': reference['origin'], 'checks': checks,
            'scope_checks_passed': all(c['passed'] for c in checks), 'groups': group_results,
            'source_anchors': anchors, 'required_modes': required_modes, 'module_obligations': obligations,
            'summary': documents['coverage-baseline']['summary'],
            'G01': 'in_progress', 'G01_remaining': unresolved,
            'overall_technical_acceptance': 'not_passed', 'runtime_executed': False,
            'hash_reverification': 'not_run_per_user_preference'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--reference', type=Path, default=Path(__file__).with_name('scope-reference.json'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Choose a new review output directory')
    result = verify(args.source, args.inventory, json.loads(args.reference.read_text(encoding='utf-8')))
    args.output.mkdir(parents=True)
    (args.output / 'scope-review.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('source_commit', 'rules_version', 'scope_checks_passed', 'summary', 'G01')}, ensure_ascii=False))
    print(json.dumps({'checks': len(result['checks']), 'failed': [c for c in result['checks'] if not c['passed']],
                      'mode_obligations': len(result['required_modes']), 'module_obligations': len(result['module_obligations'])}, ensure_ascii=False))
    if not result['scope_checks_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
