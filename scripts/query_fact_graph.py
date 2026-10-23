"""Find a typed structural path in a generated portable graph JSON."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from adapters.fact_queries import find_path

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--graph',type=Path,required=True)
    ap.add_argument('--start',required=True,help='Exact node ID or unique callable name; falls back to unique node name')
    ap.add_argument('--target',required=True,help='Exact node ID or unique callable name; falls back to unique node name')
    ap.add_argument('--kinds',required=True,help='Comma-separated allowed edge kinds')
    ap.add_argument('--reverse',action='store_true')
    ap.add_argument('--max-depth',type=int,default=12)
    args=ap.parse_args()
    graph=json.loads(args.graph.read_text(encoding='utf-8'))
    def select(value):
        matches=[n['id'] for n in graph['nodes'] if n['id']==value]
        if not matches:matches=[n['id'] for n in graph['nodes'] if n['name']==value and n['kind']=='callable']
        if not matches:matches=[n['id'] for n in graph['nodes'] if n['name']==value]
        if len(matches)!=1:ap.error('Select a unique node ID: '+value+' has '+str(len(matches))+' matches')
        return matches[0]
    result=find_path(graph,select(args.start),select(args.target),set(args.kinds.split(',')),args.reverse,args.max_depth)
    print(json.dumps({'snapshot':graph['snapshot'],**result},ensure_ascii=False,indent=2))
