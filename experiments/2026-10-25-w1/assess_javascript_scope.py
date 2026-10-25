"""Assess all JavaScript inputs through the published navigation index, without loading the full graph."""
from collections import Counter
import argparse
import json
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from projectmap.workspace import Workspace


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trial',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Choose a new result path')
    w=Workspace(args.trial/'workspace');active=w.config['active'];checks=[];files=[]
    db=sqlite3.connect(w.directory/active['index'])
    info=json.loads(db.execute('SELECT payload FROM pm_map_info').fetchone()[0]);snapshot=info['snapshot']
    def check(name,passed):checks.append({'id':name,'passed':bool(passed)})
    for (payload,) in db.execute("SELECT payload FROM pm_map_files WHERE json_extract(payload,'$.language')='javascript' ORDER BY path"):
        row=json.loads(payload)
        if not row['eligible']:continue
        kinds=dict(db.execute('SELECT kind,count(*) FROM pm_fact_nodes WHERE snapshot=? AND path=? GROUP BY kind',(snapshot,row['path'])))
        files.append({'path':row['path'],'source_role':row['role'],'graph_input':row['graph_input'],
                      'coverage':row['graph_coverage'],'node_counts':kinds})
        check('source_coverage.'+row['path'],row['graph_input'] and row['graph_coverage']['status']=='parsed' and kinds.get('code_module')==1)
    resolutions=Counter();call_reasons=Counter();module_reasons=Counter();unresolved_modules=[]
    for (payload,) in db.execute("SELECT payload FROM pm_fact_nodes WHERE snapshot=? AND kind='call_site' AND json_extract(payload,'$.language')='javascript'",(snapshot,)):
        row=json.loads(payload);resolutions[row['resolution']]+=1
        if row['resolution']=='unresolved':call_reasons[row.get('reason','missing_reason')]+=1
        check('unresolved_call_reason.'+row['id'],row['resolution']!='unresolved' or bool(row.get('reason')))
    for (payload,) in db.execute("SELECT payload FROM pm_fact_nodes WHERE snapshot=? AND kind='module_reference' AND json_extract(payload,'$.language')='javascript'",(snapshot,)):
        row=json.loads(payload);module_reasons[row.get('reason',row['resolution'])]+=1
        if row['resolution']=='unresolved':
            unresolved_modules.append({k:row[k] for k in ('path','line','name','reason') if k in row})
        check('unresolved_import_reason.'+row['id'],row['resolution']!='unresolved' or bool(row.get('reason')))
    edges={}
    for kind in ('STATIC_CALL_TARGET','STATIC_CALL_CANDIDATE','IMPORTS_MODULE'):
        edges[kind]=db.execute('''SELECT count(*) FROM pm_fact_edges e JOIN pm_fact_nodes s ON s.snapshot=e.snapshot AND s.id=e.source
          JOIN pm_fact_nodes t ON t.snapshot=e.snapshot AND t.id=e.target
          WHERE e.snapshot=? AND e.kind=? AND s.path<>t.path
          AND (json_extract(s.payload,'$.language')='javascript' OR json_extract(t.payload,'$.language')='javascript')''',(snapshot,kind)).fetchone()[0]
    check('all_53_committed_javascript_inputs',len(files)==53)
    check('same_published_snapshot',snapshot==active['snapshot'] and info['source_commit']==active['source_commit'])
    check('cross_file_javascript_calls_present',edges['STATIC_CALL_TARGET']>0)
    result={'schema':'javascript-repository-scope/1','source_commit':info['source_commit'],'snapshot':snapshot,
        'build_version':info['graph_version']['build_version'],'index_counts':info['counts'],'files':files,
        'call_resolutions':dict(resolutions),'unresolved_call_reasons':dict(call_reasons),
        'module_resolution_states':dict(module_reasons),'unresolved_modules':unresolved_modules,'cross_file_edges':edges,
        'checks':{'total':len(checks),'passed':sum(c['passed'] for c in checks),'failed':[c for c in checks if not c['passed']]},
        'passed':all(c['passed'] for c in checks),'whole_G02_accepted':False,'runtime_execution':False}
    db.close();args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('index_counts','call_resolutions','module_resolution_states','cross_file_edges','checks','passed')},ensure_ascii=False))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
