"""Score extracted directory patterns and separately compare a native artifact.

This is path correspondence evaluation. Filter execution, platform binding and
production artifact edges are distinct steps, deliberately not claimed here.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.path_patterns import match,instantiate
from projectmap.workspace import Workspace


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--trial',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    if args.output.exists():ap.error('Choose a new evidence output path')
    trial=json.loads((args.trial/'trial.json').read_text(encoding='utf-8'))
    graph=json.loads((args.trial/'graph.json').read_text(encoding='utf-8'))
    native=json.loads((Path(__file__).parent/'evidence/cmake-production.json').read_text(encoding='utf-8'))
    nodes={n['id']:n for n in graph['nodes']};edges=graph['edges'];checks=[]
    def check(name,value):checks.append({'id':name,'passed':bool(value)})
    # Independent source reference, unavailable to production extraction.
    revision='d4e8d1cf9f90208bcbe5371c127088f6fd66c688';path='build/build.py'
    sources=[n for n in nodes.values() if n['kind']=='path_value' and n['path']==path and n['line']==189 and n['role']=='source' and n['path_context']['style']=='windows']
    source=sources[0]
    destinations=[n for n in nodes.values() if n['kind']=='path_value' and n['consumer']==source['consumer'] and n['role']=='destination' and
                  n['operation_context']==source['operation_context'] and n['path_context']['style']=='windows']
    destination=destinations[0];sp=source['value'];dp=destination['value'];directory,file=sp['segments'][2],sp['segments'][4]
    iterations=[nodes[s['iteration']] for s in (directory,file)]
    check('same_pinned_source',trial['source_commit']==graph['source_commit']==native['source_commit']==revision)
    check('complete_python_control_input_scope',len(graph['input_paths'])==119 and {r['path'] for r in graph['coverage']}==set(graph['input_paths']))
    check('one_source_destination_pair_per_context',len(sources)==len(destinations)==1)
    check('source_pattern_has_fixed_directories_and_two_variables',sp['resolution']=='pattern' and sp['segments'][:2]==['server','output'] and sp['segments'][3]=='bin' and
          directory['kind']==file['kind']=='directory_entry_name' and directory['variable']!=file['variable'])
    check('destination_pattern_preserves_same_file_variable',dp['resolution']=='pattern' and dp['segments'][:4]==['server','output','build','server'] and
          dp['segments'][4]['variable']==file['variable'])
    check('directory_domains_preserved',directory['directory']['segments']==['server','output'] and file['directory']['segments'][:2]==['server','output'] and
          file['directory']['segments'][2]['variable']==directory['variable'] and file['directory']['segments'][3]=='bin')
    check('native_iterator_api_and_bindings',all(i['kind']=='path_iteration' and i['api_candidates']==['os.listdir'] and i['path_style']=='windows' and
          nodes[i['binding']]['kind']=='binding' and nodes[i['iterator']]['kind']=='call_site' for i in iterations))
    check('source_iteration_links_preserved',{i['id'] for i in iterations}<={e['target'] for e in edges if e['source']==source['id'] and e['kind']=='PATH_ITERATION_SOURCE'})
    check('pattern_is_not_a_concrete_path',sp['path'] is None and sp['relative_path'] is None and dp['path'] is None and dp['relative_path'] is None)
    check('no_unresolved_directory_base_for_reference',not sp['unresolved'] and not dp['unresolved'])
    location=native['primary_artifact']['location']
    # Windows is an explicit evaluation selection. Native automatic platform
    # binding is not inferred from '.exe' and is not established by this score.
    concrete={'base':{'kind':'source_root','source':'native-artifact-reference'},'segments':location['path'].split('/'),
              'style':'windows','unresolved':[],'conditions':[]}
    matched=match(sp,concrete);stage=instantiate(dp,matched['bindings']) if matched else None
    check('published_native_artifact_source_location',native['passed'] and location['root']=='source')
    check('native_artifact_full_path_matches_pattern',matched is not None)
    check('both_directory_memberships_supported_by_artifact_prefix',matched is not None and len(matched['membership_conditions'])==2 and
          all(c['basis']=='artifact_path_prefix' for c in matched['membership_conditions']))
    check('stage_destination_computed_from_bound_filename',stage is not None and stage['relative_path']=='server/output/build/server/profiler_server.exe')
    renamed={**concrete,'segments':concrete['segments'][:-1]+['unrelated-worker.bin']};rename_match=match(sp,renamed)
    check('different_filename_uses_same_rules',rename_match is not None and instantiate(dp,rename_match['bindings'])['relative_path']=='server/output/build/server/unrelated-worker.bin')
    other={**concrete,'segments':['unrelated-root',*concrete['segments'][1:]]}
    check('same_basename_wrong_directory_rejected',match(sp,other) is None)
    check('unbound_build_root_not_equal_to_source_root',match(sp,{**concrete,'base':{'kind':'build_root','source':'other-context'}}) is None)
    check('missing_destination_variable_not_guessed',instantiate(dp,{}) is None)
    # Compare subsequent directory copies by their extracted full prefixes.
    correspondences=[]
    for target in nodes.values():
        if target['kind']!='path_value' or target['path']!=path or target['line']!=344 or target['role']!='destination' or target['path_context']['style']!='windows':continue
        start=next(n for n in nodes.values() if n['kind']=='path_value' and n['role']=='source' and n['operation_context']==target['operation_context'] and n['path_context']['style']=='windows')
        prefix=match(start['value'],stage,prefix=True)
        if prefix:
            result=instantiate(target['value'],prefix['bindings'],suffix=prefix['suffix'])
            correspondences.append(result['relative_path'])
    check('desktop_and_plugin_directory_path_correspondence',set(correspondences)=={
        'platform/preview/resources/profiler/server/profiler_server.exe',
        'plugins/jupyterlab/mindstudio_insight_jupyterlab/resources/profiler/server/profiler_server.exe'})
    suffix_filter=next((e['target'] for e in edges if e['source']==source['id'] and e['kind']=='PATH_GUARD_SOURCE' and nodes[e['target']]['name']=='file.endswith'),None)
    check('suffix_filter_source_retained_for_next_stage',suffix_filter is not None)
    check('directory_path_no_longer_reports_unresolved_at_copy',not any(d.get('kind')=='python_path_value_unresolved' and d['path']==path and d['line']==189 for d in graph['diagnostics']))
    workspace=Workspace(args.trial/'workspace');navigation=[]
    routes=[('source_iteration',source['id'],iterations[0]['id'],['PATH_ITERATION_SOURCE']),
        ('iteration_directory',iterations[1]['id'],iterations[1]['directory'],['ITERATION_DIRECTORY']),
        ('suffix_guard',source['id'],suffix_filter,['PATH_GUARD_SOURCE'])]
    for label,a,b,kinds in routes:
        for direction,start,target in [('out',a,b),('in',b,a)]:
            result=workspace.query('path',start=start,target=target,direction=direction,kinds=kinds,depth=2)
            row={'id':label+'_'+direction,'found':result['found'],'stop_reason':result.get('stop_reason'),'snapshot_matches':result['snapshot']==graph['snapshot']}
            navigation.append(row);check('navigation_'+row['id'],row['found'] and row['stop_reason'] is None and row['snapshot_matches'])
    source_result=workspace.query('source',start=source['id'],context=1)
    check('same_version_source_navigation',source_result['source_commit']==revision and source_result['requested_line']==189 and not source_result['working_tree_read'])
    base=trial['build_version']['base_facts']
    check('reused_native_stage_versioned_unchanged',base['adapter_history_unchanged'] and base['component_versions_unchanged'] and base['input_context_unchanged'] and
          trial['path_adapter_executed_again'] and not trial['native_semantic_stage_executed_again'])
    check('original_unchanged_and_hash_preference',not trial['original_checkout_modified'] and trial['file_hash_verification']=='not_run_per_user_preference')
    check('extraction_not_given_artifact_or_source_answers',graph['provenance']['reference_used_for_extraction'] is False and graph['provenance']['working_tree_included'] is False)
    portable={'schema':'python-directory-pattern-score/1','origin':'recomputed_production_path_patterns_separate_native_artifact_reference_comparison',
        'source_commit':revision,'snapshot':graph['snapshot'],'scope':trial['scope'],'build_version':trial['build_version'],'index_counts':trial['build']['counts'],
        'path_resolution_counts':dict(Counter(n['value']['resolution'] for n in nodes.values() if n['kind']=='path_value')),
        'iteration_count':sum(n['kind']=='path_iteration' for n in nodes.values()),
        'source_pattern':sp['display_path'],'destination_pattern':dp['display_path'],
        'native_artifact_reference':{'rules_commit':native['build_version']['rules_commit'],'snapshot':native['snapshot'],'location':location},
        'evaluation_path_style_selection':'windows_explicit_reference_not_automatic_native_platform_binding',
        'computed_stage_path':stage['relative_path'] if stage else None,'subsequent_directory_path_correspondences':sorted(correspondences),
        'navigation':navigation,'checks':checks,'passed':all(c['passed'] for c in checks),
        'native_semantic_stage_executed_again':False,'path_adapter_executed_again':True,'default_workspace_rebuild':False,'installed_tool_tested':False,
        'original_checkout_modified':trial['original_checkout_modified'],'file_hash_verification':trial['file_hash_verification'],'runtime_execution':False,
        'directory_patterns_extracted':True,'filter_predicates_applied':False,'copy_contracts_applied':False,'native_platform_automatically_bound':False,
        'production_artifact_edges_emitted':False,'process_counterpart_connected':False,'whole_G02_accepted':False,'whole_G03_accepted':False}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(portable,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks':len(checks),'passed':portable['passed'],'failed':[c['id'] for c in checks if not c['passed']]}))
    if not portable['passed']:raise SystemExit(1)


if __name__=='__main__':main()
