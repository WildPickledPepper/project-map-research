"""Score the unchanged Rust value expectations against native SVF through queries."""
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
    facts=normalize(raw,provider='svf',paths=paths,source_commit=raw['source_commit'],context=raw['context'])
    graph={**facts,'source_commit':raw['source_commit'],'snapshot':'rust-svf-admission-'+raw['source_commit'],'input_paths':paths}
    discovery={'source_commit':raw['source_commit'],'files':[{'path':paths[0],'module':'fixture','language':'rust',
        'eligible':True,'status':'pending','bytes':(ROOT/'experiments/2026-10-26-r0-r1/rust-dataflow.rs').stat().st_size}],
        'modules':[{'path':'fixture'}]}
    build_index(graph,discovery,args.output/'navigation.sqlite')
    prefix='svf:'+quote(raw['context'],safe='')+':'+quote(raw['module'],safe='')+':flow:'
    checks=[];names=raw['function_display_names']
    q=ProjectMap(args.output/'navigation.sqlite',budget=Budget(10,2000,5000,1048576))
    try:
        for name,expected in [('regular',True),('member',True),('isolated',False),('after_copy',False),('borrowed',True),('through_ignored',False)]:
            functions={m for m,n in names.items() if n=='neutral_flow::'+name}
            starts=[n for n in raw['nodes'] if n['function'] in functions and n['kind']=='FormalParmVFGNode']
            ends=[n for n in raw['nodes'] if n['function'] in functions and n['kind']=='FormalRetVFGNode']
            walks=[q.walk(prefix+str(s['id']),target=prefix+str(t['id']),depth=60,kinds=['SVF_VALUE_FLOW'])
                   for s in starts for t in ends]
            found=any(r['found'] for r in walks)
            checks.append({'case':name,'expected_input_dependency':expected,'native_functions':len(functions),
                'native_source_nodes':len(starts),'native_return_nodes':len(ends),'query_found':found,
                'stop_reasons':[r['stop_reason'] for r in walks],
                'passed':len(functions)==len(starts)==len(ends)==1 and found==expected
                    and all(r['stop_reason'] is None for r in walks)})
    finally:q.close()
    report={'schema':'rust-svf-independent-admission/1','source_generator_commit':raw['source_commit'],
        'input_kind':'authored_fixture_copied_by_pinned_workflow','input_reference':'rust-dataflow.rs',
        'provider':facts['components'],'checks':checks,'passed':all(r['passed'] for r in checks),
        'whole_R0_R1_accepted':False,'runtime_execution':'independent_fixture_tests_only'}
    (args.output/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(checks))
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':main()
