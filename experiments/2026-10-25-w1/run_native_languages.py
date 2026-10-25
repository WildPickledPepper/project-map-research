"""Preserve unmodified CGC parser output for committed JS, Python and Rust sources.

This component experiment does not resolve cross-file calls or accept W1/G02.
"""
import argparse
from collections import Counter, defaultdict
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from adapters.repository_discovery import discover
from adapters.snapshot_inputs import export_inputs,git

CGC_COMMIT='93c9685bff9151f50a3121e9913e5ba2d27c1191'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--revision',default='HEAD')
    parser.add_argument('--cgc',type=Path,required=True)
    parser.add_argument('--parser-cache',type=Path,required=True)
    parser.add_argument('--dll-dir',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    for key,value in vars(args).items():
        if isinstance(value,Path):setattr(args,key,value.resolve())
    if args.output.exists() or any(args.output.is_relative_to(p) for p in (ROOT,args.source,args.cgc)):
        parser.error('Choose a new output directory outside all source checkouts')
    if git(args.cgc,'rev-parse','HEAD').decode().strip()!=CGC_COMMIT:
        raise ValueError('Use the fixed upstream CGC revision')
    if git(args.cgc,'status','--porcelain','--untracked-files=no').strip():
        raise ValueError('Upstream CGC tracked files must remain unmodified')
    inventory=discover(args.source,args.revision)
    selected=[r for r in inventory['files'] if r['language'] in {'javascript','python','rust'}
              and r['mode'] in {'100644','100755'} and r['role'] not in {'third_party','generated'}]
    args.output.mkdir(parents=True)
    selection={'files':[{'path':r['path'],'object':r['object'],'mode':r['mode']} for r in selected]}
    export_inputs(args.source,selection,args.output/'source')
    sys.path.insert(0,str(args.cgc/'src'))
    handles=[os.add_dll_directory(str(args.dll_dir))] if args.dll_dir and os.name=='nt' else []
    home=args.output/'cgc-home';home.mkdir()
    Path.home=classmethod(lambda cls:home)
    os.environ.update(LOG_FILE_PATH=str(args.output/'cgc.log'),ENABLE_APP_LOGS='ERROR',SCIP_INDEXER='false')
    import tree_sitter_language_pack as pack
    pack.configure(pack.PackConfig(cache_dir=str(args.parser_cache)))
    from codegraphcontext.tools.tree_sitter_parser import TreeSitterParser
    parsers={};records=[];totals=defaultdict(Counter)
    for language in ('javascript','python','rust'):
        started=time.monotonic()
        try:
            parsers[language]=TreeSitterParser(language)
        except Exception as error:
            parsers[language]=error
        for row in selected:
            if row['language']!=language:continue
            record={'path':row['path'],'language':language,'source_role':row['role']}
            try:
                if isinstance(parsers[language],Exception):raise parsers[language]
                data=parsers[language].parse(args.output/'source'/row['path'])
                dest=args.output/'raw-parser'/(row['path']+'.json');dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_text(json.dumps(data,indent=2,ensure_ascii=False,default=str)+'\n',encoding='utf-8')
                record.update(status='error' if data.get('error') else 'parsed',
                    counts={k:len(v) for k,v in data.items() if isinstance(v,list)})
                if data.get('error'):record['error']=data['error']
                totals[language].update(record['counts'])
            except Exception as error:
                record.update(status='error',error=str(error))
            records.append(record)
        print(json.dumps({'language':language,'files':sum(r['language']==language for r in records),
              'seconds':round(time.monotonic()-started,3),'counts':dict(totals[language])}),flush=True)
    for handle in handles:handle.close()
    result={'schema':'native-language-component-trial/1','source_commit':inventory['source_commit'],
            'upstream':{'name':'CodeGraphContext','commit':CGC_COMMIT,'version':importlib.metadata.version('codegraphcontext'),
                        'tracked_files_modified':False,'component':'unmodified TreeSitterParser language implementations'},
            'files':records,'counts_by_language':{k:dict(v) for k,v in totals.items()},
            'errors':sum(r['status']=='error' for r in records),'cross_file_resolution_executed':False,
            'normalized_graph_produced':False,'G02':'not_accepted','historical_assets_enabled':False,
            'file_hash_reverification':'not_run_per_user_preference'}
    (args.output/'native-summary.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'files':len(records),'errors':result['errors'],'G02':result['G02']}),flush=True)


if __name__=='__main__':main()
