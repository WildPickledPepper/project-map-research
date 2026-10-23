"""Compose field writes through source argument bindings, retaining call contexts."""
from collections import defaultdict


def explain_writes(graph,source_symbol,max_depth=8,max_effects=2000):
    data=graph['data']['field_flow'];locations={x['id']:x for x in data['locations']};roots={x['id']:x for x in data['roots']}
    writes=defaultdict(list);calls=defaultdict(list);gaps=[]
    for w in data['writes']:writes[w['source_symbol']].append(w)
    for c in data['calls']:calls[c['source_symbol']].append(c)
    unresolved=defaultdict(list)
    for d in data['diagnostics']:unresolved[d['source_symbol']].append(d)
    count=0;truncated=False

    def visit(uid,stack,depth):
        nonlocal count,truncated
        if uid in stack or depth>max_depth:
            truncated=True;gaps.append({'kind':'recursive_or_depth_limited','source_symbol':uid});return []
        result=[];gaps.extend(unresolved[uid])
        for w in writes[uid]:
            if count>=max_effects:truncated=True;break
            count+=1;loc=locations[w['location']]
            result.append({'write':w['id'],'writer':uid,'root':loc['root'],'selectors':loc['selectors'],
                'value_origins':[{'root':locations[lid]['root'],'selectors':locations[lid]['selectors']} if lid else None for lid in w.get('value_locations',[])],
                'values':w.get('values',[]),
                'offset':w.get('offset'),
                'operation':w['operation'],'evidence':w['evidence'],'call_chain':[],
                'condition_scopes':[{'source_symbol':uid,'conditions':w['conditions']}],
                'status':'source_effect_candidate','runtime_execution':'unknown'})
        for call in calls[uid]:
            if count>=max_effects:truncated=True;break
            by_target=defaultdict(list)
            for b in call['bindings']:by_target[b['target']].append(b)
            for target,bindings in by_target.items():
                for child in visit(target,stack|{uid},depth+1):
                    formal=roots[child['root']]
                    if formal['kind']!='parameter' or formal['const']:continue
                    if formal['mode']=='pointer' and (not child['selectors'] or child['selectors'][0]!='pointee'):continue
                    for binding in bindings:
                        if binding['parameter']!=child['root']:continue
                        if binding['actual'] is None:
                            gaps.append({'kind':'argument_location_unresolved','call_site':call['id'],'parameter':child['root']});continue
                        actual=locations[binding['actual']];selectors=child['selectors']
                        if binding['address_of'] and formal['mode']=='pointer':selectors=selectors[1:]
                        value_origins=[]
                        for origin in child.get('value_origins',[]):
                            if not origin:value_origins.append(None);continue
                            candidate=[b for b in call.get('value_bindings',call['bindings']) if b['target']==target and b['parameter']==origin['root']]
                            if not candidate:value_origins.append(origin);continue
                            source_binding=candidate[0];source=locations.get(source_binding['actual'])
                            if not source:value_origins.append(None);continue
                            suffix=origin['selectors']
                            if source_binding['address_of'] and suffix and suffix[0]=='pointee':suffix=suffix[1:]
                            value_origins.append({'root':source['root'],'selectors':source['selectors']+suffix})
                        result.append({**child,'root':actual['root'],'selectors':actual['selectors']+selectors,
                            'value_origins':value_origins,
                            'call_chain':[{'call_site':call['id'],'caller':uid,'callee':target,'parameter_index':binding['index'],
                                'offset':call.get('offset'),
                                'actual':binding['actual'],'evidence':call['evidence'],'runtime_target':'unknown'},*child['call_chain']],
                            'condition_scopes':[{'source_symbol':uid,'call_site':call['id'],'conditions':call['conditions']},*child['condition_scopes']]})
        return result

    effects=visit(source_symbol,set(),0)
    return {'source_symbol':source_symbol,'effects':effects,'roots':[roots[r] for r in sorted({e['root'] for e in effects})],
        'truncated':truncated,'max_depth':max_depth,'max_effects':max_effects,'gaps':gaps,'limits':data['limits'],
        'runtime_execution':'unknown'}
