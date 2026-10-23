"""Extract browser socket construction and receiver bindings for an existing graph."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.socket_graph import augment_sockets
from adapters.sqlite_fact_graph import _prepare


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ['source', 'base', 'typescript', 'output']: ap.add_argument('--' + name, type=Path, required=True)
    ap.add_argument('--manifest', type=Path, default=ROOT/'experiments/2026-10-23-p3/transmission-manifest.json')
    a = ap.parse_args(); source = a.source.resolve()
    graph = json.loads(a.base.read_text(encoding='utf-8')); manifest = json.loads(a.manifest.read_text(encoding='utf-8'))
    revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != graph['source_commit'] or revision != manifest['source_commit']: raise ValueError('Source versions differ')
    paths = [f['path'] for f in manifest['files']]
    if len(paths) != len(set(paths)) or set(paths) != set(graph['input_paths']): raise ValueError('Input scopes differ')
    for p in paths:
        if not (source/p).resolve().is_relative_to(source) or not (source/p).is_file(): raise ValueError('Invalid input path')
    if a.output.resolve().is_relative_to(ROOT): raise ValueError('Keep generated graphs outside the repository')
    a.output.mkdir(parents=True, exist_ok=False)
    subprocess.run(['node', str(ROOT/'adapters/typescript_socket_flow.cjs'), str(source), str(a.manifest.resolve()),
                    str(a.typescript.resolve()), str((a.output/'typescript.json').resolve())], check=True)
    facts = json.loads((a.output/'typescript.json').read_text(encoding='utf-8'))
    graph = augment_sockets(graph, facts); _prepare(graph)
    (a.output/'graph.json').write_text(json.dumps(graph, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'nodes': len(graph['nodes']), 'edges': len(graph['edges']), 'snapshot': graph['snapshot']}))
