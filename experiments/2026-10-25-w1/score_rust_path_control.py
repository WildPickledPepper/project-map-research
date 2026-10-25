"""Score the completed single-context run; product references stay in evaluation."""
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
    # Independent source-audit reference, never supplied to the extraction run.
    reference={'commit':'d4e8d1cf9f90208bcbe5371c127088f6fd66c688','path':'platform/src/default.rs',
        'constructor_line':164,'spawn_line':175,'relative_path':'resources/profiler/server/profiler_server.exe',
        'literal_sources':{'"resources"':42,'"profiler"':42,'"server"':42,'"profiler_server"':42,'"exe"':80}}
    ctor=next(n for n in nodes.values() if n['kind']=='rust_boundary' and n['family']=='command_constructor'
              and n['path']==reference['path'] and n['line']==reference['constructor_line'])
    start=next(n for n in nodes.values() if n['kind']=='rust_boundary' and n['family']=='process_start'
               and n['path']==reference['path'] and n['line']==reference['spawn_line'])
    values=[n for n in nodes.values() if n['kind']=='path_value' and n['consumer']==ctor['id']]
    value=values[0];resolved=value['value']
    component_edges=[e for e in edges if e['source']==value['id'] and e['kind']=='PATH_COMPONENT_SOURCE']
    components=[nodes[e['target']] for e in component_edges]
    contexts=set(value['analysis_contexts'])
    check('pinned_source_and_index',trial['source_commit']==graph['source_commit']==reference['commit'])
    check('one_explicit_manifest_host_release_context',trial['scope']=='one_manifest_one_native_host_release_default' and
          trial['manifest']=='platform/Cargo.toml' and trial['context']['target']=='x86_64-pc-windows-msvc' and
          trial['context']['debug_assertions'] is False and trial['context']['features']==['MindStudioInsight/default'] and len(contexts)==1)
    check('rust_inputs_and_metadata_accounted',len(graph['input_paths'])==16 and
          sum(p.endswith('.rs') for p in graph['input_paths'])==13 and
          set(graph['input_paths'])=={r['path'] for r in graph['coverage']})
    check('unchanged_original_no_hash_verification',not trial['original_checkout_modified'] and
          trial['file_hash_verification']=='not_run_per_user_preference')
    check('export_and_adapters_without_reference',graph['provenance']['input_kind']=='git_committed_blob_export' and
          graph['provenance']['working_tree_included'] is False and graph['provenance']['reference_used_for_extraction'] is False)
    check('single_backend_program_candidate',len(values)==1)
    check('complete_ordered_relative_path',resolved['relative_path']==reference['relative_path'] and
          resolved['segments']==['resources','profiler','server','profiler_server.exe'])
    check('symbolic_executable_directory_not_invented_absolute_location',resolved['resolution']=='symbolic_base' and
          resolved['base']['kind']=='current_executable_directory' and resolved['base']['workspace']==trial['manifest'] and
          resolved['path'] is None and not resolved['unresolved'])
    check('windows_style_from_context',resolved['style']=='windows' and 'windows' in trial['context']['cfg'])
    check('main_and_server_caller_frames',[(nodes[c]['path'],nodes[c]['name']) for c in value['call_stack']]==
          [('platform/src/main.rs','default::main'),('platform/src/default.rs','run_server')] and
          nodes[value['root_function']]['name']=='main' and nodes[value['root_function']]['path']=='platform/src/main.rs')
    kinds=Counter(c['kind'] for c in resolved['conditions'])
    check('successful_option_and_source_call_conditions',kinds['successful_unwrap']==2 and kinds['source_return']==1 and
          kinds['source_call_context']==2 and any(c['kind']=='binding_pattern_selected' and c['pattern']=='Some(path)' for c in resolved['conditions']))
    for name,line in reference['literal_sources'].items():
        check('literal_origin_'+name.strip('"'),any(n['path']==reference['path'] and n['line']==line and n['name']==name for n in components))
    current_exe=nodes[resolved['base']['source']]
    check('native_current_exe_origin_connected',current_exe['id'] in {n['id'] for n in components} and any(
        e['source']==current_exe['id'] and e['kind']=='EXTERNAL_CALL_REFERENCE' and
        nodes[e['target']].get('external_declaration',{}).get('canonical')=='std::env::current_exe' for e in edges))
    check('native_constructor_and_spawn',any(d.get('canonical')=='std::process::Command::new' for d in ctor['api_declarations']) and
          any(d.get('canonical')=='std::process::Command::spawn' for d in start['api_declarations']))
    check('path_source_and_caller_edges_keep_context',all(set(e['analysis_contexts'])==contexts for e in edges if
          e['source']==value['id'] and e['kind'] in {'PATH_COMPONENT_SOURCE','PATH_CALL_CONTEXT'}))
    gaps=[d for d in graph['diagnostics'] if d.get('kind')=='rust_path_value_unresolved']
    check('unresolved_file_read_remains_required',any(d['path']=='platform/src/webview.rs' and d['line']==92 and d['required'] and
          any(r['reason']=='path_expression_not_resolved' for r in d['reasons']) for d in gaps))
    workspace=Workspace(args.trial/'workspace');active=workspace.config['active'];navigation=[]
    for name,a,b,allowed in [
        ('spawn_program',start['id'],value['id'],['USES_COMMAND','COMMAND_PROGRAM','PATH_VALUE_CANDIDATE']),
        ('executable_base',value['id'],current_exe['id'],['PATH_COMPONENT_SOURCE']),
        ('constant_origin',value['id'],next(n['id'] for n in components if n['name']=='"resources"'),['PATH_COMPONENT_SOURCE']),
        ('caller_context',value['id'],value['call_stack'][-1],['PATH_CALL_CONTEXT'])]:
        for direction,origin,target in [('out',a,b),('in',b,a)]:
            result=workspace.query('path',start=origin,target=target,direction=direction,kinds=allowed,depth=4)
            row={'id':name+'_'+direction,'found':result['found'],'stop_reason':result.get('stop_reason'),
                 'snapshot_matches':result['snapshot']==graph['snapshot']}
            navigation.append(row);check('navigation_'+row['id'],row['found'] and row['stop_reason'] is None and row['snapshot_matches'])
    source=workspace.query('source',start=value['id'],context=0)
    check('source_navigation_selected_commit',source['source_commit']==reference['commit'] and source['path']==reference['path'] and
          any(r['line']==164 and 'Command::new(path)' in r['text'] for r in source['items']) and not source['working_tree_read'])
    with sqlite3.connect(workspace.directory/active['index']) as db:
        inputs={p for p,payload in db.execute('SELECT path,payload FROM pm_map_files') if json.loads(payload)['graph_input']}
        check('all_selected_inputs_marked_in_navigation',inputs==set(graph['input_paths']))
        check('index_retains_all_path_candidates',db.execute("SELECT count(*) FROM pm_fact_nodes WHERE kind='path_value'").fetchone()[0]==
              sum(n['kind']=='path_value' for n in nodes.values()))
    check('same_source_snapshot_rule_version',active['snapshot']==graph['snapshot'] and active['source_commit']==reference['commit'] and
          active['build_version']==trial['build_version']==graph['version']['build_version'])
    check('no_runtime_full_context_or_counterpart_acceptance',not trial['product_executed'] and not trial['whole_G03_accepted'] and
          value['runtime_execution']=='not_observed' and ctor['counterpart_status']=='requires_artifact_instance_and_deployment_context')
    portable={'schema':'rust-path-control-score/1','origin':'executed_production_adapters_separate_source_audit_and_index_queries',
        'source_commit':graph['source_commit'],'snapshot':graph['snapshot'],'scope':trial['scope'],'mode':trial['mode'],
        'build_version':trial['build_version'],'manifest':trial['manifest'],'context':trial['context'],'index_counts':trial['build']['counts'],
        'path_resolution_counts':dict(Counter(n['value']['resolution'] for n in nodes.values() if n['kind']=='path_value')),
        'backend_program':{'path':value['path'],'line':value['line'],'base_kind':resolved['base']['kind'],
            'relative_path':resolved['relative_path'],'resolution':resolved['resolution'],'conditions':dict(kinds),
            'callers':[{k:nodes[c][k] for k in ('path','line','name')} for c in value['call_stack']]},
        'component_sources':[{k:n[k] for k in ('path','line','name','kind')} for n in components],
        'required_path_gaps':[{'path':d['path'],'line':d['line'],'reasons':[r['reason'] for r in d['reasons']]} for d in gaps],
        'navigation':navigation,'checks':checks,'passed':all(c['passed'] for c in checks),
        'first_run_metadata_projection':'three_selected_manifests_missing_coverage_rows_fixed_in_control_runner',
        'original_checkout_modified':trial['original_checkout_modified'],'file_hash_verification':trial['file_hash_verification'],
        'default_workspace_rebuild':False,'installed_tool_tested':False,'runtime_execution':False,
        'process_counterpart_connected':False,'whole_G02_accepted':False,'whole_G03_accepted':False}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(portable,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks':len(checks),'passed':portable['passed'],'failed':[c['id'] for c in checks if not c['passed']]}))
    if not portable['passed']:raise SystemExit(1)


if __name__=='__main__':main()
