"""Run native provider checks for template, inheritance, alias and cfg semantics."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.clangd_provider import analyze
from adapters.sqlite_fact_graph import validate_graph

FILES = {'api/types.hpp': '''namespace first { struct Item { int value; }; }
namespace second { struct Item { int value; }; }
using Chosen = first::Item;
struct Parent { int action(int) { return 1; } };
struct Child: Parent {};
template<class T> T identity(T input) { return input; }
#if FEATURE_MODE
inline int enabled() { return 1; }
#else
inline int disabled() { return 0; }
#endif
''', 'runner/main.cpp': '''#include "../api/types.hpp"
int main() {
  Child child;
  Chosen item{};
  second::Item another{};
  item.value = identity<int>(child.action(1));
  another.value = 7;
  return enabled() + item.value;
}
'''}
EXPECTED = ['native_ast_for_both_files', 'inherited_method_target', 'template_call_target',
            'active_preprocessor_branch', 'inactive_branch_absent', 'same_name_field_targets_isolated',
            'member_and_receiver_reference_identities_distinct', 'native_alias_declaration_present']


async def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    source = args.output / 'source'; source.mkdir()
    active, inactive = ('enabled', 'disabled') if args.feature_mode else ('disabled', 'enabled')
    header, entry = ('api/types.hpp', 'runner/main.cpp') if args.layout == 'first' else ('lib/model.hpp', 'app/launch.cpp')
    files = {header: FILES['api/types.hpp'], entry: FILES['runner/main.cpp'].replace(
        '../api/types.hpp', '../' + header).replace('return enabled()', 'return ' + active + '()')}
    for name, content in files.items():
        path = source / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    (source / 'compile_commands.json').write_text(json.dumps([{'directory': str(source),
        'file': str(source / entry), 'arguments': ['clang++', '-std=c++17',
        '-DFEATURE_MODE=' + str(args.feature_mode), '-c', str(source / entry)]}]), encoding='utf-8')
    (args.output / 'expected.json').write_text(json.dumps(EXPECTED), encoding='utf-8')
    facts = await analyze(source, list(files), binary=args.binary, context='feature-' + str(args.feature_mode),
        source_commit='a' * 40, output=args.output / 'native', compile_commands=source)
    validate_graph({'snapshot': 'authored', **facts})
    (args.output / 'facts.json').write_text(json.dumps(facts), encoding='utf-8')
    nodes = {n['id']: n for n in facts['nodes']}
    refs = [(nodes[e['source']], nodes[e['target']]) for e in facts['edges'] if e['kind'] == 'CLANGD_REFERS_TO_DECLARATION']
    checks = [
        ('native_ast_for_both_files', len(facts['coverage']) == 2 and all(r['status'] == 'parsed' for r in facts['coverage'])),
        ('inherited_method_target', any(a['name'] == 'action' and b['path'] == header and b['line'] == 4 for a, b in refs)),
        ('template_call_target', any(a['name'] == 'identity' and b['path'] == header and b['line'] == 6 for a, b in refs)),
        ('active_preprocessor_branch', any(n['kind'] == 'callable' and n['name'] == active for n in nodes.values())),
        ('inactive_branch_absent', not any(n['kind'] == 'callable' and n['name'] == inactive for n in nodes.values())),
        ('same_name_field_targets_isolated', {b['line'] for a, b in refs if a['name'] == 'value' and b['path'] == header} == {1, 2}),
        ('member_and_receiver_reference_identities_distinct', all(a['id'] != b['id'] for a in nodes.values() for b in nodes.values() if a['kind'] == b['kind'] == 'symbol_reference' and a['path'] == b['path'] and a['line'] == b['line'] and a['column'] == b['column'] and a['native_kind'] != b['native_kind'])),
        ('native_alias_declaration_present', any(n['name'] == 'Chosen' and n['path'] == header for n in nodes.values()))]
    result = {'schema': 'r0-clang-provider/1', 'evidence_kind': 'executed_native_component',
        'checks': [{'id': name, 'passed': bool(passed)} for name, passed in checks],
        'components': facts['components'], 'coverage': facts['coverage'],
        'passed': all(passed for _, passed in checks), 'whole_G02_accepted': False}
    (args.output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--feature-mode', type=int, choices=(0, 1), default=1)
    parser.add_argument('--layout', choices=('first', 'alternate'), default='first')
    asyncio.run(run(parser.parse_args()))
