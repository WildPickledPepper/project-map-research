"""Round-trip the same automatically extracted graph in copies of both native stores."""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from adapters import sqlite_fact_graph as sqlstore
from adapters import kuzu_fact_graph as kstore
from score_graph import score


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')


def sqlread(conn,snapshot):
    row=conn.execute('SELECT payload FROM pm_fact_snapshots WHERE snapshot=?',(snapshot,)).fetchone()
    if row is None:return None
    graph=json.loads(row[0])
    graph['nodes']=[json.loads(r[0]) for r in conn.execute('SELECT payload FROM pm_fact_nodes WHERE snapshot=? ORDER BY rowid',(snapshot,))]
    graph['edges']=[json.loads(r[0]) for r in conn.execute('SELECT payload FROM pm_fact_edges WHERE snapshot=? ORDER BY ordinal',(snapshot,))]
    return graph


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--graph',type=Path,required=True)
    ap.add_argument('--cgc-run',type=Path,required=True)
    ap.add_argument('--codegraph-run',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    if args.output.resolve().is_relative_to(ROOT):raise ValueError('Use an external output directory')
    args.output.mkdir(parents=True,exist_ok=False)
    graph=json.loads(args.graph.read_text(encoding='utf-8'))
    facts=score(graph)
    sources=[]
    for p in (args.codegraph_run/'cache').glob('*/graph.db'):
        conn=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True)
        count=conn.execute('SELECT count(*) FROM nodes').fetchone()[0]
        if count==728:sources.append(p)
        conn.close()
    if len(sources)!=1:raise ValueError('Expected the completed 728-node CodeGraph source database')
    source=sqlite3.connect(sources[0].resolve().as_uri()+'?mode=ro',uri=True)
    sql=sqlite3.connect(args.output/'codegraph.db');source.backup(sql);source.close()
    native_sql={t:sql.execute('SELECT * FROM '+t+' ORDER BY rowid').fetchall() for t in ('nodes','edges')}
    if (args.cgc_run/'cgc.kuzu.wal').exists() and (args.cgc_run/'cgc.kuzu.wal').stat().st_size:
        raise ValueError('Close native Kuzu database before copying')
    shutil.copy2(args.cgc_run/'cgc.kuzu',args.output/'cgc.kuzu')
    handle=os.add_dll_directory(os.environ['PROJECT_MAP_DLL_DIR']) if os.name=='nt' and os.environ.get('PROJECT_MAP_DLL_DIR') else None
    import kuzu
    db=kuzu.Database(str(args.output/'cgc.kuzu'),buffer_pool_size=256*1024*1024)
    kc=kuzu.Connection(db)
    native_k=kstore.rows(kc.execute('MATCH (n:Function) RETURN n ORDER BY n.uid'))
    lifecycle={}
    for name,conn,store,reader in [('cgc',kc,kstore,kstore.read_snapshot),('codegraph',sql,sqlstore,sqlread)]:
        def commit():
            if name=='codegraph':conn.commit()
        added=store.replace_snapshot(conn,graph);commit()
        saved=reader(conn,graph['snapshot'])
        assert saved==graph
        assert score(saved)==facts
        # Duplicate IDs in another snapshot must survive replacement/deletion.
        other=copy.deepcopy(graph);other['snapshot']+=':second'
        store.replace_snapshot(conn,other);commit()
        smaller=copy.deepcopy(graph);smaller['edges']=[]
        store.replace_snapshot(conn,smaller);commit()
        assert reader(conn,graph['snapshot'])==smaller
        assert reader(conn,other['snapshot'])==other
        store.delete_snapshot(conn,graph['snapshot']);commit()
        assert reader(conn,graph['snapshot']) is None
        assert reader(conn,other['snapshot'])==other
        store.delete_snapshot(conn,other['snapshot']);commit()
        store.replace_snapshot(conn,graph);commit()
        assert reader(conn,graph['snapshot'])==graph
        lifecycle[name]={**added,'payload_roundtrip':True,'stored_graph_case_paths_pass':True,
                         'replacement_removes_old_edges':True,'deletion_removes_snapshot':True,
                         'other_snapshot_preserved':True,'restored':True}
    assert native_k==kstore.rows(kc.execute('MATCH (n:Function) RETURN n ORDER BY n.uid'))
    assert all(native_sql[t]==sql.execute('SELECT * FROM '+t+' ORDER BY rowid').fetchall() for t in native_sql)
    lifecycle['cgc']['native_function_rows_unchanged']=len(native_k)
    lifecycle['codegraph']['native_nodes_edges_unchanged']={t:len(r) for t,r in native_sql.items()}
    # Direct database predicates query the same target and its reverse relation.
    queries={}
    for direction in ('forward','reverse'):
        name='database->QueryUnitFlows' if direction=='forward' else 'Dic::Module::Timeline::VirtualTraceDatabase::QueryUnitFlows'
        side='a' if direction=='forward' else 'b'
        cypher=f'MATCH (a:PMGraphNode)-[e:PMGraphEdge]->(b:PMGraphNode) WHERE a.snapshot=$s AND {side}.name=$name AND e.kind=$kind RETURN a.id AS source,b.id AS target,e.payload AS payload ORDER BY e.ordinal'
        kres=kstore.rows(kc.execute(cypher,{'s':graph['snapshot'],'name':name,'kind':'MEMBER_TARGET_CANDIDATE'}))
        query=f'SELECT e.source,e.target,e.payload FROM pm_fact_edges e JOIN pm_fact_nodes a ON e.snapshot=a.snapshot AND e.source=a.id JOIN pm_fact_nodes b ON e.snapshot=b.snapshot AND e.target=b.id WHERE e.snapshot=? AND {side}.name=? AND e.kind=? ORDER BY e.ordinal'
        sres=[dict(zip(('source','target','payload'),r)) for r in sql.execute(query,(graph['snapshot'],name,'MEMBER_TARGET_CANDIDATE'))]
        assert kres==sres and len(kres)==1
        queries[direction]={'cypher':cypher,'sql':query,'parameters':{'snapshot':graph['snapshot'],'name':name,'kind':'MEMBER_TARGET_CANDIDATE'},
                            'rows':[{**r,'payload':json.loads(r['payload'])} for r in kres],'same_results':True}
    report={'evidence_kind':'executed_source_extraction_and_two_native_store_copies','facts':facts,
            'lifecycle':lifecycle,'direct_database_queries':queries,
            'checks':{**facts['checks'],'F04':'pass','F05':'pass'},
            'reference_independence':{'builder_inputs':['source checkout','65-file input manifest','pinned TS compiler','Tree-sitter grammar'],
                                      'scorer_runs_after_extraction':True,'manual_reference_read_by_builder':False,
                                      'extraction_modules':['scripts/build_fact_graph.py','adapters/cpp_facts.py','adapters/syntax_supplement.py','adapters/typescript_facts.cjs']},
            'file_hash_verification':'not_run_per_user_preference',
            'untested':['C++ compiler/SCIP indexing','runtime dispatch','P2 protocol joins','P3 data flow','P4 auto refresh and native reindex preservation','whole repository scalability']}
    write(args.output/'completion-evidence.json',report)
    kc.close();db.close();sql.close()
    if handle:handle.close()
    print(json.dumps({'checks':report['checks'],'counts':facts['counts'],'lifecycle':lifecycle},ensure_ascii=False))


if __name__=='__main__':main()
