"""Inspect one serializer using a mechanical source-include dependency closure."""
import argparse
import json
import os
from pathlib import Path,PurePosixPath
import posixpath
import re
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','manifest','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--file',action='append',required=True)
    p.add_argument('--symbol',required=True)
    a=p.parse_args()
    files={f['path'] for f in json.loads(a.manifest.read_text(encoding='utf-8'))['files']}
    chosen=set();todo=list(a.file)
    while todo:
        name=todo.pop()
        if name in chosen:continue
        if name not in files:raise ValueError(name)
        chosen.add(name)
        for quoted,include in re.findall(r'^\s*#\s*include\s*(["<])([^">]+)[">]',(a.source/name).read_text(encoding='utf-8'),re.M):
            local=posixpath.normpath(str(PurePosixPath(name).parent/include))
            targets=[local] if quoted=='"' and local in files else [f for f in files if f==include or f.endswith('/'+include)]
            if len(targets)==1:todo+=targets
    from adapters.cpp_data import DataExtractor
    from adapters.cpp_serialization import Serialization
    import tree_sitter_language_pack as pack
    if os.environ.get('PROJECT_MAP_PARSER_CACHE'):pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))
    d=DataExtractor({f:(a.source/f).read_bytes() for f in sorted(chosen)},pack.get_parser('cpp'))
    s=Serialization(d);functions=[]
    for uid,info in d.x.functions_by_id.items():
        if d.x.nodes[uid]['definition'] and d.x.nodes[uid]['name'].endswith(a.symbol):
            summary=s.analyze(uid);mappings,gaps=s.mappings(summary)
            functions.append({'name':d.x.nodes[uid]['name'],'field_mappings':mappings,'gaps':summary['gaps']+gaps})
    result={'evidence_kind':'executed_source_include_closure_serialization_probe','inputs':sorted(chosen),'functions':functions,
        'scope':'serializer summary only; not a complete graph or response-route test'}
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'inputs':len(chosen),'functions':[(f['name'],[m['wire_path'] for m in f['field_mappings']]) for f in functions]}))
