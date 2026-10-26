"""Recover diagnosed first-party headers using existing native compiler contexts."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.libclang_provider import analyze
from adapters.repository_discovery import discover
from adapters.sqlite_fact_graph import validate_graph
from projectmap.workspace import Workspace


def load(path): return json.loads(Path(path).read_text(encoding='utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('repository','cmake-capture','clang-capture','baseline-workspace','output','builtin-headers'):
        parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--revision',required=True)
    parser.add_argument('--query-driver',action='append',required=True)
    args = parser.parse_args()
    discovery = discover(args.repository,args.revision)
    paths = {r['path'] for r in discovery['files'] if r['eligible'] and r['language']=='cpp'}
    non_test = {r['path'] for r in discovery['files'] if r['role']!='test'}
    baseline = load(args.clang_capture/'facts.json')
    if baseline['components']['source_commit']!=args.revision: raise ValueError('Stale Clang baseline')
    required = {r['path'] for r in baseline['coverage'] if r['status']=='parsed_with_diagnostics'
                and r['path'] in non_test and Path(r['path']).suffix.lower() in {'.h','.hpp','.hh','.hxx'}}
    workspace = Workspace(args.baseline_workspace); active = workspace.config['active']
    if active['source_commit']!=args.revision: raise ValueError('Stale import graph')
    db = sqlite3.connect('file:'+str(workspace.directory/active['index'])+'?mode=ro',uri=True)
    try:
        pairs = db.execute('''SELECT s.path,t.path FROM pm_fact_edges e
            JOIN pm_fact_nodes s ON s.snapshot=e.snapshot AND s.id=e.source
            JOIN pm_fact_nodes t ON t.snapshot=e.snapshot AND t.id=e.target
            WHERE e.snapshot=? AND e.kind='CBM_IMPORTS' ''',(active['snapshot'],)).fetchall()
    finally: db.close()
    started = time.monotonic()
    facts = analyze(args.cmake_capture/'source',paths,
        compile_commands=args.cmake_capture/'prepared-dependencies',required_headers=required,
        context=baseline['components']['context'],source_commit=args.revision,output=args.output,
        query_drivers=args.query_driver,builtin_headers=args.builtin_headers,import_pairs=pairs,
        emit=lambda r:print(json.dumps(r),flush=True))
    validate_graph({'snapshot':'header-native-'+args.revision,**facts})
    (args.output/'facts.json').write_text(json.dumps(facts,separators=(',',':')),encoding='utf-8')
    residual = [r['path'] for r in facts['coverage'] if r['status']!='parsed']
    result = {'schema':'libclang-header-recovery/1','source_commit':args.revision,
        'context':facts['components']['context'],'components':facts['components'],
        'required_headers':len(required),'recovered_headers':len(required)-len(residual),
        'remaining_headers':residual,'nodes':len(facts['nodes']),'edges':len(facts['edges']),
        'seconds':round(time.monotonic()-started,3),'diagnostics':facts['diagnostics'],
        'coverage':facts['coverage'],'whole_G02_accepted':False,'historical_assets_enabled':False}
    (args.output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in {'diagnostics','coverage'}}),flush=True)
    if residual: raise SystemExit(1)


if __name__=='__main__': main()
