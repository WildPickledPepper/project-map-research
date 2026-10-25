"""Run the production builder/navigation with explicit static experiment scope.

Generation reads source and configuration only. The independent scorer is separate.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from projectmap.workspace import Workspace,default_analysis

CHAIN_INPUTS=['modules/compute/src/components/hotMethod/CodeTextSearch.tsx',
    'modules/compute/src/utils/DomSearch/mark.js','modules/compute/src/utils/DomSearch/RegExpTool.js',
    'modules/compute/src/utils/DomSearch/domiterator.js','modules/compute/package.json']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--revision',default='HEAD')
    parser.add_argument('--typescript',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--scope',choices=['chain','ecmascript','repository'],required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Choose a new trial output directory')
    analysis=default_analysis()
    if args.scope=='chain':analysis['scope']['include']=CHAIN_INPUTS
    elif args.scope=='ecmascript':analysis['scope']['include']=['*.ts','*.tsx','*.mts','*.cts','*.js','*.jsx','*.mjs','*.cjs','*package.json','*tsconfig.json']
    w=Workspace.create(args.output/'workspace',args.source,revision=args.revision,typescript=args.typescript,analysis=analysis)
    with (args.output/'events.jsonl').open('w',encoding='utf-8') as log:
        result=w.update(emit=lambda event:log.write(json.dumps(event,ensure_ascii=False)+'\n'))
    output={'scope':args.scope,'build':result,'status':w.status()}
    (args.output/'trial.json').write_text(json.dumps(output,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'scope':args.scope,'status':result.get('status'),'counts':result.get('counts'),
        'graph':w.config.get('active',{}).get('graph'),'error':result.get('error')},ensure_ascii=False),flush=True)
    if result.get('status')!='ready':raise SystemExit(1)


if __name__=='__main__':main()
