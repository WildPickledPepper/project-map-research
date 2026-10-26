"""Verify native captures' public navigation and pinned-source locations per file.

This is an interchange/query check, not an independent dataflow recall oracle.
The fixed semantic admission cases are scored separately.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.native_provider_graph import read_capture
from adapters.project_map import Budget,ProjectMap,build_index
from adapters.repository_discovery import discover
from adapters.snapshot_inputs import git


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('manifest','repository','output'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    manifest=json.loads(args.manifest.read_text());revision=manifest['source_commit']
    discovery=discover(args.repository,revision);paths=[r['path'] for r in discovery['files'] if r['eligible']]
    graph={k:[] for k in ('nodes','edges','coverage','diagnostics','limits')}
    graph.update(source_commit=revision,snapshot='native-query-'+revision,input_paths=paths)
    for capture in manifest['captures']:
        facts=read_capture({**capture,'directory':str((args.manifest.parent/capture['directory']).resolve())},
                           paths=paths,source_commit=revision)
        for key in ('nodes','edges','coverage','diagnostics','limits'):graph[key].extend(facts[key])
    callable_paths={n['path'] for n in graph['nodes'] if n['kind']=='callable' and n['path'] and n['line']>0}
    # Freeze source content before opening the navigation index.
    source={path:git(args.repository,'show',revision+':'+path).decode('utf-8',errors='replace').splitlines()
            for path in sorted(callable_paths)}
    build_index(graph,discovery,args.output/'navigation.sqlite')
    q=ProjectMap(args.output/'navigation.sqlite',budget=Budget(15,2000,5000,1048576))
    groups={}
    for n in graph['nodes']:
        if n['kind']=='callable' and n['path'] and n['line']>0:
            key=n['provenance']['provider'],n['provenance']['context'],n['path']
            groups.setdefault(key,[]).append(n)
    checks=[]
    try:
        for (provider,context,path),functions in sorted(groups.items()):
            n=min(functions,key=lambda n:(n['line'],n['id']))
            page=q.search(path,kind='callable',limit=200);visible={r['id'] for r in page['items']}
            while page.get('next_cursor') and n['id'] not in visible:
                page=q.search(path,kind='callable',limit=200,cursor=page['next_cursor'])
                visible.update(r['id'] for r in page['items'])
            proof=q.source(args.repository,selector=n['id'],context=0)
            kinds=['SVF_CONTAINS_VALUE'] if provider=='svf' else ['RAPX_CONTAINS_LOCAL']
            adjacent=q.neighbors(n['id'],kinds=kinds,limit=1)
            child=adjacent['items'][0]['node'] if adjacent['items'] else None
            reverse=q.neighbors(child['id'],direction='in',kinds=kinds,limit=2) if child else {'items':[]}
            expected=source[path][n['line']-1] if n['line']<=len(source[path]) else None
            actual=proof['items'][0]['text'] if proof['items'] else None
            checks.append({'provider':provider,'context':context,'path':path,'source_line':n['line'],
                'native_function':n['name'],'query_node':n['id'],'source_matches':actual==expected and expected is not None,
                'passed':n['id'] in visible and actual==expected and expected is not None
                    and any(r['node']['id']==n['id'] for r in reverse['items']),
                'source_commit':proof['source_commit'],'scope':'native_interchange_and_public_queries'})
    finally:q.close()
    result={'schema':'native-value-flow-query-checks/1','source_commit':revision,'checks':checks,
        'passed':bool(checks) and all(r['passed'] for r in checks),'checks_count':len(checks),
        'contexts':dict(Counter(r['context'] for r in checks)),
        'whole_G02_accepted':False,'historical_assets_enabled':False}
    (args.output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'checks':len(checks),'passed':result['passed'],'failures':[r for r in checks if not r['passed']]}))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
