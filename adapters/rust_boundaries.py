"""Rust boundary facts bound to native library declarations and source receivers."""
from collections import defaultdict


def augment(graph):
    nodes={n['id']:n for n in graph['nodes']};edges=graph['edges'];out=defaultdict(list);apis=defaultdict(list)
    for edge in edges:
        out[edge['source']].append(edge)
        if edge['kind']=='EXTERNAL_CALL_REFERENCE':
            for context in edge['analysis_contexts']:apis[(edge['source'],context)].append(nodes[edge['target']]['external_declaration'])
    boundaries={};constructors={};builder_calls=defaultdict(set)
    def emit(source,target,kind,context,**fields):
        edges.append({'source':source,'target':target,'kind':kind,'status':'source_candidate',
            'analysis_contexts':[context],'runtime_execution':'not_observed',
            'evidence':[{'path':nodes[source]['path'],'line':nodes[source]['line']}],**fields})
    def api_kind(api):
        package=api.get('package');container=(api.get('container') or '').split('<')[0].split('::')[-1];name=api.get('name')
        if package=='std' and container=='Command':
            return {'new':'command_constructor','spawn':'process_start','output':'process_start','status':'process_start'}.get(name)
        if package=='std' and container=='Child':return {'kill':'process_stop','wait':'process_wait','try_wait':'process_wait'}.get(name)
        if package=='std' and container=='TcpListener' and name=='bind':return 'network_listener'
        if package=='std' and container=='TcpStream' and name=='connect':return 'network_client'
        if package=='wry' and container=='WebViewBuilder':
            return {'new':'webview_builder','with_url':'frontend_loader','with_custom_protocol':'resource_protocol_registration',
                'with_file_drop_handler':'ui_event_registration'}.get(name)
        if package=='std' and api.get('canonical')=='std::fs::read':return 'file_read'
        return None
    for (call,context),candidates in apis.items():
        node=nodes[call]
        for api in candidates:
            family=api_kind(api)
            if not family:continue
            uid=call+':boundary:'+family
            if uid not in nodes:
                nodes[uid]={'id':uid,'kind':'rust_boundary','name':node['name'],'path':node['path'],'line':node['line'],
                    'column':node['column'],'language':'rust','family':family,'call':call,
                    'arguments':node['arguments'],'receiver':node.get('receiver'),'analysis_contexts':[],
                    'conditions':node['conditions'],'api_declarations':[],'runtime_execution':'not_observed',
                    'counterpart_status':'requires_artifact_instance_and_deployment_context'}
            if context not in nodes[uid]['analysis_contexts']:nodes[uid]['analysis_contexts'].append(context)
            if api not in nodes[uid]['api_declarations']:nodes[uid]['api_declarations'].append(api)
            boundaries[(call,context,family)]=uid;emit(call,uid,'DECLARES_BOUNDARY',context)
            if family in {'command_constructor','webview_builder'}:constructors[(call,context)]=uid
    def roots(value,context,family):
        pending=[value] if value else [];seen=set();found=set()
        while pending and len(seen)<300:
            current=pending.pop()
            if current in seen:continue
            seen.add(current);node=nodes[current]
            if (current,context) in constructors:
                target=constructors[(current,context)]
                if nodes[target]['family']==family:found.add(target)
                continue
            if node['kind']=='call_site':
                verified=any((a.get('package')=='std' and (a.get('container') or '').split('<')[0]=='Command' and
                    a.get('name') in {'arg','args','env','envs','current_dir','creation_flags','stdin','stdout','stderr'}) or
                    (a.get('package')=='wry' and (a.get('container') or '').split('<')[0]=='WebViewBuilder' and
                     a.get('name','').startswith('with_')) for a in apis.get((current,context),[]))
                if verified and node.get('receiver'):pending.append(node['receiver'])
            for edge in out.get(current,[]):
                if edge.get('analysis_contexts') and context not in edge['analysis_contexts']:continue
                if (edge['kind'] in {'READS_BINDING','VALUE_SOURCE','PATTERN_VALUE_SOURCE'} or
                    edge['kind']=='VALUE_COMPONENT' and node.get('syntax') in {'try_expression','reference_expression','parenthesized_expression'}):
                    pending.append(edge['target'])
        return found
    for (call,context),declarations in apis.items():
        node=nodes[call]
        for root in roots(node.get('receiver'),context,'command_constructor'):builder_calls[(root,context)].add(call)
    for (call,context,family),boundary in boundaries.items():
        node=nodes[call];record=nodes[boundary]
        if family=='command_constructor':
            for value in node['arguments'][:1]:emit(boundary,value,'COMMAND_PROGRAM',context)
        elif family=='process_start':
            for constructor in roots(node.get('receiver'),context,'command_constructor'):
                emit(boundary,constructor,'USES_COMMAND',context)
                for option in sorted(builder_calls[(constructor,context)]):
                    other=nodes[option]
                    if other['path']==node['path'] and other['start_byte']<=node['start_byte']:
                        for argument in other['arguments']:emit(boundary,argument,'COMMAND_OPTION_SOURCE',context,
                            option_call=option,conditions=other['conditions'],ordering='source_order_not_runtime_order')
        elif family in {'frontend_loader','resource_protocol_registration','ui_event_registration'}:
            owners=roots(node.get('receiver'),context,'webview_builder')
            record.setdefault('builder_candidates',[])
            record['builder_candidates']=sorted(set(record['builder_candidates'])|owners)
            for owner in owners:emit(owner,boundary,'CONFIGURES_WEBVIEW',context)
            for edge in out[call]:
                if edge['kind']=='PASSES_CALLBACK' and context in edge['analysis_contexts']:
                    emit(boundary,edge['target'],'CAN_DISPATCH_TO',context,condition='registered_event_or_protocol_matches')
            for value in node['arguments']:emit(boundary,value,'BOUNDARY_ARGUMENT',context)
        elif family in {'network_listener','network_client','file_read'}:
            for value in node['arguments']:emit(boundary,value,'BOUNDARY_ARGUMENT',context)
    graph['nodes']=list(nodes.values());return graph
