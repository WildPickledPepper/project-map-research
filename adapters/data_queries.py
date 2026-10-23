"""Explain receiver factories and state dependencies from extracted records."""
from collections import deque


def walk_values(value):
    if isinstance(value,dict):
        yield value
        for item in value.values():yield from walk_values(item)
    elif isinstance(value,list):
        for item in value:yield from walk_values(item)


def explain_receiver(graph,call_id,max_depth=5,max_functions=100):
    data=graph['data'];summaries={s['source_symbol']:s for s in data['summaries']}
    matches=[(s,c) for s in data['summaries'] for c in s['calls'] if c['call_site']==call_id]
    if len(matches)!=1:raise ValueError('Expected one C++ source call ID')
    owner,call=matches[0];receiver=call['receiver']
    roots={target for value in walk_values(receiver) for target in value.get('targets',[])}
    reached=set();truncated=False;pending=deque((i,0) for i in sorted(roots))
    while pending:
        uid,depth=pending.popleft()
        if uid in reached:continue
        if depth>max_depth or len(reached)>=max_functions:truncated=True;continue
        reached.add(uid)
        for c in summaries.get(uid,{}).get('calls',[]):
            pending.extend((target,depth+1) for target in c['targets'])
    accesses=data['accesses'];storages={s['id']:s for s in data['storages']}
    reads=[a for a in accesses if a['role']=='read' and a['source_symbol'] in reached]
    storage_ids={a['storage'] for a in reads};writers=[a for a in accesses if a['role']=='write' and a['storage'] in storage_ids]
    allocations={a['id']:a for a in data['allocations']};factories=[]
    for writer in writers:
        roots=[e['target'] for e in graph['edges'] if e['source']==writer['id'] and e['kind']=='STORED_ALLOCATION_CANDIDATE']
        for root in roots:
            factory=allocations[root]
            products=[a for a in allocations.values() if a['enclosing_allocation']==root]
            bindings=[b for b in data['callbacks'] if b['kind']=='bind_constructor_parameter' and b['owner'] in factory['type_candidates']]
            invocations=[b for b in data['callbacks'] if b['kind']=='invoke' and b['member'] in {x['member'] for x in bindings}]
            summary=summaries[writer['source_symbol']]
            control_targets={target for value in walk_values(summary['controls']) for target in value.get('targets',[])}
            state_reads=[a for a in accesses if a['role']=='read' and a['source_symbol'] in control_targets]
            state_writes=[a for a in accesses if a['role']=='write' and a['storage'] in {r['storage'] for r in state_reads}]
            factories.append({'storage':writer['storage'],'write':writer,'allocation':factory,'callback_products':products,
                'callback_bindings':bindings,'callback_invocations':invocations,'control_inputs':summary['controls'],
                'control_state_reads':state_reads,'control_state_writes':state_writes})
    nodes={n['id']:n for n in graph['nodes']};seen=set();pending=[call_id];implementations=[]
    while pending:
        uid=pending.pop()
        if uid in seen:continue
        seen.add(uid)
        n=nodes[uid]
        if n.get('definition') and uid!=call_id:
            cls=n['name'].rsplit('::',1)[0]
            evidence=[{'storage':f['storage'],'allocation':p['id'],'conditions':p['conditions']} for f in factories
                      for p in [f['allocation'],*f['callback_products']] if cls in p['type_candidates']]
            implementations.append({'id':uid,'name':n['name'],'path':n['path'],'line':n['line'],'factory_support':evidence,
                                    'runtime_selection':'unknown'})
        pending.extend(e['target'] for e in graph['edges'] if e['source']==uid and e['kind'] in {'MEMBER_TARGET_CANDIDATE','OVERRIDE_CANDIDATE','DECLARES_DEFINITION'})
    return {'call':call,'owner':owner['source_symbol'],'receiver':receiver,
            'producer_functions':[{'id':s,'name':summaries[s]['name'],'returns':summaries[s]['returns']} for s in sorted(reached) if s in summaries],
            'storages':[storages[i] for i in sorted(storage_ids)],'reads':reads,'factory_candidates':factories,
            'implementations':implementations,'truncated':truncated,'max_depth':max_depth,'max_functions':max_functions,
            'status':'source_candidates','runtime_selection':'unknown',
            'remaining_conditions':['same_live_pool_instance_and_key','factory_callback_invoked_successfully','database_open_succeeds',
                                    'pool_not_replaced_or_released','runtime_data_type_and_request_values'],
            'limits':data['limits']}
