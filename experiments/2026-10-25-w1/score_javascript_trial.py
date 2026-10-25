"""Score a previously generated JS/TS graph and query its production navigation index."""
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
    if args.output.exists():parser.error('Choose a new scoring output file')
    reference=json.loads(Path(__file__).with_name('javascript-reference.json').read_text(encoding='utf-8'))
    w=Workspace(args.trial/'workspace');active=w.config['active']
    db=sqlite3.connect((w.directory/active['index']).as_uri()+'?mode=ro',uri=True)
    info=json.loads(db.execute('SELECT payload FROM pm_map_info').fetchone()[0]);snapshot=info['snapshot']
    if info['source_commit']!=reference['source_commit']:raise ValueError('Reference/source version mismatch')
    def nodes_at(kind,path=None,name=None):
        sql='SELECT payload FROM pm_fact_nodes WHERE snapshot=? AND kind=?';params=[snapshot,kind]
        for column,value in [('path',path),('name',name)]:
            if value is not None:sql+=' AND '+column+'=?';params.append(value)
        return [json.loads(row[0]) for row in db.execute(sql,params)]
    def edges_from(kind,source):
        return [json.loads(row[0]) for row in db.execute(
            'SELECT payload FROM pm_fact_edges WHERE snapshot=? AND kind=? AND source=? ORDER BY ordinal',
            (snapshot,kind,source))]
    def target(edge):
        row=db.execute('SELECT payload FROM pm_fact_nodes WHERE snapshot=? AND id=?',(snapshot,edge['target'])).fetchone()
        return json.loads(row[0])
    checks=[]
    def check(name,passed,**detail):checks.append({'id':name,'passed':bool(passed),**detail})
    for spec in reference['required_calls']:
        found=[]
        for call in nodes_at('call_site',spec['caller_path'],spec['callee']):
            for edge in edges_from('STATIC_CALL_TARGET',call['id']):
                declaration=target(edge)
                if declaration['path']==spec['target_path'] and (not spec.get('target_name') or declaration['name']==spec['target_name']):found.append(edge)
        check(spec['id'],found,edges=found)
    for index,pair in enumerate(reference['required_imports']):
        found=db.execute('''SELECT 1 FROM pm_fact_edges e
            JOIN pm_fact_nodes s ON s.snapshot=e.snapshot AND s.id=e.source
            JOIN pm_fact_nodes t ON t.snapshot=e.snapshot AND t.id=e.target
            WHERE e.snapshot=? AND e.kind='IMPORTS_MODULE' AND s.path=? AND t.path=? LIMIT 1''',
            (snapshot,*pair)).fetchone()
        check('import.'+str(index),found is not None)
    spec=reference['dynamic_method'];calls=nodes_at('call_site',spec['path'],spec['callee'])
    certain=[e for c in calls for e in edges_from('STATIC_CALL_TARGET',c['id'])]
    candidates=[target(e)['name'] for c in calls for e in edges_from('STATIC_CALL_CANDIDATE',c['id'])]
    check('dynamic_selection_retained',calls and not certain and set(candidates)==set(spec['target_names']),candidates=candidates)
    spec=reference['required_path'];start=nodes_at('callable',name=spec['start_name'])
    end=nodes_at('callable',name=spec['target_name'])
    path=w.query('path',start=start[0]['id'],target=end[0]['id'],depth=spec['max_depth'],nodes=1000,edges=3000,seconds=10) if len(start)==len(end)==1 else {}
    check('navigation_forward_path',path.get('found'),result=path)
    reverse=w.query('path',start=end[0]['id'],target=start[0]['id'],direction='in',depth=spec['max_depth'],nodes=1000,edges=3000,seconds=10) if len(start)==len(end)==1 else {}
    check('navigation_reverse_path',reverse.get('found'),result=reverse)
    if end:
        source=w.query('source',start=end[0]['id'])
        check('javascript_source_navigation',source.get('source_commit')==reference['source_commit'] and source.get('path')==end[0]['path'])
    files=[json.loads(row[0]) for row in db.execute("SELECT payload FROM pm_map_files WHERE json_extract(payload,'$.graph_input')=1 ORDER BY path")]
    result={'schema':'javascript-trial-score/1','source_commit':info['source_commit'],'build_version':info['graph_version']['build_version'],
        'snapshot':snapshot,'checks':checks,'passed':all(c['passed'] for c in checks),
        'coverage':[row['graph_coverage'] for row in files],'input_paths':[row['path'] for row in files],
        'runtime_execution':False,'whole_G02_accepted':False,'scoring_source':'published_navigation_index_read_only'}
    db.close()
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'checks':len(checks),'passed':result['passed'],'failed':[c for c in checks if not c['passed']]},ensure_ascii=False))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
