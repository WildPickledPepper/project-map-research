"""Replay source Cargo build plans for all available native Rust cfg hosts."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.cargo_declared_artifacts import augment
from adapters.cargo_source_bindings import augment as bind_sources
from adapters.project_map import ProjectMap,build_index


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--index',type=Path,required=True);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args();out=args.output.resolve()
    if out.exists() or out.is_relative_to(ROOT):p.error('Use a new output outside the research checkout')
    out.mkdir(parents=True);started=time.monotonic()
    db=sqlite3.connect(args.index.resolve().as_uri()+'?mode=ro',uri=True)
    try:
        info=json.loads(db.execute('SELECT payload FROM pm_map_info').fetchone()[0]);snapshot=info['snapshot']
        files=[json.loads(r[0]) for r in db.execute('SELECT payload FROM pm_map_files ORDER BY path')]
        modules=[json.loads(r[0]) for r in db.execute('SELECT payload FROM pm_map_modules ORDER BY path')]
        nodes={}
        for kind in ('python_process_invocation','python_environment_effect','analysis_context'):
            for raw, in db.execute('SELECT payload FROM pm_fact_nodes WHERE snapshot=? AND kind=?',(snapshot,kind)):
                n=json.loads(raw);nodes[n['id']]=n
        for file in files:
            if file.get('language')!='rust':continue
            for raw, in db.execute("SELECT payload FROM pm_fact_nodes WHERE snapshot=? AND path=? AND kind IN ('code_module','callable')",(snapshot,file['path'])):
                n=json.loads(raw)
                if n.get('language')=='rust':nodes[n['id']]=n
        edges=[]
        for n in list(nodes.values()):
            if n['kind']!='code_module':continue
            for raw, in db.execute("SELECT payload FROM pm_fact_edges WHERE snapshot=? AND source=? AND kind='CONTAINS_SYMBOL'",(snapshot,n['id'])):
                e=json.loads(raw)
                if e['target'] in nodes:edges.append(e)
    finally:db.close()
    paths=[r['path'] for r in files if r.get('graph_input')]
    graph={'source_commit':info['source_commit'],'snapshot':snapshot+':cargo-host-replay','input_paths':paths,
           'nodes':list(nodes.values()),'edges':edges,'diagnostics':[],
           'coverage':[{'path':path,'status':'selected_build_facts_not_full_reanalysis'} for path in paths]}
    import tree_sitter_language_pack as pack
    if os.environ.get('PROJECT_MAP_PARSER_CACHE'):pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))
    augment(graph,root=args.source,paths=paths,output=out/'queries',parser=pack.get_parser('rust'))
    bind_sources(graph)
    (out/'graph.json').write_text(json.dumps(graph,ensure_ascii=False),encoding='utf-8')
    build_index(graph,{'source_commit':info['source_commit'],'files':files,'modules':modules},out/'navigation.sqlite')
    checks=[];query=ProjectMap(out/'navigation.sqlite',expected_snapshot=graph['snapshot'])
    try:
        for e in graph['edges']:
            if e['kind']!='EXECUTABLE_ENTRY_CANDIDATE':continue
            forward=query.walk(e['source'],target=e['target'],kinds=[e['kind']],depth=1)
            reverse=query.walk(e['target'],target=e['source'],direction='in',kinds=[e['kind']],depth=1)
            checks.append({'case':'cargo_entry_bidirectional','context':e['build_context'],
                           'passed':forward['found'] and reverse['found']})
    finally:query.close()
    configs=[n for n in graph['nodes'] if n['kind']=='build_configuration']
    result={'schema':'source-cargo-host-replay/1','source_commit':info['source_commit'],
            'query_summary':graph['cargo_declared_artifacts'],
            'contexts':[{'id':n['id'],'manifest':n['path'],'target_system':n['target_system'],'state':n['state']} for n in configs],
            'gaps_by_reason':dict(Counter(r.get('reason',r['kind']) for r in graph['diagnostics'])),
            'checks':checks,'passed':bool(configs) and all(c['passed'] for c in checks),
            'seconds':round(time.monotonic()-started,3),'default_whole_map_updated':False,'G03_G04_accepted':False}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({**result,'contexts':[{'manifest':n['path'],'host_target':n['target_system']['host_target'],
                         'target':n['target_system']['target']} for n in configs],
                         'query_summary':{k:v for k,v in graph['cargo_declared_artifacts'].items() if k!='contexts'},
                         'checks':{'total':len(checks),'passed':sum(c['passed'] for c in checks)}}))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
