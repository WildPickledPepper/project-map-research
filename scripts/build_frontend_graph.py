"""Extract frontend consumers using the same-version protocol/data graph's APIs."""
import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.frontend_graph import augment_frontend
from adapters.sqlite_fact_graph import _prepare


def build(source, manifest, base, typescript, output):
    source = source.resolve()
    config = json.loads(manifest.read_text(encoding='utf-8'))
    graph = json.loads(base.read_text(encoding='utf-8'))
    revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != config['source_commit'] or revision != graph['source_commit']:
        raise ValueError('Source, manifest and graph must have the same Git revision')
    paths = [f['path'] for f in config['files']]
    if len(paths) != len(set(paths)) or set(paths) != set(graph['input_paths']):
        raise ValueError('Frontend extraction must use the base graph input scope')
    for p in paths:
        if PurePosixPath(p).is_absolute() or '\\' in p or not (source / p).resolve().is_relative_to(source):
            raise ValueError('Input escapes source')
        if not (source / p).is_file():
            raise ValueError('Missing input: ' + p)
    if output.resolve().is_relative_to(ROOT):
        raise ValueError('Keep generated graphs outside the research repository')
    output.mkdir(parents=True, exist_ok=False)
    subprocess.run(['node', str(ROOT / 'adapters/typescript_data_flow.cjs'), str(source),
                    str(manifest.resolve()), str(base.resolve()), str(typescript.resolve()),
                    str((output / 'typescript.json').resolve())], check=True)
    facts = json.loads((output / 'typescript.json').read_text(encoding='utf-8'))
    graph = augment_frontend(graph, facts)
    graph['provenance']['frontend_compiler'] = {k: facts[k] for k in
        ['compiler_version', 'compiler_options', 'compiler_options_origin', 'path_configs']}
    _prepare(graph)
    (output / 'graph.json').write_text(json.dumps(graph, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'nodes': len(graph['nodes']), 'edges': len(graph['edges']), 'snapshot': graph['snapshot']}))
    return graph


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ['source', 'manifest', 'base', 'typescript', 'output']:
        ap.add_argument('--' + name, type=Path, required=True)
    a = ap.parse_args()
    build(a.source, a.manifest, a.base, a.typescript, a.output)
