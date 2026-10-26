"""Check native callable-to-reference navigation using retained compiler captures."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.clangd_provider import diagnostic_precision
from adapters.project_map import ProjectMap,build_index


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--capture',action='append',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    reports=[]
    for ordinal,capture in enumerate(args.capture):
        facts=json.loads((capture/'facts.json').read_text(encoding='utf-8'))
        native_ids={n['id'] for n in facts['nodes']}
        native_edges=[dict(e) for e in facts['edges']]
        facts=diagnostic_precision(facts)
        nodes={n['id']:n for n in facts['nodes']}
        entry,=[n for n in facts['nodes'] if n['kind']=='callable' and n['name']=='main']
        paths=[r['path'] for r in facts['coverage']]
        graph={**facts,'snapshot':'native-range-probe-'+str(ordinal),
               'source_commit':facts['components']['source_commit'],'input_paths':paths}
        files=[{'path':p,'module':p.split('/')[0],'language':'cpp','status':'pending',
                'eligible':True,'bytes':(capture/'source'/p).stat().st_size} for p in paths]
        discovery={'source_commit':graph['source_commit'],'files':files,
                   'modules':[{'path':m} for m in sorted({r['module'] for r in files})]}
        index=args.output/(str(ordinal)+'.sqlite')
        build_index(graph,discovery,index)
        q=ProjectMap(index)
        checks=[]
        try:
            for name in ('action','identity'):
                targets={e['target'] for e in facts['edges'] if e['kind']=='CLANGD_REFERS_TO_DECLARATION'
                         and nodes[e['source']]['name']==name}
                assert len(targets)==1
                target=targets.pop()
                for direction,start,end in [('out',entry['id'],target),('in',target,entry['id'])]:
                    result=q.walk(start,target=end,direction=direction,depth=2,
                                  kinds=['CLANGD_LEXICALLY_CONTAINS_REFERENCE','CLANGD_REFERS_TO_DECLARATION'])
                    checks.append({'name':name,'direction':direction,'passed':result['found']
                        and result['stop_reason'] is None,'path_kinds':[e['kind'] for e in result['items']]})
        finally:q.close()
        derived=[e for e in facts['edges'] if e['kind']=='CLANGD_LEXICALLY_CONTAINS_REFERENCE']
        checks.append({'name':'native_ids_and_existing_edges_preserved','passed':
            native_ids==set(nodes) and all(e in facts['edges'] for e in native_edges)})
        checks.append({'name':'lexical_owners_have_the_same_source_path','passed':
            all(nodes[e['source']]['path']==nodes[e['target']]['path'] for e in derived)})
        reports.append({'context':facts['components']['context'],'components':facts['components'],
                        'derived_edges':len(derived),'checks':checks})
    report={'schema':'native-reference-owner-query-probe/1','origin':'retained_native_compiler_captures',
        'cases':reports,'passed':all(c['passed'] for r in reports for c in r['checks']),
        'new_native_compilation_executed':False,'runtime_execution':False,'whole_G02_accepted':False}
    # Public metadata omits local compile-database paths retained in raw captures.
    for row in report['cases']:
        row['components'].pop('compile_command_adjustment',None)
    (args.output/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'cases':len(reports),'checks':sum(len(r['checks']) for r in reports),'passed':report['passed']}))
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':main()
