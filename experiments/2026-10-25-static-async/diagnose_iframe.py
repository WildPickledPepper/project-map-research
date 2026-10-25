"""Count join stages in memory on saved phase outputs, without changing facts."""
import argparse
import ast
from collections import Counter
import inspect
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from adapters.callback_graph import augment_callbacks
from adapters import return_bridge_queries as queries
from adapters import socket_queries


class Counters(ast.NodeTransformer):
    def visit_For(self,node):
        self.generic_visit(node)
        node.body.insert(0,ast.parse('counts['+repr('for '+ast.unparse(node.target))+'] += 1').body[0])
        return node

    def visit_If(self,node):
        self.generic_visit(node)
        node.body.insert(0,ast.parse('counts['+repr('if '+ast.unparse(node.test)[:120])+'] += 1').body[0])
        return node


def load(path):return json.loads(path.read_text(encoding='utf-8'))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['returns','callbacks','protocol','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--command',default='operator/category')
    p.add_argument('--socket',action='store_true')
    a=p.parse_args();returns=load(a.returns/'typescript_return_flow.cjs.json');callbacks=load(a.callbacks/'typescript_response_flow.cjs.json')
    protocol=load(a.protocol/'protocol-checkpoint.json')
    base={'snapshot':'component_diagnosis','source_commit':protocol['source_commit'],'nodes':returns['nodes'],
          'edges':[],'provenance':{},'extractors':{},'diagnostics':[]}
    graph=augment_callbacks(base,callbacks);graph.update(return_flow=returns['return_flow'],protocol=protocol['protocol'],edges=protocol['edges'])
    provider=next(p['id'] for p in graph['protocol']['providers'] if p['command']==a.command)
    if a.socket:
        graph['socket_flow']=load(a.returns/'typescript_socket_flow.cjs.json')['socket_flow']
    module=socket_queries if a.socket else queries;name='receiver_links' if a.socket else 'iframe_links'
    tree=Counters().visit(ast.parse(inspect.getsource(getattr(module,name))));ast.fix_missing_locations(tree)
    counts=Counter();namespace={**vars(module),'counts':counts};exec(compile(tree,'<join counters>','exec'),namespace)
    links=namespace[name](graph) if a.socket else namespace[name](graph,provider)
    result={'scope':'in-memory join diagnosis from saved components; not a rebuilt or published graph',
        'command':a.command,'links':len(links),'stages':dict(counts)}
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
