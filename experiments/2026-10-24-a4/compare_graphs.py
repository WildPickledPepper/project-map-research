"""Compare complete parsed graph contents, excluding only snapshot identity."""
import argparse
import json
from pathlib import Path
import time


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--first', type=Path, required=True)
    p.add_argument('--second', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    started = time.perf_counter()
    with a.first.open(encoding='utf-8') as f: first = json.load(f)
    with a.second.open(encoding='utf-8') as f: second = json.load(f)
    ids = [first['snapshot'], second['snapshot']]
    versions = [first['version']['build_version'], second['version']['build_version']]
    for value in (first, second): value.pop('snapshot'); value['version'].pop('snapshot')
    differences = [k for k in sorted(set(first) | set(second)) if first.get(k) != second.get(k)]
    result = {'evidence_kind': 'executed_complete_graph_direct_JSON_comparison',
        'source_commit': first['source_commit'], 'snapshots': ids, 'build_versions': versions,
        'equal': first == second, 'differing_top_level_keys': differences,
        'counts': {'nodes': len(first['nodes']), 'edges': len(first['edges']), 'inputs': len(first['input_paths'])},
        'elapsed_seconds': round(time.perf_counter()-started, 4),
        'comparison': 'direct parsed JSON equality excluding only snapshot and version.snapshot',
        'file_hash_verification': 'not_run_per_user_preference'}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result))
