"""Join source-derived message identities, with explicit deployment scope.

The configuration binds source roots to services, never commands to handlers.
Each message has its own stages: shared send functions cannot fan out queries.
"""
from copy import deepcopy

PROTOCOL_KINDS={'EMITS_MESSAGE','MATCHES_REGISTERED_PROTOCOL','DECODES_MESSAGE',
                'DISPATCHES_REGISTERED_HANDLER','RESOLVES_HANDLER'}


def services_for(path,config,role):
    return sorted({s['id'] for s in config.get('services',[]) for prefix in s.get(role+'_paths',[])
                   if path==prefix.rstrip('/') or path.startswith(prefix.rstrip('/')+'/')})


def field_value(payload,fields):
    if len(fields)!=1:return None,'field_identity_unresolved'
    value=payload.get('fields',{}).get(fields[0],{})
    if value.get('state')!='constant':return None,'value_unknown_or_absent'
    return value.get('value'),None


def match_message(message,providers,config):
    source_services=services_for(message.get('receiver_scope',message['path']),config,'consumer')
    matches=[];unknown=[]
    for p in providers:
        target_services=services_for(p['path'],config,'provider')
        if source_services and target_services and not set(source_services)&set(target_services):continue
        command,reason=field_value(message['payload'],p['command_fields'])
        if reason:unknown.append({'provider':p['id'],'reason':reason});continue
        if command!=p['command']:continue
        scope,reason=field_value(message['payload'],p['scope_fields'])
        if not reason and p['scope_values'] and scope not in p['scope_values']:continue
        conditions=['configured_service_binding','source_registration_active','runtime_transport_reaches_configured_service',
                    'source_type_and_factory_candidates','request_passes_validation_and_filters',*message.get('conditions',[])]
        gaps=[]
        if len(source_services)!=1 or len(target_services)!=1:gaps.append('service_scope_unknown_or_ambiguous')
        if reason or len(p['scope_values'])!=1:gaps.append('module_scope_unknown_or_ambiguous')
        if p['status']!='registered_candidate':gaps.append(p['status'])
        if p.get('decoded_key_status')!='source_mapping_candidate':gaps.append('decoded_dispatch_key_mapping_unresolved')
        if not p['handler_methods']:gaps.append('handler_body_outside_input_or_unresolved')
        matches.append({'provider':p['id'],'conditions':conditions,'gaps':gaps,
                        'consumer_services':source_services,'provider_services':target_services})
    if len(matches)>1:status='ambiguous'
    elif matches:status='candidate' if matches[0]['gaps'] else 'matched_conditional'
    else:status='unknown' if unknown else 'unmatched'
    return {'status':status,'matches':matches,'unknown_identities':unknown,
            'service_binding_origin':'supplied_deployment_config','runtime_connection':'not_observed'}


def augment(graph,typescript,cpp,config):
    graph=deepcopy(graph);nodes=graph['nodes'];edges=graph['edges'];known={n['id'] for n in nodes}
    providers=cpp['providers'];by_provider={p['id']:p for p in providers};results=[]
    def node(uid,kind,name,path,line,**extra):
        if uid not in known:nodes.append(dict(id=uid,kind=kind,name=name,path=path,line=line,**extra));known.add(uid)
        return uid
    def edge(a,b,kind,evidence,**extra):
        edges.append(dict(source=a,target=b,kind=kind,status='conditional',evidence=evidence,**extra))
    for consumer in typescript['consumers']:
        boundaries=[b for b in consumer['boundaries'] if b['transport']=='socket']
        if not boundaries:
            results.append({'consumer':consumer['id'],'name':consumer['name'],'status':consumer['status'],'matches':[]});continue
        for index,message in enumerate(boundaries):
            mid=consumer['id']+':message:'+str(index)
            outcome=match_message(message,providers,config)
            results.append({'consumer':consumer['id'],'name':consumer['name'],'message':mid,**outcome})
            node(mid,'protocol_message',consumer['name']+' message',message['path'],message['line'],payload=message['payload'],
                 flow_evidence=message['events'],conditions=message['conditions'],resolution=outcome['status'])
            start=consumer['source_owner'] or consumer['source_call']
            edge(start,mid,'EMITS_MESSAGE',message['events'],conditions=message['conditions'])
            for match in outcome['matches']:
                p=by_provider[match['provider']];base=mid+':'+p['id']
                stage=node(base+':registration','protocol_registration',str(p['command']),p['path'],p['line'],
                    scope_values=p['scope_values'],scope_fields=p['scope_fields'],command_fields=p['command_fields'],
                    factory_evidence=p['factory_group'],scope_evidence=p['scope_lookups'],gaps=match['gaps'])
                edge(mid,stage,'MATCHES_REGISTERED_PROTOCOL',p['handler_registration']['evidence']+p['decoder_registration']['evidence'],
                     conditions=match['conditions'],gaps=match['gaps'],resolution=outcome['status'])
                d=p['decoder_registration'];decode=node(base+':decode','protocol_decoder',d['value_expression'],d['path'],d['line'],
                    source_symbols=d['functions'],key_mappings=p.get('decoded_key_mappings',[]))
                edge(stage,decode,'DECODES_MESSAGE',d['evidence'],conditions=['registered_decoder_selected','decoded_key_mapping_is_source_candidate'])
                h=p['handler_registration'];dispatch=node(base+':dispatch','protocol_dispatch',h['value_expression'],h['path'],h['line'])
                edge(decode,dispatch,'DISPATCHES_REGISTERED_HANDLER',h['evidence'],conditions=['decoded_request_preserves_registry_key'])
                for method in p['dispatch_evidence']:
                    edge(dispatch,method['id'],'RESOLVES_HANDLER',method['evidence'],conditions=['runtime_handler_instance_matches_registered_type'])
    graph['protocol']={'version':'0.2.0','deployment':config,'providers':providers,'results':results,
                       'diagnostics':typescript.get('diagnostics',[])+cpp.get('diagnostics',[]),
                       'limits':typescript['limits']+cpp['limits'],'traversal_kinds':sorted(PROTOCOL_KINDS)}
    return graph
