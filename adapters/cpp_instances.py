"""Source object identities and receiver contexts, without whole-program alias claims."""
from collections import defaultdict

from adapters.syntax_supplement import identity,parents,text,walk
from adapters.cpp_facts import declared_name


def borrowed_declaration(node):
    declarator=node.child_by_field_name('declarator')
    if not declarator:return False
    return any(n.type in {'reference_declarator','pointer_declarator','abstract_pointer_declarator'} for n in walk(declarator)
               if n.start_byte<(declarator.child_by_field_name('value').start_byte if declarator.child_by_field_name('value') else declarator.end_byte))


def extract_instances(data):
    x=data.x;objects={};accessors={};declarations={};direct={};calls={};method_contexts=defaultdict(set)
    def owner_of(node):return next((p for p in parents(node) if p.type in {'function_definition','lambda_expression'}),None)
    def add_object(uid,info,var,kind,typ=None):
        named=declared_name(var)
        if named is None:return None
        typ=typ or data.types.type(text(var.child_by_field_name('type')),info['path'],info['scope'])
        if typ.get('kind')!='object' or not typ.get('names'):return None
        oid='object:'+identity(info['path'],kind,var)
        objects[oid]={'id':oid,'kind':kind,'name':text(named),'owner_types':typ['names'],
            'source_symbol':uid,'path':info['path'],'line':var.start_point[0]+1,
            'identity_scope':'process_and_link_image' if kind=='static_local_object' else 'one_function_invocation',
            'evidence':[data.evidence(info['path'],var)]}
        declarations[(info['path'],var.start_byte)]=oid;return oid
    for uid,info in x.functions_by_id.items():
        if not x.nodes[uid]['definition']:continue
        for n in walk(info['container']):
            if n.type=='declaration' and owner_of(n)==info['container'] and any(c.type=='storage_class_specifier' and text(c)=='static' for c in n.children):
                add_object(uid,info,n,'static_local_object')
        returns=[n for n in walk(info['container']) if n.type=='return_statement' and owner_of(n)==info['container']]
        mode=next((p.type for p in parents(info['node']) if p.type in {'reference_declarator','pointer_declarator'} and p.end_byte<=info['container'].end_byte),None)
        if not mode or not returns:continue
        resolved=[]
        for ret in returns:
            value=ret.named_children[0] if ret.named_children else None
            if value and value.type=='pointer_expression' and text(value).lstrip().startswith('&'):value=value.named_children[-1]
            variables=x.variables(text(value),value,info['path'],uid) if value and value.type=='identifier' else []
            oid=declarations.get((info['path'],variables[0]['node'].start_byte)) if variables else None
            resolved.append(oid)
        if None not in resolved and len(set(resolved))==1:
            accessors[uid]={'source_symbol':uid,'instance':resolved[0],'return_mode':'pointer' if mode=='pointer_declarator' else 'reference',
                            'evidence':[data.evidence(info['path'],r) for r in returns]}

    def infer(node,uid,info,depth=0):
        if node is None or depth>8:return set()
        if node.type in {'parenthesized_expression','pointer_expression'}:return infer(node.named_children[-1],uid,info,depth+1) if node.named_children else set()
        if node.type=='call_expression':
            targets=data.targets(node,uid,info)
            if targets and all(t in accessors for t in targets):return {accessors[t]['instance'] for t in targets}
            return set()
        if node.type=='identifier':
            vs=x.variables(text(node),node,info['path'],uid)
            if not vs:return set()
            var=vs[0];key=(info['path'],var['node'].start_byte)
            if var['node'].type!='declaration':return set()
            if key in declarations:return {declarations[key]}
            if any(n.type=='assignment_expression' and text(n.child_by_field_name('left'))==text(node) and var['node'].end_byte<=n.start_byte<node.start_byte for n in walk(info['container'])):return set()
            if var['value'] is not None:
                value=var['value'];pointer_result=False
                if value.type=='call_expression':
                    targets=data.targets(value,uid,info)
                    pointer_result=bool(targets) and all(accessors.get(t,{}).get('return_mode')=='pointer' for t in targets)
                if borrowed_declaration(var['node']) or pointer_result or value.type=='pointer_expression':return infer(value,uid,info,depth+1)
            # An object value is a distinct local even when copied from an accessor.
            typ=data.types.infer(node,uid,info)
            if typ.get('kind')=='object' and typ.get('names'):
                oid=add_object(uid,info,var['node'],'local_object',typ)
                if oid:return {oid}
        return set()

    for uid,info in x.functions_by_id.items():
        if not x.nodes[uid]['definition']:continue
        for call in walk(info['container']):
            if call.type!='call_expression':continue
            cid='cpp:'+identity(info['path'],'call_site',call);fn=call.child_by_field_name('function')
            targets=data.targets(call,uid,info);receiver=fn.child_by_field_name('argument') if fn and fn.type=='field_expression' else None
            ids=infer(receiver,uid,info) if receiver else set()
            implicit=bool(fn and (fn.type=='identifier' or receiver is not None and text(receiver)=='this'))
            calls[cid]={'call_site':cid,'source_symbol':uid,'targets':targets,'instances':set(ids),'implicit_this':implicit,
                        'evidence':[data.evidence(info['path'],call)]}
            direct[cid]=set(ids)
            for target in targets:method_contexts[target].update(ids)
    # Only this-receiver calls propagate context; a differently named local
    # receiver cannot borrow an instance merely because its type matches.
    changed=True
    while changed:
        changed=False
        for call in calls.values():
            if not call['implicit_this']:continue
            for oid in list(method_contexts[call['source_symbol']]):
                owners=set(objects[oid]['owner_types'])
                for owner in list(owners):owners.update(x.base_names.get(owner,[]))
                for target in call['targets']:
                    if '::'.join(x.functions_by_id[target]['scope']) not in owners:continue
                    if oid not in call['instances']:call['instances'].add(oid);changed=True
                    if oid not in method_contexts[target]:method_contexts[target].add(oid);changed=True
    contexts=[{**c,'instances':sorted(c['instances']),'basis':'direct_receiver_source' if direct[cid] else 'propagated_this_receiver'}
              for cid,c in calls.items() if c['instances']]
    accesses=[]
    for access in data.accesses:
        for oid in sorted(method_contexts[access['source_symbol']]):
            accesses.append({'access':access['id'],'instance':oid,'source_symbol':access['source_symbol'],
                             'status':'source_context_candidate','instance_scope':objects[oid]['identity_scope']})
    return {'objects':list(objects.values()),'accessors':list(accessors.values()),'calls':contexts,'accesses':accesses,
            'closed_world':False,'limits':['unseen_callers_remain_unknown','dynamic_aliases_not_resolved','local_identity_requires_same_invocation',
                                         'static_identity_requires_same_process_and_link_image']}
