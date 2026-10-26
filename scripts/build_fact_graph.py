"""Extract a portable graph from a manifest and source checkout; no reference input."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from adapters.cpp_facts import analyze


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')


def remaining_coverage(paths,covered):
    from adapters.repository_discovery import manifest_kind
    records=[]
    for p in paths:
        if p in covered:continue
        if p.endswith('.sh') or manifest_kind(p)=='native_boundary':status='provider_required'
        elif p.endswith('package.json'):status='workspace_package_metadata'
        elif p.endswith('.json'):status='configuration_recorded_not_applied'
        else:status='unsupported_extension'
        records.append({'path':p,'status':status})
    return records


def build(source,manifest_path,ts_module,output):
    source=source.resolve()
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    revision=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    if revision!=manifest['source_commit']:raise ValueError('Checkout commit differs from manifest')
    paths=[f['path'] for f in manifest['files']]
    if len(set(paths))!=len(paths):raise ValueError('Duplicate manifest path')
    for p in paths:
        if PurePosixPath(p).is_absolute() or '\\' in p or not (source/p).resolve().is_relative_to(source):
            raise ValueError('Manifest paths must remain in the source directory')
        if not (source/p).is_file():raise ValueError('Missing manifest file: '+p)
    output.mkdir(parents=True,exist_ok=False)
    import tree_sitter_language_pack as pack
    if os.environ.get('PROJECT_MAP_PARSER_CACHE'):
        pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))
    cpp=analyze({p:(source/p).read_bytes() for p in paths if PurePosixPath(p).suffix in {'.h','.hpp','.cpp','.cc','.cxx'}},pack.get_parser('cpp'))
    write(output/'cpp.json',cpp)
    subprocess.run(['node',str(ROOT/'adapters/typescript_facts.cjs'),str(source),str(manifest_path.resolve()),
                    str(ts_module.resolve()),str((output/'typescript.json').resolve())],check=True)
    ts=json.loads((output/'typescript.json').read_text(encoding='utf-8'))
    covered={r['path'] for g in (cpp,ts) for r in g['coverage']}
    metadata=remaining_coverage(paths,covered)
    graph={'schema_version':1,'snapshot':revision+':p1-facts-v1','source_commit':revision,
           'extractors':{'cpp':'cpp_facts/0.1.0','typescript':'typescript_facts/0.1.0','typescript_compiler':ts['compiler_version'],
                         'tree_sitter':'0.25.2','tree_sitter_language_pack':'1.20.0'},
           'input_paths':paths,'coverage':cpp['coverage']+ts['coverage']+metadata,
           'compiler_options':ts['compiler_options'],'compiler_options_origin':ts['compiler_options_origin'],
           'nodes':cpp['nodes']+ts['nodes'],'edges':cpp['edges']+ts['edges'],
           'diagnostics':cpp['diagnostics']+ts['diagnostics'],'limits':cpp['limits']+ts['limits'],
           'provenance':{'source':'Git revision plus supplied manifest','reference_used_for_extraction':False,
                         'file_hash_verification':'not_run_per_user_preference','update_mode':'explicit_full_rebuild'}}
    write(output/'graph.json',graph)
    print(json.dumps({'nodes':len(graph['nodes']),'edges':len(graph['edges']),'files':len(graph['coverage'])}))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--manifest',type=Path,default=ROOT/'experiments/2026-10-23-p1/evidence/input-manifest.json')
    ap.add_argument('--typescript',type=Path,default=ROOT/'node_modules/typescript/lib/typescript.js')
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    if args.output.resolve().is_relative_to(ROOT):raise ValueError('Keep generated graphs outside Git')
    build(args.source,args.manifest,args.typescript,args.output)
