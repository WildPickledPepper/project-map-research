"""Import-bound Python API boundaries and ownership joins over normalized facts.

Rules name library APIs, not project symbols. Unknown values retain expressions;
only a shared source object establishes application/runner/route ownership.
"""
from collections import defaultdict

CONSTRUCTORS={'aiohttp.web.Application','aiohttp.web.AppRunner','aiohttp.web.TCPSite',
              'aiohttp.ClientSession','aiohttp.web.WebSocketResponse','subprocess.Popen'}
PROCESS_START={'subprocess.Popen','subprocess.run','subprocess.call','subprocess.check_call','subprocess.check_output',
               'asyncio.create_subprocess_exec','asyncio.create_subprocess_shell'}
PROCESS_STOP={'subprocess.Popen.terminate','subprocess.Popen.kill','subprocess.Popen.wait'}
NETWORK_CLIENT={'aiohttp.ClientSession.ws_connect','aiohttp.ClientSession.request','aiohttp.ClientSession.get',
                'aiohttp.ClientSession.post','websockets.connect'}
NETWORK_LISTENER={'aiohttp.web.TCPSite','asyncio.start_server','websockets.serve'}
ROUTES={'aiohttp.web.Application.router.add_'+verb for verb in ('route','get','post','put','patch','delete','head','options')}
FLOW={'READS_BINDING','VALUE_SOURCE','CONTEXT_VALUE_SOURCE','DEFAULT_VALUE'}


