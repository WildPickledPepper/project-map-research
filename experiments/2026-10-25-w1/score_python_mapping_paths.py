"""Check real platform-dictionary path selection separately from Cargo pairing."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.file_predicate_values import conditions
from projectmap.workspace import Workspace


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--trial',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    if args.output.exists():ap.error('Choose a new evidence path')
    trial=json.loads((args.trial/'trial.json').read_text(encoding='utf-8'))
    graph=json.loads((args.trial/'graph.json').read_text(encoding='utf-8'));nodes={n['id']:n for n in graph['nodes']};checks=[]
    def check(name,value):checks.append({'id':name,'passed':bool(value)})
    # Source positions and expected names below are independent score references.
    revision='d4e8d1cf9f90208bcbe5371c127088f6fd66c688'
    values=[n for n in nodes.values() if n['kind']=='path_value' and n['path']=='build/build.py' and n['line']==532 and n['value']['style']=='windows']
    check('same_pinned_source',graph['source_commit']==trial['source_commit']==revision)
    check('all_selected_python_inputs',len(graph['input_paths'])==119 and {r['path'] for r in graph['coverage']}==set(graph['input_paths']))
    check('full_guarded_source_and_destination_candidates',len(values)==8 and sum(v['role']=='source' for v in values)==4)
    selected={};results={}
    for host in ('Windows','Linux','Darwin'):
        selected[host]=[];results[host]=[]
        for v in values:
            result=conditions(v['value']['conditions'],style='windows',host_system={'name':host,'path_style':'windows' if host=='Windows' else 'posix'})
            if result['permitted']:selected[host].append(v);results[host].append(result)
    win={v['role']:v['value']['relative_path'] for v in selected['Windows']}
    linux={v['role']:v['value']['relative_path'] for v in selected['Linux']}
    check('windows_renamed_executable_paths',len(selected['Windows'])==2 and win=={
        'source':'platform/target/release/MindStudioInsight.exe','destination':'platform/preview/MindStudio-Insight.exe'})
    # Linux here is an explicit predicate-selection check on the same lexical
    # candidates, not proof of the Linux Cargo build or runtime platform.
    check('missing_linux_keys_select_defaults',len(selected['Linux'])==2 and linux=={
        'source':'platform/target/release/MindStudioInsight','destination':'platform/preview/MindStudio-Insight'})
    check('macos_excludes_this_file_copy_branch',not selected['Darwin'])
    check('selected_candidates_have_complete_paths',all(v['value']['resolution']=='symbolic_base' and not v['value']['unresolved'] for v in selected['Windows']))
    check('same_call_pair',len({v['operation_context'] for v in selected['Windows']})==1)
    check('selected_values_keep_runtime_guards',all(r['residual'] for r in results['Windows']))
    source=next(v for v in selected['Windows'] if v['role']=='source')
    lookup=next(e['target'] for e in graph['edges'] if e['source']==source['id'] and e['kind']=='PATH_LOOKUP_SOURCE')
    key=next(e['target'] for e in graph['edges'] if e['source']==source['id'] and e['kind']=='PATH_GUARD_SOURCE' and
        nodes[e['target']].get('expression_kind')=='Tuple')
    check('native_mapping_definition_retained',nodes[lookup]['kind']=='value' and nodes[lookup]['expression_kind']=='Dict' and nodes[lookup]['path']=='build/build.py')
    check('native_tuple_key_retained',nodes[key]['line']==528)
    check('typed_selection_conditions_complete',all(c['predicate_complete'] for v in values for c in v['value']['conditions'] if c['kind']=='mapping_entry_selected'))
    check('copy_path_no_longer_unresolved',not any(d.get('kind')=='python_path_value_unresolved' and d['path']=='build/build.py' and d['line']==532 for d in graph['diagnostics']))
    workspace=Workspace(args.trial/'workspace');navigation=[]
    for label,a,b,kind in [('mapping_definition',source['id'],lookup,'PATH_LOOKUP_SOURCE'),('mapping_key',source['id'],key,'PATH_GUARD_SOURCE')]:
        for direction,start,target in [('out',a,b),('in',b,a)]:
            result=workspace.query('path',start=start,target=target,direction=direction,kinds=[kind],depth=2)
            row={'id':label+'_'+direction,'found':result['found'],'stop_reason':result.get('stop_reason'),'snapshot_matches':result['snapshot']==graph['snapshot']}
            navigation.append(row);check('navigation_'+row['id'],row['found'] and row['stop_reason'] is None and row['snapshot_matches'])
    code=workspace.query('source',start=source['id'])
    check('same_version_copy_source',code['source_commit']==revision and code['path']=='build/build.py' and code['requested_line']==532 and not code['working_tree_read'])
    check('same_index_version',workspace.config['active']['build_version']==trial['build_version']==graph['version']['build_version'])
    base=trial['build_version']['base_facts']
    check('native_stage_versioned_and_unchanged',base['adapter_history_unchanged'] and base['component_versions_unchanged'] and base['input_context_unchanged'] and
        trial['path_adapter_executed_again'] and not trial['native_semantic_stage_executed_again'])
    check('original_checkout_and_hash_preference',not trial['original_checkout_modified'] and trial['file_hash_verification']=='not_run_per_user_preference')
    check('reference_not_used_by_extractor',graph['provenance']['reference_used_for_extraction'] is False and graph['provenance']['working_tree_included'] is False)
    check('control_scope_not_whole_acceptance',not trial['default_workspace_rebuild'] and not trial['product_executed'] and not trial['whole_G03_accepted'])
    portable={'schema':'python-mapping-path-score/1','origin':'executed_production_path_adapter_cached_native_facts_independent_dictionary_source_reference',
        'source_commit':revision,'snapshot':graph['snapshot'],'scope':trial['scope'],'build_version':trial['build_version'],'index_counts':trial['build']['counts'],
        'windows_copy_paths':win,'linux_default_selection_paths':linux,'macos_copy_branch_excluded':not selected['Darwin'],
        'host_selection':'explicit_predicate_scoring_context_not_native_cargo_build_or_runtime',
        'navigation':navigation,'checks':checks,'passed':all(c['passed'] for c in checks),
        'path_adapter_executed_again':True,'native_semantic_stage_executed_again':False,'default_workspace_rebuild':False,'installed_tool_tested':False,
        'original_checkout_modified':trial['original_checkout_modified'],'file_hash_verification':trial['file_hash_verification'],
        'runtime_execution':False,'cargo_build_context_connected':False,'process_counterpart_connected':False,'whole_G02_accepted':False,'whole_G03_accepted':False}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(portable,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks':len(checks),'passed':portable['passed'],'failed':[c['id'] for c in checks if not c['passed']]}))
    if not portable['passed']:raise SystemExit(1)


if __name__=='__main__':main()
