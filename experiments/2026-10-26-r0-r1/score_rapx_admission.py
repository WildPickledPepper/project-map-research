"""Check independent Rust values, borrowing and ignored arguments via native facts."""
import argparse
import json
from pathlib import Path
import sys
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.native_value_flow import normalize
from adapters.project_map import Budget,ProjectMap,build_index


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--native',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    raw=json.loads(args.native.read_text());paths=['src/lib.rs']
    facts=normalize(raw,provider='rapx',paths=paths,source_commit=raw['source_commit'],context=raw['context'])
    graph={**facts,'source_commit':raw['source_commit'],'snapshot':'rapx-admission-'+raw['source_commit'],'input_paths':paths}
    discovery={'source_commit':raw['source_commit'],'files':[{'path':paths[0],'module':'fixture','language':'rust',
        'eligible':True,'status':'pending','bytes':(ROOT/'experiments/2026-10-26-r0-r1/rust-dataflow.rs').stat().st_size}],
        'modules':[{'path':'fixture'}]}
    build_index(graph,discovery,args.output/'navigation.sqlite')
    prefix='rapx:'+quote(raw['context'],safe='')+':'+quote(raw['crate'],safe='')+':function:'
    checks=[];functions={f['name']:f for f in raw['functions']}
    q=ProjectMap(args.output/'navigation.sqlite',budget=Budget(10,2000,5000,1048576))
    try:
        for name,expected in [('regular',True),('member',True),('isolated',False),('after_copy',False),('borrowed',True),('through_ignored',False)]:
            key=next(k for k in functions if k==name or k.endswith('::'+name))
            uid=prefix+quote(key,safe='')
            result=q.walk(uid+':local:1',target=uid+':local:0',depth=60,
                          kinds=['RAPX_VALUE_FLOW','RAPX_ACTUAL_TO_FORMAL','RAPX_RETURN_TO_CALLER'])
            checks.append({'case':name,'expected_input_dependency':expected,'query_found':result['found'],
                           'stop_reason':result['stop_reason'],'passed':result['found']==expected and result['stop_reason'] is None})
        for name in ('borrow_field','borrow_identity'):
            function=next(v for k,v in functions.items() if k==name or k.endswith('::'+name))
            summaries=[r for r in function['alias_summary'] if {r['left'],r['right']}=={0,1}]
            checks.append({'case':name,'native_argument_return_aliases':summaries,'passed':bool(summaries)})
    finally:q.close()
    report={'schema':'rapx-independent-admission/1','source_generator_commit':raw['source_commit'],
        'input_kind':'authored_fixture_copied_by_pinned_workflow','input_reference':'rust-dataflow.rs',
        'provider':facts['components'],'checks':checks,'passed':all(r['passed'] for r in checks),
        'whole_R0_R1_accepted':False,'runtime_execution':'independent_fixture_tests_only'}
    (args.output/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(checks))
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':main()
