"""Run production Rust adapters in one explicit native Cargo context, then index.

This is a language/context control, separate from default all-context rebuilding.
No independent path/reference names enter extraction.
"""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.snapshot_inputs import export_inputs,select_inputs,validate_path,git
from adapters.rust_project import binary,discover,tool_output
from adapters.rust_semantics import analyze
from adapters.rust_boundaries import augment as boundaries
from adapters.rust_path_values import augment as paths_augment
from adapters.sqlite_fact_graph import validate_graph
from projectmap.version import rules_version
from projectmap.workspace import Workspace,default_analysis
from scripts.build_fact_graph import remaining_coverage


def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('source','output'):ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--revision',required=True);ap.add_argument('--manifest',required=True)
    args=ap.parse_args();output=args.output.resolve();original=args.source.resolve();manifest=validate_path(args.manifest)
    if output.exists() or output.is_relative_to(original) or output.is_relative_to(ROOT):ap.error('Choose a new output directory outside both repositories')
    rules=rules_version(require_clean=True)
    original_status=git(original,'status','--porcelain','--untracked-files=normal')
    config=default_analysis();config['scope']['include']=['*.rs','*Cargo.toml','*Cargo.lock','*.cargo/*','*rust-toolchain*']
    selected=select_inputs(original,args.revision,config);output.mkdir(parents=True)
    root=output/'source';export_inputs(original,selected,root);selected_paths=[r['path'] for r in selected['files']]
    metadata=discover(root,selected_paths)
    if manifest not in metadata['workspaces']:raise ValueError('Choose a discovered Cargo workspace manifest')
    tools={name:tool_output([binary(name),'--version'],root).strip() for name in ('cargo','rustc','rust-analyzer')}
    host=next(s.removeprefix('host: ') for s in tool_output([binary('rustc'),'-vV'],root).splitlines() if s.startswith('host: '))
    features=[p['name']+'/default' for p in metadata['packages'] if p['workspace']==manifest and 'default' in p.get('features',{})]
    cfg=[f for f in tool_output([binary('rustc'),'--print','cfg','--target',host],root).splitlines() if f!='debug_assertions']
    context={'target':host,'features':features,'cfg':cfg,'debug_assertions':False,'basis':'single_native_host_release_default_control','supported_product_mode':'not_proven'}
    import tree_sitter_language_pack as pack
    if os.environ.get('PROJECT_MAP_PARSER_CACHE'):pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))
    parser=pack.get_parser('rust')
    with (output/'events.jsonl').open('w',encoding='utf-8') as events:
        graph=analyze(root,selected_paths,parser,output=output/'native',contexts=[(manifest,context)],
            emit=lambda row:(events.write(json.dumps(row)+'\n'),events.flush()))
    graph=paths_augment(root,boundaries(graph),parser)
    # Preserve metadata inputs in the navigation projection, as the production
    # mixed-language builder does; this does not add language facts for TOML.
    graph['coverage'].extend(remaining_coverage(selected_paths,{r['path'] for r in graph['coverage']}))
    snapshot=selected['source_commit']+':native-path-control:'+uuid.uuid4().hex
    version={'rules_commit':rules,'rust_tools':tools,'packages':{n:importlib.metadata.version(n) for n in ('tree-sitter','tree-sitter-language-pack')}}
    graph.update(snapshot=snapshot,source_commit=selected['source_commit'],input_paths=selected_paths,
        extractors={'rust':'native_adapters_path_control/1'},
        version={'source_commit':selected['source_commit'],'snapshot':snapshot,'config':selected['config'],'build_version':version},
        provenance={'input_kind':'git_committed_blob_export','working_tree_included':False,'reference_used_for_extraction':False,
            'mode':'single_context_production_adapters_not_default_workspace_rebuild','file_hash_verification':'not_run_per_user_preference'})
    validate_graph(graph);write(output/'graph.json',graph)
    workspace=Workspace.create(output/'workspace',original,revision=selected['source_commit'],analysis=selected['config'])
    indexed=workspace.attach(output/'graph.json')
    original_modified=original_status!=git(original,'status','--porcelain','--untracked-files=normal')
    write(output/'trial.json',{'scope':'one_manifest_one_native_host_release_default','source_commit':selected['source_commit'],
        'build':indexed,'manifest':manifest,'context':context,'build_version':version,'input_paths':selected_paths,
        'mode':'production_adapter_control_and_workspace_attach','original_checkout_modified':original_modified,
        'file_hash_verification':'not_run_per_user_preference','product_executed':False,'whole_G03_accepted':False})
    if original_modified:raise ValueError('Original checkout status changed during the experiment')
    print(json.dumps({'status':indexed['status'],'scope':'single native context','counts':indexed['counts']}))


if __name__=='__main__':main()
