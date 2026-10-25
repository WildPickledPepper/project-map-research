"""Assemble the standalone skill with a versioned wheel outside the research checkout."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
SCRIPTS={'build_project_snapshot','build_chain_closure_graph','build_fact_graph'}


def validate_wheel(path):
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        for name in names:
            if name.endswith('/'):continue
            part=Path(name)
            if '..' in part.parts or part.is_absolute():raise ValueError('Unsafe wheel path')
            first=part.parts[0]
            if first not in {'adapters','projectmap','scripts'} and not first.endswith('.dist-info'):
                raise ValueError('Unexpected wheel payload: '+name)
            if first=='scripts' and (part.suffix!='.py' or part.stem not in SCRIPTS):
                raise ValueError('Research-only script in wheel: '+name)
        info=json.loads(z.read('projectmap/_build_info.json'))
        if info.get('benchmark_materials_included') is not False:raise ValueError('Missing isolation metadata')
        return {'wheel_entries':len(names),'rules_commit':info['rules_commit'],'benchmark_materials_included':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--wheel',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--install-to',type=Path)
    a=p.parse_args();output=a.output.resolve()
    if output.is_relative_to(ROOT):p.error('Keep binary distributions outside Git')
    report=validate_wheel(a.wheel)
    from projectmap.version import rules_version
    if report['rules_commit']!=rules_version(require_clean=True):p.error('Wheel belongs to another tool revision')
    destination=a.install_to.expanduser().resolve() if a.install_to else None
    if destination and destination.exists():p.error('Install destination already exists; preserve existing skill')
    with tempfile.TemporaryDirectory() as temporary:
        folder=Path(temporary)/'project-map-assistant'
        shutil.copytree(ROOT/'skills/project-map-assistant',folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        (folder/'assets').mkdir();shutil.copy2(a.wheel,folder/'assets'/a.wheel.name)
        output.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for path in sorted(folder.rglob('*')):
                if path.is_file():z.write(path,path.relative_to(folder.parent).as_posix())
        if destination:shutil.copytree(folder,destination)
    print(json.dumps({'archive':str(output),'installed_skill':str(destination) if destination else None,**report}))


if __name__=='__main__':
    import sys
    sys.path.insert(0,str(ROOT))
    main()
