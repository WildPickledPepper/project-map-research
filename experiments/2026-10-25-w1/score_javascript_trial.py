"""Score a previously generated JS/TS graph and query its production navigation index."""
import argparse
import json
from pathlib import Path
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
    w=Workspace(args.trial/'workspace');graph=json.loads(Path(w.config['active']['graph']).read_text(encoding='utf-8'))
    if graph['source_commit']!=reference['source_commit']:raise ValueError('Reference/source version mismatch')
    nodes={n['id']:n for n in graph['nodes']};checks=[]
    def check(name,passed,**detail):checks.append({'id':name,'passed':bool(passed),**detail})
    call_edges=[e for e in graph['edges'] if e['kind']=='STATIC_CALL_TARGET']
    for spec in reference['required_calls']:
        found=[e for e in call_edges if nodes[e['source']]['path']==spec['caller_path'] and
            nodes[e['source']]['name']==spec['callee'] and nodes[e['target']]['path']==spec['target_path'] and
            (not spec.get('target_name') or nodes[e['target']]['name']==spec['target_name'])]
        check(spec['id'],found,edges=found)
    imports=[(nodes[e['source']]['path'],nodes[e['target']]['path']) for e in graph['edges'] if e['kind']=='IMPORTS_MODULE']
    for index,pair in enumerate(reference['required_imports']):check('import.'+str(index),tuple(pair) in imports)
    spec=reference['dynamic_method'];calls=[n for n in graph['nodes'] if n['kind']=='call_site' and n['path']==spec['path'] and n['name']==spec['callee']]
    certain=[e for e in call_edges if e['source'] in {c['id'] for c in calls}]
    candidates=[nodes[e['target']]['name'] for e in graph['edges'] if e['kind']=='STATIC_CALL_CANDIDATE' and e['source'] in {c['id'] for c in calls}]
    check('dynamic_selection_retained',calls and not certain and set(candidates)==set(spec['target_names']),candidates=candidates)
    spec=reference['required_path'];start=[n for n in graph['nodes'] if n['kind']=='callable' and n['name']==spec['start_name']]
    end=[n for n in graph['nodes'] if n['kind']=='callable' and n['name']==spec['target_name']]
    path=w.query('path',start=start[0]['id'],target=end[0]['id'],depth=spec['max_depth'],nodes=1000,edges=3000,seconds=10) if len(start)==len(end)==1 else {}
    check('navigation_forward_path',path.get('found'),result=path)
    reverse=w.query('path',start=end[0]['id'],target=start[0]['id'],direction='in',depth=spec['max_depth'],nodes=1000,edges=3000,seconds=10) if len(start)==len(end)==1 else {}
    check('navigation_reverse_path',reverse.get('found'),result=reverse)
    if end:
        source=w.query('source',start=end[0]['id'])
        check('javascript_source_navigation',source.get('source_commit')==reference['source_commit'] and source.get('path')==end[0]['path'])
    result={'schema':'javascript-trial-score/1','source_commit':graph['source_commit'],'build_version':graph['version']['build_version'],
        'snapshot':graph['snapshot'],'checks':checks,'passed':all(c['passed'] for c in checks),
        'coverage':graph['coverage'],'input_paths':graph['input_paths'],'runtime_execution':False,'whole_G02_accepted':False}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'checks':len(checks),'passed':result['passed'],'failed':[c for c in checks if not c['passed']]},ensure_ascii=False))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
