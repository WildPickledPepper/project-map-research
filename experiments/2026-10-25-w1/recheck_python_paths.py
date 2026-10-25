"""Recompute production paths from unchanged, versioned language/interface facts.

The native stage is reused only when its source/configuration, adapter Git
history and installed component versions match. No file hashes are computed.
The path adapter, source ASTs and navigation index run again from fresh exports.
"""
import argparse
import importlib.metadata
import json
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.snapshot_inputs import export_inputs,select_inputs,git
from adapters.python_path_values import augment
from adapters.sqlite_fact_graph import validate_graph
from projectmap.version import rules_version
from projectmap.workspace import Workspace

SEMANTIC_COMPONENTS=['adapters/python_facts.py','adapters/python_contexts.py','adapters/python_boundaries.py']
PATH_LIMITS={'python_path_styles_are_explicit_runtime_candidates',
    'python_file_operations_require_control_flow_options_destination_and_deployment_context',
    'python_path_caller_frames_and_directory_enumeration_not_expanded'}


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('source','base-trial','output'):ap.add_argument('--'+name,type=Path,required=True)
    args=ap.parse_args();original=args.source.resolve();output=args.output.resolve();base_dir=args.base_trial.resolve()
    if output.exists() or output.is_relative_to(original) or output.is_relative_to(ROOT):ap.error('Choose a new output directory outside both repositories')
    current=rules_version(require_clean=True);base_path=base_dir/'native-base.json'
    if base_path.is_file():
        graph=read(base_path)
        if graph.get('cached_stage')!='python_semantics_and_boundaries_before_paths':raise ValueError('Unknown cached fact stage')
    else:
        graph=read(base_dir/'graph.json')
        if graph.get('extractors')!={'python':'production_adapters_path_control/1'} or any(n['kind']=='file_operation_context' for n in graph['nodes']):
            raise ValueError('Legacy cache migration requires the pre-caller-context Python control graph')
        removed={n['id'] for n in graph['nodes'] if n['kind'] in {'path_value','python_file_operation'}}
        graph['nodes']=[n for n in graph['nodes'] if n['id'] not in removed]
        graph['edges']=[e for e in graph['edges'] if e['source'] not in removed and e['target'] not in removed]
        graph['diagnostics']=[d for d in graph['diagnostics'] if d.get('kind') not in {
            'python_path_value_unresolved','python_file_operation_argument_expansion','python_file_operation_missing_argument'}]
        graph['limits']=[s for s in graph['limits'] if s not in PATH_LIMITS]
        graph['snapshot']+=':before-path-projection';graph['version']['snapshot']=graph['snapshot']
        graph['cached_stage']='python_semantics_and_boundaries_before_paths'
        graph['extractors']={'python':'cached_ast_jedi_and_interface_stage/1'}
    baseline=graph['version']['build_version']['rules_commit']
    if git(ROOT,'diff',baseline,current,'--',*SEMANTIC_COMPONENTS).strip():raise ValueError('Python semantic/interface components changed; rebuild native facts')
    components={'jedi':importlib.metadata.version('jedi'),'parso':importlib.metadata.version('parso'),'python':sys.version.split()[0]}
    if graph['components']!=components:raise ValueError('Native component versions changed; rebuild native facts')
    if graph['provenance']['working_tree_included'] is not False or graph['provenance']['reference_used_for_extraction'] is not False:
        raise ValueError('Require committed-source native facts without evaluation references')
    original_status=git(original,'status','--porcelain','--untracked-files=normal')
    selected=select_inputs(original,graph['source_commit'],graph['version']['config'])
    inputs=[r['path'] for r in selected['files']]
    if set(inputs)!=set(graph['input_paths']) or selected['config']!=graph['version']['config']:raise ValueError('Input selection/context changed; rebuild native facts')
    validate_graph(graph);base_snapshot=graph['snapshot'];base_counts={'nodes':len(graph['nodes']),'edges':len(graph['edges'])}
    output.mkdir(parents=True);root=output/'source';export_inputs(original,selected,root)
    write(output/'native-base.json',graph)
    graph=augment(root,graph);snapshot=selected['source_commit']+':python-path-recheck:'+uuid.uuid4().hex
    base_facts={'snapshot':base_snapshot,'rules_commit':baseline,'components':SEMANTIC_COMPONENTS,
        'adapter_history_unchanged':True,'component_versions_unchanged':True,'input_context_unchanged':True,'counts':base_counts}
    version={'rules_commit':current,'python_components':components,'base_facts':base_facts}
    graph.pop('cached_stage',None)
    graph.update(snapshot=snapshot,extractors={'python':'production_paths_recomputed_cached_ast_jedi_and_interfaces/1'},
        version={'source_commit':selected['source_commit'],'snapshot':snapshot,'config':selected['config'],'build_version':version},
        provenance={'input_kind':'git_committed_blob_export','working_tree_included':False,'reference_used_for_extraction':False,
            'mode':'cached_language_interface_facts_production_path_recheck','file_hash_verification':'not_run_per_user_preference'})
    validate_graph(graph);write(output/'graph.json',graph)
    workspace=Workspace.create(output/'workspace',original,revision=selected['source_commit'],analysis=selected['config'])
    indexed=workspace.attach(output/'graph.json')
    changed=original_status!=git(original,'status','--porcelain','--untracked-files=normal')
    write(output/'trial.json',{'scope':'python_paths_recomputed_all_selected_python_inputs','source_commit':selected['source_commit'],
        'mode':'cached_native_facts_production_path_adapter_and_workspace_attach','build':indexed,'build_version':version,'input_paths':inputs,
        'original_checkout_modified':changed,'file_hash_verification':'not_run_per_user_preference','default_workspace_rebuild':False,
        'native_semantic_stage_executed_again':False,'path_adapter_executed_again':True,'product_executed':False,'whole_G03_accepted':False})
    if changed:raise ValueError('Original checkout status changed')
    print(json.dumps({'status':indexed['status'],'counts':indexed['counts'],'native_facts_reused':True,'path_adapter_recomputed':True}))


if __name__=='__main__':main()
