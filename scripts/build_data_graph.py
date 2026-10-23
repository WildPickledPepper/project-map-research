"""Add C++ selection/storage evidence to a same-version protocol graph."""
import argparse
import json
import os
from pathlib import Path,PurePosixPath
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from adapters.cpp_data import analyze_data
from adapters.data_graph import augment
from adapters.sqlite_fact_graph import _prepare


def build(source,manifest_path,base_path,output):
    source=source.resolve();manifest=json.loads(manifest_path.read_text(encoding='utf-8'));base=json.loads(base_path.read_text(encoding='utf-8'))
    revision=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    if revision!=manifest['source_commit'] or revision!=base['source_commit']:raise ValueError('Source, manifest and base graph must have the same Git revision')
    paths=[f['path'] for f in manifest['files']]
    if len(paths)!=len(set(paths)) or not set(base['input_paths'])<=set(paths):raise ValueError('Expected a unique superset of base inputs')
    for p in paths:
        if PurePosixPath(p).is_absolute() or '\\' in p or not (source/p).resolve().is_relative_to(source):raise ValueError('Input path escapes source')
        if not (source/p).is_file():raise ValueError('Missing input: '+p)
    output.mkdir(parents=True,exist_ok=False)
    import tree_sitter_language_pack as pack
    if os.environ.get('PROJECT_MAP_PARSER_CACHE'):pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))
    cpp=analyze_data({p:(source/p).read_bytes() for p in paths if PurePosixPath(p).suffix in {'.h','.hpp','.cpp','.cc','.cxx'}},pack.get_parser('cpp'))
    graph=augment(base,cpp,paths);_prepare(graph)
    for name,value in [('cpp-data.json',cpp),('graph.json',graph)]:
        (output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'nodes':len(graph['nodes']),'edges':len(graph['edges']),**{k:len(graph['data'][k]) for k in ['storages','accesses','allocations','selections','callbacks']}}))
    return graph


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--base',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--manifest',type=Path,default=ROOT/'experiments/2026-10-23-p3/input-manifest.json')
    a=ap.parse_args()
    if a.output.resolve().is_relative_to(ROOT):raise ValueError('Keep generated graphs outside the research repo')
    build(a.source,a.manifest,a.base,a.output)
