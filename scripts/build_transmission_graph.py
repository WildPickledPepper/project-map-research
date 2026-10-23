"""Extract C++ source JSON-to-send paths and attach them to a portable graph."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.cpp_data import DataExtractor
from adapters.cpp_transmission import Transmission
from adapters.transmission_graph import augment_transmission
from adapters.sqlite_fact_graph import _prepare


def build(source, manifest, base, output):
    source = source.resolve(); paths = [f['path'] for f in manifest['files']]
    revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != manifest['source_commit'] or revision != base['source_commit']: raise ValueError('Source versions differ')
    if len(paths) != len(set(paths)) or not set(base['input_paths']) <= set(paths): raise ValueError('Expected unique superset of base inputs')
    for p in paths:
        if PurePosixPath(p).is_absolute() or '\\' in p or not (source/p).resolve().is_relative_to(source): raise ValueError('Input escapes source')
        if not (source/p).is_file(): raise ValueError('Missing input: ' + p)
    import tree_sitter_language_pack as pack
    if os.environ.get('PROJECT_MAP_PARSER_CACHE'): pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))
    extractor = DataExtractor({p: (source/p).read_bytes() for p in paths if PurePosixPath(p).suffix in {'.h', '.hpp', '.cpp', '.cc', '.cxx'}}, pack.get_parser('cpp'))
    flow = Transmission(extractor).build(); graph = augment_transmission(base, extractor.facts, flow, paths); _prepare(graph)
    output.mkdir(parents=True, exist_ok=False)
    for name, obj in [('cpp-transmission.json', flow), ('graph.json', graph)]:
        (output/name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'files': len(paths), 'nodes': len(graph['nodes']), 'edges': len(graph['edges']),
                      'sources': len(flow['sources']), 'transmissions': len(flow['transmissions']), 'diagnostics': len(flow['diagnostics'])}))
    return graph


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ['source', 'base', 'output']: ap.add_argument('--' + name, type=Path, required=True)
    ap.add_argument('--manifest', type=Path, default=ROOT/'experiments/2026-10-23-p3/transmission-manifest.json')
    a = ap.parse_args()
    if a.output.resolve().is_relative_to(ROOT): raise ValueError('Keep generated graphs outside research repository')
    build(a.source, json.loads(a.manifest.read_text(encoding='utf-8')), json.loads(a.base.read_text(encoding='utf-8')), a.output)
