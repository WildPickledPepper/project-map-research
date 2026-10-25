"""Recompute boundary templates on versioned native Rust facts, then index them."""
import argparse
import copy
import json
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.rust_argument_templates import augment
from adapters.snapshot_inputs import export_inputs,git,select_inputs
from adapters.sqlite_fact_graph import validate_graph
from projectmap.version import rules_version
from projectmap.workspace import Workspace


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('source','base-trial','parser-cache','output'):ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--revision',required=True);args=ap.parse_args();rules=rules_version(require_clean=True)
    if args.output.exists() or args.output.resolve().is_relative_to(args.source.resolve()):ap.error('Choose a new output outside source')
    graph=json.loads((args.base_trial/'graph.json').read_text(encoding='utf-8'))
    if graph.get('rust_argument_templates'):raise ValueError('Use native facts preceding template projection')
    config=copy.deepcopy(graph['version']['config']);selection=select_inputs(args.source,args.revision,config)
    if selection['source_commit']!=graph['source_commit']:raise ValueError('Cached source revision differs')
    paths=[r['path'] for r in selection['files']]
    if set(paths)!=set(graph['input_paths']):raise ValueError('Cached native input scope differs')
    before=git(args.source,'status','--porcelain');base=graph['version']['build_version']
    args.output.mkdir(parents=True);export_inputs(args.source,selection,args.output/'source')
    version={'rules_commit':rules,'python':sys.version.split()[0],'base_facts':base}
    graph['snapshot']=selection['source_commit']+':rust-argument-control:'+uuid.uuid4().hex
    graph['version']={'source_commit':graph['source_commit'],'snapshot':graph['snapshot'],'config':config,'build_version':version}
    graph['provenance'].update(input_kind='git_committed_blob_export',working_tree_included=False,reference_used_for_extraction=False,
        update_mode='current_argument_projection_on_versioned_native_rust_facts',file_hash_verification='not_run_per_user_preference')
    import tree_sitter_language_pack as pack
    pack.configure(pack.PackConfig(cache_dir=str(args.parser_cache)))
    graph=augment(args.output/'source',graph,pack.get_parser('rust'));validate_graph(graph)
    with (args.output/'graph.json').open('w',encoding='utf-8') as stream:json.dump(graph,stream)
    workspace=Workspace.create(args.output/'workspace',args.source,revision=selection['source_commit'],analysis=config)
    indexed=workspace.attach(args.output/'graph.json')
    trial={'schema':'rust-argument-control/1','origin':'current_argument_projection_on_versioned_native_rust_facts',
        'scope':'single_windows_release_default_rust_context','source_commit':graph['source_commit'],'snapshot':graph['snapshot'],
        'build_version':version,'input_count':len(paths),'index_counts':indexed['counts'],'template_summary':graph['rust_argument_templates'],
        'argument_projection_executed_again':True,'native_semantic_stage_executed_again':False,'default_workspace_rebuild':False,
        'installed_tool_tested':False,'runtime_execution':False,'cpp_argument_decode_connected':False,'backend_listener_connected':False,
        'whole_G03_accepted':False,'original_checkout_modified':git(args.source,'status','--porcelain')!=before,
        'file_hash_verification':'not_run_per_user_preference'}
    if rules_version(require_clean=True)!=rules:raise ValueError('Rules changed during control')
    for name,value in [('trial.json',trial),('selection.json',selection)]:
        (args.output/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'input_count':len(paths),'index_counts':indexed['counts'],'templates':trial['template_summary'],'rules_commit':rules}))


if __name__=='__main__':main()
