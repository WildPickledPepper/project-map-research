"""Assess database selection and instance-scoped state evidence in a CGC copy."""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from adapters.data_graph import INSTANCE_IMPACT_KINDS
from adapters.data_queries import explain_receiver
from adapters.fact_queries import find_path
from adapters import kuzu_fact_graph as store
from score_increment import score


def assess(graph):
    previous=score(graph);data=graph['data'];nodes={n['id']:n for n in graph['nodes']}
    def method(suffix):
        found=[s for s in data['summaries'] if s['name'].endswith(suffix)];assert len(found)==1,suffix
        return found[0]
    lookup=method('DataBaseManager::GetTraceDatabaseByFileId')
    call,=[c for c in lookup['calls'] if c['expression']=='it->second->GetConnection()']
    assert [nodes[t]['name'] for t in call['targets']]==['Dic::Module::Timeline::DBConnectionPool<T>::GetConnection']
    binding=call['resolution']['candidates'][0]['template_bindings']['T']
    assert binding['names']==['Dic::Module::Timeline::VirtualTraceDatabase'] and not call['resolution']['gaps']
    receiver=explain_receiver(graph,'cpp:a2e15a2a22054e9348abea55')
    reached={x['name'] for x in receiver['producer_functions']}
    assert any(n.endswith('DBConnectionPool<T>::CreatConnection') for n in reached)
    assert any(n.endswith('DBConnectionPool<T>::GetConnection') for n in reached)
    db=next(p for f in receiver['factory_candidates'] for p in f['callback_products'] if p['line']==60)
    txt=next(p for f in receiver['factory_candidates'] for p in f['callback_products'] if p['type_spelling']=='TextTraceDatabase')
    derived=next(p for f in receiver['factory_candidates'] for p in f['callback_products'] if p['line']==98)
    assert next(c for c in db['conditions'] if c['kind']=='switch_label')['entry_labels']==['DataType::DB']
    assert next(c for c in txt['conditions'] if c['kind']=='switch_label')['entry_labels']==['DataType::TEXT','default']
    assert any(c['kind']=='early_exit_guard' and c['when'] is False for c in derived['conditions'])
    setter=method('DataBaseManager::SetDataType')['source_symbol'];getter=method('DataBaseManager::GetDataType')['source_symbol']
    forward=find_path(graph,setter,getter,INSTANCE_IMPACT_KINDS);reverse=find_path(graph,getter,setter,INSTANCE_IMPACT_KINDS,reverse=True)
    assert forward['found'] and reverse['found']
    instance_ids={n['instance'] for n in forward['nodes'] if 'instance' in n};assert len(instance_ids)==1
    instance=next(o for o in data['instances']['objects'] if o['id'] in instance_ids)
    assert instance['kind']=='static_local_object' and instance['identity_scope']=='process_and_link_image'
    accessor=next(a for a in data['instances']['accessors'] if a['instance']==instance['id'])
    assert nodes[accessor['source_symbol']]['name'].endswith('DataBaseManager::Instance')
    setter_calls=[c for c in data['instances']['calls'] if setter in c['targets'] and instance['id'] in c['instances']]
    assert len(setter_calls)>=2
    assert any('ProjectParserJson.cpp' in e['path'] for c in setter_calls for e in c['evidence'])
    assert any('RankOverlapStore.cpp' in e['path'] for c in setter_calls for e in c['evidence'])
    def brief(path):
        return {**path,'nodes':[{k:n[k] for k in ['id','kind','name','path','line','instance','instance_scope'] if k in n} for n in path['nodes']]}
    return {'evidence_kind':'executed_source_extraction_and_queries','source_commit':graph['source_commit'],
      'snapshot':graph['snapshot'],'phase_status':'P3_in_progress','counts':previous['counts'],
      'gates':{'D01':'pass','D02':'incomplete','D03':'incomplete','D04':'pass','D05':'incomplete'},
      'scope':'140 selected files; source candidates with explicit runtime conditions',
      'database_paths':{k:p for k,p in previous['paths'].items() if k in {'db','db_reverse','text','text_reverse'}},
      'iterator_call':call,'factory_conditions':{'db':db['conditions'],'text':txt['conditions'],'derived_db':derived['conditions']},
      'receiver_functions':[{'id':s['id'],'name':s['name']} for s in receiver['producer_functions']],
      'receiver_runtime_conditions':receiver['remaining_conditions'],'instance':instance,'accessor':accessor,'setter_call_contexts':setter_calls,
      'instance_paths':{'forward':brief(forward),'reverse':brief(reverse)},'instance_limits':data['instances']['limits'],
      'remaining':['D02 response field production, transport, unpacking and consumer state writes',
                   'D03 reverse influence from response fields with request scope','D05 consolidated whole-chain explanation',
                   'cross-module P7 case','P4 automatic updates','P5 observed runtime','P6 real historical assets'],
      'file_hash_verification':'not_run_per_user_preference'}


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--graph',type=Path,required=True)
    ap.add_argument('--cgc-db',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--buffer-pool-mb',type=int,default=1024);a=ap.parse_args()
    if a.buffer_pool_mb<=0:raise ValueError('Buffer pool must be positive')
    if a.output.resolve().is_relative_to(ROOT):raise ValueError('Keep databases in a new external directory')
    a.output.mkdir(parents=True,exist_ok=False);graph=json.loads(a.graph.read_text(encoding='utf-8'));report=assess(graph)
    report['rules_revision']=subprocess.check_output(['git','log','-1','--format=%H','--','adapters/cpp_data.py','adapters/cpp_value_types.py','adapters/cpp_control.py','adapters/cpp_instances.py','adapters/data_graph.py'],cwd=ROOT,text=True).strip()
    storage_revision=subprocess.check_output(['git','log','-1','--format=%H','--','adapters/kuzu_fact_graph.py'],cwd=ROOT,text=True).strip()
    test=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    (a.output/'python-tests.txt').write_text(test.stdout+test.stderr,encoding='utf-8');assert test.returncode==0,test.stderr
    import re
    report['python_tests']={'passed':True,'count':int(re.search(r'Ran (\d+) tests',test.stderr)[1])}
    wal=Path(str(a.cgc_db)+'.wal')
    if wal.exists() and wal.stat().st_size:raise ValueError('Close native database before copying')
    shutil.copy2(a.cgc_db,a.output/'cgc.kuzu')
    handle=os.add_dll_directory(os.environ['PROJECT_MAP_DLL_DIR']) if os.name=='nt' and os.environ.get('PROJECT_MAP_DLL_DIR') else None
    import kuzu
    db=kuzu.Database(str(a.output/'cgc.kuzu'),buffer_pool_size=a.buffer_pool_mb*1024*1024);conn=kuzu.Connection(db)
    native=store.rows(conn.execute('MATCH (n:Function) RETURN n ORDER BY n.uid'))
    print('Insert and read complete graph',flush=True)
    inserted=store.replace_snapshot(conn,graph);saved=store.read_snapshot(conn,graph['snapshot']);assert saved==graph
    assert assess(saved)=={k:v for k,v in report.items() if k not in {'rules_revision','python_tests'}}
    short=copy.deepcopy(graph);short['edges']=[e for e in short['edges'] if e['kind']!='INSTANCE_VALUE_READ_BY']
    print('Replace graph after removing instance-state edges',flush=True)
    store.replace_snapshot(conn,short);assert store.read_snapshot(conn,graph['snapshot'])==short
    print('Delete and restore graph',flush=True)
    store.delete_snapshot(conn,graph['snapshot']);assert store.read_snapshot(conn,graph['snapshot']) is None
    store.replace_snapshot(conn,graph);assert store.read_snapshot(conn,graph['snapshot'])==graph
    assert native==store.rows(conn.execute('MATCH (n:Function) RETURN n ORDER BY n.uid'))
    report['storage']={**inserted,'payload_roundtrip':True,'stored_queries_pass':True,'replace_delete_restore':True,
                      'native_rows_unchanged':len(native),'buffer_pool_mb':a.buffer_pool_mb,'adapter_revision':storage_revision}
    conn.close();db.close()
    if handle:handle.close()
    (a.output/'selection.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'gates':report['gates'],'counts':report['counts'],'tests':report['python_tests'],'storage':report['storage']}))
