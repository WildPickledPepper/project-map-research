"""Verify an existing native capture through the shared source/navigation API."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.native_provider_graph import read_capture
from adapters.project_map import Budget,ProjectMap,build_index
from adapters.repository_discovery import discover


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture',type=Path,required=True);p.add_argument('--repository',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((args.capture/'manifest.json').read_text(encoding='utf-8'))
    if len(manifest['captures'])!=1:raise ValueError('This verifier checks one native context at a time')
    capture={**manifest['captures'][0]};capture['directory']=str((args.capture/capture['directory']).resolve())
    discovery=discover(args.repository,manifest['source_commit'])
    paths=[r['path'] for r in discovery['files'] if r['eligible']]
    facts=read_capture(capture,paths=paths,source_commit=manifest['source_commit'])
    owned=sorted({n['path'] for n in facts['nodes'] if n['path']})
    snapshot='native-capture-query:'+manifest['source_commit']+':'+capture['context_key']
    graph={**facts,'source_commit':manifest['source_commit'],'snapshot':snapshot,'input_paths':owned}
    index=args.output/'navigation.sqlite';build_index(graph,discovery,index)
    nodes={n['id']:n for n in facts['nodes']};checks=[]
    q=ProjectMap(index,budget=Budget(5,200,500,131072),expected_snapshot=snapshot)
    try:
        for path in owned:
            for kind in ('SVF_VALUE_FLOW','SVF_POINTS_TO'):
                edge=next((e for e in facts['edges'] if e['kind']==kind and nodes[e['source']]['path']==path),None)
                if edge is None:
                    checks.append({'path':path,'kind':kind,'passed':False,'reason':'no_source_bound_native_edge'});continue
                source=q.source(args.repository,selector=edge['source'],context=0)
                forward=q.walk(edge['source'],target=edge['target'],depth=1,kinds=[kind])
                reverse=q.walk(edge['target'],target=edge['source'],depth=1,direction='in',kinds=[kind])
                checks.append({'path':path,'kind':kind,'source_id':edge['source'],'target_id':edge['target'],
                    'passed':bool(source['items']) and forward['found'] and reverse['found'] and
                        all(r.get('stop_reason') is None for r in (source,forward,reverse))})
        for key,bad in [('source_commit','0'*40),('context_key','wrong/configuration')]:
            rejected=False
            try:read_capture({**capture,key:bad},paths=paths,source_commit=manifest['source_commit'])
            except ValueError:rejected=True
            checks.append({'case':key+'_mismatch','passed':rejected})
    finally:q.close()
    result={'schema':'native-context-query-checks/1','source_commit':manifest['source_commit'],
            'context':capture['context_key'],'capture_only_index':True,'published_whole_map_updated':False,
            'counts':{'nodes':len(nodes),'edges':dict(Counter(e['kind'] for e in facts['edges']))},
            'source_paths':owned,'checks':checks,'passed':all(r['passed'] for r in checks),
            'whole_G02_accepted':False}
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
