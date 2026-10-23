"""Score the fresh Insight build with the existing P3 reference assertions.

This is an experiment scorer, not an extraction input. Application identifiers
and expected answers remain in the P3 scorer.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT/'experiments/2026-10-23-p3'))
from run_combined import assess


def verify(directory, test_log, baseline):
    read = lambda name: json.loads((directory/name).read_text(encoding='utf-8'))
    graph = read('graph.json'); selection = read('selection.json'); request = read('request.json'); result = read('result.json')
    assert graph['source_commit'] == selection['source_commit'] == request['source_commit']
    assert graph['snapshot'] == request['snapshot']
    assert graph['version'] == {k: request[k] for k in ['source_commit', 'snapshot', 'config', 'build_version']}
    assert graph['input_paths'] == request['input_paths'] == [f['path'] for f in selection['files']]
    assert len(graph['input_paths']) == 154
    assert graph['provenance']['input_kind'] == 'git_committed_blob_export'
    assert graph['provenance']['working_tree_included'] is False
    assert graph['provenance']['update_mode'] == 'full_rebuild'
    assert graph['provenance']['trigger'] == 'explicit_cli'
    assert result['nodes'] == len(graph['nodes']) and result['edges'] == len(graph['edges'])
    assert result['storage'] == 'kuzu' and result['storage_roundtrip'] is True
    assert (directory/'graph.kuzu').is_file()
    scored = assess(graph)
    old = json.loads(baseline.read_text(encoding='utf-8'))
    assert old['source_commit'] == graph['source_commit'] and set(old['input_paths']) == set(graph['input_paths'])
    before = {n['id'] for n in old['nodes']}; after = {n['id'] for n in graph['nodes']}
    added = [n for n in graph['nodes'] if n['id'] not in before]
    log = test_log.read_text(encoding='utf-8')
    assert re.search(r'\nOK\s*$', log)
    return {'evidence_kind': 'executed_full_rebuild_and_existing_P3_case_assertions',
            'source_commit': graph['source_commit'], 'snapshot': graph['snapshot'], 'build_version': graph['version']['build_version'],
            'counts': scored['counts'], 'case_gates': scored['gates'], 'build': result,
            'previous_staged_build': {'snapshot': old['snapshot'], 'nodes': len(old['nodes']), 'edges': len(old['edges']),
                'added_node_kinds': dict(Counter(n['kind'] for n in added)), 'added_node_paths': dict(Counter(n['path'] for n in added)),
                'removed_node_ids': len(before - after), 'whole_graph_equivalence': 'not_claimed; all phases now use the final input scope'},
            'scope': 'same 154 selected paths as P3; committed source only',
            'omitted': dict(Counter(item['reason'] for item in selection['omitted'])),
            'tests': {'python': int(re.search(r'Ran (\d+) tests', log)[1]), 'passed': True},
            'automatic_trigger_and_publish': 'not_implemented_in_this_increment',
            'P4_acceptance': {key: 'pending' for key in ['U01', 'U02', 'U03', 'U04', 'U06']},
            'incremental': 'disabled; U05 not applicable',
            'file_hash_verification': 'not_run_per_user_preference'}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ['build', 'python-log', 'baseline', 'output']: ap.add_argument('--'+name, type=Path, required=True)
    args = ap.parse_args(); result = verify(args.build, args.python_log, args.baseline)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result))
