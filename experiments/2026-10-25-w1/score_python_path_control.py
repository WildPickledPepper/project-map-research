"""Evaluate a completed Python control against separate source-audit anchors."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from projectmap.workspace import Workspace


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--trial',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    if args.output.exists():ap.error('Choose a new evidence output path')
    trial=json.loads((args.trial/'trial.json').read_text(encoding='utf-8'))
    graph=json.loads((args.trial/'graph.json').read_text(encoding='utf-8'))
    nodes={n['id']:n for n in graph['nodes']};edges=graph['edges'];checks=[]
    def check(name,value):checks.append({'id':name,'passed':bool(value)})
    # Source reference is deliberately confined to evaluation, after extraction.
    revision='d4e8d1cf9f90208bcbe5371c127088f6fd66c688';path='build/build.py'
    def op(line):return next(n for n in nodes.values() if n['kind']=='python_file_operation' and n['path']==path and n['line']==line)
    def values(operation,role,style='windows'):
        return [n for n in nodes.values() if n['kind']=='path_value' and n['consumer']==operation['id'] and n['role']==role and n['path_context']['style']==style]
    server=op(344);server_source=values(server,'source')[0];server_destination=values(server,'destination')[0]
    resources=op(384);resource_source=values(resources,'source')[0];resource_destination=values(resources,'destination')[0]
    plugin=op(347);plugin_source=values(plugin,'source')[0];plugin_destination=values(plugin,'destination')[0]
    loop_copy=op(189);launcher_copy=op(532)
    check('same_pinned_source',trial['source_commit']==graph['source_commit']==revision)
    check('all_committed_python_inputs_selected',len(graph['input_paths'])==119 and all(p.endswith(('.py','.pyi')) for p in graph['input_paths']))
    check('coverage_matches_selected_inputs',{r['path'] for r in graph['coverage']}==set(graph['input_paths']) and all(r['status']=='parsed' for r in graph['coverage']))
    check('versioned_production_adapters_and_source_export',trial['mode']=='production_adapter_control_and_workspace_attach' and
          graph['provenance']['input_kind']=='git_committed_blob_export' and graph['provenance']['working_tree_included'] is False and
          graph['provenance']['reference_used_for_extraction'] is False)
    check('actual_python_components',trial['build_version']['python_components']['jedi']=='0.19.2' and trial['build_version']['python_components']['parso']=='0.8.5')
    check('unchanged_original_and_hash_preference',not trial['original_checkout_modified'] and trial['file_hash_verification']=='not_run_per_user_preference')
    for label,node,expected in [('backend_source',server_source,'server/output/build/server'),
                                ('resource_source',resource_source,'platform/resources'),
                                ('resource_destination',resource_destination,'platform/preview/resources'),
                                ('plugin_source',plugin_source,'build/plugin_install.py')]:
        v=node['value'];check(label+'_full_path',v['resolution']=='symbolic_base' and v['base']['kind']=='canonical_source_root' and
            v['relative_path']==expected and not v['unresolved'] and any(c['kind']=='canonical_source_layout_required' for c in v['conditions']))
    destination=server_destination['value'];parameter=nodes[destination['base']['source']] if destination.get('base') else {}
    check('backend_destination_keeps_helper_parameter_identity',destination['resolution']=='symbolic_base' and destination['relative_path']=='server' and
          destination['base']['kind']=='parameter' and parameter.get('kind')=='parameter' and parameter.get('name')=='profiler_path')
    check('helper_destinations_share_parameter_identity',plugin_destination['value']['base']==destination['base'] and
          plugin_destination['value']['relative_path']=='plugin_install.py' and not plugin_destination['value']['unresolved'])
    check('copy_tree_directory_root_semantics',server['api_candidates']==['shutil.copytree'] and server['destination_semantics']==['directory_root'] and
          resources['destination_semantics']==['directory_root'])
    check('copy_file_exact_destination_semantics',plugin['api_candidates']==['shutil.copyfile'] and plugin['destination_semantics']==['exact_path'])
    check('directory_entry_copy_remains_unresolved',all(v['value']['resolution']=='unresolved' for role in ('source','destination') for v in values(loop_copy,role)))
    check('dynamic_launcher_filename_remains_unresolved',all(v['value']['resolution']=='unresolved' for role in ('source','destination') for v in values(launcher_copy,role)))
    check('mapping_status_preserves_pending_obligations',all(opr['mapping_status']=='requires_control_flow_options_and_destination_context' for opr in
          (server,resources,plugin,loop_copy,launcher_copy)))
    check('both_runtime_path_styles_retained',{n['path_context']['style'] for n in nodes.values() if n['kind']=='path_value'}=={'windows','posix'})
    component_edges=[e for e in edges if e['source']==server_source['id'] and e['kind']=='PATH_COMPONENT_SOURCE']
    components=[nodes[e['target']] for e in component_edges]
    check('backend_path_literals_have_source_positions',all(any(n['literal']==literal and n['path']==path for n in components if n.get('literal_type')=='str')
          for literal in ('server','output','build')))
    check('source_file_origin_retained',any(n.get('identifier')=='__file__' and n['path']==path for n in components))
    path_gaps=[d for d in graph['diagnostics'] if d.get('kind')=='python_path_value_unresolved']
    check('directory_loop_and_launcher_have_required_path_gaps',all(any(d['path']==path and d['line']==line and d['required'] for d in path_gaps) for line in (189,532)))
    workspace=Workspace(args.trial/'workspace');active=workspace.config['active'];navigation=[]
    for label,origin,target,allowed in [
        ('backend_source',server['id'],server_source['id'],['FILE_SOURCE','PATH_VALUE_CANDIDATE']),
        ('backend_destination',server['id'],server_destination['id'],['FILE_DESTINATION','PATH_VALUE_CANDIDATE']),
        ('resource_destination',resources['id'],resource_destination['id'],['FILE_DESTINATION','PATH_VALUE_CANDIDATE']),
        ('backend_literal',server_source['id'],next(n['id'] for n in components if n.get('literal')=='output'),['PATH_COMPONENT_SOURCE'])]:
        for direction,a,b in [('out',origin,target),('in',target,origin)]:
            result=workspace.query('path',start=a,target=b,direction=direction,kinds=allowed,depth=3)
            row={'id':label+'_'+direction,'found':result['found'],'stop_reason':result.get('stop_reason'),'snapshot_matches':result['snapshot']==graph['snapshot']}
            navigation.append(row);check('navigation_'+row['id'],row['found'] and row['stop_reason'] is None and row['snapshot_matches'])
    source=workspace.query('source',start=server['id'],context=1)
    check('same_commit_source_navigation',source['source_commit']==revision and source['path']==path and source['requested_line']==344 and
          any(r['line']==344 and 'shutil.copytree' in r['text'] for r in source['items']) and not source['working_tree_read'])
    with sqlite3.connect(workspace.directory/active['index']) as db:
        inputs={p for p,payload in db.execute('SELECT path,payload FROM pm_map_files') if json.loads(payload)['graph_input']}
        check('navigation_input_projection',inputs==set(graph['input_paths']))
        check('file_operations_and_paths_survive_indexing',all(db.execute('SELECT count(*) FROM pm_fact_nodes WHERE kind=?',(kind,)).fetchone()[0]==
              sum(n['kind']==kind for n in nodes.values()) for kind in ('path_value','python_file_operation')))
    check('same_index_snapshot_and_rule_version',active['snapshot']==graph['snapshot'] and active['build_version']==trial['build_version']==graph['version']['build_version'])
    check('no_execution_or_process_pairing_claim',not trial['product_executed'] and not trial['whole_G03_accepted'] and
          all(n['runtime_execution']=='not_observed' for n in (server,server_source,server_destination)))
    def describe(value):return {'path':value['path'],'line':value['line'],'role':value['role'],'path_style':value['path_context']['style'],
        'base_kind':value['value']['base']['kind'] if value['value'].get('base') else None,
        'relative_path':value['value']['relative_path'],'resolution':value['value']['resolution']}
    portable={'schema':'python-path-control-score/1','origin':'executed_production_adapters_separate_source_audit_and_index_queries',
        'source_commit':revision,'snapshot':graph['snapshot'],'scope':trial['scope'],'mode':trial['mode'],'build_version':trial['build_version'],
        'index_counts':trial['build']['counts'],'operation_counts':dict(Counter(a for n in nodes.values() if n['kind']=='python_file_operation' for a in n['api_candidates'])),
        'path_resolution_counts':dict(Counter(n['value']['resolution'] for n in nodes.values() if n['kind']=='path_value')),
        'selected_paths':[describe(v) for v in (server_source,server_destination,resource_source,resource_destination,plugin_source,plugin_destination)],
        'required_gap_counts':dict(Counter(r['reason'] for d in path_gaps for r in d['reasons'])),
        'navigation':navigation,'checks':checks,'passed':all(c['passed'] for c in checks),
        'original_checkout_modified':trial['original_checkout_modified'],'file_hash_verification':trial['file_hash_verification'],
        'default_workspace_rebuild':False,'installed_tool_tested':False,'runtime_execution':False,
        'directory_enumeration_expanded':False,'caller_path_contexts_expanded':False,'process_counterpart_connected':False,
        'whole_G02_accepted':False,'whole_G03_accepted':False}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(portable,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks':len(checks),'passed':portable['passed'],'failed':[c['id'] for c in checks if not c['passed']]}))
    if not portable['passed']:raise SystemExit(1)


if __name__=='__main__':main()
