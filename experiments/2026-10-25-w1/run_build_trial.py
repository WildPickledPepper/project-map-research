"""Run native build extraction through the production workspace with explicit environment inputs."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from projectmap.workspace import Workspace


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('source','typescript','analysis','output'):ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--revision',required=True)
    ap.add_argument('--scope',choices=['repository','cmake_cpp_control'],required=True)
    args=ap.parse_args()
    if args.output.exists():ap.error('Choose a new output directory')
    config=json.loads(args.analysis.read_text(encoding='utf-8'))
    if args.scope=='cmake_cpp_control':
        config['scope']['include']=['*.cpp','*.cc','*.cxx','*.h','*.hpp','*CMakeLists.txt','*.cmake']
    workspace=Workspace.create(args.output/'workspace',args.source,revision=args.revision,typescript=args.typescript,analysis=config)
    with (args.output/'events.jsonl').open('w',encoding='utf-8') as stream:
        result=workspace.update(emit=lambda row:(stream.write(json.dumps(row)+'\n'),stream.flush()))
    (args.output/'trial.json').write_text(json.dumps({'scope':args.scope,'build':result,'status':workspace.status()},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'scope':args.scope,**result}),flush=True)
    if result.get('status')!='ready':raise SystemExit(1)


if __name__=='__main__':main()
