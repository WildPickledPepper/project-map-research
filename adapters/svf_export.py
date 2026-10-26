"""Run upstream PySVF and serialize its native value-flow and points-to results."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def read_points(filename):
    """Read the upstream text interchange; no alias inference is performed here."""
    points=[]
    for line in Path(filename).read_text().splitlines():
        if '->' not in line:continue
        match=re.fullmatch(r'\s*(\d+)\s*->\s*\{([\d\s,]*)\}\s*',line)
        if not match:raise ValueError('Malformed native points-to record')
        source=int(match[1])
        points.extend({'source':source,'target':int(item)}
                      for item in match[2].replace(',',' ').split())
    return points


def export(bitcode,native_points=None,*,single_process_points=False,progress=None):
    import pysvf
    if single_process_points and native_points:
        raise ValueError('Same-process export cannot consume a different process capture')
    with tempfile.TemporaryDirectory(prefix='svf-native-') as temporary:
        own_points=Path(temporary)/'points-to.txt'
        options=['-svfg']
        if single_process_points:options.append('-write-ander='+str(own_points))
        if progress:progress('native_analysis_start')
        pysvf.buildSVFModule([*options,str(Path(bitcode).resolve())])
        if progress:progress('native_analysis_complete')
        if single_process_points and not own_points.is_file():
            raise RuntimeError('Installed PySVF did not write same-process points-to results')
        data=serialize_current(pysvf,own_points if single_process_points else native_points,
                               same_process_file=single_process_points)
        if progress:progress('serialization_complete')
        return data


def serialize_current(pysvf,native_points=None,*,same_process_file=False):
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
        points=read_points(native_points)
        if same_process_file:
            wanted={p[key] for p in points for key in ('source','target')}
            for uid,value in pag:
                if uid in wanted:variables[uid]=value
            if wanted-variables.keys():raise ValueError('Native points-to endpoints missing from the current PAG')
    return {'schema':'svf-native-export/1','package_version':importlib.metadata.version('pysvf'),
        'nodes':nodes,'edges':edges,'points_to':points,
        'variables':[{'id':uid,'name':v.getName(),'kind':type(v).__name__,'text':str(v)}
                     for uid,v in variables.items()],
        'python_points_to_binding_available':points_method is not None,
        'points_to_identity_status':'unverified_cross_process_ids' if native_points and not same_process_file else 'same_process_native_ids',
        'points_to_backend':'same_process_upstream_text' if same_process_file else 'same_distribution_native_wpa_cli' if native_points else 'native_python_binding' if points_method else 'unavailable',
        'export_native_analysis_runs':1,
        'same_process_endpoints_checked':bool(same_process_file),
        'native_pta_interface':dir(pta),
        'precision':'native_static_candidate','analysis':'SVF Andersen and full SVFG'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bitcode',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source-root',required=True);p.add_argument('--source-commit',required=True)
    p.add_argument('--context',required=True);p.add_argument('--module',required=True)
    p.add_argument('--native-points',type=Path)
    p.add_argument('--single-process-points',action='store_true')
    p.add_argument('--language',choices=['cpp','rust'],default='cpp')
    p.add_argument('--source-directory',default='')
    p.add_argument('--compiler-receipt',type=Path)
    args=p.parse_args()
    if args.output.exists():p.error('Use a new native output')
    data=export(args.bitcode,args.native_points,single_process_points=args.single_process_points)
    data.update(source_root=args.source_root,source_commit=args.source_commit,context=args.context,module=args.module)
    data.update(language=args.language,source_directory=args.source_directory)
    if args.compiler_receipt:
        receipt=json.loads(args.compiler_receipt.read_text())
        if receipt['source_commit']!=args.source_commit or receipt['context']!=args.context:
            raise ValueError('Compiler receipt source/context differs')
        data['compiler_context']={k:receipt[k] for k in ('compiler','target','release','native_cfg',
            'debug_assertions','analysis_optimization')}
    if args.language=='rust' and shutil.which('rustfilt'):
        names=sorted({n['function'] for n in data['nodes'] if n.get('function')})
        result=subprocess.run(['rustfilt'],input='\n'.join(names)+'\n',capture_output=True,text=True,check=True,timeout=30)
        data['function_display_names']=dict(zip(names,result.stdout.splitlines()))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,separators=(',',':')),encoding='utf-8')
    print(json.dumps({'nodes':len(data['nodes']),'edges':len(data['edges']),'points_to':len(data['points_to'])}))


if __name__=='__main__': main()
