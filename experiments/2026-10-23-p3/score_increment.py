"""Assess P3's first data increment; expected project names stay in the scorer."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from adapters.data_graph import END_TO_END_KINDS,RESOURCE_IMPACT_KINDS
from adapters.data_queries import explain_receiver,walk_values
from adapters.fact_queries import find_path


def score(graph):
    nodes={n['id']:n for n in graph['nodes']}
    def symbol(name):
        candidates=[n for n in nodes.values() if n['kind']=='callable' and n['name']==name]
        definitions=[n for n in candidates if n.get('definition')]
        candidates=definitions or candidates;assert len(candidates)==1,name
        return candidates[0]['id']
    def brief(path):
        assert path['found']
        edges=[]
        for edge in path['edges']:
            value={k:edge[k] for k in ['source','target','kind','status','conditions','condition','basis','runtime_selection','receiver_types'] if k in edge}
            value['evidence']=[{k:e[k] for k in ['path','line','kind','field'] if k in e} for e in edge['evidence']]
            edges.append(value)
        return {**path,'nodes':[{k:n[k] for k in ['id','name','kind','path','line']} for n in path['nodes']],'edges':edges}
    start=symbol('getUnitFlows');paths={}
    for label,name in [('db','Dic::Module::FullDb::DbTraceDataBase::QueryUnitFlows'),('text','Dic::Module::Timeline::TextTraceDatabase::QueryUnitFlows')]:
        end=symbol(name)
        paths[label]=brief(find_path(graph,start,end,END_TO_END_KINDS,max_depth=16))
        paths[label+'_reverse']=brief(find_path(graph,end,start,END_TO_END_KINDS,reverse=True,max_depth=16))
        assert any(e['kind']=='MATCHES_REGISTERED_PROTOCOL' for e in paths[label]['edges'])
        assert any(e['kind']=='OVERRIDE_CANDIDATE' for e in paths[label]['edges'])
    owner=symbol('Dic::Module::Timeline::QueryFlowsBySliceInfoHandler::HandleRequest')
    call,=[c for s in graph['data']['summaries'] if s['source_symbol']==owner for c in s['calls'] if c['expression'].startswith('database->QueryUnitFlows')]
    receiver=explain_receiver(graph,call['call_site']);assert not receiver['truncated']
    selection=receiver['receiver']['initializer'];assert selection['kind']=='conditional_expression'
    assert selection['condition']['expression']=='request.params.dbPath.empty()'
    branches=selection['branches'];assert [b['when'] for b in branches]==[True,False]
    branch_names=[{nodes[t]['name'] for v in walk_values(b['value']) for t in v.get('targets',[])} for b in branches]
    assert any(n.endswith('GetTraceDatabaseByRankId') for n in branch_names[0])
    assert any(n.endswith('GetTraceDatabaseByFileId') for n in branch_names[1])
    assert len(receiver['factory_candidates'])==3
    assert {p['type_spelling'] for f in receiver['factory_candidates'] for p in f['callback_products']}=={'FullDb::DbTraceDataBase','TextTraceDatabase'}
    assert all(f['callback_bindings'] and f['callback_invocations'] for f in receiver['factory_candidates'])
    assert all(i['factory_support'] for i in receiver['implementations'])
    assert sum(bool(f['control_state_reads'] and f['control_state_writes']) for f in receiver['factory_candidates'])==2
    setter=symbol('Dic::Module::Timeline::DataBaseManager::SetDataType');getter=symbol('Dic::Module::Timeline::DataBaseManager::GetDataType')
    paths['state']=brief(find_path(graph,setter,getter,RESOURCE_IMPACT_KINDS))
    paths['state_reverse']=brief(find_path(graph,getter,setter,RESOURCE_IMPACT_KINDS,reverse=True))
    assert any(e['kind']=='POTENTIALLY_READ_BY' for e in paths['state']['edges'])
    return {'evidence_kind':'executed_source_extraction_and_query','phase_status':'P3_in_progress',
      'source_commit':graph['source_commit'],'snapshot':graph['snapshot'],
      'counts':{'files':len(graph['input_paths']),'nodes':len(graph['nodes']),'edges':len(graph['edges']),
                **{k:len(graph['data'][k]) for k in ['storages','accesses','allocations','selections','callbacks']}},
      'paths':paths,'receiver':receiver,
      'assertions':{'frontend_to_db_and_text_both_directions':True,'request_field_selects_lookup':True,
                    'three_pool_creation_sources':True,'two_data_type_control_dependencies':True,
                    'callback_parameter_binding_and_invocation':True,'shared_state_both_directions':True},
      'gates':{key:'incomplete' for key in ['D01','D02','D03','D04','D05']},
      'remaining':['resolve container iterator value to pool method and preserve template substitution',
                   'complete early-exit and switch fallthrough conditions','qualify shared-state instance identity',
                   'D02 response production/unpack/consumer/state propagation','D03 field/resource reverse influence with request context',
                   'D05 consolidated gaps and full P3 storage verification','register cross-module P7 case'],
      'file_hash_verification':'not_run_per_user_preference'}


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--graph',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();result=score(json.loads(a.graph.read_text(encoding='utf-8')))
    if a.output.exists():raise ValueError('Use a new output file')
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'assertions':result['assertions'],'counts':result['counts'],'gates':result['gates']}))
