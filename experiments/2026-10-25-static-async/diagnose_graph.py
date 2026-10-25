"""Inspect query-stage counts on a complete saved graph."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from adapters.response_queries import explain_response
from adapters.return_bridge_queries import iframe_links
from adapters.socket_queries import explain_socket_receivers

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--graph',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();g=json.loads(a.graph.read_text(encoding='utf-8'));result=[]
    for command in ['operator/category','unit/flows','Memory/snapshot/blocks']:
        provider=next(p for p in g['protocol']['providers'] if p['command']==command)
        response=explain_response(g,provider['id']);socket=explain_socket_receivers(g,provider=provider['id'])
        result.append({'command':command,'response_routes':len(response['routes']),'response_states':response['visited_states'],
            'response_truncated':response['truncated'],'response_gaps':dict(Counter(d['kind'] for d in response['gaps'])),
            'receivers':socket['total_receivers'],'backend_links':socket['total_backend_links'],'socket_truncated':socket['truncated'],
            'iframe_links':len(iframe_links(g,provider['id']))})
        a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result[-1]),flush=True)
