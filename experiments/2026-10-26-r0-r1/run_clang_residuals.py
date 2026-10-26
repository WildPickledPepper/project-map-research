"""Re-query only files whose native definition-query budget was exhausted."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.clangd_provider import analyze_batch, diagnostic_precision
from adapters.sqlite_fact_graph import validate_graph


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('base','capture','output','binary'):ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--revision',required=True);ap.add_argument('--query-driver',action='append',default=[])
    args=ap.parse_args();started=time.monotonic()
    if args.output.exists():ap.error('Use a new output')
    base=json.loads((args.base/'facts.json').read_text(encoding='utf-8'))
    native=json.loads((args.capture/'result.json').read_text(encoding='utf-8'))
    if base['components']['source_commit']!=args.revision or native['source_commit']!=args.revision:
        raise ValueError('Source revisions do not agree')
    pending={r['path'] for r in base['coverage'] if r.get('reference_budget_exhausted')}
    all_paths=[r['path'] for r in base['coverage']]
    if not pending:raise ValueError('No query-budget residuals to retry')
    args.output.mkdir(parents=True)
    with (args.output/'events.jsonl').open('w',encoding='utf-8') as stream:
        fresh=analyze_batch(args.capture/'source',sorted(pending),output=args.output/'retry',
            binary=args.binary,context=base['components']['context'],source_commit=args.revision,
            compile_commands=args.capture/'prepared-dependencies',query_drivers=args.query_driver,
            reference_budget=10000,input_paths=all_paths,
            emit=lambda r:(stream.write(json.dumps(r)+'\n'),stream.flush()))
    old_nodes={n['id']:n for n in base['nodes']}
    retained_edges=[e for e in base['edges'] if old_nodes[e['source']]['path'] not in pending]
    old_nodes.update({n['id']:n for n in fresh['nodes'] if n['kind']!='declaration' or n['id'] not in old_nodes})
    base.update(nodes=list(old_nodes.values()),edges=retained_edges+fresh['edges'],
        coverage=[r for r in base['coverage'] if r['path'] not in pending]+fresh['coverage'],
        diagnostics=[r for r in base['diagnostics'] if r.get('path') not in pending]+fresh['diagnostics'])
    base=diagnostic_precision(base)
    validate_graph({'snapshot':'native-cpp-'+args.revision,**base})
    if {r['path'] for r in base['coverage']}!=set(all_paths):raise ValueError('Retry changed file scope')
    (args.output/'facts.json').write_text(json.dumps(base,separators=(',',':')),encoding='utf-8')
    result={'source_commit':args.revision,'context':base['components']['context'],'files':len(all_paths),
        'retried_files':len(pending),'remaining_budget_files':sum(r.get('reference_budget_exhausted',False) for r in base['coverage']),
        'provider_failed_files':sum(r['status']=='provider_failed' for r in base['coverage']),
        'seconds':round(time.monotonic()-started,3),'nodes':len(base['nodes']),'edges':len(base['edges']),
        'native_capture_reused':True,'hash_verification':'not_run_per_user_preference','whole_G02_accepted':False}
    (args.output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result),flush=True)
    if result['remaining_budget_files'] or result['provider_failed_files']:raise SystemExit(1)


if __name__=='__main__':main()
