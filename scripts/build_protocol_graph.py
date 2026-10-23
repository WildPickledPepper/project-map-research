"""Build source-derived protocol evidence without a reference/answer input."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from adapters.cpp_protocol import analyze_protocol
from adapters.protocol_graph import augment
from scripts.build_fact_graph import remaining_coverage,write


def build(source,manifest_path,ts_module,deployment_path,output):
    source=source.resolve();manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    revision=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    if revision!=manifest['source_commit']:raise ValueError('Checkout commit differs from manifest')
    paths=[f['path'] for f in manifest['files']]
    if len(paths)!=len(set(paths)):raise ValueError('Duplicate input path')
    for p in paths:
        if PurePosixPath(p).is_absolute() or '\\' in p or not (source/p).resolve().is_relative_to(source):raise ValueError('Input escapes source root')
        if not (source/p).is_file():raise ValueError('Missing input: '+p)
    output.mkdir(parents=True,exist_ok=False)
    import tree_sitter_language_pack as pack
    if os.environ.get('PROJECT_MAP_PARSER_CACHE'):pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))
    cpp=analyze_protocol({p:(source/p).read_bytes() for p in paths if PurePosixPath(p).suffix in {'.h','.hpp','.cpp','.cc','.cxx'}},pack.get_parser('cpp'))
    write(output/'cpp.json',cpp)
    subprocess.run(['node',str(ROOT/'adapters/typescript_protocol_flow.cjs'),str(source),str(manifest_path.resolve()),
                    str(ts_module.resolve()),str((output/'typescript.json').resolve())],check=True)
    ts=json.loads((output/'typescript.json').read_text(encoding='utf-8'));facts=cpp['facts']
    covered={r['path'] for g in (facts,ts) for r in g['coverage']}
    graph={'schema_version':1,'snapshot':revision+':p2-protocol-v1','source_commit':revision,
      'extractors':{'cpp':'cpp_protocol/0.2.0','typescript':'typescript_protocol_flow/0.2.0','typescript_compiler':ts['compiler_version'],
                    'tree_sitter':'0.25.2','tree_sitter_language_pack':'1.20.0'},
      'input_paths':paths,'coverage':facts['coverage']+ts['coverage']+remaining_coverage(paths,covered),
      'nodes':facts['nodes']+ts['nodes'],'edges':facts['edges']+ts['edges'],
      'diagnostics':facts['diagnostics']+ts['diagnostics'],'limits':facts['limits']+ts['limits'],
      'provenance':{'reference_used_for_extraction':False,'file_hash_verification':'not_run_per_user_preference',
                    'deployment_scope':'configured','update_mode':'explicit_full_rebuild'},'path_configs':ts['path_configs']}
    graph=augment(graph,ts['protocol'],cpp['protocol'],json.loads(deployment_path.read_text(encoding='utf-8')))
    write(output/'graph.json',graph)
    from collections import Counter
    print(json.dumps({'files':len(paths),'nodes':len(graph['nodes']),'edges':len(graph['edges']),
       'providers':len(cpp['protocol']['providers']),'statuses':dict(Counter(r['status'] for r in graph['protocol']['results']))}))
    return graph


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--manifest',type=Path,default=ROOT/'experiments/2026-10-23-p2/input-manifest.json')
    ap.add_argument('--deployment',type=Path,default=ROOT/'experiments/2026-10-23-p2/deployment.json')
    ap.add_argument('--typescript',type=Path,default=ROOT/'node_modules/typescript/lib/typescript.js')
    a=ap.parse_args()
    if a.output.resolve().is_relative_to(ROOT):raise ValueError('Keep generated graphs outside Git')
    build(a.source,a.manifest,a.typescript,a.deployment,a.output)
