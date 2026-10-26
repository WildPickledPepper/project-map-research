"""Join versioned startup/argument facts and recompute scoped command-word bindings."""
import argparse
import json
from pathlib import Path
import sys
import uuid
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.process_argument_bindings import augment
from adapters.snapshot_inputs import git,select_inputs
from adapters.sqlite_fact_graph import validate_graph
from projectmap.version import rules_version
from projectmap.workspace import Workspace


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('source','startup-trial','rust-argument-trial','cpp-argv-trial','output'):ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--revision',required=True);args=ap.parse_args();rules=rules_version(require_clean=True)
    if args.output.exists() or args.output.resolve().is_relative_to(args.source.resolve()):ap.error('Choose a new output outside source')
    before=git(args.source,'status','--porcelain');args.output.mkdir(parents=True)
    graph=json.loads((args.startup_trial/'graph.json').read_text(encoding='utf-8'))
    if graph.get('process_argument_bindings'):raise ValueError('Use a startup graph preceding argument binding')
    selection=select_inputs(args.source,args.revision,graph['version']['config']);paths=[r['path'] for r in selection['files']]
    if graph['source_commit']!=selection['source_commit'] or set(graph['input_paths'])!=set(paths):raise ValueError('Startup source revision/scope differs')
    versions={'startup':graph['version']['build_version']};known={n['id']:n for n in graph['nodes']};counts={};imported={}
    for label,directory,predicate,metadata in [
        ('rust_arguments',args.rust_argument_trial,lambda n:n['id'].startswith('rust-value:'),'rust_argument_templates'),
        ('cpp_argv',args.cpp_argv_trial,lambda n:n['kind'] in {'string_key_decoder','cpp_entry_argv','cpp_argv_decoder_binding'},'cpp_argv_origins')]:
        source=json.loads((directory/'graph.json').read_text(encoding='utf-8'))
        if source['source_commit']!=graph['source_commit'] or not set(source['input_paths'])<=set(paths):raise ValueError('Argument source revision/scope differs')
        enriched=label=='cpp_argv' and 'cpp_string_switches' in source
        member_kinds={'source_member_storage','cpp_member_declaration','source_member_effect'} if enriched else set()
        selected=[n for n in source['nodes'] if predicate(n) or n['kind'] in member_kinds];ids={n['id'] for n in selected}
        if any(n['id'] in known and n['kind']!='source_member_storage' for n in selected):raise ValueError('Argument projection nodes already exist in startup graph')
        overlaid=0;added=0
        for node in selected:
            if node['id'] in known:
                previous=known[node['id']]
                if previous['kind'] not in {'storage_member','source_member_storage'}:raise ValueError('Unexpected cached member node kind')
                if any(previous.get(key)!=node.get(key) for key in ('owner','path','line')):raise ValueError('Cached member source identity differs')
                kind=known[node['id']]['kind'];known[node['id']].update(node);known[node['id']]['kind']=kind;overlaid+=1
            else:graph['nodes'].append(node);known[node['id']]=node;added+=1
        relations=[e for e in source['edges'] if e['source'] in ids or e['target'] in ids]
        if any(e['source'] not in known or e['target'] not in known for e in relations):raise ValueError('Versioned argument relation has no startup source target')
        graph['edges'].extend(relations)
        graph['diagnostics'].extend(d for d in source['diagnostics'] if d['kind'] in {
            'rust_argument_template_unresolved','cpp_string_decoder_unresolved','cpp_argv_origin_unresolved',
            'cpp_member_declaration_unresolved','cpp_string_switch_unresolved','cpp_value_type_unresolved'})
        graph[metadata]=source[metadata]
        if label=='cpp_argv':graph['cpp_string_decoders']=source['cpp_string_decoders']
        if enriched:
            for field in ('cpp_member_declarations','cpp_member_effects','cpp_string_switches'):graph[field]=source[field]
            graph.setdefault('data',{}).update(source['data'])
        versions[label]=source['version']['build_version'];counts[label]=len(source['input_paths'])
        imported[label]={'nodes':len(selected),'edges':len(relations)}
        if enriched:imported[label].update(added_nodes=added,overlaid_member_nodes=overlaid)
        del source
    graph['snapshot']=graph['source_commit']+':process-argument-control:'+uuid.uuid4().hex
    version={'rules_commit':rules,'python':sys.version.split()[0],'cached_build_versions':versions}
    graph['version']={'source_commit':graph['source_commit'],'snapshot':graph['snapshot'],'config':selection['config'],'build_version':version}
    graph['provenance'].update(input_kind='versioned_cached_startup_and_argument_facts',working_tree_included=False,
        reference_used_for_extraction=False,update_mode='current_scoped_process_argument_projection',file_hash_verification='not_run_per_user_preference')
    graph=augment(graph);validate_graph(graph)
    with (args.output/'graph.json').open('w',encoding='utf-8') as stream:json.dump(graph,stream)
    workspace=Workspace.create(args.output/'workspace',args.source,revision=selection['source_commit'],analysis=selection['config'])
    indexed=workspace.attach(args.output/'graph.json')
    trial={'schema':'process-argument-control/1','origin':'current_argument_binding_on_versioned_startup_and_argument_facts',
        'source_commit':graph['source_commit'],'snapshot':graph['snapshot'],'build_version':version,'scope':'cpp_cmake_python_rust_startup_argument_control',
        'input_count':len(paths),'cached_argument_input_counts':counts,'imported_argument_facts':imported,'index_counts':indexed['counts'],
        'argument_binding_summary':graph['process_argument_bindings'],'current_argument_binding_executed_again':True,
        'language_semantics_executed_again':False,'cmake_configure_executed_again':False,'default_workspace_rebuild':False,
        'installed_tool_tested':False,'product_compiled':False,'runtime_execution':False,'payload_value_equivalence_established':False,
        'backend_listener_connected':False,'whole_G03_accepted':False,'original_checkout_modified':git(args.source,'status','--porcelain')!=before,
        'file_hash_verification':'not_run_per_user_preference'}
    if 'cpp_string_switches' in graph:
        trial.update(schema='process-literal-switch-control/1',switch_summary=graph['cpp_string_switches'],
            member_summary=graph['cpp_member_declarations'],member_effect_summary=graph['cpp_member_effects'])
    if rules_version(require_clean=True)!=rules:raise ValueError('Rules changed during control')
    for name,value in [('trial.json',trial),('selection.json',selection)]:
        (args.output/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'rules_commit':rules,'input_count':len(paths),'index_counts':indexed['counts'],'bindings':trial['argument_binding_summary']}))


if __name__=='__main__':main()
