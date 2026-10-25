"""Export all committed first-party Python sources and run the new semantic component."""
import argparse
from collections import Counter
from fnmatch import fnmatchcase
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from adapters.repository_discovery import discover
from adapters.snapshot_inputs import export_inputs
from adapters.python_facts import analyze


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ('source','output'):ap.add_argument('--'+key,type=Path,required=True)
    ap.add_argument('--revision',required=True)
    ap.add_argument('--include',action='append',help='Optional explicit component-trial scope; production defaults include all')
    args=ap.parse_args();args.source=args.source.resolve();args.output=args.output.resolve()
    if args.output.exists() or any(args.output.is_relative_to(p) for p in (ROOT,args.source)):ap.error('Choose a new external output')
    inventory=discover(args.source,args.revision)
    rows=[r for r in inventory['files'] if r['language']=='python' and r['eligible']]
    if args.include:rows=[r for r in rows if any(fnmatchcase(r['path'],pattern) for pattern in args.include)]
    args.output.mkdir(parents=True)
    export_inputs(args.source,{'files':[{k:r[k] for k in ('path','object','mode')} for r in rows]},args.output/'source')
    started=time.monotonic();facts=analyze(args.output/'source',[r['path'] for r in rows],
        emit=lambda row:print(json.dumps(row),file=sys.stderr,flush=True))
    from adapters.python_boundaries import augment
    facts=augment(facts)
    (args.output/'facts.json').write_text(json.dumps(facts,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    result={'schema':'python-semantic-component-trial/1','source_commit':inventory['source_commit'],
            'components':facts['components'],'seconds':round(time.monotonic()-started,3),
            'coverage':facts['coverage'],'nodes':dict(Counter(n['kind'] for n in facts['nodes'])),
            'edges':dict(Counter(e['kind'] for e in facts['edges'])),
            'call_resolutions':dict(Counter(n['resolution'] for n in facts['nodes'] if n['kind']=='call_site')),
            'diagnostics':facts['diagnostics'],'runtime_execution':False,'whole_G02_accepted':False}
    result['scope']=args.include or ['*']
    (args.output/'result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in {'coverage','diagnostics'}},ensure_ascii=False))


if __name__=='__main__':main()
