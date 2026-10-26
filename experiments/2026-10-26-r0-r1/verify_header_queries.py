"""Check every recovered header through the public index and committed source API."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.project_map import Budget,ProjectMap,build_index
from adapters.repository_discovery import discover
from adapters.native_provider_graph import read_capture,merge


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('capture','repository','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--workspace',type=Path)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    receipt=json.loads((args.capture/'result.json').read_text())
    discovery=discover(args.repository,receipt['source_commit'])
    paths=[r['path'] for r in discovery['files'] if r['eligible'] and r['language']=='cpp']
    facts=read_capture({'provider':'libclang','directory':str(args.capture.resolve()),
        'source_commit':receipt['source_commit'],'context_key':receipt['context']},
        paths=paths,source_commit=receipt['source_commit'])
    graph={'nodes':[],'edges':[],'coverage':[],'limits':[],'diagnostics':[],
           'snapshot':'header-query-'+receipt['source_commit'],'source_commit':receipt['source_commit'],'input_paths':paths}
    merge(graph,facts,provider='libclang',context=receipt['context'])
    index=args.output/'navigation.sqlite';snapshot=None
    if args.workspace:
        from projectmap.workspace import Workspace
        workspace=Workspace(args.workspace);active=workspace.config['active']
        if active['source_commit']!=receipt['source_commit']:raise ValueError('Published source differs from header capture')
        index=workspace.directory/active['index'];snapshot=active['snapshot']
    else:build_index(graph,discovery,index)
    nodes={n['id']:n for n in facts['nodes']};out=defaultdict(list)
    for e in facts['edges']:out[e['source']].append(e)
    counts=Counter(n['path'] for n in facts['nodes']);checks=[]
    q=ProjectMap(index,budget=Budget(15,1000,2000,1048576),expected_snapshot=snapshot)
    try:
        for row in facts['coverage']:
            path=row['path']
            candidates=[n for n in facts['nodes'] if n['path']==path and n['kind'] in {'symbol_reference','call_site'}]
            reference=next((n for n in candidates if any(e['kind']=='CLANG_TU_REFERS_TO_DECLARATION' for e in out[n['id']])),None)
            if reference is None:
                checks.append({'path':path,'passed':False,'reason':'no_internal_native_reference'});continue
            edge=next(e for e in out[reference['id']] if e['kind']=='CLANG_TU_REFERS_TO_DECLARATION')
            target=nodes[edge['target']]
            source=q.source(args.repository,selector=reference['id'],context=0)
            forward=q.walk(reference['id'],target=target['id'],depth=1,kinds=['CLANG_TU_REFERS_TO_DECLARATION'])
            reverse=q.walk(target['id'],target=reference['id'],direction='in',depth=1,kinds=['CLANG_TU_REFERS_TO_DECLARATION'])
            search=q.search(path,limit=3)
            passed=row['status']=='parsed' and counts[path]>0 and bool(source['items']) and bool(search['items'])
            passed=passed and forward['found'] and reverse['found'] and source.get('stop_reason') is None
            checks.append({'path':path,'native_nodes':counts[path],'native_references':len(candidates),
                'reference':{'name':reference['name'],'line':reference['line'],'column':reference['column']},
                'target':{'name':target['name'],'path':target['path'],'line':target['line'],'native_usr':target['native_usr']},
                'source':source['items'],'forward':forward['found'],'reverse':reverse['found'],'passed':bool(passed)})
    finally:q.close()
    report={'schema':'header-public-query-review/1','source_commit':receipt['source_commit'],
        'provider':facts['components'],'headers':len(checks),'checks':checks,'passed':all(r['passed'] for r in checks),
        'scope':'published_unified_snapshot' if args.workspace else 'recovered_header_capture_and_public_index',
        'snapshot':snapshot,
        'whole_G02_accepted':False,'runtime_execution':False,'historical_assets_enabled':False}
    (args.output/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'headers':len(checks),'failed':sum(not r['passed'] for r in checks)}))
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':main()
