"""Independently verify Insight's Cargo invocation and environment provenance."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.python_process_values import resolve,environment_value
from projectmap.workspace import Workspace


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--trial',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    if args.output.exists():ap.error('Choose a new evidence path')
    trial=json.loads((args.trial/'trial.json').read_text(encoding='utf-8'))
    graph=json.loads((args.trial/'graph.json').read_text(encoding='utf-8'));nodes={n['id']:n for n in graph['nodes']}
    checks=[]
    def check(name,value):checks.append({'id':name,'passed':bool(value)})
    # These source positions and expected values are scoring references only.
    revision='d4e8d1cf9f90208bcbe5371c127088f6fd66c688';host={'name':'Windows','path_style':'windows'}
    invocations=[n for n in nodes.values() if n['kind']=='python_process_invocation'];effects=[n for n in nodes.values() if n['kind']=='python_environment_effect']
    candidates=[]
    for node in invocations:
        if node['path']!='build/build.py' or node['line']!=644 or node['path_style']!='windows':continue
        if not any(nodes[c]['path']=='build/build.py' and nodes[c]['line']==404 for c in node['call_stack']):continue
        selected=resolve(node,host)
        if selected['status']=='conditional_candidate':candidates.append((node,selected))
    check('same_pinned_source',trial['source_commit']==graph['source_commit']==revision)
    check('all_python_inputs_retained',len(graph['input_paths'])==119 and {r['path'] for r in graph['coverage']}==set(graph['input_paths']))
    check('production_adapter_version',graph['extractors']['python']['values']=='import_bound_paths_mappings_and_process_calls/0.7.0')
    check('one_windows_cargo_build_invocation',len(candidates)==1)
    invocation,selected=candidates[0]
    argv=[a[0]['text'] if len(a)==1 else None for a in selected['argv']]
    cwd=selected['cwd'][0]['path_value'];target=environment_value(invocation,effects,'CARGO_TARGET_DIR',host)
    check('exact_command_argv',argv==['cargo.exe','build','--release'] and invocation['argument_form']=='sequence')
    check('native_library_process_identity',invocation['api_candidates']==['subprocess.Popen'] and not invocation['library_member_writes'])
    check('source_root_working_directory',cwd['resolution']=='symbolic_base' and cwd['base']['kind']=='canonical_source_root' and cwd['relative_path']=='platform')
    check('target_directory_source_resolved',target['known'] and target['value']['text'] is None and target['value']['path_value']['relative_path']=='platform/target' and
        target['value']['path_value']['base']['kind']=='canonical_source_root')
    writer=nodes[target['writer']]
    check('source_environment_writer_location',writer['path']=='build/build.py' and writer['line']==373 and writer['api']=='os.putenv' and writer['effect']=='set')
    check('putenv_process_environment_mapping_distinction',writer['also_updates_os_environ'] is False)
    check('same_root_environment_context',writer['root_function']==invocation['root_function'] and target['basis']=='same_root_resolved_source_order_conditional_on_invocation')
    check('environment_binding_remains_conditional',target['runtime_execution']=='not_observed' and set(target['conditions'])=={
        'source_environment_operation_succeeds','no_unmodeled_environment_write_before_child_start'})
    check('direct_process_settings',selected['settings']['shell']=={'known':True,'value':False} and all(
        selected['settings'][k]=={'known':True,'value':None} for k in ('env','executable','preexec_fn')))
    check('no_resolver_static_gaps',not selected['gaps'])
    check('late_and_unbound_runtime_inputs_not_filled',not environment_value(invocation,effects,'INDEPENDENT_UNSUPPLIED_ENVIRONMENT',host)['known'])
    check('conditional_other_write_not_promoted',not environment_value(invocation,effects,'LD_PRELOAD',host)['known'])
    boundary=invocation['call']+':boundary:process_start'
    check('existing_process_boundary_connected',boundary in nodes and any(e['kind']=='PROCESS_BOUNDARY' and e['source']==invocation['id'] and e['target']==boundary for e in graph['edges']))
    check('command_component_origins_connected',any(e['kind']=='PROCESS_ARGUMENT_COMPONENT' and e['source']==invocation['id'] for e in graph['edges']))
    arg=next(e['target'] for e in graph['edges'] if e['source']==invocation['id'] and e['kind']=='PROCESS_ARGUMENT_SOURCE')
    cwd_source=next(e['target'] for e in graph['edges'] if e['source']==invocation['id'] and e['kind']=='PROCESS_WORKING_DIRECTORY')
    key_source=next(e['target'] for e in graph['edges'] if e['source']==writer['id'] and e['kind']=='ENVIRONMENT_EFFECT_SOURCE' and nodes[e['target']].get('literal')=='CARGO_TARGET_DIR')
    workspace=Workspace(args.trial/'workspace');navigation=[]
    for label,a,b,kind in [('argv_source',invocation['id'],arg,'PROCESS_ARGUMENT_SOURCE'),('cwd_source',invocation['id'],cwd_source,'PROCESS_WORKING_DIRECTORY'),
            ('environment_writer',invocation['id'],writer['id'],'PROCESS_ENVIRONMENT_EFFECT'),('environment_key',writer['id'],key_source,'ENVIRONMENT_EFFECT_SOURCE')]:
        for direction,start,goal in [('out',a,b),('in',b,a)]:
            result=workspace.query('path',start=start,target=goal,direction=direction,kinds=[kind],depth=2)
            row={'id':label+'_'+direction,'found':result['found'],'stop_reason':result.get('stop_reason'),'snapshot_matches':result['snapshot']==graph['snapshot']}
            navigation.append(row);check('navigation_'+row['id'],row['found'] and row['stop_reason'] is None and row['snapshot_matches'])
    source=workspace.query('source',start=invocation['id'])
    check('same_version_process_source',source['source_commit']==revision and source['path']=='build/build.py' and source['requested_line']==644 and not source['working_tree_read'])
    check('same_index_rule_version',workspace.config['active']['build_version']==graph['version']['build_version']==trial['build_version'])
    base=trial['build_version']['base_facts']
    check('native_facts_versioned_unchanged',all(base[k] for k in ('adapter_history_unchanged','component_versions_unchanged','input_context_unchanged')) and
        trial['path_adapter_executed_again'] and not trial['native_semantic_stage_executed_again'])
    check('working_tree_and_reference_not_inputs',not graph['provenance']['working_tree_included'] and not graph['provenance']['reference_used_for_extraction'] and not trial['original_checkout_modified'])
    check('no_file_hash_verification',trial['file_hash_verification']=='not_run_per_user_preference')
    check('no_full_runtime_or_cargo_native_claim',not trial['default_workspace_rebuild'] and not trial['product_executed'] and not trial['whole_G03_accepted'])
    portable={'schema':'python-process-control-score/1','origin':'executed_production_process_values_cached_native_semantics_independent_cargo_call_reference',
        'source_commit':revision,'snapshot':graph['snapshot'],'scope':trial['scope'],'build_version':trial['build_version'],'index_counts':trial['build']['counts'],
        'invocation_record_count':len(invocations),'environment_effect_record_count':len(effects),
        'selected_process':{'path':invocation['path'],'line':invocation['line'],'api':invocation['api_candidates'],'argv':argv,
            'cwd':cwd['relative_path'],'environment':{'CARGO_TARGET_DIR':target['value']['path_value']['relative_path']},
            'environment_writer_line':writer['line'],'also_updates_os_environ':writer['also_updates_os_environ'],
            'value_binding_basis':target['basis'],'conditions':target['conditions']},
        'process_diagnostic_counts':dict(Counter(d['kind'] for d in graph['diagnostics'] if d['kind'].startswith('python_process_'))),
        'navigation':navigation,'checks':checks,'passed':all(c['passed'] for c in checks),
        'host_selection':'explicit_windows_source_predicate_control_not_native_cargo_build',
        'native_semantic_stage_executed_again':False,'path_and_process_adapters_executed_again':True,'default_workspace_rebuild':False,'installed_tool_tested':False,
        'runtime_execution':False,'cargo_native_target_connected':False,'process_counterpart_connected':False,'whole_G02_accepted':False,'whole_G03_accepted':False,
        'original_checkout_modified':trial['original_checkout_modified'],'file_hash_verification':trial['file_hash_verification']}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(portable,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks':len(checks),'passed':portable['passed'],'failed':[c['id'] for c in checks if not c['passed']]}))
    if not portable['passed']:raise SystemExit(1)


if __name__=='__main__':main()
