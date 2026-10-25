"""Score the published Python navigation index against a separate source audit."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from projectmap.workspace import Workspace


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--trial',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    if args.output.exists():ap.error('Choose a new result path')
    reference=json.loads(Path(__file__).with_name('python-reference.json').read_text(encoding='utf-8'))
    native=json.loads(Path(__file__).with_name('evidence').joinpath('native-summary.json').read_text(encoding='utf-8'))
    trial=json.loads((args.trial/'trial.json').read_text(encoding='utf-8'));workspace=Workspace(args.trial/'workspace')
    active=workspace.config['active'];db=sqlite3.connect((workspace.directory/active['index']).as_uri()+'?mode=ro',uri=True)
    info=json.loads(db.execute('SELECT payload FROM pm_map_info').fetchone()[0]);snapshot=info['snapshot'];checks=[]
    if info['source_commit']!=reference['source_commit']:raise ValueError('Source/reference mismatch')
    def check(name,passed,**detail):checks.append({'id':name,'passed':bool(passed),**detail})
    def nodes(path,kind,name=None):
        sql='SELECT payload FROM pm_fact_nodes WHERE snapshot=? AND path=? AND kind=?';params=[snapshot,path,kind]
        if name is not None:sql+=' AND name=?';params.append(name)
        return [json.loads(r[0]) for r in db.execute(sql,params)]
    def edges(kind,source=None):
        sql='SELECT payload FROM pm_fact_edges WHERE snapshot=? AND kind=?';params=[snapshot,kind]
        if source is not None:sql+=' AND source=?';params.append(source)
        return [json.loads(r[0]) for r in db.execute(sql,params)]
    def unique(path,kind,name):
        found=nodes(path,kind,name)
        return found[0] if len(found)==1 else None
    expected={r['path'] for r in native['files'] if r['language']=='python'}
    if trial['scope']=='proxy':expected={p for p in expected if p.startswith('plugins/ProfilerServerProxy/')}
    files=[]
    for (payload,) in db.execute("SELECT payload FROM pm_map_files WHERE json_extract(payload,'$.language')='python' ORDER BY path"):
        row=json.loads(payload)
        if not row.get('graph_input'):continue
        files.append({k:row[k] for k in ('path','graph_input','graph_coverage')})
        check('file.'+row['path'],row['graph_coverage']['status']=='parsed' and len(nodes(row['path'],'code_module'))==1)
    check('expected_python_file_scope',{r['path'] for r in files}==expected,count=len(files))
    for index,spec in enumerate(reference['required_calls']):
        target=unique(spec['target_path'],'callable',spec['target_name'])
        found=[e for call in nodes(spec['path'],'call_site',spec['callee']) for e in edges('STATIC_CALL_TARGET',call['id']) if target and e['target']==target['id']]
        check('call.'+str(index),bool(found),evidence=found)
    boundaries={}
    for spec in reference['boundaries']:
        found=[n for n in nodes(spec['path'],'python_boundary',spec['name']) if n['family']==spec['family']]
        boundaries[spec['family']]=found[0] if len(found)==1 else None
        check('boundary.'+spec['family'],len(found)==1,evidence=found)
    listener=boundaries['network_listener'];route=boundaries['route_registration'];client=boundaries['network_client'];process=boundaries['process_start']
    joined=edges('EXPOSES_ROUTE',listener['id']) if listener else []
    check('same_application_listener_route',route and any(e['target']==route['id'] and e.get('application_sources') for e in joined),evidence=joined)
    handler=unique(reference['path_target']['path'],'callable',reference['handler'])
    dispatch=edges('CAN_DISPATCH_TO',route['id']) if route else []
    check('registered_request_handler',handler and any(e['target']==handler['id'] for e in dispatch),evidence=dispatch)
    releases=[e for e in edges('USES_PROCESS_HANDLE') if process and e['target']==process['id']]
    check('owned_process_teardown',len(releases)==4 and all(e['status']=='candidate' for e in releases),evidence=releases)
    if client:
        parameters=[e['target'] for value in client.get('address_values',[]) for e in edges('READS_BINDING',value)]
        supplied=[e for e in edges('BINDS_ARGUMENT') if e['target'] in parameters]
        values=[]
        for edge in supplied:
            row=db.execute('SELECT payload FROM pm_fact_nodes WHERE snapshot=? AND id=?',(snapshot,edge['source'])).fetchone()
            if row:values.append(json.loads(row[0]))
        check('selected_backend_address_origin',any(v.get('expression_kind')=='JoinedStr' and 'selected_server.host' in v['name'] and 'selected_server.port' in v['name'] for v in values),evidence=values)
    start=unique(reference['path_start']['path'],'callable',reference['path_start']['name'])
    for direction in ('out','in'):
        result=workspace.query('path',start=(start if direction=='out' else client)['id'],
            target=(client if direction=='out' else start)['id'],direction=direction,kinds=reference['path_kinds'],
            depth=16,nodes=1000,edges=3000,seconds=10) if start and client else {}
        check('navigation.'+direction,result.get('found') and result.get('stop_reason') is None,
              evidence={k:result[k] for k in ('found','direction','items','visited_nodes','examined_edges','stop_reason') if k in result})
    if start:
        source=workspace.query('source',start=start['id'])
        check('same_version_source_navigation',source.get('source_commit')==reference['source_commit'] and source.get('path')==start['path'])
    counts=dict(db.execute("SELECT kind,count(*) FROM pm_fact_nodes WHERE snapshot=? AND json_extract(payload,'$.language')='python' GROUP BY kind",(snapshot,)))
    calls=Counter();unknown=Counter();apis=Counter()
    for (payload,) in db.execute("SELECT payload FROM pm_fact_nodes WHERE snapshot=? AND kind='call_site' AND json_extract(payload,'$.language')='python'",(snapshot,)):
        node=json.loads(payload);calls[node['resolution']]+=1
        if node['resolution']=='unresolved':unknown[node.get('reason','missing_reason')]+=1
    for (payload,) in db.execute("SELECT payload FROM pm_fact_nodes WHERE snapshot=? AND kind='python_boundary'",(snapshot,)):
        apis[json.loads(payload)['family']]+=1
    check('unresolved_calls_have_reasons','missing_reason' not in unknown)
    db.close()
    result={'schema':'python-production-trial-score/1','source_commit':info['source_commit'],'snapshot':snapshot,
        'build_version':info['graph_version']['build_version'],'scope':trial['scope'],'index_counts':info['counts'],
        'files':files,'python_node_counts':counts,'call_resolutions':dict(calls),'unresolved_call_reasons':dict(unknown),
        'boundary_families':dict(apis),'checks':checks,'passed':all(c['passed'] for c in checks),
        'runtime_execution':False,'whole_G02_accepted':False,'backend_counterpart_status':'pending_artifact_and_instance_identity'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'checks':len(checks),'passed':result['passed'],'failed':[c['id'] for c in checks if not c['passed']],
                      'call_resolutions':dict(calls),'boundaries':dict(apis)}))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
