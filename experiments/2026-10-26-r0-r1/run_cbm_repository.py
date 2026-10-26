"""Export committed repository inputs and run the original CBM indexer."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.cbm_provider import index
from adapters.snapshot_inputs import export_inputs, select_inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'output', 'binary', 'cache-dir', 'runtime-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--revision', required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Use a new output')
    selection = select_inputs(args.source, args.revision, {'version': 1,
        'scope': {'include': ['*'], 'exclude': []}, 'deployment': {}, 'storage': 'json'})
    args.output.mkdir(parents=True)
    (args.output / 'selection.json').write_text(json.dumps(selection), encoding='utf-8')
    export_inputs(args.source, selection, args.output / 'source')
    paths = [r['path'] for r in selection['files']]
    facts = index(args.output / 'source', args.output / 'native', paths=paths,
        source_commit=selection['source_commit'], binary=args.binary,
        cache_dir=args.cache_dir, runtime_dir=args.runtime_dir)
    (args.output / 'facts.json').write_text(json.dumps(facts, separators=(',', ':')), encoding='utf-8')
    print(json.dumps({'status': 'ready', 'files': len(paths), 'nodes': len(facts['nodes']),
                      'edges': len(facts['edges']), 'coverage': len(facts['coverage'])}), flush=True)


if __name__ == '__main__':
    main()
