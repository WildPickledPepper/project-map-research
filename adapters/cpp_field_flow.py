"""Source-scoped object paths, field writes and reference-argument bindings.

These facts retain call sites so output effects can be substituted per invocation.
Only declared std container mutations and smart-pointer accessors are modeled.
"""
from collections import defaultdict
import json

from adapters.cpp_data import arguments,enclosing_function
from adapters.cpp_facts import declared_name
from adapters.cpp_control import predicates
from adapters.syntax_supplement import identity,text,walk


def declaration_mode(node):
    d=node.child_by_field_name('declarator')
    if d and d.type=='init_declarator':d=d.child_by_field_name('declarator')
    kinds={n.type for n in walk(d)} if d else set()
    return 'reference' if 'reference_declarator' in kinds else 'pointer' if 'pointer_declarator' in kinds else 'value'


class FieldFlow:
    def __init__(self,data):
        self.d=data;self.x=data.x;self.roots={};self.locations={};self.writes=[];self.calls=[];self.transfers=[];self.diagnostics=[]
        self.adjacency=defaultdict(list);self.parameters={};self.cache={}
        for e in data.facts['edges']:
            if e['kind'] in {'MEMBER_TARGET_CANDIDATE','DECLARES_DEFINITION','OVERRIDE_CANDIDATE'}:self.adjacency[e['source']].append(e)
        for uid,info in self.x.functions_by_id.items():
            if not self.x.nodes[uid]['definition']:continue
            self.parameters[uid]=[self.root(p,uid,info,i) for i,p in enumerate(info['parameter_nodes'])]

    def root(self,node,uid,info,index=None):
        rid='binding:'+identity(info['path'],'field_binding',node)
        if rid not in self.roots:
            typ=text(node.child_by_field_name('type'));mode=declaration_mode(node)
            self.roots[rid]={'id':rid,'source_symbol':uid,'name':text(declared_name(node)),
                'kind':'parameter' if index is not None else 'local','parameter_index':index,'mode':mode,
                'const':any(c.type=='type_qualifier' and text(c)=='const' for c in node.children),
                'type_spelling':typ,'type':self.d.types.type(typ,info['path'],info['scope']),
                'evidence':[self.d.evidence(info['path'],node)]}
        return rid

    def intern(self,root,selectors,typ,indirect=False):
        lid=root+':'+json.dumps(selectors,ensure_ascii=False,separators=(',',':'))
        self.locations[lid]={'id':lid,'root':root,'selectors':selectors,'type':typ,'indirect':indirect}
        return lid

    def dereference(self,lid):
        if lid is None:return None
        loc=self.locations[lid];typ=loc['type']
        if typ.get('kind')=='standard' and typ['name'] in self.d.types.POINTERS and typ['arguments']:
            typ=typ['arguments'][0]
        elif not loc['indirect']:return None
        return self.intern(loc['root'],loc['selectors']+['pointee'],typ)

    def location(self,node,uid,info,seen=None):
        if node is None:return None
        seen=set() if seen is None else seen
        if len(seen)>12:return None
        kind=node.type
        if kind=='parenthesized_expression':return self.location(node.named_children[-1],uid,info,seen)
        if kind=='pointer_expression':
            value=self.location(node.named_children[-1],uid,info,seen)
            return self.dereference(value) if text(node).lstrip().startswith('*') else value
        if kind=='identifier':
            vs=self.x.variables(text(node),node,info['path'],uid)
            if not vs:return None
            var=vs[0];decl=var['node'];key=(info['path'],decl.start_byte)
            if key in seen:return None
            mode=declaration_mode(decl)
            if mode=='pointer' and any(n.type=='assignment_expression' and text(n.child_by_field_name('left'))==text(node)
                    and decl.end_byte<=n.start_byte<node.start_byte for n in walk(info['container'])):return None
            if mode in {'reference','pointer'} and var['value'] is not None:
                return self.location(var['value'],uid,info,seen|{key})
            params=info['parameter_nodes'];index=next((i for i,p in enumerate(params) if p==decl),None)
            rid=self.root(decl,uid,info,index);typ=self.roots[rid]['type']
            if var['type']=='auto':typ=self.d.types.infer(node,uid,info)
            return self.intern(rid,[],typ,mode=='pointer')
        if kind=='field_expression':
            receiver=node.child_by_field_name('argument');lid=self.location(receiver,uid,info,seen)
            if text(node.child_by_field_name('operator'))=='->':lid=self.dereference(lid)
            if lid is None:return None
            loc=self.locations[lid];name=text(node.child_by_field_name('field'))
            fields=[self.d.field(name,owner) for owner in loc['type'].get('names',[])];fields=[f for f in fields if f]
            typ=self.d.types.type(fields[0]['type'],fields[0]['path'],fields[0]['owner'].split('::')) if len(fields)==1 else self.d.types.unknown('field_type_unresolved')
            return self.intern(loc['root'],loc['selectors']+['member:'+name],typ)
        if kind=='subscript_expression':
            lid=self.location(node.child_by_field_name('argument'),uid,info,seen)
            if lid is None:return None
            loc=self.locations[lid];element=self.d.types.elements(loc['type'])
            if element.get('kind')=='pair':element=element['second']
            ix=node.child_by_field_name('indices');value=ix.named_children[0] if ix and ix.named_children else None
            selector='index:'+text(value) if value and value.type in {'number_literal','string_literal'} else 'index:*'
            return self.intern(loc['root'],loc['selectors']+[selector],element)
        if kind=='call_expression':
            fn=node.child_by_field_name('function')
            if text(fn)=='std::move' and len(arguments(node))==1:return self.location(arguments(node)[0],uid,info,seen)
            if text(fn).startswith(('dynamic_cast<','static_cast<','const_cast<')) and len(arguments(node))==1:
                return self.location(arguments(node)[0],uid,info,seen)
            if fn and fn.type=='field_expression' and text(fn.child_by_field_name('field'))=='get' and not arguments(node):
                lid=self.location(fn.child_by_field_name('argument'),uid,info,seen)
                if lid and self.locations[lid]['type'].get('name') in self.d.types.POINTERS:return lid
        return None

    def targets(self,node,uid,info):
        cid='cpp:'+identity(info['path'],'call_site',node);pending=[cid,*self.d.targets(node,uid,info)]
        reached=set();found=set();evidence=[]
        while pending:
            tid=pending.pop()
            if tid in reached:continue
            reached.add(tid)
            if self.x.nodes.get(tid,{}).get('definition'):found.add(tid)
            for e in self.adjacency[tid]:evidence.append(e);pending.append(e['target'])
        return sorted(found),evidence

    def build(self):
        for uid,info in self.x.functions_by_id.items():
            if not self.x.nodes[uid]['definition']:continue
            for node in walk(info['container']):
                if enclosing_function(node)!=info['container']:continue
                location=None;operation=None;values=[]
                if node.type=='assignment_expression':
                    location=self.location(node.child_by_field_name('left'),uid,info)
                    operation=text(node.child_by_field_name('operator'));values=[node.child_by_field_name('right')]
                if node.type=='binary_expression' and text(node.child_by_field_name('operator'))=='<<':
                    actual=self.location(node.child_by_field_name('right'),uid,info)
                    if actual:self.diagnostics.append({'kind':'operator_transfer_not_expanded','source_symbol':uid,
                        'call_site':'cpp:'+identity(info['path'],'object_transfer',node),'arguments':[actual],
                        'offset':node.start_byte,'conditions':predicates(node),'evidence':[self.d.evidence(info['path'],node)]})
                if node.type=='call_expression':
                    fn=node.child_by_field_name('function');args=arguments(node)
                    if fn and fn.type=='field_expression':
                        receiver=self.location(fn.child_by_field_name('argument'),uid,info)
                        method=text(fn.child_by_field_name('field'));typ=self.locations.get(receiver,{}).get('type',{})
                        if typ.get('kind')=='standard' and typ.get('name') in self.d.types.MAPS|self.d.types.SEQUENCES and method in self.d.WRITES:
                            location=receiver;operation='std::'+method;values=args
                    targets,resolution=self.targets(node,uid,info)
                    bindings=[];value_bindings=[]
                    for target in targets:
                        for i,rid in enumerate(self.parameters.get(target,[])):
                            formal=self.roots[rid]
                            if i>=len(args):continue
                            actual=self.location(args[i],uid,info)
                            binding={'target':target,'parameter':rid,'index':i,'actual':actual,
                                'address_of':args[i].type=='pointer_expression' and text(args[i]).lstrip().startswith('&'),
                                'argument_evidence':self.d.evidence(info['path'],args[i])}
                            value_bindings.append(binding)
                            if formal['mode']!='value' and not formal['const']:bindings.append(binding)
                    if value_bindings:
                        self.transfers.append({'id':'cpp:'+identity(info['path'],'call_site',node),'source_symbol':uid,'targets':targets,
                            'bindings':value_bindings,'offset':node.start_byte,'conditions':predicates(node),'evidence':[self.d.evidence(info['path'],node)]})
                    if bindings:
                        self.calls.append({'id':'cpp:'+identity(info['path'],'call_site',node),'source_symbol':uid,'targets':targets,
                            'bindings':bindings,'value_bindings':value_bindings,'conditions':predicates(node),'resolution_evidence':resolution,
                            'offset':node.start_byte,
                            'evidence':[self.d.evidence(info['path'],node)],'runtime_target':'unknown'})
                    elif not targets and any(self.location(a,uid,info) for a in args):
                        transparent=text(fn)=='std::move' or text(fn).startswith(('dynamic_cast<','static_cast<','const_cast<'))
                        if not transparent:self.diagnostics.append({'kind':'call_effects_unresolved','source_symbol':uid,
                            'call_site':'cpp:'+identity(info['path'],'call_site',node),'arguments':[self.location(a,uid,info) for a in args],
                            'offset':node.start_byte,'conditions':predicates(node),'evidence':[self.d.evidence(info['path'],node)]})
                if location and operation:
                    self.writes.append({'id':'field-write:'+identity(info['path'],'field_write',node),'source_symbol':uid,
                        'location':location,'operation':operation,'conditions':predicates(node),
                        'offset':node.start_byte,
                        'values':[self.d.expr(v,uid,info) for v in values if v is not None],
                        'value_locations':[self.location(v,uid,info) for v in values if v is not None],
                        'evidence':[self.d.evidence(info['path'],node)],'status':'source_effect_candidate'})
        return {'version':'0.2.0','roots':list(self.roots.values()),'locations':list(self.locations.values()),
            'writes':self.writes,'calls':self.calls,'transfers':self.transfers,'diagnostics':self.diagnostics,
            'limits':['source_candidates_without_compiler_overload_resolution','unknown_calls_may_write_through_aliases',
                'pointer_rebinding_not_resolved','copy_writes_do_not_escape_to_original','loop_indices_may_be_unknown',
                'lambda_execution_not_expanded','implicit_this_member_effects_not_expanded']}
