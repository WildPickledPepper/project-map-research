"""Post-extraction source contracts and public-query checks for every frozen component.

References are selected from pinned source before opening the fact index. This
checks representative declaration/import fidelity and navigation, not exhaustive
semantic recall or cross-boundary correctness. It never supplies production rules.
"""
import argparse
import ast
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.project_map import Budget, ProjectMap
from projectmap.workspace import Workspace

ROLES = {'first_party', 'build_support', 'deployment_support'}


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def references(source, path, language, parsers):
    """Read only source syntax; do not call production fact/linking adapters."""
    if language not in {'python', 'typescript', 'tsx', 'javascript', 'cpp', 'rust', 'shell'}:
        return []
    data = (source / path).read_bytes().replace(b'\r\n', b'\n')
    lines = data.decode('utf-8', errors='replace').splitlines()
    found = []
    if language == 'python':
        try:
            tree = ast.parse(data)
        except SyntaxError:
            return []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                found.append(('type' if isinstance(node, ast.ClassDef) else 'callable', node.name, node.lineno, node.lineno))
            elif isinstance(node, ast.alias):
                found.append(('module_reference', node.asname or node.name, node.lineno, node.lineno))
        if not tree.body or all(isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                                and isinstance(n.value.value, str) for n in tree.body):
            found.append(('code_module', path, 1, 1))
    elif language in {'typescript', 'tsx', 'javascript', 'cpp', 'rust', 'shell'}:
        import tree_sitter_language_pack as pack
        grammar = {'typescript': 'typescript', 'tsx': 'tsx', 'javascript': 'javascript',
                   'cpp': 'cpp', 'rust': 'rust', 'shell': 'bash'}[language]
        parser = parsers.setdefault(grammar, pack.get_parser(grammar))
        tree = parser.parse(data)
        kinds = {'function_declaration': 'callable', 'function_declarator': 'callable',
                 'function_item': 'callable', 'function_definition': 'callable',
                 'class_declaration': 'type', 'interface_declaration': 'type',
                 'type_alias_declaration': 'type', 'enum_declaration': 'type',
                 'class_specifier': 'type', 'struct_specifier': 'type',
                 'enum_specifier': 'type', 'alias_declaration': 'type',
                 'struct_item': 'type', 'enum_item': 'type', 'trait_item': 'type',
                 'type_item': 'type', 'variable_declarator': 'value', 'const_item': 'value',
                 'variable_assignment': 'value'}
        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            category = kinds.get(node.type)
            named = node.child_by_field_name('name')
            if node.type == 'function_declarator':
                named = node.child_by_field_name('declarator')
            if category and named is not None and named.type in {
                    'identifier', 'field_identifier', 'type_identifier', 'qualified_identifier', 'word', 'variable_name'}:
                name = named.text.decode('utf-8')
                if name and '<' not in name:
                    found.append((category, name.split('::')[-1], named.start_point[0] + 1,
                                  node.start_point[0] + 1))
            if node.type == 'preproc_include':
                named = node.child_by_field_name('path')
                if named:
                    found.append(('module_reference', named.text.decode('utf-8'), node.start_point[0] + 1,
                                  node.start_point[0] + 1))
            stack.extend(reversed(node.named_children))
    # Prefer real callable/type declarations to variables/imports, then source order.
    found.sort(key=lambda r: (r[0] not in {'callable', 'type'}, r[2], r[1]))
    unique = {}
    for kind, name, line, start_line in found:
        unique.setdefault((kind, name, line), {'kind': kind, 'name': name, 'path': path,
            'line': line, 'declaration_start_line': start_line,
            'source': lines[line - 1].strip()[:240]})
    return list(unique.values())[:2]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('trial', 'frozen-scope', 'output'):
        ap.add_argument('--' + name, required=True, type=Path)
    args = ap.parse_args()
    if args.output.exists():
        ap.error('Use a new output directory')
    args.output.mkdir(parents=True)
    frozen = load(args.frozen_scope / 'reviewed-scope.json')
    inventory = load(args.frozen_scope / 'module-inventory.json')
    trial = load(args.trial / 'trial.json')
    workspace = Workspace(args.trial / 'workspace')
    assert trial['build']['status'] == 'ready'
    active = workspace.config['active']
    assert frozen['source_commit'] == inventory['source_commit'] == active['source_commit']
    # Read the immutable export used by the published build, never a mutable tree.
    source = Path(active['graph']).parent / 'source'
    all_modules = {m['id']: m for m in inventory['modules']}
    required = {m['id']: m for m in frozen['modules']}
    owned = defaultdict(list)
    for row in inventory['files']:
        identifier = row['module']
        while identifier is not None and identifier not in required:
            identifier = all_modules[identifier]['parent']
        if identifier and row['scope_role'] in ROLES:
            owned[identifier].append(row)
    import os
    import tree_sitter_language_pack as pack
    if os.environ.get('PROJECT_MAP_PARSER_CACHE'):
        pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))
    parsers = {}
    contracts = []
    for identifier in required:
        selected = []
        for row in sorted(owned[identifier], key=lambda f: f['path']):
            refs = references(source, row['path'], row.get('language'), parsers)
            if refs:
                selected.extend(refs)
                if len({r['path'] for r in selected}) >= 2:
                    break
        contracts.append({'id': identifier, 'references': selected,
                          'selection': 'first_two_declaration_bearing_owned_sources_in_path_order'})
    # Freeze expected declarations BEFORE consulting graph contents.
    (args.output / 'source-contracts.json').write_text(json.dumps({
        'source_commit': frozen['source_commit'], 'modules': contracts,
        'origin': 'pinned_source_syntax_before_fact_index_read',
        'independence_limit': 'shared_standard_grammars; representative_declarations_not_full_semantic_oracle'},
        ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    q = ProjectMap(workspace.directory / active['index'], budget=Budget(10, 500, 500, 524288),
                   expected_snapshot=active['snapshot'])
    reports = []
    try:
        for contract in contracts:
            checks = []
            for reference in contract['references']:
                rows = [json.loads(r[0]) for r in q.db.execute(
                    'SELECT payload FROM pm_fact_nodes WHERE snapshot=? AND path=? AND kind=?',
                    (active['snapshot'], reference['path'], reference['kind']))]
                matches = [n for n in rows if n['name'].replace('::', '.').split('.')[-1] == reference['name'].replace('::', '.').split('.')[-1]
                           and reference['declaration_start_line'] <= n['line'] <= reference['line']]
                visible = q.search(reference['path'], kind=reference['kind'], limit=200)
                visible_ids = {n['id'] for n in visible['items']}
                if matches:
                    chosen = next((n for n in matches if n['id'] in visible_ids), matches[0])
                    status = q.status(chosen['id'])
                    proof = q.source(workspace.source, selector=chosen['id'], line=reference['line'], context=0)
                    neighbors = {direction: q.neighbors(chosen['id'], direction=direction, limit=2)
                                 for direction in ('in', 'out')}
                    ok = (chosen['id'] in visible_ids and status['items'][0]['id'] == chosen['id']
                          and proof['source_commit'] == frozen['source_commit']
                          and proof['path'] == reference['path']
                          and proof['items'] and proof['items'][0]['text'].strip()[:240] == reference['source'])
                    checks.append({**reference, 'passed': bool(ok), 'matched_ids': [n['id'] for n in matches],
                        'query_node': chosen['id'], 'search_truncated': visible.get('truncated', False),
                        'native_provenance': {k: v for k, v in chosen.get('provenance', {}).items()
                                              if k in {'provider', 'version', 'adapter', 'context', 'source_commit'}},
                        'neighbor_kinds': {d: [r['kind'] for r in result['items']] for d, result in neighbors.items()}})
                else:
                    checks.append({**reference, 'passed': False, 'matched_ids': [], 'reason': 'expected_source_declaration_not_found'})
            reports.append({'id': contract['id'], 'checks': checks,
                'representative_source_contract': 'passed' if checks and all(c['passed'] for c in checks) else 'needs_review',
                'G02': 'pending_remaining_semantic_and_diagnostic_review'})
    finally:
        q.close()
    result = {'schema': 'repository-source-contract-review/1', 'source_commit': frozen['source_commit'],
        'snapshot': active['snapshot'], 'rules_version': active['build_version'],
        'required_components': len(required), 'modules': reports,
        'summary': dict(Counter(m['representative_source_contract'] for m in reports)),
        'checks': sum(len(m['checks']) for m in reports),
        'failed_checks': sum(not c['passed'] for m in reports for c in m['checks']),
        'whole_G02_accepted': False, 'runtime_execution': False, 'historical_assets_enabled': False,
        'interpretation': 'representative_definition_import_and_query_fidelity; not_exhaustive_call_or_data_recall'}
    (args.output / 'review.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('required_components', 'summary', 'checks', 'failed_checks')}))


if __name__ == '__main__':
    main()
