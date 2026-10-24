"""Extract both sides of record 24's source change with the frozen C++ analyzer.

Input is all product C++ files changed by the fix, not an end-to-end repository
snapshot. External calls remain outside this two-file fact scope.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.cpp_facts import analyze
import tree_sitter_language_pack as pack


def run(source, history, output):
    output.mkdir(parents=True, exist_ok=False)
    data = json.loads(history.read_text(encoding='utf-8'))
    record = next(r for r in data['records'] if r['id'] == 24)
    inputs = [p for p in record['source_diff']['changed_paths'] if p.endswith(('.cpp', '.h')) and '/test/' not in p]
    if os.environ.get('PROJECT_MAP_PARSER_CACHE'):
        pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))
    parser = pack.get_parser('cpp')
    versions = {}
    for label, revision in [('before', record['source_versions']['pre_fix_first_parent']), ('after', record['source_versions']['fixed_merge'])]:
        blobs = {p: subprocess.check_output(['git', '-C', str(source), 'show', revision + ':' + p], stderr=subprocess.PIPE) for p in inputs}
        graph = analyze(blobs, parser)
        nodes = {n['id']: n for n in graph['nodes']}
        calls = [n for n in graph['nodes'] if n['kind'] == 'call_site' and n['name'] == 'HasNumaData']
        rows = []
        for call in calls:
            owners = [nodes[e['source']] for e in graph['edges'] if e['target'] == call['id'] and e['kind'] == 'OBSERVES_CALL']
            rows.append({'call': {k: call[k] for k in ('id', 'kind', 'name', 'path', 'line')},
                'owners': [{k: n[k] for k in ('id', 'name', 'path', 'line')} for n in owners],
                'target_edges': [e for e in graph['edges'] if e['source'] == call['id']]})
        versions[label] = {'source_commit': revision, 'input_paths': inputs, 'nodes': len(graph['nodes']),
            'edges': len(graph['edges']), 'coverage': graph['coverage'], 'numa_calls': rows}
        (output/(label+'-facts.json')).write_text(json.dumps(graph, ensure_ascii=False, separators=(',', ':'))+'\n', encoding='utf-8')
    old = versions['before']['numa_calls']
    new = versions['after']['numa_calls']
    checks = {'two_general_import_calls_before': len(old) == 2 and all(r['call']['path'].endswith('/ImportActionHandler.cpp') for r in old),
        'one_db_parser_call_after': len(new) == 1 and new[0]['call']['path'].endswith('/ProjectParserDb.cpp'),
        'general_import_direct_calls_removed': not any(r['call']['path'].endswith('/ImportActionHandler.cpp') for r in new),
        'all_three_calls_have_source_owner': all(r['owners'] for r in old+new)}
    result = {'evidence_kind': 'executed_historical_before_after_cpp_fact_extraction', 'historical_record': 24,
        'selection': 'all product C++ files changed by the pinned fix', 'versions': versions, 'checks': checks,
        'passed': all(checks.values()), 'limits': ['two-file changed-source fact scope',
            'external receiver targets and complete downstream chain not validated here',
            'TEXT cache corruption and timing require runtime evidence'], 'runtime_reproduced': False}
    (output/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'checks': checks, 'counts': {k: len(v['numa_calls']) for k, v in versions.items()}}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('source', 'history', 'output'): p.add_argument('--'+key, type=Path, required=True)
    a = p.parse_args()
    run(a.source, a.history, a.output)
