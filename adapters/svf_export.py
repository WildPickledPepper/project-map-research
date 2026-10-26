"""Serialize existing PySVF value-flow and points-to results without solving them."""
import argparse
import importlib.metadata
import json
from pathlib import Path


def export(bitcode):
    import pysvf
    pysvf.buildSVFModule(['-svfg', str(Path(bitcode).resolve())])
    graph=pysvf.getSVFG(); pag=pysvf.getPAG(); pta=pysvf.get_pta()
    if graph is None: raise RuntimeError('SVF did not construct its native value-flow graph')
    nodes=[]; edges=[]; variables={}; points=[]
    for node in graph.getNodes():
        native=node.getICFGNode()
        function=native.getFun() if native else None
        value=node.getValue() if node.isStmtVFGNode() or node.isArgumentVFGNode() else None
        record={'id':node.getId(),'kind':type(node).__name__,'text':str(node),
                'source_location':native.getSourceLoc() if native else None,
                'function':function.getName() if function else None,
                'function_location':function.getSourceLoc() if function else None,
                'value':value.getId() if value else None}
        nodes.append(record)
        if value: variables[value.getId()]=value
        for edge in node.getOutEdges():
            edges.append({'source':edge.getSrcNode().getId(),'target':edge.getDstNode().getId(),
                'kind':type(edge).__name__,'direct':edge.isDirectVFGEdge(),
                'indirect':edge.isIndirectVFGEdge(),'call':edge.isCallVFGEdge(),'return':edge.isRetVFGEdge(),
                'callsite':edge.getCallSiteId() if hasattr(edge,'getCallSiteId') else None})
    for uid,value in list(variables.items()):
        if not value.isPointer(): continue
        for target in pta.getPts(uid):
            target=int(target); points.append({'source':uid,'target':target})
            variables.setdefault(target,pag.getGNode(target))
    return {'schema':'svf-native-export/1','package_version':importlib.metadata.version('pysvf'),
        'nodes':nodes,'edges':edges,'points_to':points,
        'variables':[{'id':uid,'name':v.getName(),'kind':type(v).__name__,'text':str(v)}
                     for uid,v in variables.items()],
        'precision':'native_static_candidate','analysis':'SVF Andersen and full SVFG'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bitcode',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source-root',required=True);p.add_argument('--source-commit',required=True)
    p.add_argument('--context',required=True);p.add_argument('--module',required=True)
    args=p.parse_args()
    if args.output.exists():p.error('Use a new native output')
    data=export(args.bitcode)
    data.update(source_root=args.source_root,source_commit=args.source_commit,context=args.context,module=args.module)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,separators=(',',':')),encoding='utf-8')
    print(json.dumps({'nodes':len(data['nodes']),'edges':len(data['edges']),'points_to':len(data['points_to'])}))


if __name__=='__main__': main()
