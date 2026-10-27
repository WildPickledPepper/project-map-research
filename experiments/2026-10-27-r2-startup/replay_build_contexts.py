"""Replay multiple native CMake captures into the shared navigation schema."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from adapters.cmake_project import extract
from adapters.project_map import ProjectMap,build_index


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--index',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--capture',nargs=2,action='append',required=True,metavar=('CONTEXT','DIRECTORY'))
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();out=args.output.resolve()
    if out.exists() or out.is_relative_to(ROOT):p.error('Use a new external output')
    out.mkdir(parents=True);started=time.monotonic()
    db=sqlite3.connect(args.index.resolve().as_uri()+'?mode=ro',uri=True)
    try:
        info=json.loads(db.execute('SELECT payload FROM pm_map_info').fetchone()[0])
        files=[json.loads(r[0]) for r in db.execute('SELECT payload FROM pm_map_files ORDER BY path')]
        modules=[json.loads(r[0]) for r in db.execute('SELECT payload FROM pm_map_modules ORDER BY path')]
        entries=[json.loads(r[0]) for r in db.execute(
            "SELECT payload FROM pm_fact_nodes WHERE snapshot=? AND name='main' AND kind='callable'",(info['snapshot'],))]
    finally:db.close()
    entries=[n for n in entries if n['id'].startswith('cpp:')]
    paths=[r['path'] for r in files if r.get('graph_input')]
    captures=[{'directory':str(Path(directory).resolve()),'source_commit':info['source_commit'],'context_key':key}
              for key,directory in args.capture]
    facts=extract(args.source,paths,source_commit=info['source_commit'],output=out/'native',
                  config={'version':1,'cmake':{'captures':captures}},source_facts={'nodes':entries})
    graph={**facts,'source_commit':info['source_commit'],'snapshot':info['snapshot']+':build-context-replay',
           'input_paths':paths,'nodes':facts['nodes']+entries,
           'coverage':[{'path':path,'status':'build_context_replay_not_full_file_reanalysis'} for path in paths]}
    (out/'graph.json').write_text(json.dumps(graph,ensure_ascii=False),encoding='utf-8')
    build_index(graph,{'source_commit':info['source_commit'],'files':files,'modules':modules},out/'navigation.sqlite')
    nodes={n['id']:n for n in graph['nodes']};checks=[]
    query=ProjectMap(out/'navigation.sqlite',expected_snapshot=graph['snapshot'])
    try:
        for edge in graph['edges']:
            if edge['kind']!='EXECUTABLE_ENTRY_CANDIDATE':continue
            f=query.walk(edge['source'],target=edge['target'],kinds=[edge['kind']],depth=1)
            r=query.walk(edge['target'],target=edge['source'],kinds=[edge['kind']],direction='in',depth=1)
            checks.append({'case':'native_executable_entry_bidirectional','target':nodes[edge['source']]['name'],
                           'entry_path':nodes[edge['target']]['path'],'context':edge['build_context'],
                           'passed':f['found'] and r['found']})
    finally:query.close()
    checks.append({'case':'every_supplied_context_replayed','passed':len(facts['contexts'])==len(captures)
                   and all(r.get('capture_reused') for r in facts['contexts'])})
    checks.append({'case':'native_ids_unique_across_contexts','passed':len(nodes)==len(graph['nodes'])})
    result={'schema':'native-build-context-replay/1','source_commit':info['source_commit'],
            'contexts':[{k:r[k] for k in ('key','target_system','configurations','capture_reused')} for r in facts['contexts']],
            'node_kinds':dict(Counter(n['kind'] for n in graph['nodes'])),
            'checks':checks,'passed':all(r['passed'] for r in checks),'seconds':round(time.monotonic()-started,3),
            'default_whole_map_updated':False,'G03_G04_accepted':False,
            'source_symbols':'reused_existing_cpp_entry_declarations_only',
            'product_compiled_or_executed_in_replay':False}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
