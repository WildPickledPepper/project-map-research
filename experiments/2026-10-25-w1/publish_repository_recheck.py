"""Publish post-build scores for one shared full-repository snapshot."""
import argparse
import json
from pathlib import Path
import re


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('rust', 'python', 'javascript', 'javascript-scope', 'output'):
        ap.add_argument('--' + name, type=Path, required=True)
    args = ap.parse_args()
    sources = {'rust': args.rust, 'python': args.python, 'javascript': args.javascript,
               'javascript-scope': args.javascript_scope}
    records = {key: json.loads(path.read_text(encoding='utf-8')) for key, path in sources.items()}
    basis = records['rust']
    for name, row in records.items():
        assert row['passed'] and not row['runtime_execution'] and not row['whole_G02_accepted']
        assert (row['source_commit'], row['snapshot'], row['build_version']) == (
            basis['source_commit'], basis['snapshot'], basis['build_version'])
        if name != 'javascript': assert row['index_counts'] == basis['index_counts']
    assert records['python']['scope'] == 'repository'
    # Full per-input coverage remains in the raw scorer output and published
    # language-specific records. The JS chain record only needs its witnesses.
    javascript = records['javascript']
    javascript.pop('coverage'); javascript.pop('input_paths')
    def portable(value):
        if isinstance(value, str):
            assert not re.search(r'[A-Za-z]:[\\/](?:Users|workspace)[\\/]', value), value
        elif isinstance(value, dict):
            for child in value.values(): portable(child)
        elif isinstance(value, list):
            for child in value: portable(child)
    for name, row in records.items():
        portable(row)
        path = args.output / ('multilang-repository-' + name + '.json')
        if path.exists(): ap.error('Evidence already exists: ' + path.name)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, row in records.items():
        (args.output / ('multilang-repository-' + name + '.json')).write_text(
            json.dumps(row, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('Published four language score records from one full-repository snapshot.')


if __name__ == '__main__': main()
