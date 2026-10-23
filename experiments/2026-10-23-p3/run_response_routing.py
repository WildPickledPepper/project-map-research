"""Verify source response-object routes, ordering and persisted query results."""
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
from adapters.response_queries import explain_response
from adapters import kuzu_fact_graph as store


def assess(graph):
    provider=next(p for p in graph['protocol']['providers'] if p['command']=='unit/flows')
    result=explain_response(graph,provider['id']);names={n['id']:n['name'] for n in graph['nodes']}
    assert result['status']=='source_response_route_candidate' and not result['truncated']
    assert len(result['routes'])==4 and len({r['object_root'] for r in result['routes']})==1
    sends={r['steps'][0]['evidence'][0]['line']:r for r in result['routes']};assert set(sends)=={38,47,61,65}
    routes=[];body_path=['pointee','member:body','member:unitAllFlows']
    for line,route in sorted(sends.items()):
        assert route['protocol_owner']=='Dic::Protocol::TimelineProtocol'
        assert names[route['serializer']]=='Dic::Protocol::TimelineProtocol::ToUnitFlowsResponseJson'
        steps=route['steps'];assert len(steps)==6
        assert all(a['callee']==b['caller'] for a,b in zip(steps,steps[1:]))
        assert [names[s['callee']] for s in steps]==['Dic::SendResponse','Dic::Server::WsSessionImpl::OnResponse',
            'Dic::Server::WsSessionImpl::SendResponse','Dic::Protocol::ProtocolManager::ToJson',
            'Dic::Protocol::ProtocolUtil::ToJson','Dic::Protocol::TimelineProtocol::ToUnitFlowsResponseJson']
        assert all(s['evidence'] for s in steps)
        assert steps[-1]['key']=='unit/flows' and steps[-1]['registry']=='Dic::Protocol::ProtocolUtil::resToJsonFactory'
        mappings=route['field_mappings'];assert len({tuple(m['wire_path']) for m in mappings})==34
        for m in mappings:
            assert m['selectors']==['pointee']+['element' if p=='*' else 'member:'+p for p in m['wire_path']]
        body=[p for p in route['production_links'] if p['selectors']==body_path]
        writes={p['write'] for p in body};assert len(writes)==(7 if line in {61,65} else 0)
        assert len(body)==(182 if writes else 0)
        assert {names[p['writer']].split('::')[-2] for p in body}==({'DbTraceDataBase','TextTraceDatabase'} if writes else set())
        routes.append({**route,'send_line':line,'body_write_sites':len(writes),'body_links':len(body)})
    assert any(g['kind']=='operator_transfer_not_expanded' and any(c.get('expression')=='(useResponseQueue)' and c.get('when') for c in g['conditions']) for g in result['gaps'])
    return {'evidence_kind':'executed_source_extraction_contextual_route_and_storage_query',
        'source_commit':graph['source_commit'],'snapshot':graph['snapshot'],'phase_status':'P3_in_progress','gate_under_test':'D02_incomplete',
        'counts':{'files':len(graph['input_paths']),'nodes':len(graph['nodes']),'edges':len(graph['edges']),
            'routes':len(routes),'callback_wire_paths':34,'body_write_sites':7,'body_paths':26,
            'visited_states':result['visited_states']},
        'provider':provider['id'],'routes':routes,'gaps':result['gaps'],'limits':result['limits'],
        'query':{'max_depth':result['max_depth'],'max_states':result['max_states'],'truncated':result['truncated']},
        'symbols':{uid:names[uid] for r in routes for s in r['steps'] for uid in [s['caller'],s['callee']]},
        'remaining':['D02 JSON string transport and frontend unpacking','D02 frontend field consumers and state writes',
            'D03 response-field reverse influence','D05 consolidated whole-chain gaps','conditional queue transfer model'],
        'file_hash_verification':'not_run_per_user_preference'}


def compact(report):
    """Intern repeated evidence; retain every source record and all references."""
    records={};lookup={};shared={};shared_lookup={}
    def visit(value):
        if isinstance(value,list):return [visit(v) for v in value]
        if not isinstance(value,dict):return value
        result={}
        for key,item in value.items():
            if key=='evidence':
                refs=[]
                for evidence in item:
                    encoded=json.dumps(evidence,sort_keys=True)
                    if encoded not in lookup:
                        uid='source:'+str(len(records));lookup[encoded]=uid;records[uid]=evidence
                    refs.append(lookup[encoded])
                result['evidence_refs']=list(dict.fromkeys(refs))
            elif key in {'conditions','production_calls','field_mappings','production_links'} and item:
                encoded=json.dumps(item,sort_keys=True)
                identity=(key,encoded)
                if identity not in shared_lookup:
                    uid=key+':'+str(len(shared_lookup));shared_lookup[identity]=uid
                    shared[uid]=visit(item)
                result[key+'_ref']=shared_lookup[identity]
            else:result[key]=visit(item)
        return result
    result=visit(report);result['source_evidence']=records;result['shared_records']=shared;return result


def expand(report):
    def visit(value):
        if isinstance(value,list):return [visit(v) for v in value]
        if not isinstance(value,dict):return value
        result={}
        for key,item in value.items():
            if key=='evidence_refs':result['evidence']=[report['source_evidence'][ref] for ref in item]
            elif key.endswith('_ref') and item in report.get('shared_records',{}):result[key[:-4]]=visit(report['shared_records'][item])
            else:result[key]=visit(item)
        return result
    return visit({k:v for k,v in report.items() if k not in {'source_evidence','shared_records'}})


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--graph',type=Path,required=True)
    ap.add_argument('--cgc-db',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    if a.output.resolve().is_relative_to(ROOT):raise ValueError('Keep database copies outside research repository')
    a.output.mkdir(parents=True,exist_ok=False)
    graph=json.loads(a.graph.read_text(encoding='utf-8'));report=assess(graph)
    report['rules_revision']=subprocess.check_output(['git','log','-1','--format=%H','--','adapters/cpp_response_routing.py','adapters/response_queries.py','adapters/field_queries.py'],cwd=ROOT,text=True).strip()
    report['extraction_rules_revision']=subprocess.check_output(['git','log','-1','--format=%H','--','adapters/cpp_data.py','adapters/cpp_response_routing.py','adapters/cpp_field_flow.py','adapters/data_graph.py'],cwd=ROOT,text=True).strip()
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
        print('Persist response-object routes and rerun scoped query',flush=True)
        inserted=store.replace_snapshot(conn,graph);saved=store.read_snapshot(conn,graph['snapshot']);assert saved==graph
        assert assess(saved)=={k:v for k,v in report.items() if k not in {'rules_revision','extraction_rules_revision','python_tests'}}
        assert native==store.rows(conn.execute('MATCH (n:Function) RETURN n ORDER BY n.uid'))
        report['storage']={**inserted,'payload_roundtrip':True,'stored_response_query_pass':True,
            'native_rows_unchanged':len(native),'buffer_pool_mb':1024}
    finally:
        conn.close();db.close()
        if handle:handle.close()
    # Repeated evidence entries have no ordering semantics; compaction removes
    # duplicate references but retains all distinct source records.
    packed=compact(report);assert compact(expand(packed))==packed
    (a.output/'response-routing.json').write_text(json.dumps(packed,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['counts','python_tests','storage']}))
