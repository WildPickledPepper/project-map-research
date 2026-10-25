"""Interpret all Cargo calls in a pinned Python process graph; no product build."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.cargo_source_bindings import interpret,ADAPTER_VERSION
from adapters.snapshot_inputs import select_inputs,commit,git
from projectmap.version import rules_version
from projectmap.workspace import default_analysis


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source',type=Path,required=True);ap.add_argument('--revision',required=True)
    ap.add_argument('--process-trial',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();rules=rules_version(require_clean=True)
    if args.output.exists() or args.output.resolve().is_relative_to(args.source.resolve()):ap.error('Choose a new output outside source')
    selection=select_inputs(args.source,args.revision,default_analysis());revision=selection['source_commit']
    graph=json.loads((args.process_trial/'graph.json').read_text(encoding='utf-8'))
    paths=[f['path'] for f in selection['files']];python_paths={p for p in paths if Path(p).suffix in {'.py','.pyi'}}
    if (graph['source_commit']!=revision or set(graph['input_paths'])!=python_paths or
        graph['version']['source_commit']!=revision or graph['provenance']['working_tree_included']):
        raise ValueError('Cached process facts do not match selected committed Python inputs')
    before=git(args.source,'status','--porcelain');args.output.mkdir(parents=True)
    nodes={n['id']:n for n in graph['nodes']};effects=[n for n in nodes.values() if n['kind']=='python_environment_effect']
    host={'name':'Windows','path_style':'windows'};requests=[]
    for invocation in nodes.values():
        if invocation['kind']!='python_process_invocation':continue
        spec=interpret(invocation,effects,host_system=host,input_paths=paths)
        if spec is None:continue
        writers={value['writer']: {k:nodes[value['writer']][k] for k in ('path','line','api','effect')}
            for value in spec['environment_sources'].values() if value.get('writer') in nodes}
        requests.append({'invocation':invocation['id'],'path':invocation['path'],'line':invocation['line'],
            'call_stack':[{k:nodes[c][k] for k in ('path','line')} for c in invocation['call_stack']],
            'request':spec,'environment_writers':writers})
    trial={'schema':'cargo-source-request-control/1','origin':'cached_source_process_facts_current_cargo_interpretation',
        'source_commit':revision,'build_version':{'rules_commit':rules,'python':sys.version.split()[0]},'adapter':ADAPTER_VERSION,
        'base_process_version':graph['version']['build_version'],'base_snapshot':graph['snapshot'],
        'host_selection':{'host_system':host,'basis':'explicit_source_predicate_control_not_native_host_measurement'},
        'input_count':len(paths),'python_input_count':len(python_paths),
        'discovered_manifests':[p for p in paths if Path(p).name=='Cargo.toml'],
        'source_request_records':len(requests),'resolved_source_requests':sum(not r['request']['gaps'] for r in requests),
        'cargo_interpreter_executed_again':True,'native_semantic_stage_executed_again':False,
        'default_workspace_rebuild':False,'native_cargo_build_executed':False,'product_executable_run':False,
        'native_cargo_target_connected':False,'process_counterpart_connected':False,'whole_G03_accepted':False,
        'original_checkout_modified':git(args.source,'status','--porcelain')!=before,
        'file_hash_verification':'not_run_per_user_preference'}
    if commit(args.source,args.revision)!=revision or rules_version(require_clean=True)!=rules:raise ValueError('Version changed during control')
    for name,value in [('selection.json',selection),('requests.json',requests),('trial.json',trial)]:
        (args.output/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'source_request_records':len(requests),'resolved_source_requests':trial['resolved_source_requests'],
        'rules_commit':rules,'original_checkout_modified':trial['original_checkout_modified']}))


if __name__=='__main__':main()
