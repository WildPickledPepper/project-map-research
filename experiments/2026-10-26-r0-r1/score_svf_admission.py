"""Score the frozen six C++ dependency cases through the existing query API."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.native_value_flow import normalize,location
from adapters.project_map import Budget,ProjectMap,build_index


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--native',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    raw=json.loads(args.native.read_text());path='experiments/2026-10-26-reuse-audit/joern-probe.cpp'
    facts=normalize(raw,provider='svf',paths=[path],source_commit=raw['source_commit'],context=raw['context'])
    graph={**facts,'source_commit':raw['source_commit'],'snapshot':'svf-admission-'+raw['source_commit'],'input_paths':[path]}
    discovery={'source_commit':raw['source_commit'],'files':[{'path':path,'module':'fixture','language':'cpp',
        'eligible':True,'status':'pending','bytes':(ROOT/path).stat().st_size}],'modules':[{'path':'fixture'}]}
    build_index(graph,discovery,args.output/'navigation.sqlite')
    prefix='svf:'+__import__('urllib.parse',fromlist=['quote']).quote(raw['context'],safe='')+':'+raw['module']+':flow:'
    lines=(ROOT/path).read_text().splitlines();checks=[]
    q=ProjectMap(args.output/'navigation.sqlite',budget=Budget(10,2000,5000,1048576))
    try:
        for case,expected in [('regular',True),('member',True),('isolated',False),('after_copy',False),('borrowed',True),('getter',True)]:
            function='_Z'+str(len(case))+case+'i'
            line_no,line=next((i+1,s) for i,s in enumerate(lines) if s.startswith('void '+case+'('))
            column=line.index('sink(')+1
            starts=[n for n in raw['nodes'] if n['function']==function and n['kind']=='FormalParmVFGNode']
            ends=[n for n in raw['nodes'] if n['function']==function and n['kind']=='ActualParmVFGNode'
                  and location(n.get('source_location'),raw['source_root'],{path})=={'path':path,'line':line_no,'column':column}]
            found=False;reasons=[]
            for source in starts:
                for target in ends:
                    result=q.walk(prefix+str(source['id']),target=prefix+str(target['id']),depth=60,kinds=['SVF_VALUE_FLOW'])
                    found=found or result['found'];reasons.append(result['stop_reason'])
            checks.append({'case':case,'expected_input_dependency':expected,'native_source_nodes':len(starts),
                'native_sink_nodes':len(ends),'query_found':found,'stop_reasons':reasons,
                'passed':len(starts)==1 and len(ends)==1 and found==expected and all(r is None for r in reasons)})
    finally:q.close()
    report={'schema':'svf-frozen-admission/1','source_commit':raw['source_commit'],'provider':facts['components'],
            'checks':checks,'passed':all(r['passed'] for r in checks),'whole_R0_R1_accepted':False}
    (args.output/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(checks))
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':main()
