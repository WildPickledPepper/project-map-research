"""Inventory committed repository structure and package/build dependencies."""
import argparse
from collections import Counter
from fnmatch import fnmatchcase
import json
from pathlib import Path
import re
import subprocess


def inventory(source, revision, module_patterns):
    git=lambda *a:subprocess.check_output(['git','-C',str(source),*a])
    commit=git('rev-parse','--verify',revision+'^{commit}').decode().strip()
    paths=git('ls-tree','-r','--name-only','-z',commit).decode('utf-8').strip('\0').split('\0')
    roots=set()
    for path in paths:
        parts=path.split('/')
        for pattern in module_patterns:
            count=len(pattern.split('/')); prefix='/'.join(parts[:count])
            if len(parts)>count and fnmatchcase(prefix,pattern): roots.add(prefix)
    modules=[]; covered=set(); diagnostics=[]
    for root in sorted(roots):
        files=[p for p in paths if p.startswith(root+'/')]; covered.update(files)
        manifests=[p for p in files if p in (root+'/package.json',root+'/CMakeLists.txt')]
        metadata, dependencies=[],[]
        for path in manifests:
            raw=git('show',commit+':'+path).decode('utf-8')
            if path.endswith('package.json'):
                try: package=json.loads(raw)
                except ValueError:
                    diagnostics.append({'path':path,'reason':'invalid_package_json'}); continue
                metadata.append({'path':path,'line':1,'name':package.get('name'),'description':package.get('description'),'version':package.get('version'),'scripts':package.get('scripts',{})})
                for kind in ('dependencies','devDependencies','peerDependencies'):
                    for name,version in package.get(kind,{}).items():
                        dependencies.append({'name':name,'version':version,'kind':kind,'evidence':{'path':path,'line':next((i for i,l in enumerate(raw.splitlines(),1) if json.dumps(name) in l),1)}})
            else:
                metadata.append({'path':path,'line':1,'kind':'cmake_build'})
                for match in re.finditer(r'(?im)^\s*(find_package|add_subdirectory|target_link_libraries)\s*\(([^)]*)\)',raw):
                    dependencies.append({'kind':match[1],'expression':match[2].strip(),'resolution':'source_expression','evidence':{'path':path,'line':raw[:match.start()].count('\n')+1}})
        modules.append({'path':root,'name':root.rsplit('/',1)[-1],'file_count':len(files),
                        'extensions':dict(Counter(Path(p).suffix or '<none>' for p in files)),
                        'metadata':metadata,'dependencies':dependencies,'description_origin':'source_package_metadata'})
    return {'schema_version':1,'source_commit':commit,'evidence_kind':'committed_repository_inventory',
            'module_patterns':module_patterns,'tracked_files':len(paths),'module_assigned_files':len(covered),
            'outside_module_roots':sorted(set(paths)-covered),'modules':modules,'diagnostics':diagnostics,
            'semantics':'Structure covers tracked paths; semantic analysis coverage is reported separately by the graph.'}


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source',type=Path,required=True);ap.add_argument('--revision',default='HEAD')
    ap.add_argument('--module-pattern',action='append',required=True);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();r=inventory(a.source,a.revision,a.module_pattern)
    if a.output.exists():raise ValueError('Use a new output path')
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'modules':len(r['modules']),'tracked_files':r['tracked_files']}))
