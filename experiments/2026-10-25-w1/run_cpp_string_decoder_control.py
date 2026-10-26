"""Extract typed string dispatch from all selected C++ source, without product execution."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import sys
import uuid
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.cpp_data import DataExtractor
from adapters.cpp_protocol import ProtocolExtractor
from adapters.cpp_string_decoders import augment
from adapters.snapshot_inputs import export_inputs,git,select_inputs
from adapters.sqlite_fact_graph import validate_graph
from projectmap.version import rules_version
from projectmap.workspace import Workspace


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('source','parser-cache','output'):ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--revision',required=True);ap.add_argument('--argv-origins',action='store_true')
    ap.add_argument('--member-declarations',action='store_true')
    ap.add_argument('--literal-switches',action='store_true')
    args=ap.parse_args();rules=rules_version(require_clean=True)
    if args.output.exists() or args.output.resolve().is_relative_to(args.source.resolve()):ap.error('Choose a new output outside source')
    config={'version':1,'scope':{'discovery':{},'include':['*.h','*.hpp','*.cpp','*.cc','*.cxx']},'deployment':{},'storage':'json'}
    selection=select_inputs(args.source,args.revision,config);paths=[r['path'] for r in selection['files']]
    before=git(args.source,'status','--porcelain');args.output.mkdir(parents=True);export_inputs(args.source,selection,args.output/'source')
    import tree_sitter_language_pack as pack
    pack.configure(pack.PackConfig(cache_dir=str(args.parser_cache)))
    data=DataExtractor({p:(args.output/'source'/p).read_bytes() for p in paths},pack.get_parser('cpp'))
    protocol=ProtocolExtractor({},None,extractor=data.x,facts=data.facts,value_types=data.types)
    graph={**data.facts,'input_paths':paths,'source_commit':selection['source_commit'],
        'snapshot':selection['source_commit']+':cpp-string-decoder:'+uuid.uuid4().hex}
    version={'rules_commit':rules,'python':sys.version.split()[0],
        'packages':{p:importlib.metadata.version(p) for p in ('tree-sitter','tree-sitter-language-pack')}}
    graph['version']={'source_commit':graph['source_commit'],'snapshot':graph['snapshot'],'config':selection['config'],'build_version':version}
    graph['provenance']={'input_kind':'git_committed_blob_export','working_tree_included':False,'reference_used_for_extraction':False,
        'update_mode':'cpp_source_facts_and_string_decoder_control','file_hash_verification':'not_run_per_user_preference'}
    graph=augment(graph,data,protocol)
    if args.member_declarations or args.literal_switches:
        from adapters.cpp_member_declarations import project as project_members
        members=project_members(list(data.fields.values()))
        graph['nodes'].extend(members['nodes']);graph['edges'].extend(members['edges']);graph['diagnostics'].extend(data.diagnostics)
        graph['cpp_member_declarations']=members['summary']
    if args.literal_switches:
        from adapters.cpp_member_effects import extract_member_effects,project as project_effects
        from adapters.cpp_string_switches import augment as switches
        records=extract_member_effects(data);effects=project_effects(records)
        graph['nodes'].extend(effects['nodes']);graph['edges'].extend(effects['edges']);graph['cpp_member_effects']=effects['summary']
        graph['data']={'member_declarations':list(data.fields.values()),'member_effects':records}
        graph=switches(graph,data,protocol)
    if args.argv_origins:
        from adapters.cpp_argv_origins import augment as argv_origins
        graph=argv_origins(graph,data,protocol)
    validate_graph(graph)
    with (args.output/'graph.json').open('w',encoding='utf-8') as stream:json.dump(graph,stream)
    workspace=Workspace.create(args.output/'workspace',args.source,revision=selection['source_commit'],analysis=selection['config'])
    indexed=workspace.attach(args.output/'graph.json')
    trial={'schema':'cpp-string-decoder-control/1','origin':'current_cpp_source_facts_and_string_decoder_extraction',
        'source_commit':graph['source_commit'],'snapshot':graph['snapshot'],'build_version':version,'scope':'all_selected_cpp_source_no_cmake_context',
        'input_count':len(paths),'index_counts':indexed['counts'],'decoder_summary':graph['cpp_string_decoders'],
        'cpp_source_extraction_executed_again':True,'cmake_configure_executed_again':False,'default_workspace_rebuild':False,
        'installed_tool_tested':False,'runtime_execution':False,'argv_origin_connected':False,'rust_argument_paired':False,
        'backend_listener_connected':False,'whole_G03_accepted':False,'original_checkout_modified':git(args.source,'status','--porcelain')!=before,
        'file_hash_verification':'not_run_per_user_preference'}
    if args.argv_origins:
        trial.update(schema='cpp-argv-origin-control/1',origin='current_cpp_source_facts_string_decoding_and_argv_origins',
            argv_origin_connected=bool(graph['cpp_argv_origins']['counts'].get('complete_origins')),
            argv_summary=graph['cpp_argv_origins'])
    if args.member_declarations:
        trial.update(schema='cpp-member-declaration-control/1',origin='current_cpp_source_facts_with_member_declaration_alternatives',
            member_summary=graph['cpp_member_declarations'])
    if args.literal_switches:
        trial.update(schema='cpp-literal-switch-control/1',origin='current_cpp_source_member_effects_switches_and_argv',
            member_summary=graph['cpp_member_declarations'],member_effect_summary=graph['cpp_member_effects'],
            switch_summary=graph['cpp_string_switches'])
    if rules_version(require_clean=True)!=rules:raise ValueError('Rules changed during control')
    for name,value in [('trial.json',trial),('selection.json',selection)]:
        (args.output/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'input_count':len(paths),'index_counts':indexed['counts'],'decoder_summary':trial['decoder_summary'],'rules_commit':rules}))


if __name__=='__main__':main()
