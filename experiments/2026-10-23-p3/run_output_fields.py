"""Assess real response field production and persist its query facts in Kuzu."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from adapters.field_queries import explain_writes
from adapters import kuzu_fact_graph as store


def assess(graph):
    names={n['id']:n['name'] for n in graph['nodes']}
    uid=next(n['id'] for n in graph['nodes'] if n['name']=='Dic::Module::Timeline::QueryFlowsBySliceInfoHandler::HandleRequest' and n.get('definition'))
    result=explain_writes(graph,uid)
    selected=[e for e in result['effects'] if e['selectors']==['pointee','member:body','member:unitAllFlows']]
    assert not result['truncated'] and len(selected)==len({e['write'] for e in selected})==7
    roots={r['id']:r for r in result['roots']};root_ids={e['root'] for e in selected};assert len(root_ids)==1
    root=roots[next(iter(root_ids))];assert root['name']=='responsePtr' and root['kind']=='local'
    db=[e for e in selected if names[e['writer']].startswith('Dic::Module::FullDb::DbTraceDataBase::')]
    txt=[e for e in selected if names[e['writer']].startswith('Dic::Module::Timeline::TextTraceDatabase::')]
    assert len(db)==5 and len(txt)==2
    for effect in selected:
        assert len(effect['call_chain'])==2 and effect['call_chain'][0]['caller']==uid
        assert effect['call_chain'][-1]['callee']==effect['writer']
        assert effect['condition_scopes'] and effect['evidence'] and effect['runtime_execution']=='unknown'
        assert all(c['parameter_index']>=0 and c['actual'] and c['evidence'] for c in effect['call_chain'])
    assert any(c['kind']=='early_exit_guard' for e in selected for s in e['condition_scopes'] for c in s['conditions'])
    flow=graph['data']['field_flow']
    return {'evidence_kind':'executed_source_extraction_and_contextual_query','source_commit':graph['source_commit'],
        'snapshot':graph['snapshot'],'phase_status':'P3_in_progress','gate_under_test':'D02_incomplete',
        'scope':'response field production only; 141 selected source files',
        'counts':{'files':len(graph['input_paths']),'nodes':len(graph['nodes']),'edges':len(graph['edges']),
            **{k:len(flow[k]) for k in ['roots','locations','writes','calls','diagnostics']}},
        'entry':{'id':uid,'name':names[uid]},'response_object':root,
        'production':{'db_write_sites':len(db),'text_write_sites':len(txt),'total_handler_effects':len(result['effects']),
            'selected_effects':selected,'symbols':{i:names[i] for e in selected for c in e['call_chain'] for i in [c['caller'],c['callee']]},
            'truncated':result['truncated'],'max_depth':result['max_depth'],'max_effects':result['max_effects']},
        'unresolved_query_gaps':result['gaps'],'limits':result['limits'],
        'remaining':['D02 serialization and wire fields','D02 response transport and frontend unpacking',
            'D02 frontend field consumers and state writes','D03 response-field reverse impact',
            'D05 consolidated whole-chain gaps','P4 automatic refresh','P5 runtime evidence','P6 real historical assets','P7 final reuse'],
        'file_hash_verification':'not_run_per_user_preference'}


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--graph',type=Path,required=True)
    ap.add_argument('--cgc-db',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    if a.output.resolve().is_relative_to(ROOT):raise ValueError('Keep database copies outside the research repository')
    a.output.mkdir(parents=True,exist_ok=False);graph=json.loads(a.graph.read_text(encoding='utf-8'));report=assess(graph)
    report['rules_revision']=subprocess.check_output(['git','log','-1','--format=%H','--','adapters/cpp_field_flow.py','adapters/field_queries.py','adapters/data_graph.py'],cwd=ROOT,text=True).strip()
    test=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    (a.output/'python-tests.txt').write_text(test.stdout+test.stderr,encoding='utf-8');assert test.returncode==0,test.stderr
    report['python_tests']={'passed':True,'count':int(re.search(r'Ran (\d+) tests',test.stderr)[1])}
    wal=Path(str(a.cgc_db)+'.wal')
    if wal.exists() and wal.stat().st_size:raise ValueError('Close native database before copying')
    shutil.copy2(a.cgc_db,a.output/'cgc.kuzu')
    handle=os.add_dll_directory(os.environ['PROJECT_MAP_DLL_DIR']) if os.name=='nt' and os.environ.get('PROJECT_MAP_DLL_DIR') else None
    import kuzu
    db=kuzu.Database(str(a.output/'cgc.kuzu'),buffer_pool_size=1024*1024*1024);conn=kuzu.Connection(db)
    try:
        native=store.rows(conn.execute('MATCH (n:Function) RETURN n ORDER BY n.uid'))
        print('Persist output field facts and query the saved snapshot',flush=True)
        inserted=store.replace_snapshot(conn,graph);saved=store.read_snapshot(conn,graph['snapshot']);assert saved==graph
        assert assess(saved)=={k:v for k,v in report.items() if k not in {'rules_revision','python_tests'}}
        assert native==store.rows(conn.execute('MATCH (n:Function) RETURN n ORDER BY n.uid'))
        report['storage']={**inserted,'payload_roundtrip':True,'stored_output_query_pass':True,
            'native_rows_unchanged':len(native),'buffer_pool_mb':1024}
    finally:
        conn.close();db.close()
        if handle:handle.close()
    (a.output/'output-fields.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'counts':report['counts'],'production':{k:report['production'][k] for k in ['db_write_sites','text_write_sites','truncated']},'tests':report['python_tests'],'storage':report['storage']}))
