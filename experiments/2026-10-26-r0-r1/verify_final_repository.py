"""Verify final integration invariants and source/native queries on a published map."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.project_map import Budget,ProjectMap
from projectmap.workspace import Workspace


def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('trial','audit','contracts','output'):ap.add_argument('--'+name,type=Path,required=True)
    args=ap.parse_args()
    if args.output.exists():ap.error('Choose a new output')
    trial=load(args.trial/'trial.json');audit=load(args.audit);contracts=load(args.contracts)
    workspace=Workspace(args.trial/'workspace');active=workspace.config['active']
    q=ProjectMap(workspace.directory/active['index'],budget=Budget(10,1000,2000,1048576),
                 expected_snapshot=active['snapshot'])
    checks=[]
    def check(name,passed,detail=None):
        checks.append({'id':name,'passed':bool(passed),'detail':detail})
        print(json.dumps({'check':name,'passed':bool(passed)}),flush=True)
    def rows(sql,params):
        deadline=time.monotonic()+30
        q.db.set_progress_handler(lambda:time.monotonic()>deadline,10000)
        try:return q.db.execute(sql,params).fetchall()
        finally:q.db.set_progress_handler(None,0)
    def scalar(sql,*params):
        return rows(sql,(active['snapshot'],*params))[0][0]
    witnesses=[]
    try:
        check('same_published_source_snapshot_and_rules',all(
            row['source_commit']==active['source_commit'] and row['snapshot']==active['snapshot']
            for row in (audit,contracts)) and audit['build_version']==active['build_version']
              and contracts['rules_version']==active['build_version'])
        check('all_frozen_components_and_files_accounted',audit['passed'] and len(audit['modules'])==129
              and q.info['counts']['tracked_files']==4855)
        check('previous_zero_base_fact_queue_empty',audit['summary']['owned_non_test_sources_without_base_facts']==0)
        check('all_representative_source_contracts_pass',contracts['summary']=={'passed':129}
              and contracts['checks']==450 and contracts['failed_checks']==0)
        counts={'cbm_nodes':scalar("SELECT count(*) FROM pm_fact_nodes WHERE snapshot=? AND id LIKE 'cbm:%'"),
            'clangd_nodes':scalar("SELECT count(*) FROM pm_fact_nodes WHERE snapshot=? AND id LIKE 'clangd:%'"),
            'original_clangd_edges':scalar("SELECT count(*) FROM pm_fact_edges WHERE snapshot=? AND kind LIKE 'CLANGD_%' AND kind<>'CLANGD_LEXICALLY_CONTAINS_REFERENCE'"),
            'native_lexical_reference_edges':scalar("SELECT count(*) FROM pm_fact_edges WHERE snapshot=? AND kind='CLANGD_LEXICALLY_CONTAINS_REFERENCE'"),
            'bash_command_sites':scalar("SELECT count(*) FROM pm_fact_nodes WHERE snapshot=? AND id LIKE 'bash:%' AND kind='call_site'")}
        check('native_provider_id_and_edge_counts_preserved',counts['cbm_nodes']==33031
              and counts['clangd_nodes']==262218 and counts['original_clangd_edges']==392970,counts)
        check('native_reference_owners_and_bash_sites_present',counts['native_lexical_reference_edges']>0
              and counts['bash_command_sites']==340)
        wrong=scalar('''SELECT count(*) FROM pm_fact_edges e
            JOIN pm_fact_nodes s ON s.snapshot=e.snapshot AND s.id=e.source
            JOIN pm_fact_nodes t ON t.snapshot=e.snapshot AND t.id=e.target
            WHERE e.snapshot=? AND e.kind='CLANGD_LEXICALLY_CONTAINS_REFERENCE' AND
                (s.path<>t.path OR s.kind<>'callable' OR t.kind<>'symbol_reference')''')
        check('native_lexical_links_keep_file_and_entity_kind',wrong==0,wrong)
        check('cbm_inferred_relations_retain_candidate_precision',scalar(
            "SELECT count(*) FROM pm_fact_edges WHERE snapshot=? AND kind LIKE 'CBM_%' AND status NOT IN ('candidate','source_relation')")==0)
        shell=q.search('build/mindstudio_insight_gui_set_environment.sh',kind='call_site',limit=30)
        check('command_only_source_is_queryable',[n['name'] for n in shell['items']]==
              ['npm','apt-get','apt-get','update-alternatives','apt-get','python3'])
        candidates=rows('''SELECT id,path,name FROM pm_fact_nodes
            WHERE snapshot=? AND kind='callable' AND id LIKE 'clangd:%' AND path LIKE '%.cpp'
            ORDER BY path,id LIMIT 512''',(active['snapshot'],)) if counts['native_lexical_reference_edges'] else []
        used=set()
        for source,path,caller in candidates:
            if path in used:continue
            body=q.neighbors(source,kinds=['CLANGD_LEXICALLY_CONTAINS_REFERENCE'],limit=13)
            if body['next_cursor'] or len(body['items'])>12:continue
            chosen=None
            for item in body['items']:
                targets=q.neighbors(item['node']['id'],kinds=['CLANGD_REFERS_TO_DECLARATION'],limit=3)
                for target in targets['items']:
                    if target['node']['kind']!='callable':continue
                    incoming=q.neighbors(target['node']['id'],direction='in',kinds=['CLANGD_REFERS_TO_DECLARATION'],limit=9)
                    if incoming['next_cursor'] or len(incoming['items'])>8:continue
                    chosen=target['node'];break
                if chosen:break
            if not chosen:continue
            results=[q.walk(start,target=end,direction=direction,depth=2,
                        kinds=['CLANGD_LEXICALLY_CONTAINS_REFERENCE','CLANGD_REFERS_TO_DECLARATION'])
                     for start,end,direction in [(source,chosen['id'],'out'),(chosen['id'],source,'in')]]
            witnesses.append({'path':path,'caller':caller,'target':chosen['name'],
                'forward':results[0]['found'],'reverse':results[1]['found'],
                'stop_reasons':[r['stop_reason'] for r in results]})
            used.add(path)
            if len(witnesses)==8:break
        check('native_callable_reference_target_bidirectional_queries',len(witnesses)==8
              and all(r['forward'] and r['reverse'] and r['stop_reasons']==[None,None] for r in witnesses),witnesses)
        check('original_checkout_unchanged_and_history_disabled',not trial['original_checkout_modified']
              and trial['historical_assets_enabled'] is False)
        result={'schema':'final-repository-integration-checks/1','source_commit':active['source_commit'],
            'snapshot':active['snapshot'],'build_version':active['build_version'],'counts':q.info['counts'],
            'checks':checks,'passed':all(c['passed'] for c in checks),
            'whole_G02_accepted':False,'runtime_execution':False,'historical_assets_enabled':False,
            'interpretation':'integration_and_representative_query_checks; semantic_gates_are_separate'}
    finally:q.close()
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'checks':len(checks),'passed':result['passed']}))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
