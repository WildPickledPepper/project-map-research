"""Run production Python adapters for all selected Python inputs, then index."""
import argparse
import json
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.snapshot_inputs import export_inputs,select_inputs,git
from adapters.python_facts import analyze
from adapters.python_boundaries import augment as boundaries
from adapters.python_path_values import augment as paths_augment
from adapters.sqlite_fact_graph import validate_graph
from projectmap.version import rules_version
from projectmap.workspace import Workspace,default_analysis


def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('source','output'):ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--revision',required=True);args=ap.parse_args()
    output=args.output.resolve();original=args.source.resolve()
    if output.exists() or output.is_relative_to(original) or output.is_relative_to(ROOT):ap.error('Choose a new output directory outside both repositories')
    rules=rules_version(require_clean=True)
    original_status=git(original,'status','--porcelain','--untracked-files=normal')
    config=default_analysis();config['scope']['include']=['*.py','*.pyi']
    selected=select_inputs(original,args.revision,config);output.mkdir(parents=True)
    root=output/'source';export_inputs(original,selected,root);inputs=[r['path'] for r in selected['files']]
    with (output/'events.jsonl').open('w',encoding='utf-8') as events:
        graph=analyze(root,inputs,emit=lambda row:(events.write(json.dumps(row)+'\n'),events.flush()))
    graph=paths_augment(root,boundaries(graph))
    snapshot=selected['source_commit']+':python-path-control:'+uuid.uuid4().hex
    version={'rules_commit':rules,'python_components':graph['components']}
    graph.update(snapshot=snapshot,source_commit=selected['source_commit'],input_paths=inputs,
        extractors={'python':'production_adapters_path_control/1'},
        version={'source_commit':selected['source_commit'],'snapshot':snapshot,'config':selected['config'],'build_version':version},
        provenance={'input_kind':'git_committed_blob_export','working_tree_included':False,'reference_used_for_extraction':False,
            'mode':'python_control_production_adapters_not_default_workspace_rebuild','file_hash_verification':'not_run_per_user_preference'})
    validate_graph(graph);write(output/'graph.json',graph)
    workspace=Workspace.create(output/'workspace',original,revision=selected['source_commit'],analysis=selected['config'])
    indexed=workspace.attach(output/'graph.json')
    original_modified=original_status!=git(original,'status','--porcelain','--untracked-files=normal')
    write(output/'trial.json',{'scope':'python_control_all_selected_python_inputs','source_commit':selected['source_commit'],
        'build':indexed,'build_version':version,'input_paths':inputs,'mode':'production_adapter_control_and_workspace_attach',
        'original_checkout_modified':original_modified,'file_hash_verification':'not_run_per_user_preference',
        'product_executed':False,'whole_G03_accepted':False})
    if original_modified:raise ValueError('Original checkout status changed during the experiment')
    print(json.dumps({'status':indexed['status'],'scope':'selected Python inputs','counts':indexed['counts']}))


if __name__=='__main__':main()
