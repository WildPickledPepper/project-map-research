"""Assessment only. Expected endpoint names never enter graph construction."""
from collections import Counter
from adapters.fact_queries import find_path
from adapters.protocol_graph import PROTOCOL_KINDS

CASES={
 'getUnitFlows':('unit/flows','Dic::Module::Timeline::QueryFlowsBySliceInfoHandler::HandleRequest'),
 'queryTimelineOffset':('timeline/rankOffset','Dic::Module::Timeline::RankOffsetHandler::HandleRequest'),
 'createCurve':('create/curve','Dic::Module::Timeline::CreateCurveHandler::HandleRequest'),
}


def score(graph):
    nodes={n['id']:n for n in graph['nodes']};cases={};endpoints={}
    def symbol(name):
        choices=[n for n in nodes.values() if n['kind']=='callable' and n['name']==name]
        definitions=[n for n in choices if n.get('definition')]
        choices=definitions or choices
        assert len(choices)==1,name
        return choices[0]['id']
    def brief(path):
        return {'found':path['found'],'reverse':path['reverse'],
          'nodes':[{k:n[k] for k in ['id','kind','name','path','line']} for n in path['nodes']],
          'edges':[{**{k:e[k] for k in ['source','target','kind','status']},'conditions':e.get('conditions',[]),
                    'evidence':[dict(path=v['path'],line=v['line']) for v in e['evidence'] if 'path' in v and 'line' in v]} for e in path['edges']]}
    for name,(command,handler) in CASES.items():
        result,=[r for r in graph['protocol']['results'] if r['name']==name]
        assert result['status']=='matched_conditional',(name,result)
        provider,=[p for p in graph['protocol']['providers'] if p['id']==result['matches'][0]['provider']]
        assert provider['command']==command and provider['scope_values']==['timeline']
        start=symbol(name);end=symbol(handler);endpoints[name]=(start,end)
        forward=find_path(graph,start,end,PROTOCOL_KINDS);reverse=find_path(graph,end,start,PROTOCOL_KINDS,reverse=True)
        assert forward['found'] and reverse['found']
        message=nodes[result['message']]
        assert message['payload']['fields']['moduleName']['value']=='timeline'
        assert message['payload']['fields']['command']['value']==command
        assert provider['decoded_key_status']=='source_mapping_candidate'
        cases[name]={'command':command,'provider':provider['id'],'status':result['status'],'payload':message['payload'],
                     'scope_fields':provider['scope_fields'],'command_fields':provider['command_fields'],
                     'forward':brief(forward),'reverse':brief(reverse),
                     'flow_event_kinds':dict(Counter(e['kind'] for e in message['flow_evidence']))}
    cross=[]
    for a,(start,_) in endpoints.items():
        for b,(_,end) in endpoints.items():
            if a==b:continue
            assert not find_path(graph,start,end,PROTOCOL_KINDS)['found']
            assert not find_path(graph,end,start,PROTOCOL_KINDS,reverse=True)['found']
            cross.append({'consumer':a,'other_handler':b,'forward_found':False,'reverse_found':False})
    return {'source_commit':graph['source_commit'],'snapshot':graph['snapshot'],'cases':cases,'cross_request_checks':cross,
      'counts':{'files':len(graph['input_paths']),'nodes':len(graph['nodes']),'edges':len(graph['edges']),
                'providers':len(graph['protocol']['providers']),'results':len(graph['protocol']['results']),
                'statuses':dict(Counter(r['status'] for r in graph['protocol']['results'])),
                'protocol_edge_kinds':dict(Counter(e['kind'] for e in graph['edges'] if e['kind'] in PROTOCOL_KINDS))},
      'remaining_results':[r for r in graph['protocol']['results'] if r['status']!='matched_conditional']}
