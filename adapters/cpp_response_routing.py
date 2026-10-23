"""Extract parameter-scoped registry selection and callback invocation facts.

Reuses lexical/type candidates and object locations. Application registry,
callback, field and command names are source inputs, never matching rules.
"""
from copy import deepcopy

from adapters.cpp_data import arguments,enclosing_function
from adapters.cpp_facts import declared_name
from adapters.cpp_control import predicates
from adapters.syntax_supplement import identity,text,walk


class ResponseRouting:
    def __init__(self,data,flow,protocol):
        self.d=data;self.x=data.x;self.flow=flow;self.p=protocol
        self.p.collect_field_writes()
        self.returners={r['source_symbol'] for r in self.p.lookups}
        changed=True
        while changed:
            before=len(self.returners)
            for s in self.d.summaries:
                if any(set(c['targets'])&self.returners for c in s['calls']):self.returners.add(s['source_symbol'])
            changed=len(self.returners)!=before

    @staticmethod
    def unknown(reason):return {'kind':'unknown','reason':reason}

    def origin(self,node,uid,info,env=None,seen=None,depth=0):
        if node is None or depth>10:return self.unknown('missing_or_depth_limited')
        env=env or {};seen=seen or set();path=info['path'];kind=node.type
        recur=lambda n:self.origin(n,uid,info,env,seen,depth+1)
        evidence=self.d.evidence(path,node)
        if kind=='identifier':
            variables=self.x.variables(text(node),node,path,uid)
            if variables:
                var=variables[0];key=(path,var['node'].start_byte)
                if key in seen:return self.unknown('recursive_initializer')
                if var['value'] is not None:
                    init=self.p.local_initializer(text(node),node,info)
                    if init is None:return self.unknown('reassigned_or_unresolved_local')
                    return self.origin(init,uid,info,env,seen|{key},depth+1)
        if kind in {'identifier','field_expression','pointer_expression','parenthesized_expression'}:
            lid=self.flow.location(node,uid,info)
            if lid:
                location=self.flow.locations[lid];rid=location['root'];suffix=location['selectors']
                if rid in env:
                    actual=env[rid]
                    if actual['kind']!='location' and suffix:return self.unknown('field_of_non_location')
                    if actual['kind']=='location':return {**actual,'selectors':actual['selectors']+suffix,'evidence':actual.get('evidence',[])+[evidence]}
                    return actual
                return {'kind':'location','root':rid,'selectors':suffix,'evidence':[evidence]}
        if kind=='subscript_expression':
            field=self.d.receiver_field(node.child_by_field_name('argument'),uid,info)
            indices=node.child_by_field_name('indices');key=indices.named_children[0] if indices and indices.named_children else None
            if field and field['container'] in {'map','unordered_map'}:
                return {'kind':'registry_value','registry':field['owner']+'::'+field['name'],'key':recur(key),'evidence':[evidence]}
        if kind=='call_expression':
            fn=node.child_by_field_name('function');args=arguments(node)
            if text(fn)=='std::move' and len(args)==1:return recur(args[0])
            if fn and fn.type=='field_expression':
                receiver=fn.child_by_field_name('argument');method=text(fn.child_by_field_name('field'))
                field=self.d.receiver_field(receiver,uid,info)
                if field and field['container'] in {'map','unordered_map'} and method=='at' and len(args)==1:
                    return {'kind':'registry_value','registry':field['owner']+'::'+field['name'],'key':recur(args[0]),'evidence':[evidence]}
                if method=='value' and not args:
                    source=recur(receiver)
                    if source['kind']=='registry_value':return {**source,'evidence':[evidence,*source['evidence']]}
            candidates,_=self.flow.targets(node,uid,info);returns=[]
            for target in set(candidates)&self.returners:
                callee=self.x.functions_by_id[target]
                actuals={rid:recur(arg) for rid,arg in zip(self.flow.parameters[target],args)}
                for ret in walk(callee['container']):
                    if ret.type=='return_statement' and ret.named_children and enclosing_function(ret)==callee['container']:
                        value=self.origin(ret.named_children[0],target,callee,actuals,seen,depth+1)
                        if value['kind']=='registry_value':returns.append({**value,'evidence':[evidence,*value['evidence']]})
            # Multiple different registry/key alternatives remain unresolved.
            if returns:
                def semantic(v):return (v['registry'],v['key'].get('kind'),v['key'].get('root'),tuple(v['key'].get('selectors',[])),v['key'].get('value'))
                if all(semantic(v)==semantic(returns[0]) for v in returns):return returns[0]
                return self.unknown('ambiguous_registry_return')
        value,evidence=self.p.constant(node,path,info['scope'])
        if value is not None:return {'kind':'literal','value':value,'evidence':evidence}
        return self.unknown('unmodeled_registry_dependency')

    def build(self):
        selections=[];invocations=[]
        for uid,info in self.x.functions_by_id.items():
            if not self.x.nodes[uid]['definition']:continue
            for call in walk(info['container']):
                if call.type!='call_expression' or enclosing_function(call)!=info['container']:continue
                fn=call.child_by_field_name('function')
                if fn is None:continue
                record={'call_site':'cpp:'+identity(info['path'],'call_site',call),'source_symbol':uid,
                    'offset':call.start_byte,
                    'arguments':[self.flow.location(a,uid,info) for a in arguments(call)],
                    'conditions':predicates(call),'evidence':[self.d.evidence(info['path'],call)]}
                if fn.type=='field_expression':
                    selected=self.origin(fn.child_by_field_name('argument'),uid,info)
                    if selected['kind']=='registry_value':
                        selections.append({**record,'selection':selected,'targets':self.flow.targets(call,uid,info)[0]})
                if fn.type in {'identifier','call_expression','parenthesized_expression'}:
                    selected=self.origin(fn,uid,info)
                    if selected['kind']=='registry_value':invocations.append({**record,'selection':selected})
        return {'version':'0.1.0','selected_receiver_calls':selections,'callback_invocations':invocations,
            'decoded_fields':deepcopy(self.p.field_writes),'registrations':deepcopy(self.p.registrations),
            'limits':['source_registry_and_overload_candidates','registry_instances_require_selection_context',
                'unknown_keys_do_not_select_a_unique_callback','queue_and_deferred_delivery_not_expanded',
                'field_write_order_is_source_order_not_execution_proof']}
