"""Publish one complete production snapshot using revision-bound native captures."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from projectmap.workspace import Workspace, default_analysis
from adapters.snapshot_inputs import git


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('source','output','typescript','cmake-capture','cbm-capture','clang-capture'):
        ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--revision',required=True)
    ap.add_argument('--header-capture',type=Path)
    args=ap.parse_args()
    if args.output.exists():ap.error('Use a new output')
    before=git(args.source,'status','--porcelain','--untracked-files=normal')
    context=json.loads((args.clang_capture/'result.json').read_text(encoding='utf-8'))['context']
    analysis=default_analysis()
    analysis['build']={'version':1,'cmake':{'captures':[{'directory':str(args.cmake_capture.resolve()),
        'source_commit':args.revision}]},'providers':{'captures':[
        {'provider':'cbm','directory':str(args.cbm_capture.resolve()),'source_commit':args.revision,'context_key':'selected_repository'},
        {'provider':'clangd','directory':str(args.clang_capture.resolve()),'source_commit':args.revision,'context_key':context}]}}
    if args.header_capture:
        analysis['build']['providers']['captures'].append({'provider':'libclang',
            'directory':str(args.header_capture.resolve()),'source_commit':args.revision,'context_key':context})
    workspace=Workspace.create(args.output/'workspace',args.source,revision=args.revision,
                                typescript=args.typescript,analysis=analysis)
    started=time.monotonic()
    with (args.output/'events.jsonl').open('w',encoding='utf-8') as stream:
        result=workspace.update(emit=lambda r:(stream.write(json.dumps(r)+'\n'),stream.flush()))
    changed=before!=git(args.source,'status','--porcelain','--untracked-files=normal')
    receipt={'scope':'repository','source_commit':args.revision,'build':result,
        'status':workspace.status(),'seconds':round(time.monotonic()-started,3),
        'original_checkout_modified':changed,'native_capture_reuse':True,
        'historical_assets_enabled':False,'hash_verification':'not_run_per_user_preference',
        'whole_G02_accepted':False}
    (args.output/'trial.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'seconds':receipt['seconds'],'original_checkout_modified':changed,
                      'result':result}),flush=True)
    if result['status']!='ready' or changed:raise SystemExit(1)


if __name__=='__main__':main()