class Boundaries:
    def __init__(self,facts):
        self.facts=facts;self.nodes={n['id']:n for n in facts['nodes']};self.out=defaultdict(list);self.incoming=defaultdict(list)
        self.boundaries={}
        for edge in facts['edges']:
            self.out[edge['source']].append(edge);self.incoming[edge['target']].append(edge)

    def targets(self,uid,kinds):
        result=[e['target'] for e in self.out[uid] if e['kind'] in kinds]
        if 'BINDS_ARGUMENT' in kinds:result.extend(e['source'] for e in self.incoming[uid] if e['kind']=='BINDS_ARGUMENT')
        return result

    def api(self,uid,seen=None):
        seen=set() if seen is None else seen
        if uid in seen:return set()
        seen=seen|{uid};node=self.nodes[uid];result=set()
        if node['kind']=='module_reference':
            if node['resolution'].startswith('source_') or node.get('level'):return result
            if node['syntax']=='Import':result.add(node['imported_name'] if node.get('aliased') else node['imported_name'].split('.')[0])
            else:result.add('.'.join(p for p in (node.get('module'),node['imported_name']) if p))
        elif node['kind']=='call_site':
            # Return type is modeled only for the library constructors listed above.
            for target in self.targets(uid,{'CALLS_EXPRESSION'}):result.update(self.api(target,seen)&CONSTRUCTORS)
        elif node.get('member'):
            for edge in self.out[uid]:
                if edge['kind']=='VALUE_COMPONENT' and edge.get('field')=='value':
                    result.update(name+'.'+node['member'] for name in self.api(edge['target'],seen))
        for target in self.targets(uid,FLOW|{'BINDS_ARGUMENT'}):result.update(self.api(target,seen))
        return result

    def called_api(self,uid):
        return set().union(*(self.api(t) for t in self.targets(uid,{'CALLS_EXPRESSION'})))

    def argument(self,uid,index,keywords=()):
        args=[e for e in self.out[uid] if e['kind']=='CALL_ARGUMENT']
        by_keyword=[e['target'] for e in args if e.get('keyword') in keywords and e.get('keyword') is not None]
        return by_keyword or [e['target'] for e in args if e.get('index')==index and e.get('keyword') is None]

    def origins(self,uid,constructors,seen=None):
        seen=set() if seen is None else seen
        if uid in seen:return set()
        seen=seen|{uid};node=self.nodes[uid]
        if node['kind']=='call_site':
            apis=self.called_api(uid)
            if apis&constructors:return {uid}
            if apis&{'aiohttp.web.AppRunner','aiohttp.web.TCPSite'}:
                return set().union(*(self.origins(t,constructors,seen) for t in self.argument(uid,0,('app','runner'))))
        return set().union(*(self.origins(t,constructors,seen) for t in self.targets(uid,FLOW|{'BINDS_ARGUMENT'})))

    def callbacks(self,uid,seen=None):
        seen=set() if seen is None else seen
        if uid in seen:return set()
        seen=seen|{uid};node=self.nodes[uid]
        if node['kind'] in {'callable','type'}:return {uid}
        if node['kind']=='call_site' and 'functools.partial' in self.called_api(uid):
            return set().union(*(self.callbacks(t,seen) for t in self.argument(uid,0)))
        children=self.targets(uid,FLOW|{'BINDS_ARGUMENT','IMPORTS_SYMBOL'})
        if node.get('expression_kind')=='IfExp':
            children.extend(e['target'] for e in self.out[uid] if e['kind']=='VALUE_COMPONENT' and e.get('field') in {'body','orelse'})
        return set().union(*(self.callbacks(t,seen) for t in children))

    def edge(self,source,target,kind,status='conditional_source',**extra):
        node=self.nodes[source]
        self.facts['edges'].append({'source':source,'target':target,'kind':kind,'status':status,
            'evidence':[{k:node[k] for k in ('path','line','column')}],'runtime_execution':'not_observed',**extra})

    def build(self):
        for call in list(self.nodes.values()):
            if call['kind']!='call_site':continue
            uid=call['id'];apis=self.called_api(uid)
            matches=[('process_start',apis&PROCESS_START),('process_stop',apis&PROCESS_STOP),
                     ('network_client',apis&NETWORK_CLIENT),('network_listener',apis&NETWORK_LISTENER),('route_registration',apis&ROUTES)]
            for family,selected in matches:
                if not selected:continue
                bid=uid+':boundary:'+family
                node={'id':bid,'kind':'python_boundary','family':family,'name':call['name'],
                    **{k:call[k] for k in ('path','line','column','language','conditions')},
                    'call':uid,'api_candidates':sorted(selected),'evidence_kind':'import_binding_and_ast_value_flow',
                    'resolution':'source_api_reference','runtime_execution':'not_observed',
                    'counterpart_status':'pending_identity_and_context',
                    'arguments':[{k:e[k] for k in ('target','index','keyword','spread') if k in e} for e in self.out[uid] if e['kind']=='CALL_ARGUMENT']}
                self.nodes[bid]=node;self.facts['nodes'].append(node);self.boundaries[bid]=node
                self.edge(uid,bid,'DECLARES_BOUNDARY')
                if family=='network_client':node['address_values']=self.argument(uid,0,('url','uri','str_or_url'))
                elif family=='process_start':node['command_values']=self.argument(uid,0,('args','program','cmd'))
                elif family=='network_listener':
                    if 'aiohttp.web.TCPSite' in selected:
                        node['host_values']=self.argument(uid,1,('host',));node['port_values']=self.argument(uid,2,('port',))
                        node['applications']=sorted(set().union(*(self.origins(t,{'aiohttp.web.Application'}) for t in self.argument(uid,0,('runner',)))))
                    else:
                        node['handler_values']=self.argument(uid,0,('client_connected_cb','ws_handler','handler'))
                elif family=='route_registration':
                    # Attribute(value=app.router, attr=add_*) retains exact app value identity.
                    callee=self.targets(uid,{'CALLS_EXPRESSION'})
                    receiver=[e['target'] for t in callee for e in self.out[t] if e['kind']=='VALUE_COMPONENT' and e.get('field')=='value']
                    apps=[]
                    for receiver_value in receiver:
                        apps.extend(e['target'] for e in self.out[receiver_value] if e['kind']=='VALUE_COMPONENT' and e.get('field')=='value')
                    node['applications']=sorted(set().union(*(self.origins(t,{'aiohttp.web.Application'}) for t in apps)))
                    is_route=any(a.endswith('.add_route') for a in selected)
                    node['route_values']=self.argument(uid,1 if is_route else 0,('path',))
                    node['handler_values']=self.argument(uid,2 if is_route else 1,('handler',))
                for value in node.get('handler_values',[]):
                    for handler in sorted(self.callbacks(value)):
                        self.edge(bid,handler,'CAN_DISPATCH_TO',basis='framework_callback_argument',
                                  condition='owning_listener_route_and_runtime_request_must_match')
        listeners=[b for b in self.boundaries.values() if b['family']=='network_listener']
        routes=[b for b in self.boundaries.values() if b['family']=='route_registration']
        for listener in listeners:
            for route in routes:
                common=set(listener.get('applications',[]))&set(route.get('applications',[]))
                if common:self.edge(listener['id'],route['id'],'EXPOSES_ROUTE',application_sources=sorted(common))
        starts={b['call']:b for b in self.boundaries.values() if b['family']=='process_start'}
        for boundary in self.boundaries.values():
            if boundary['family']!='process_stop':continue
            callee=self.targets(boundary['call'],{'CALLS_EXPRESSION'})
            receivers=[e['target'] for t in callee for e in self.out[t] if e['kind']=='VALUE_COMPONENT' and e.get('field')=='value']
            for receiver in receivers:
                for origin in self.origins(receiver,{'subprocess.Popen'}):
                    if origin in starts:self.edge(boundary['id'],starts[origin]['id'],'USES_PROCESS_HANDLE',status='candidate',
                        receiver_value=receiver,identity_basis='source_handle_flow_requires_runtime_instance_context')
        return self.facts


def augment(facts):
    return Boundaries(facts).build()
