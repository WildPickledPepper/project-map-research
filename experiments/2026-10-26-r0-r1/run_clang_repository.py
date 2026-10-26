"""Collect native C++ semantics from an existing revision-bound CMake export."""
import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.clangd_provider import analyze
from adapters.repository_discovery import discover
from adapters.sqlite_fact_graph import validate_graph


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repository', 'capture', 'output', 'binary'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--query-driver', action='append', default=[])
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Use a new output')
    receipt = json.loads((args.capture / 'result.json').read_text(encoding='utf-8'))
    if receipt['source_commit'] != args.revision or not receipt['attempts'][-1]['configured']:
        raise ValueError('A successful native capture of the same source revision is required')
    discovery = discover(args.repository, args.revision)
    paths = [r['path'] for r in discovery['files'] if r['eligible'] and r['language'] == 'cpp']
    source = args.capture / 'source'
    if any(not (source / p).is_file() for p in paths):
        raise ValueError('Native capture is missing selected C++ source')
    args.output.mkdir(parents=True)
    lock = threading.Lock(); started = time.monotonic()
    events = (args.output / 'events.jsonl').open('w', encoding='utf-8')
    def emit(row):
        with lock:
            events.write(json.dumps(row) + '\n'); events.flush()
    def worker(ordinal):
        subset = paths[ordinal::args.workers]
        facts = asyncio.run(analyze(source, subset, binary=args.binary,
            context=receipt['subdir'] + '/' + receipt['configuration'], source_commit=args.revision,
            output=args.output / str(ordinal), compile_commands=args.capture / 'prepared-dependencies',
            query_drivers=args.query_driver, input_paths=paths, emit=emit))
        (args.output / (str(ordinal) + '-facts.json')).write_text(json.dumps(facts), encoding='utf-8')
        return facts
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            results = list(pool.map(worker, range(args.workers)))
    finally:
        events.close()
    nodes = {}
    for result in results:
        for node in result['nodes']:
            previous = nodes.get(node['id'])
            if previous is None or node['kind'] != 'declaration':
                nodes[node['id']] = node
    facts = {key: [v for result in results for v in result[key]]
             for key in ('edges', 'coverage', 'diagnostics')}
    facts.update(nodes=list(nodes.values()), components=results[0]['components'],
                 limits=sorted({v for r in results for v in r['limits']}))
    validate_graph({'snapshot': 'native-cpp-' + args.revision, **facts})
    (args.output / 'facts.json').write_text(json.dumps(facts, separators=(',', ':')), encoding='utf-8')
    report = {'source_commit': args.revision, 'context': facts['components']['context'],
        'seconds': round(time.monotonic() - started, 3), 'files': len(paths),
        'coverage_records': len(facts['coverage']), 'nodes': len(nodes), 'edges': len(facts['edges']),
        'whole_G02_accepted': False, 'native_capture_reused': True,
        'hash_verification': 'not_run_per_user_preference'}
    (args.output / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
