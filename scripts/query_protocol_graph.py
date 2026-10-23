"""Query a request-specific path, or explain matching/unknown identity results."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from adapters.fact_queries import find_path
from adapters.protocol_graph import PROTOCOL_KINDS


def resolve(graph,name):
    direct=[n['id'] for n in graph['nodes'] if n['id']==name]
    if direct:return direct[0]
    matches=[n for n in graph['nodes'] if n['kind']=='callable' and n['name']==name]
    definitions=[n for n in matches if n.get('definition')]
    if definitions:matches=definitions
    if len(matches)!=1:raise ValueError('Use an exact node ID for absent/ambiguous symbol: '+name)
    return matches[0]['id']


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('graph',type=Path)
    ap.add_argument('--from',dest='start');ap.add_argument('--to',dest='target');ap.add_argument('--reverse',action='store_true')
    ap.add_argument('--explain',help='consumer qualified name');ap.add_argument('--depth',type=int,default=12)
    a=ap.parse_args();g=json.loads(a.graph.read_text(encoding='utf-8'))
    if a.explain:result=[r for r in g['protocol']['results'] if r['name']==a.explain]
    else:result=find_path(g,resolve(g,a.start),resolve(g,a.target),PROTOCOL_KINDS,reverse=a.reverse,max_depth=a.depth)
    print(json.dumps(result,ensure_ascii=False,indent=2))
