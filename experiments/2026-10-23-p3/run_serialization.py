"""Score real source-derived serializer mappings and query the persisted graph."""
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
from adapters.serialization_queries import explain_serialization
from adapters.field_queries import explain_writes
from adapters import kuzu_fact_graph as store


def assess(graph):
    uid=next(n['id'] for n in graph['nodes'] if n['name']=='Dic::Protocol::TimelineProtocol::ToUnitFlowsResponseJson' and n.get('definition'))
    result=explain_serialization(graph,uid);mappings=result['field_mappings']
    prefix=('body','unitAllFlows');flow=prefix+('*','flows')
    body={prefix,prefix+('*','cat'),flow}
    body|={flow+('*',f) for f in ['title','cat','id']}
    body|={flow+('*',side,f) for side in ['from','to'] for f in ['dbPath','pid','tid','timestamp','duration','depth','name','id','metaType','rankId']}
    envelope={(f,) for f in ['id','requestId','result','command','moduleName','resultCallbackId']}|{('error','code'),('error','message')}
    assert not result['truncated'] and {tuple(m['wire_path']) for m in mappings}==body|envelope
    assert len(body)==26 and len(envelope)==8
    for m in mappings:
        assert m['source']['selectors']==['element' if p=='*' else 'member:'+p for p in m['wire_path']]
        assert m['source']['parameter']==0 and m['source']['root_types']==['Dic::Protocol::UnitFlowsResponse']
        assert m['evidence'] and all(e['path'] in graph['input_paths'] for e in m['evidence'])
        assert not any(c.get('kind')=='unresolved_overload_requirement' for c in m['conditions'])
        assert (m['relation']=='array_iteration_source')==(tuple(m['wire_path']) in {prefix,flow})
    assert not any('budget' in g['kind'] for g in result['gaps'])
    assert all(g.get('wire_path',[None])[0]=='type' for g in result['gaps'])
    registration,=result['registrations'];assert registration['key']=='unit/flows'
    assert registration['owner']=='Dic::Protocol::TimelineProtocol'
    assert any(e['kind']=='REGISTERS_SERIALIZER_CANDIDATE' and e['target']==uid for e in graph['edges'])
    assert len([n for n in graph['nodes'] if n['kind']=='serialized_field' and n['source_symbol']==uid])==34
    handler=next(n['id'] for n in graph['nodes'] if n['name']=='Dic::Module::Timeline::QueryFlowsBySliceInfoHandler::HandleRequest' and n.get('definition'))
    production=explain_writes(graph,handler)
    effects=[e for e in production['effects'] if e['selectors']==['pointee','member:body','member:unitAllFlows']]
    assert len(effects)==7 and not production['truncated']
    compact=[{'wire_path':m['wire_path'],'selectors':m['source']['selectors'],'relation':m['relation'],
              'conversion':m['source'].get('conversion'),'conditions':m['conditions'],'evidence':m['evidence']} for m in mappings]
    data=graph['data']['serialization']
    return {'evidence_kind':'executed_source_extraction_and_persisted_query','source_commit':graph['source_commit'],
        'snapshot':graph['snapshot'],'phase_status':'P3_in_progress','gate_under_test':'D02_incomplete',
        'scope':'141 selected files; source serializer mapping and registration; delivery and frontend pending',
        'counts':{'files':len(graph['input_paths']),'nodes':len(graph['nodes']),'edges':len(graph['edges']),
            'serializer_summaries':len(data['functions']),'registrations':len(data['registrations']),
            'callback_mapping_variants':len(mappings),'callback_wire_paths':34,'body_paths':26,'envelope_paths':8},
        'callback':{'id':uid,'name':result['name'],'registration':registration},'mappings':compact,
        'callback_gaps':result['gaps'],'budgets':data['budgets'],'limits':data['limits'],
        'previous_production_query':{'handler':handler,'write_sites':len(effects),'truncated':False},
        'producer_serializer_join':'pending_protocol_and_response_instance_context',
        'remaining':['D02 producer-to-serializer contextual join','D02 response transport and frontend unpacking',
            'D02 frontend consumers and state writes','D03 response-field reverse impact','D05 consolidated whole-chain gaps'],
        'file_hash_verification':'not_run_per_user_preference'}


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--graph',type=Path,required=True)
    ap.add_argument('--cgc-db',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    if a.output.resolve().is_relative_to(ROOT):raise ValueError('Keep databases outside research repository')
    a.output.mkdir(parents=True,exist_ok=False)
    graph=json.loads(a.graph.read_text(encoding='utf-8'));report=assess(graph)
    report['rules_revision']=subprocess.check_output(['git','log','-1','--format=%H','--','adapters/cpp_serialization.py','adapters/data_graph.py','adapters/serialization_queries.py'],cwd=ROOT,text=True).strip()
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
        print('Persist serialization mappings and query the saved snapshot',flush=True)
        inserted=store.replace_snapshot(conn,graph);saved=store.read_snapshot(conn,graph['snapshot']);assert saved==graph
        assert assess(saved)=={k:v for k,v in report.items() if k not in {'rules_revision','python_tests'}}
        assert native==store.rows(conn.execute('MATCH (n:Function) RETURN n ORDER BY n.uid'))
        report['storage']={**inserted,'payload_roundtrip':True,'stored_serialization_query_pass':True,
            'native_rows_unchanged':len(native),'buffer_pool_mb':1024}
    finally:
        conn.close();db.close()
        if handle:handle.close()
    (a.output/'serialization.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['counts','python_tests','storage']}))
