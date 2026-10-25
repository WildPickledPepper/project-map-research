"""Inspect C++ registry extraction on a mechanical include closure."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','manifest','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--file', action='append', required=True)
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
    from adapters.cpp_protocol import ProtocolExtractor
    from adapters.cpp_data import DataExtractor
    import tree_sitter_language_pack as pack
    if os.environ.get('PROJECT_MAP_PARSER_CACHE'):pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))
    data=DataExtractor({f:(a.source/f).read_bytes() for f in sorted(chosen)},pack.get_parser('cpp'))
    result=ProtocolExtractor(None,None,extractor=data.x,facts=data.facts,value_types=data.types).build()
    result['inspection']={'using_directives':{p:u['using'] for p,u in data.x.units.items() if u['using']}}
    a.output.write_text(json.dumps(result,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'inputs':len(chosen),'registrations':len(result['protocol']['registrations']),
                      'object_registrations':sum(bool(r['objects']) for r in result['protocol']['registrations']),
                      'providers':len(result['protocol']['providers'])}))
