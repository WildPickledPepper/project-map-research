"""Join versioned C++/CMake/Python/Rust facts with current deployment rules."""
import argparse
import json
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.snapshot_inputs import select_inputs,export_inputs,git
from adapters.cargo_declared_artifacts import augment
from adapters.cargo_source_bindings import augment as bind
from adapters.artifact_copy_graph import augment as copies
from adapters.executable_deployment_graph import augment as deployments
from adapters.sqlite_fact_graph import validate_graph
from projectmap.version import rules_version
from projectmap.workspace import Workspace


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('source','cpp-trial','python-trial','rust-trial','parser-cache','output'):ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--revision',required=True);args=ap.parse_args();rules=rules_version(require_clean=True)
    if args.output.exists() or args.output.resolve().is_relative_to(args.source.resolve()):ap.error('Choose a new output outside source')
    bases={name:json.loads((getattr(args,name+'_trial')/'graph.json').read_text(encoding='utf-8')) for name in ('cpp','python','rust')}
    config={'version':1,'scope':{'discovery':{},'include':['*.h','*.hpp','*.cpp','*.cc','*.cxx','*CMakeLists.txt','*.cmake',
        '*.py','*.pyi','*.rs','*Cargo.toml','*Cargo.lock','*/.cargo/config','*/.cargo/config.toml','*rust-toolchain*']},'deployment':{},'storage':'json'}
    selection=select_inputs(args.source,args.revision,config);paths=[r['path'] for r in selection['files']]
    if any(g['source_commit']!=selection['source_commit'] for g in bases.values()):raise ValueError('Cached source revisions differ')
    if set(paths)!=set().union(*(set(g['input_paths']) for g in bases.values())):raise ValueError('Selected input union differs from cached facts')
    if any(g.get('artifact_copy_flow') or g.get('executable_deployment') for g in bases.values()):raise ValueError('Source facts must precede copy/deployment projection')
    before=git(args.source,'status','--porcelain');args.output.mkdir(parents=True);export_inputs(args.source,selection,args.output/'source')
    versions={name:g['version']['build_version'] for name,g in bases.items()}
    counts={name:len(g['input_paths']) for name,g in bases.items()}
    version={'rules_commit':rules,'python':sys.version.split()[0],'cached_rule_versions':{name:v['rules_commit'] for name,v in versions.items()}}
    graph=bases['cpp']
    for name in ('python','rust'):
        for key in ('nodes','edges','coverage','diagnostics','limits'):graph[key].extend(bases[name].get(key,[]))
    graph['input_paths']=paths;graph['snapshot']=selection['source_commit']+':executable-deployment:'+uuid.uuid4().hex
    graph['version']={'source_commit':graph['source_commit'],'snapshot':graph['snapshot'],'config':selection['config'],'build_version':version}
    graph['provenance'].update(input_kind='git_committed_blob_export',working_tree_included=False,reference_used_for_extraction=False,
        update_mode='versioned_cached_language_cmake_facts_current_cargo_copy_deployment_projection',file_hash_verification='not_run_per_user_preference')
    import tree_sitter_language_pack as pack
    pack.configure(pack.PackConfig(cache_dir=str(args.parser_cache)))
    graph=deployments(copies(bind(augment(graph,root=args.output/'source',paths=paths,output=args.output/'cargo-native',parser=pack.get_parser('rust')))))
    validate_graph(graph)
    with (args.output/'graph.json').open('w',encoding='utf-8') as f:json.dump(graph,f)
    workspace=Workspace.create(args.output/'workspace',args.source,revision=selection['source_commit'],analysis=selection['config'])
    indexed=workspace.attach(args.output/'graph.json');native=json.loads((args.output/'cargo-native/receipt.json').read_text(encoding='utf-8'))
    trial={'schema':'executable-deployment-control/1','origin':'current_deployment_projection_on_versioned_cpp_cmake_python_rust_facts',
        'source_commit':graph['source_commit'],'snapshot':graph['snapshot'],'scope':'cpp_cmake_python_rust_startup_control',
        'build_version':version,'input_count':len(paths),'cached_input_counts':counts,'index_counts':indexed['counts'],
        'cargo_version':native['cargo_version'],'rustc_version':native['rustc_version'],
        'native_query_labels':[c['label'] for c in native['commands']],'native_query_returncodes':[c['returncode'] for c in native['commands']],
        'current_cargo_copy_deployment_executed_again':True,'language_semantics_executed_again':False,'cmake_configure_executed_again':False,
        'default_workspace_rebuild':False,'installed_tool_tested':False,'product_compiled':False,'product_executable_run':False,
        'runtime_process_identity_observed':False,'whole_G03_accepted':False,'original_checkout_modified':git(args.source,'status','--porcelain')!=before,
        'file_hash_verification':'not_run_per_user_preference'}
    if rules_version(require_clean=True)!=rules:raise ValueError('Rules changed during control')
    for name,value in [('trial.json',trial),('selection.json',selection),('cached-provenance.json',versions)]:
        (args.output/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'input_count':len(paths),'index_counts':indexed['counts'],'deployment':graph['executable_deployment'],'rules_commit':rules}))


if __name__=='__main__':main()
