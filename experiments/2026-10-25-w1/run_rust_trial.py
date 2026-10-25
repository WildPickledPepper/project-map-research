"""Build a real production workspace; independent Rust scoring runs afterwards."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from projectmap.workspace import Workspace,default_analysis


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('source','typescript','output'):ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--revision',required=True);ap.add_argument('--scope',choices=['rust','repository'],required=True)
    args=ap.parse_args()
    if args.output.exists():ap.error('Choose a new output directory')
    analysis=default_analysis()
    if args.scope=='rust':analysis['scope']['include']=['*.rs','*Cargo.toml','*Cargo.lock','*.cargo/*','*rust-toolchain*']
    workspace=Workspace.create(args.output/'workspace',args.source,revision=args.revision,typescript=args.typescript,analysis=analysis)
    with (args.output/'events.jsonl').open('w',encoding='utf-8') as stream:
        result=workspace.update(emit=lambda row:(stream.write(json.dumps(row)+'\n'),stream.flush()))
    (args.output/'trial.json').write_text(json.dumps({'scope':args.scope,'build':result,'status':workspace.status()},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'scope':args.scope,**result}),flush=True)
    if result.get('status')!='ready':raise SystemExit(1)


if __name__=='__main__':main()
