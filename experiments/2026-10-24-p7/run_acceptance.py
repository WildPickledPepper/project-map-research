"""Score extracted P7 facts against independent case expectations, then rebuild equivalence."""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
from project_query import ProjectQuery,render_markdown
from adapters.protocol_graph import match_message
from adapters.return_bridge_queries import explain_return_bridge


def run(graph_path,inventory_path,catalog_path,runtime_store,output,rebuild=None):
    if output.exists():raise ValueError('Use a fresh output directory')
    output.mkdir(parents=True)
    read=lambda p:json.loads(p.read_text(encoding='utf-8'))
    graph=read(graph_path);inventory=read(inventory_path);catalog=read(catalog_path);q=ProjectQuery(graph,inventory,catalog)
    def save(name,value):(output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    checks={};results=[]
    expected={'getUnitFlows':'QueryFlowsBySliceInfoHandler::HandleRequest',
              'queryTimelineOffset':'RankOffsetHandler::HandleRequest','memoryCurveGet':'QueryMemoryViewHandler::HandleRequest'}
    for api,handler in expected.items():
        query=q.trace(api);save(api+'-protocol.json',query)
        checks[api+'_unique_scoped_handler']=query['total']==1 and query['items'][0]['consumer']['status']=='matched_conditional' and [n['name'].rsplit('::',2)[-2] for n in query['items'][0]['handlers']]==[handler.split('::')[0]]
        row=query['items'][0];results.append({'api':api,'handler':row['handlers'],'provider':row['provider']['id'],'status':row['consumer']['status']})
        if api=='queryTimelineOffset':continue
        field=['unitAllFlows'] if api=='getUnitFlows' else ['lines']
        chain=q.trace(api,field=field,limit=500);save(api+'-chain.json',chain)
        checks[api+'_return_to_state']=len(chain['chains'])==1 and chain['chains'][0]['status']=='conditional_source_chain' and bool(chain['chains'][0]['summary']['states'])
        results[-1]['field']=field;results[-1]['chain']={k:chain['chains'][0][k] for k in ('status','summary','truncated','conditions','unexpanded')}
        results[-1]['stages']=dict(Counter(e['stage'] for e in chain['items']))
        results[-1]['gap_kinds']=dict(Counter(e['kind'] for e in chain['chains'][0]['gaps']))
    memory=q.trace('memoryCurveGet')['items'][0];provider=memory['provider'];message=memory['message']
    deployment=graph['protocol']['deployment'];providers=graph['protocol']['providers']
    deleted=match_message(message,[p for p in providers if p['id']!=provider['id']],deployment)
    renamed=deepcopy(message)
    renamed['payload']['fields'][provider['command_fields'][0]]={'state':'constant','value':'never/registered/negative'}
    changed=match_message(renamed,providers,deployment)
    other_scope=deepcopy(message);other_scope['payload']['fields'][provider['scope_fields'][0]]={'state':'constant','value':'distinct-module-negative'}
    scoped=match_message(other_scope,providers,deployment)
    checks.update(deleted_provider_not_matched=not deleted['matches'],changed_command_not_matched=not changed['matches'],other_module_not_matched=not scoped['matches'])
    # Mutate only extracted serialization facts, not original source. This is a
    # query isolation test, not an automatic-refresh/source-mutation experiment.
    mutation=deepcopy(graph)
    for function in mutation['data']['serialization']['functions']:
        function['field_mappings']=[f for f in function['field_mappings'] if 'lines' not in f['wire_path']]
    replaced=explain_return_bridge(mutation,provider['id'],field_path=['lines'])
    checks['removed_serialized_field_has_no_consumer_link']=replaced['total_links']==0
    impact=q.impact(changed_paths=['server/src/modules/memory/parser/CurveContainer.cpp'],limit=500)
    save('cache-impact.json',impact);checks['cache_reverse_entry']=any(x['name']=='memoryCurveGet' for x in impact['items'])
    dbpaths=[]
    for node in q.search('QueryMemoryView',kind='callable',limit=500)['items']:
        if node.get('definition') and node['name'].endswith('::QueryMemoryView'):
            reverse=q.impact(name=node['id'],limit=500);save(node['name'].split('::')[-2]+'-impact.json',reverse)
            ok=any(x['name']=='memoryCurveGet' for x in reverse['items']);checks[node['name']+'_reverse']=ok;dbpaths.append({'node':node,'reaches_memory_api':ok})
    resource=q.resource('CurveContainer',limit=500);save('cache-resources.json',resource)
    checks['cache_member_write_read_and_clear_present']=all(any(s['storage']['name']==name and
        any(e['role']=='write' for e in s['member_effects']) and
        any(e['role'] in {'read','receiver_use'} for e in s['member_effects']) for s in resource['items']) for name in ('key','flatData','legends'))
    chain=q.trace('memoryCurveGet',field=['lines'],limit=500)
    state=[e for e in chain['items'] if e['stage']=='frontend_state']
    checks['frontend_request_id_guard_retained']=bool(state) and all(any('requestId !== requestIdRef.current' in str(c) and c.get('when') is False for c in e['conditions'] if isinstance(c,dict)) for e in state)
    runs=q.runs(runtime_store,limit=500);save('runs.json',runs)
    checks['runtime_records_keep_original_versions']=runs['total']==5 and all(not r['eligible_for_direct_overlay'] and not r['verification_carried_forward'] for r in runs['items'])
    assets=q.assets();checks['P6_pending_explicit']=assets['status']=='not_connected' and assets['applicability']=='not_evaluated'
    overview=q.overview(limit=500);save('overview.json',overview);(output/'project-map.md').write_text(render_markdown(overview),encoding='utf-8')
    checks['all_tracked_paths_in_inventory']=sum(g['tracked_files'] for g in catalog['top_level_groups'])==inventory['tracked_files']
    checks['unexpanded_languages_visible']=all(any(l['name']==lang and l['graph_input_files']==0 for l in catalog['languages']) for lang in ('Python','Rust'))
    checks['paging_and_depth_explicit']=q.search('QueryMemoryView',limit=1)['truncated'] and memory['consumer']['status']=='matched_conditional' and q.trace('memoryCurveGet',depth=0)['items'][0]['depth_limit_reached']
    rebuild_result={'status':'not_run'}
    if rebuild:
        second=read(rebuild);a=deepcopy(graph);b=deepcopy(second)
        for g in (a,b):g.pop('snapshot');g['version'].pop('snapshot')
        same=a==b;checks['fresh_graph_semantic_equality']=same
        rebuild_result={'status':'passed' if same else 'failed','first':graph['snapshot'],'second':second['snapshot'],
                        'comparison':'direct JSON equality excluding only snapshot ID and version.snapshot; no hash verification',
                        'differing_top_level_keys':[k for k in a if a[k]!=b.get(k)]}
    result={'evidence_kind':'executed_source_queries_and_independent_case_scoring','source_commit':graph['source_commit'],
        'snapshot':graph['snapshot'],'build_version':graph['version']['build_version'],
        'counts':{'input_files':len(graph['input_paths']),'nodes':len(graph['nodes']),'edges':len(graph['edges']),
                  'member_effects':len(graph['data']['member_effects']['effects']),'coverage':dict(Counter(x['status'] for x in graph['coverage']))},
        'checks':checks,'passed':all(checks.values()),'chains':results,'database_reverse':dbpaths,
        'negative_scope':'extracted-fact mutations; source refresh was separately accepted in P4',
        'negative_results':{'delete_provider':deleted['status'],'change_command':changed['status'],'different_module':scoped['status'],'removed_field_links':replaced['total_links']},
        'rebuild':rebuild_result,'P6':'pending_external_assets','memory_runtime':'not_executed','whole_repository_semantics':False}
    save('validation.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('graph','inventory','catalog','runtime-store','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--rebuild',type=Path);a=p.parse_args()
    r=run(a.graph,a.inventory,a.catalog,a.runtime_store,a.output,a.rebuild)
    print(json.dumps({'passed':r['passed'],'checks':r['checks']}));raise SystemExit(0 if r['passed'] else 1)
