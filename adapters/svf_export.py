"""Serialize existing PySVF value-flow and points-to results without solving them."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import re


def export(bitcode,native_points=None):
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
    points_method=getattr(pta,'getPts',None) or getattr(pta,'get_pts',None)
    for uid,value in list(variables.items()) if points_method and not native_points else []:
        if not value.isPointer(): continue
        for target in points_method(uid):
            target=int(target); points.append({'source':uid,'target':target})
            variables.setdefault(target,pag.getGNode(target))
    if native_points:
        for match in re.finditer(r'^(\d+)\s*->\s*\{([\d\s,]*)\}',Path(native_points).read_text(),re.M):
            source=int(match[1])
            for item in match[2].replace(',',' ').split():
                target=int(item);points.append({'source':source,'target':target})
                for uid in (source,target):
                    if uid not in variables:variables[uid]=pag.getGNode(uid)
    return {'schema':'svf-native-export/1','package_version':importlib.metadata.version('pysvf'),
        'nodes':nodes,'edges':edges,'points_to':points,
        'variables':[{'id':uid,'name':v.getName(),'kind':type(v).__name__,'text':str(v)}
                     for uid,v in variables.items()],
        'python_points_to_binding_available':points_method is not None,
        'points_to_backend':'same_distribution_native_wpa_cli' if native_points else 'native_python_binding' if points_method else 'unavailable',
        'native_pta_interface':dir(pta),
        'precision':'native_static_candidate','analysis':'SVF Andersen and full SVFG'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bitcode',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source-root',required=True);p.add_argument('--source-commit',required=True)
    p.add_argument('--context',required=True);p.add_argument('--module',required=True)
    p.add_argument('--native-points',type=Path)
    args=p.parse_args()
    if args.output.exists():p.error('Use a new native output')
    data=export(args.bitcode,args.native_points)
    data.update(source_root=args.source_root,source_commit=args.source_commit,context=args.context,module=args.module)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,separators=(',',':')),encoding='utf-8')
    print(json.dumps({'nodes':len(data['nodes']),'edges':len(data['edges']),'points_to':len(data['points_to'])}))


if __name__=='__main__': main()
