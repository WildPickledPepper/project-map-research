"""Compose response object transfers and scoped serializer registry selections."""
from collections import defaultdict
from copy import deepcopy
import json

from adapters.field_queries import explain_writes


def explain_response(graph,provider_id,max_depth=12,max_states=2000):
    if max_depth<1 or max_states<1:raise ValueError('query budgets must be positive')
    provider=next(p for p in graph['protocol']['providers'] if p['id']==provider_id)
    data=graph['data'];flow=data['field_flow'];routing=data['response_routing']
    roots={r['id']:r for r in flow['roots']};locs={r['id']:r for r in flow['locations']}
    nodes={n['id']:n for n in graph['nodes']};calls=defaultdict(list);invocations=defaultdict(list)
    selected={s['call_site']:s for s in routing['selected_receiver_calls'] if s['targets']}
    unresolved=defaultdict(list)
    callback_sites={c['call_site'] for c in routing['callback_invocations']}
    for d in flow['diagnostics']:
        if d.get('call_site') not in callback_sites:unresolved[d['source_symbol']].append(d)
    serializers={s['source_symbol']:s for s in data['serialization']['functions'] if s['field_mappings']}
    bases=defaultdict(set)
    for e in graph['edges']:
        if e['kind']=='INHERITS':bases[nodes[e['source']]['name']].add(nodes[e['target']]['name'])
    def lineage(name):
        todo=[name];found=set()
        while todo:
            n=todo.pop()
            if n in found:continue
            found.add(n);todo.extend(bases[n])
        return found
    def names(typ):
        while typ.get('name') in {'std::unique_ptr','std::shared_ptr'} and typ.get('arguments'):typ=typ['arguments'][0]
        return set(typ.get('names',[]))
    def compatible(actual,formal):
        a,b=names(actual),names(formal)
        return not a or not b or any(lineage(x)&b for x in a)
    for c in flow.get('transfers',[]):calls[c['source_symbol']].append(c)
    for c in routing['callback_invocations']:invocations[c['source_symbol']].append(c)
    callees={s['source_symbol']:{t for c in s['calls'] for t in c['targets']} for s in data['summaries']}
    decoder_reachable=set();todo=list(provider['decoder_registration'].get('functions',[]))
    while todo:
        uid=todo.pop()
        if uid in decoder_reachable:continue
        decoder_reachable.add(uid);todo.extend(callees.get(uid,[]))
    effects_cache={};gaps=[];routes=[];visited=0;truncated=False
    def effects(uid):
        if uid not in effects_cache:
            effects_cache[uid]=explain_writes(graph,uid,max_depth=max_depth)
            if effects_cache[uid]['truncated']:gaps.append({'kind':'field_effect_query_truncated','source_symbol':uid})
        return effects_cache[uid]['effects']
    def position(e):return e['call_chain'][0].get('offset') if e['call_chain'] else e.get('offset')
    def mapped(location,state):
        if not location or location['root']!=state['root']:return None
        suffix=location['selectors']
        if state.get('address_of'):
            if not suffix or suffix[0]!='pointee':return None
            suffix=suffix[1:]
        return tuple(state['prefix']+suffix)
    def literal(value):
        if value.get('kind') in {'string_literal','number_literal','true','false'}:
            try:return json.loads(value['expression'])
            except ValueError:return None
        return None
    def initial_values(handler):
        known={}
        for root in roots.values():
            if root['source_symbol']!=handler or root['kind']!='parameter':continue
            types=names(root['type']);prefix=['pointee'] if root['mode']=='pointer' or root['type'].get('name') in {'std::unique_ptr','std::shared_ptr'} else []
            for field in routing['decoded_fields']:
                if field['source_symbol'] not in decoder_reachable:continue
                if not any(lineage(t)&set(field['owner_types']) for t in types):continue
                choices=[]
                if set(field['wire_fields'])&set(provider['command_fields']):choices.append(provider['command'])
                if set(field['wire_fields'])&set(provider['scope_fields']):choices+=provider['scope_values']
                if choices:known[(root['id'],tuple(prefix+['member:'+field['member']]))]={'values':choices,'unknown':False,'evidence':field['evidence']}
        return known
    def values_at(state,call,request_values):
        values=deepcopy(state['values'])
        for e in sorted(effects(state['uid']),key=lambda e:position(e) if position(e) is not None else -1):
            offset=position(e)
            if offset is None or offset>=call['offset']:continue
            dest=mapped(e,state)
            if dest is None:continue
            value=None
            if len(e.get('value_origins',[]))==1 and e['value_origins'][0]:
                origin=e['value_origins'][0];source=mapped(origin,state)
                value=values.get(source) if source is not None else request_values.get((origin['root'],tuple(origin['selectors'])))
            if value is None and len(e.get('values',[]))==1:
                scalar=literal(e['values'][0])
                if scalar is not None:value={'values':[scalar],'unknown':False,'evidence':[]}
            value=deepcopy(value) if value else {'values':[],'unknown':True,'evidence':[]}
            value['evidence']+=e['evidence']
            # Branch feasibility is retained, never inferred from source order.
            conditional=any(c.get('kind') in {'branch','switch','loop'} for scope in e['condition_scopes'] for c in scope['conditions'])
            if conditional:
                old=values.get(dest,{'values':[],'unknown':True,'evidence':[]})
                value={'values':list(dict.fromkeys(old['values']+value['values'])),'unknown':old['unknown'] or value['unknown'],'evidence':old['evidence']+value['evidence']}
            values[dest]=value
        return values
    def key_value(selection,state,values):
        key=selection['key']
        if key['kind']=='literal':return {'values':[key['value']],'unknown':False,'evidence':key['evidence']}
        location=mapped(key,state) if key['kind']=='location' else None
        return values.get(location,{'values':[],'unknown':True,'evidence':[]})
    def unique(value):return value['values'][0] if not value['unknown'] and len(value['values'])==1 else None
    for handler in provider['handler_methods']:
        request_values=initial_values(handler);production=effects(handler)
        origin_roots=sorted({e['root'] for e in production if roots[e['root']]['source_symbol']==handler})
        for origin_root in origin_roots:
            pending=[{'uid':handler,'root':origin_root,'prefix':[],'values':{},'steps':[],'protocol_owner':None}]
            while pending:
                state=pending.pop();visited+=1
                if visited>max_states:truncated=True;gaps.append({'kind':'response_state_budget_exhausted'});pending.clear();break
                if len(state['steps'])>=max_depth:truncated=True;gaps.append({'kind':'response_depth_limit','source_symbol':state['uid']});continue
                for diagnostic in unresolved[state['uid']]:
                    if any(mapped(locs.get(a),state) is not None for a in diagnostic.get('arguments',[])):
                        gaps.append({'kind':diagnostic['kind'],'source_symbol':state['uid'],'object_root':origin_root,
                            'evidence':diagnostic['evidence'],'conditions':diagnostic.get('conditions',[])})
                for call in invocations[state['uid']]:
                    values=values_at(state,call,request_values);key=key_value(call['selection'],state,values);command=unique(key)
                    if command is None:
                        gaps.append({'kind':'callback_key_unknown','call_site':call['call_site']});continue
                    owner=state['protocol_owner']
                    for registration in data['serialization']['registrations']:
                        if registration['registry']!=call['selection']['registry'] or registration['key']!=command or registration['owner']!=owner:continue
                        for callback in set(registration['functions'])&set(serializers):
                            mappings=[];links=[]
                            for m in serializers[callback]['field_mappings']:
                                i=m['source']['parameter']
                                actual=locs.get(call['arguments'][i]) if i<len(call['arguments']) else None
                                prefix=mapped(actual,state)
                                if prefix is None:continue
                                selectors=prefix+tuple(m['source']['selectors'])
                                mappings.append({'wire_path':m['wire_path'],'selectors':list(selectors),'relation':m['relation'],
                                    'conditions':m['conditions'],'evidence':m['evidence']})
                                first=state['steps'][0]['offset'] if state['steps'] else call['offset']
                                for e in production:
                                    p=tuple(e['selectors'])
                                    if e['root']==origin_root and selectors[:len(p)]==p and position(e) is not None and position(e)<first:
                                        links.append({'write':e['write'],'writer':e['writer'],'wire_path':m['wire_path'],'selectors':e['selectors'],
                                            'conditions':e['condition_scopes'],'evidence':e['evidence'],'production_calls':e['call_chain']})
                            if not mappings:continue
                            links=list({json.dumps([x['write'],x['wire_path']],sort_keys=True):x for x in links}.values())
                            routes.append({'handler':handler,'object_root':origin_root,'serializer':callback,'protocol_owner':owner,
                                'steps':state['steps']+[{'call_site':call['call_site'],'caller':state['uid'],'callee':callback,
                                    'kind':'registered_callback','evidence':call['evidence']+call['selection']['evidence']+registration['evidence']+key['evidence'],
                                    'conditions':call['conditions'],'key':command,'registry':registration['registry']}],
                                'field_mappings':mappings,'production_links':links,'runtime_execution':'unknown',
                                'conditions':['provider_request_identity','source_overload_and_virtual_candidates','selected_protocol_instance_matches_factory_group',
                                    'no_intervening_unmodeled_mutation','source_write_precedes_send_does_not_prove_reaching_value']})
                for call in calls[state['uid']]:
                    candidates=[b for b in call['bindings'] if mapped(locs.get(b['actual']),state) is not None]
                    if not candidates:continue
                    values=values_at(state,call,request_values);owner=state['protocol_owner'];selection_evidence=[]
                    if call['id'] in selected:
                        selected_call=selected[call['id']];key=key_value(selected_call['selection'],state,values);scope=unique(key)
                        registries={r['registry'] for r in provider['scope_registrations']}
                        if selected_call['selection']['registry'] not in registries:continue
                        if scope is None:gaps.append({'kind':'protocol_scope_key_unknown','call_site':call['id']});continue
                        if scope not in provider['scope_values']:continue
                        component=[c for c in provider['factory_group']['components'] if c['class']==provider['decoder_registration']['owner']]
                        registrations=[r for r in provider['scope_registrations'] if r['registry']==selected_call['selection']['registry'] and r['factory_method'] in {c['method'] for c in component}]
                        if len(component)!=1 or not registrations:continue
                        owner=component[0]['class'];selection_evidence=selected_call['selection']['evidence']+key['evidence']+component[0]['evidence']
                    for b in candidates:
                        actual=locs[b['actual']];formal=roots[b['parameter']]
                        if not compatible(actual['type'],formal['type']):continue
                        if any(step['caller']==b['target'] for step in state['steps']):continue
                        step={'call_site':call['id'],'caller':state['uid'],'callee':b['target'],'parameter_index':b['index'],
                            'actual':b['actual'],'formal':b['parameter'],'offset':call['offset'],'kind':'argument_transfer',
                            'mode':formal['mode'],'conditions':call['conditions'],'evidence':call['evidence']+selection_evidence}
                        pending.append({'uid':b['target'],'root':b['parameter'],'prefix':list(mapped(actual,state)),
                            'address_of':b['address_of'],'values':values,'steps':state['steps']+[step],'protocol_owner':owner})
            if truncated and visited>max_states:break
    return {'snapshot':graph['snapshot'],'source_commit':graph['source_commit'],'provider':provider_id,
        'status':'source_response_route_candidate' if routes else 'unresolved','routes':routes,
        'gaps':list({json.dumps(g,sort_keys=True):g for g in gaps}.values()),
        'visited_states':visited,'max_states':max_states,'max_depth':max_depth,
        'truncated':truncated or any(r['truncated'] for r in effects_cache.values()),
        'limits':routing['limits'],'runtime_delivery':'unknown'}
