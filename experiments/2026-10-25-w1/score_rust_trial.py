"""Check normalized Rust production navigation against independent source references."""
import argparse
from collections import Counter,defaultdict,deque
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
    if args.output.exists():ap.error('Choose a new score output')
    base=Path(__file__).resolve().parent
    reference=json.loads((base/'rust-reference.json').read_text(encoding='utf-8'))
    native=json.loads((base/'evidence/native-summary.json').read_text(encoding='utf-8'))
    workspace=Workspace(args.trial/'workspace');active=workspace.config['active']
    db=sqlite3.connect((workspace.directory/active['index']).as_uri()+'?mode=ro',uri=True)
    info=json.loads(db.execute('SELECT payload FROM pm_map_info').fetchone()[0]);snapshot=info['snapshot']
    nodes={n['id']:n for row in db.execute("SELECT payload FROM pm_fact_nodes WHERE snapshot=? AND json_extract(payload,'$.language')='rust'",(snapshot,)) if (n:=json.loads(row[0]))}
    edges=[json.loads(row[0]) for row in db.execute("SELECT payload FROM pm_fact_edges WHERE snapshot=? AND source LIKE 'rust:%'",(snapshot,))]
    out=defaultdict(list)
    for edge in edges:out[edge['source']].append(edge)
    checks=[]
    def check(name,passed,**detail):checks.append({'id':name,'passed':bool(passed),**detail})
    def find(kind,path,**fields):return [n for n in nodes.values() if n['kind']==kind and n['path']==path and all(n.get(k)==v for k,v in fields.items())]
    check('source_version',info['source_commit']==reference['source_commit']==native['source_commit'])
    expected={r['path'] for r in native['files'] if r['language']=='rust'};files=[]
    for (payload,) in db.execute("SELECT payload FROM pm_map_files WHERE json_extract(payload,'$.language')='rust' ORDER BY path"):
        row=json.loads(payload)
        if not row.get('graph_input'):continue
        files.append({k:row[k] for k in ('path','graph_input','graph_coverage')})
        check('file.'+row['path'],row['graph_coverage']['status']=='parsed' and len(find('code_module',row['path']))==1)
    check('rust_file_scope',{f['path'] for f in files}==expected)
    starts=find('callable',reference['start']['path'],name=reference['start']['name']);start=starts[0] if len(starts)==1 else None
    selected={}
    for spec in reference['boundaries']:
        found=find('rust_boundary',spec['path'],**{k:v for k,v in spec.items() if k not in {'id','path'}})
        selected[spec['id']]=found[0] if len(found)==1 else None
        check('boundary.'+spec['id'],len(found)==1,evidence=found)
    def witness(target,context):
        if not start or not target:return None
        pending=deque([(start['id'],[])]);seen={start['id']}
        while pending:
            here,path=pending.popleft()
            if here==target:return path
            for edge in out[here]:
                if edge['kind'] not in reference['path_kinds'] or edge.get('analysis_contexts') and context not in edge['analysis_contexts']:continue
                if edge['target'] not in seen:seen.add(edge['target']);pending.append((edge['target'],path+[edge]))
        return None
    for spec in reference['views']:
        matches=[n for n in nodes.values() if n['kind']=='analysis_context' and n['workspace']==spec['workspace'] and
            not n['debug_assertions'] and reference['default_feature'] in n['features'] and 'target_os='+json.dumps(spec['os']) in n['cfg']]
        context=matches[0]['id'] if len(matches)==1 else None;view=selected[spec['id']];resource=selected[spec['resource']]
        check('context.'+spec['id'],context is not None)
        for target_name in ('backend',spec['id']):
            target=selected[target_name];path=witness(target['id'],context) if target and context else None
            check('context_path.'+spec['id']+'.'+target_name,path is not None,context=context,evidence=path)
        if view and resource:
            check('same_builder.'+spec['id'],bool(set(view.get('builder_candidates',[]))&set(resource.get('builder_candidates',[]))))
            callbacks=[e for e in out[resource['id']] if e['kind']=='CAN_DISPATCH_TO' and context in e['analysis_contexts']]
            check('resource_callback.'+spec['id'],bool(callbacks),evidence=callbacks)
    if start:
        for name in ('backend','windows_view','linux_view'):
            target=selected[name]
            for direction in ('out','in'):
                result=workspace.query('path',start=(start if direction=='out' else target)['id'],target=(target if direction=='out' else start)['id'],
                    direction=direction,kinds=reference['path_kinds'],depth=16,nodes=1500,edges=5000,seconds=10) if target else {}
                common=None
                for item in result.get('items',[]):
                    (payload,)=db.execute('SELECT payload FROM pm_fact_edges WHERE snapshot=? AND ordinal=?',(snapshot,item['ordinal'])).fetchone()
                    edge=json.loads(payload)
                    if edge.get('analysis_contexts'):common=set(edge['analysis_contexts']) if common is None else common&set(edge['analysis_contexts'])
                check('navigation.'+name+'.'+direction,result.get('found') and result.get('stop_reason') is None and bool(common),
                    evidence={k:result[k] for k in ('found','items','stop_reason','direction') if k in result},common_context_count=len(common or ()))
        source=workspace.query('source',start=start['id']);check('same_version_source',source.get('source_commit')==reference['source_commit'])
    backend=selected['backend']
    command=[e for e in out[backend['id']] if e['kind']=='USES_COMMAND'] if backend else []
    check('backend_command_has_program_source',bool(command) and any(e['kind']=='COMMAND_PROGRAM' for row in command for e in out[row['target']]))
    options=[e for e in out[backend['id']] if e['kind']=='COMMAND_OPTION_SOURCE'] if backend else []
    check('backend_options_include_port_and_policy',any('--wsPort=' in nodes[e['target']].get('expression','') for e in options) and
        any('--notStrict' in nodes[e['target']].get('expression','') for e in options))
    captures=[n for n in nodes.values() if n.get('syntax')=='format_capture' and n['path']=='platform/src/default.rs' and n['name']=='port']
    check('backend_format_capture_binds_parameter',any(nodes[e['target']]['kind']=='parameter' for n in captures for e in out[n['id']] if e['kind']=='READS_BINDING'))
    calls=[n for n in nodes.values() if n['kind']=='call_site']
    check('unresolved_calls_are_explicit',all(n.get('reason') for n in calls if n.get('resolution')=='unresolved'))
    db.close()
    result={'schema':'rust-production-trial-score/1','source_commit':info['source_commit'],'snapshot':snapshot,
        'build_version':info['graph_version']['build_version'],'index_counts':info['counts'],'files':files,
        'rust_node_counts':dict(Counter(n['kind'] for n in nodes.values())),
        'call_resolutions':dict(Counter(n.get('resolution') for n in calls)),
        'boundary_families':dict(Counter(n['family'] for n in nodes.values() if n['kind']=='rust_boundary')),
        'checks':checks,'passed':all(c['passed'] for c in checks),'runtime_execution':False,'whole_G02_accepted':False,
        'backend_counterpart_status':'pending_executable_artifact_and_deployment_instance_identity'}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks':len(checks),'passed':result['passed'],'failed':[c['id'] for c in checks if not c['passed']]}))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
