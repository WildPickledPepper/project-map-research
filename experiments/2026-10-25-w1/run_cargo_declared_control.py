"""Replay Cargo queries/copy projection over versioned Python and Rust facts."""
import argparse
import json
import os
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.snapshot_inputs import select_inputs,export_inputs,git
from adapters.cargo_declared_artifacts import augment
from adapters.cargo_source_bindings import augment as bind
from adapters.artifact_copy_graph import augment as copies
from adapters.sqlite_fact_graph import validate_graph
from projectmap.version import rules_version
from projectmap.workspace import Workspace


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('source','python-trial','rust-trial','parser-cache','output'):ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--revision',required=True);args=ap.parse_args();rules=rules_version(require_clean=True)
    if args.output.exists() or args.output.resolve().is_relative_to(args.source.resolve()):ap.error('Choose a new output outside source')
    py=json.loads((args.python_trial/'graph.json').read_text(encoding='utf-8'))
    rust=json.loads((args.rust_trial/'graph.json').read_text(encoding='utf-8'))
    analysis={'version':1,'scope':{'discovery':{},'include':['*.py','*.pyi','*.rs','*Cargo.toml','*Cargo.lock',
        '*/.cargo/config','*/.cargo/config.toml','*rust-toolchain*']},'deployment':{},'storage':'json'}
    selection=select_inputs(args.source,args.revision,analysis);paths=[f['path'] for f in selection['files']]
    if (py['source_commit']!=rust['source_commit'] or py['source_commit']!=selection['source_commit'] or
        set(paths)!=set(py['input_paths'])|set(rust['input_paths'])):raise ValueError('Source revision or selected cached input union differs')
    if any(g.get('artifact_copy_flow') or any(n['kind']=='build_artifact' for n in g['nodes']) for g in (py,rust)):
        raise ValueError('Expected source facts before native artifact/copy projection')
    before=git(args.source,'status','--porcelain');args.output.mkdir(parents=True)
    export_inputs(args.source,selection,args.output/'source')
    version={'rules_commit':rules,'python':sys.version.split()[0],
        'cached_python':py['version']['build_version'],'cached_rust':rust['version']['build_version']}
    for key in ('nodes','edges','coverage','diagnostics','limits'):py[key].extend(rust.get(key,[]))
    py['input_paths']=paths;py['snapshot']=selection['source_commit']+':cargo-declared-control:'+uuid.uuid4().hex
    py['version']={'source_commit':py['source_commit'],'snapshot':py['snapshot'],'config':selection['config'],'build_version':version}
    py['provenance'].update(input_kind='git_committed_blob_export',working_tree_included=False,reference_used_for_extraction=False,
        update_mode='cached_python_rust_source_facts_current_cargo_queries_and_copy_projection',file_hash_verification='not_run_per_user_preference')
    import tree_sitter_language_pack as pack
    pack.configure(pack.PackConfig(cache_dir=str(args.parser_cache)))
    graph=copies(bind(augment(py,root=args.output/'source',paths=paths,output=args.output/'cargo-native',parser=pack.get_parser('rust'))))
    validate_graph(graph);(args.output/'graph.json').write_text(json.dumps(graph),encoding='utf-8')
    workspace=Workspace.create(args.output/'workspace',args.source,revision=selection['source_commit'],analysis=selection['config'])
    built=workspace.attach(args.output/'graph.json')
    receipt=json.loads((args.output/'cargo-native/receipt.json').read_text(encoding='utf-8'))
    trial={'schema':'cargo-declared-control/1','origin':'current_cargo_queries_and_projection_on_cached_source_facts',
        'source_commit':graph['source_commit'],'snapshot':graph['snapshot'],'scope':'python_rust_source_and_cargo_control',
        'build_version':version,'input_count':len(paths),'python_input_count':len(json.loads((args.python_trial/'graph.json').read_text(encoding='utf-8'))['input_paths']),
        'rust_input_count':len(rust['input_paths']),'index_counts':built['counts'],'cargo_version':receipt['cargo_version'],'rustc_version':receipt['rustc_version'],
        'native_query_labels':[c['label'] for c in receipt['commands']],'native_query_returncodes':[c['returncode'] for c in receipt['commands']],
        'cargo_queries_and_copy_projection_executed_again':True,'python_rust_semantics_executed_again':False,
        'default_workspace_rebuild':False,'installed_tool_tested':False,'product_compiled':False,'build_scripts_executed':False,
        'product_executable_run':False,'process_counterpart_connected':False,'whole_G03_accepted':False,
        'original_checkout_modified':git(args.source,'status','--porcelain')!=before,'file_hash_verification':'not_run_per_user_preference'}
    if rules_version(require_clean=True)!=rules:raise ValueError('Rule version changed during control')
    (args.output/'trial.json').write_text(json.dumps(trial,indent=2)+'\n',encoding='utf-8')
    (args.output/'selection.json').write_text(json.dumps(selection,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'input_count':len(paths),'index_counts':built['counts'],'rules_commit':rules}))


if __name__=='__main__':main()
