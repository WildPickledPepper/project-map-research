"""Independent source anchors for the completed Python caller-context recheck."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
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
    revision='d4e8d1cf9f90208bcbe5371c127088f6fd66c688'
    # These product paths and lines are evaluation references, not adapter input.
    expected={'platform/preview/resources/profiler/server':1,
        'plugins/jupyterlab/mindstudio_insight_jupyterlab/resources/profiler/server':2}
    operation=next(n for n in nodes.values() if n['kind']=='python_file_operation' and n['path']=='build/build.py' and n['line']==344)
    values=[n for n in nodes.values() if n['kind']=='path_value' and n['consumer']==operation['id'] and n['path_context']['style']=='windows']
    paired=defaultdict(lambda:defaultdict(list))
    for value in values:paired[value['operation_context']][value['role']].append(value)
    destinations={v['value']['relative_path']:v for roles in paired.values() for v in roles['destination']}
    check('pinned_source',trial['source_commit']==graph['source_commit']==revision)
    check('complete_python_input_scope',len(graph['input_paths'])==119 and {r['path'] for r in graph['coverage']}==set(graph['input_paths']))
    base=trial['build_version']['base_facts']
    check('unchanged_versioned_language_interface_fact_reuse',base['adapter_history_unchanged'] and base['component_versions_unchanged'] and
          base['input_context_unchanged'] and base['counts']=={'nodes':76402,'edges':105988})
    check('path_stage_recomputed_not_fresh_native_rebuild',trial['path_adapter_executed_again'] and
          not trial['native_semantic_stage_executed_again'] and not trial['default_workspace_rebuild'])
    check('two_backend_destination_contexts',set(destinations)==set(expected) and len(paired)==2)
    check('backend_source_paired_with_each_own_destination',all(len(roles['source'])==len(roles['destination'])==1 and
          roles['source'][0]['value']['relative_path']=='server/output/build/server' and
          roles['source'][0]['operation_context']==roles['destination'][0]['operation_context'] for roles in paired.values()))
    for path,depth in expected.items():
        value=destinations[path];context=nodes[value['operation_context']]
        label='desktop' if depth==1 else 'jupyterlab'
        check(label+'_full_symbolic_path',value['value']['resolution']=='symbolic_base' and
              value['value']['base']['kind']=='canonical_source_root' and not value['value']['unresolved'])
        check(label+'_native_call_stack',len(value['call_stack'])==depth and value['call_stack']==context['call_stack'] and
              all(nodes[c]['kind']=='call_site' and nodes[c]['path']=='build/build.py' for c in value['call_stack']))
        check(label+'_source_conditions_preserved',any(c['kind']=='native_call_argument_binding' for c in value['value']['conditions']) and
              any(c['kind']=='canonical_source_layout_required' for c in value['value']['conditions']))
        check(label+'_context_node_is_scoped',context['kind']=='file_operation_context' and context['operation']==operation['id'] and
              context['api_candidates']==['shutil.copytree'] and context['root_basis']=='no_resolved_static_callers' and not context['gaps'])
    plugin=destinations['plugins/jupyterlab/mindstudio_insight_jupyterlab/resources/profiler/server']
    guards=[c for c in plugin['value']['conditions'] if c['kind']=='preceding_control_transfer_not_taken']
    predicate_ids={p['test'] for c in guards for p in c['when'] if p.get('test') in nodes}
    build_predicate=next((p for p in predicate_ids if 'BUILD_JUPYTERLAB' in nodes[p]['name']),None)
    check('jupyterlab_build_flag_and_prior_return_guard',build_predicate is not None and any(c['transfer']=='Return' for c in guards))
    check('guard_sources_connected',build_predicate is not None and any(e['source']==plugin['id'] and e['target']==build_predicate and
          e['kind']=='PATH_GUARD_SOURCE' for e in edges))
    check('all_path_values_have_real_operation_context',all(n.get('operation_context') in nodes and
          nodes[n['operation_context']]['kind']=='file_operation_context' for n in nodes.values() if n['kind']=='path_value'))
    gaps=[d for d in graph['diagnostics'] if d.get('kind')=='python_path_value_unresolved']
    check('directory_entry_copy_still_required_gap',any(d['path']=='build/build.py' and d['line']==189 and d['required'] for d in gaps))
    workspace=Workspace(args.trial/'workspace');navigation=[]
    desktop=destinations['platform/preview/resources/profiler/server']
    routes=[('paired_desktop',desktop['operation_context'],desktop['id'],['CONTEXT_PATH_VALUE']),
        ('desktop_caller',desktop['id'],desktop['call_stack'][-1],['PATH_CALL_CONTEXT']),
        ('jupyterlab_guard',plugin['id'],build_predicate,['PATH_GUARD_SOURCE'])]
    for name,start,target,kinds in routes:
        for direction,a,b in [('out',start,target),('in',target,start)]:
            result=workspace.query('path',start=a,target=b,direction=direction,kinds=kinds,depth=2)
            row={'id':name+'_'+direction,'found':result['found'],'stop_reason':result.get('stop_reason'),'snapshot_matches':result['snapshot']==graph['snapshot']}
            navigation.append(row);check('navigation_'+row['id'],row['found'] and row['stop_reason'] is None and row['snapshot_matches'])
    source=workspace.query('source',start=desktop['id'],context=1)
    check('same_commit_source_navigation',source['source_commit']==revision and source['path']=='build/build.py' and source['requested_line']==344 and not source['working_tree_read'])
    check('same_index_version',workspace.config['active']['snapshot']==graph['snapshot'] and
          workspace.config['active']['build_version']==trial['build_version']==graph['version']['build_version'])
    check('original_unchanged_no_hash_verification',not trial['original_checkout_modified'] and trial['file_hash_verification']=='not_run_per_user_preference')
    check('no_reference_given_to_extractor_or_runtime_claim',graph['provenance']['reference_used_for_extraction'] is False and
          graph['provenance']['working_tree_included'] is False and not trial['product_executed'] and not trial['whole_G03_accepted'])
    portable={'schema':'python-path-context-score/1','origin':'recomputed_production_path_adapter_cached_unchanged_native_facts_separate_source_audit',
        'source_commit':revision,'snapshot':graph['snapshot'],'scope':trial['scope'],'build_version':trial['build_version'],
        'index_counts':trial['build']['counts'],'path_resolution_counts':dict(Counter(n['value']['resolution'] for n in nodes.values() if n['kind']=='path_value')),
        'operation_context_count':sum(n['kind']=='file_operation_context' for n in nodes.values()),
        'backend_destinations':[{'relative_path':p,'base_kind':v['value']['base']['kind'],'caller_count':len(v['call_stack']),
            'callers':[{k:nodes[c][k] for k in ('path','line','name')} for c in v['call_stack']]} for p,v in sorted(destinations.items())],
        'required_gap_counts':dict(Counter(r['reason'] for d in gaps for r in d['reasons'])),
        'navigation':navigation,'checks':checks,'passed':all(c['passed'] for c in checks),
        'native_semantic_stage_executed_again':False,'path_adapter_executed_again':True,'default_workspace_rebuild':False,
        'installed_tool_tested':False,'original_checkout_modified':trial['original_checkout_modified'],
        'file_hash_verification':trial['file_hash_verification'],'runtime_execution':False,
        'directory_enumeration_expanded':False,'process_counterpart_connected':False,'whole_G02_accepted':False,'whole_G03_accepted':False}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(portable,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks':len(checks),'passed':portable['passed'],'failed':[c['id'] for c in checks if not c['passed']]}))
    if not portable['passed']:raise SystemExit(1)


if __name__=='__main__':main()
