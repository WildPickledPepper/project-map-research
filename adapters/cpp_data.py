"""C++ value selection, scoped container access and factory source evidence.

Records source dependencies and path predicates, not execution or alias proofs.
Project identifiers are extracted; only std container/allocation APIs are modeled.
"""
from collections import defaultdict
import re

from adapters.cpp_facts import Extractor, declared_name, parameter_type, scoped_name
from adapters.syntax_supplement import cpp_scope, identity, parents, text, walk
from adapters.cpp_control import predicates


def canonical(name):
    """Remove balanced template arguments from a qualified owner spelling."""
    anonymous=[]
    def protect(match):
        anonymous.append(match.group());return '\x00'+str(len(anonymous)-1)+'\x00'
    name=re.sub(r'<anonymous@[^>]+>',protect,name)
    result=[];depth=0
    for c in name:
        if c=='<':depth+=1
        elif c=='>':depth=max(0,depth-1)
        elif not depth:result.append(c)
    return re.sub(r'\x00(\d+)\x00',lambda m:anonymous[int(m[1])],''.join(result))


def arguments(node):
    value=node.child_by_field_name('arguments') if node else None
    return list(value.named_children) if value else []


def enclosing_function(node):
    return next((p for p in parents(node) if p.type in {'function_definition','lambda_expression'}),None)


class DataExtractor:
    CONTAINERS={'map','unordered_map','multimap','unordered_multimap','set','unordered_set','deque','vector','list'}
    READS={'at','find','count','contains','begin','end','front','back','size','empty'}
    WRITES={'emplace','insert','insert_or_assign','try_emplace','erase','clear','push_back','emplace_back','pop_front','pop_back'}

    def __init__(self,sources,parser):
        self.x=Extractor(sources,parser);self.facts=self.x.build();self.fields={};self.diagnostics=[]
        self.accesses=[];self.allocations=[];self.selections=[];self.summaries=[];self.callbacks=[]
        self.by_owner=defaultdict(list);self.functions=defaultdict(list)
        for uid,info in self.x.functions_by_id.items():
            if self.x.nodes[uid]['definition']:
                self.by_owner[canonical('::'.join(info['scope']))].append((uid,info))
                self.functions[canonical(info['signature'][0])].append((uid,info))
        self.discover_fields()
        from adapters.cpp_value_types import ValueTypes
        self.types=ValueTypes(self)

    @staticmethod
    def evidence(path,node):return {'path':path,'line':node.start_point[0]+1,'expression':text(node)[:700]}

    def discover_fields(self):
        for path,unit in self.x.units.items():
            for node in walk(unit['tree'].root_node):
                if node.type not in {'class_specifier','struct_specifier'}:continue
                name=node.child_by_field_name('name');body=node.child_by_field_name('body')
                if name is None or body is None:continue
                owner=scoped_name(canonical('::'.join(cpp_scope(node)+[text(name)])),path)
                for member in body.named_children:
                    if member.type!='field_declaration':continue
                    field=declared_name(member)
                    if field is None:continue
                    typ=text(member.child_by_field_name('type'));match=re.match(r'std::(\w+)\s*<',typ)
                    self.fields[(owner,text(field))]={'id':'storage:'+identity(path,'member',member),'owner':owner,'name':text(field),
                        'path':path,'line':member.start_point[0]+1,'type':typ,
                        'container':match[1] if match and match[1] in self.CONTAINERS else None,
                        'instance_identity':'class_member_instance_unresolved','evidence':[self.evidence(path,member)]}

    def field(self,name,owner,seen=None):
        owner=canonical(owner);seen=set() if seen is None else seen
        if owner in seen:return None
        seen.add(owner)
        if (owner,name) in self.fields:return self.fields[(owner,name)]
        for base in sorted(self.x.base_names.get(owner,[])):
            found=self.field(name,base,seen)
            if found:return found
        return None

    def receiver_field(self,node,uid,info):
        if node is None:return None
        if node.type=='identifier':
            if self.x.variables(text(node),node,info['path'],uid):return None
            return self.field(text(node),'::'.join(info['scope']))
        if node.type=='field_expression':
            receiver=node.child_by_field_name('argument');name=text(node.child_by_field_name('field'))
            if text(receiver)=='this':return self.field(name,'::'.join(info['scope']))
            if hasattr(self,'types'):
                inferred=self.types.infer(receiver,uid,info)
                if text(node.child_by_field_name('operator'))=='->':inferred=self.types.dereference(inferred)
                types=inferred.get('names',[])
            else:types=self.x.infer(receiver,info['path'],info['scope'],uid)['names']
            found=[self.field(name,t) for t in types];found=[f for f in found if f]
            if len(found)==1:return found[0]
        return None

    def base_targets(self,call,uid,info):
        function=call.child_by_field_name('function')
        if function is None:return []
        groups,_=self.x.targets(call,info['path'],info['scope'],uid)
        result=[]
        for group in groups:
            for tid in group:
                target=self.x.functions_by_id[tid]
                for did,d in self.functions.get(canonical(target['signature'][0]),[]):
                    if d['signature'][1:]==target['signature'][1:]:result.append(did)
        if function.type=='identifier':
            name=text(function);argc=len(arguments(call));visible=self.x.visibility.get(info['path'],{info['path']})
            def accepts(f):
                declarations=[self.x.functions_by_id[t] for t in self.x.functions[f['signature']]
                              if self.x.functions_by_id[t]['path'] in visible]
                return any(sum(p.child_by_field_name('default_value') is None for p in d['parameter_nodes'])<=argc<=len(d['parameter_nodes']) for d in declarations)
            owner='::'.join(info['scope'])
            if owner in self.x.classes:
                for group in self.x.members(owner,name):
                    for tid in group:
                        f=self.x.functions_by_id[tid]
                        if self.x.nodes[tid]['definition'] and accepts(f):result.append(tid)
                if result:return self.prefer_visible_definitions(result,info['path'])
            for length in range(len(info['scope']),-1,-1):
                q=canonical('::'.join(info['scope'][:length]+[name]));found=[]
                for tid,f in self.functions.get(q,[]):
                    if accepts(f):found.append(tid)
                if found:result.extend(found);break
        return self.prefer_visible_definitions(result,info['path'])

    def prefer_visible_definitions(self,targets,path):
        visible=self.x.visibility.get(path,{path})
        signatures={self.x.functions_by_id[t]['signature'] for t in targets if self.x.functions_by_id[t]['path'] in visible}
        return sorted({t for t in targets if self.x.functions_by_id[t]['path'] in visible or self.x.functions_by_id[t]['signature'] not in signatures})

    def targets(self,call,uid,info):return self.types.call(call,uid,info)['targets']

    def expr(self,node,uid,info,depth=0,seen=None):
        """A bounded expression tree retaining aliases, calls and branch inputs."""
        if node is None:return {'kind':'missing'}
        if depth>8:return {'kind':'unknown','reason':'depth_limit','expression':text(node)}
        seen=set() if seen is None else seen
        result={'kind':node.type,'expression_id':'expr:'+identity(info['path'],'expression',node),**self.evidence(info['path'],node)}
        if node.type=='identifier':
            variables=self.x.variables(text(node),node,info['path'],uid)
            if variables:
                var=variables[0];key=(var['node'].start_byte,info['path'])
                result['binding']={'path':info['path'],'line':var['node'].start_point[0]+1,'type':var['type']}
                writes=[n for n in walk(info['container']) if n.type=='assignment_expression' and text(n.child_by_field_name('left'))==text(node)
                        and var['node'].end_byte<=n.start_byte<node.start_byte]
                if writes:
                    result.update(kind='unknown',reason='intervening_assignment',writes=[self.evidence(info['path'],n) for n in writes])
                    if key not in seen:
                        result['write_candidates']=[{'value':self.expr(n.child_by_field_name('right'),uid,info,depth+1,seen|{key}),
                                                     'conditions':predicates(n)} for n in writes]
                elif var['value'] is not None and key not in seen:result['initializer']=self.expr(var['value'],uid,info,depth+1,seen|{key})
        elif node.type=='call_expression':
            result['targets']=self.targets(node,uid,info)
            result['arguments']=[self.expr(a,uid,info,depth+1,seen) for a in arguments(node)]
            f=node.child_by_field_name('function')
            if f and f.type=='field_expression':result['receiver']=self.expr(f.child_by_field_name('argument'),uid,info,depth+1,seen)
            if not result['targets']:result['target_status']='unresolved_or_library_call'
        elif node.type=='conditional_expression':
            result['condition']=self.expr(node.child_by_field_name('condition'),uid,info,depth+1,seen)
            result['branches']=[{'when':b,'value':self.expr(node.child_by_field_name(k),uid,info,depth+1,seen)} for b,k in [(True,'consequence'),(False,'alternative')]]
        elif node.type in {'field_expression','subscript_expression','subscript_argument_list','argument_list','condition_clause','parenthesized_expression','pointer_expression','binary_expression'}:
            result['parts']=[self.expr(c,uid,info,depth+1,seen) for c in node.named_children]
        return result

    def collect_access(self,node,uid,info):
        field=None;operation=None;key=None;value=None;role=None
        if node.type=='call_expression':
            f=node.child_by_field_name('function')
            if f is None or f.type!='field_expression':return
            field=self.receiver_field(f.child_by_field_name('argument'),uid,info);operation=text(f.child_by_field_name('field'))
            if not field or not field['container']:return
            if operation in self.READS:role='read'
            elif operation in self.WRITES:role='write'
            else:
                self.diagnostics.append({'kind':'container_operation_unmodeled','operation':operation,**self.evidence(info['path'],node)});return
            a=arguments(node);key=a[0] if a else None;value=a[1] if len(a)>1 else None
        elif node.type=='subscript_expression':
            field=self.receiver_field(node.child_by_field_name('argument'),uid,info)
            if not field or not field['container']:return
            ix=node.child_by_field_name('indices');key=ix.named_children[0] if ix and ix.named_children else None
            parent=node.parent
            if parent and parent.type=='assignment_expression' and parent.child_by_field_name('left')==node:
                role='write';operation=text(parent.child_by_field_name('operator')) or '=';value=parent.child_by_field_name('right')
            else:role='read';operation='operator[]'
        else:return
        rec={'id':'access:'+identity(info['path'],'storage_access',node),'storage':field['id'],'role':role,'operation':operation,
             'source_symbol':uid,'conditions':predicates(node),'key':self.expr(key,uid,info),'value':self.expr(value,uid,info) if value else None,
             'evidence':[self.evidence(info['path'],node)],'path':info['path'],'line':node.start_point[0]+1,
             'alias_status':'candidate','runtime_key_equality':'not_observed'}
        if role=='read' and operation=='operator[]' and field['container'] in {'map','unordered_map'}:
            rec['implicit_write']='default_insertion_if_key_absent'
        self.accesses.append(rec)

    def allocation(self,node,uid,info):
        typ=None;factory=None
        if node.type=='new_expression':typ=text(node.child_by_field_name('type'));factory='new'
        elif node.type=='call_expression':
            f=node.child_by_field_name('function')
            if text(f).startswith(('std::make_shared<','std::make_unique<')):
                template=next((n for n in walk(f) if n.type=='template_argument_list'),None)
                if template and template.named_children:typ=text(template.named_children[0]);factory=canonical(text(f))
        if not typ:return
        targets=self.x.resolve_type(canonical(typ),info['path'],info['scope'])['names']
        parent_factory=next((p for p in parents(node) if p.type=='call_expression' and text(p.child_by_field_name('function')).startswith(('std::make_shared<','std::make_unique<'))),None)
        self.allocations.append({'id':'allocation:'+identity(info['path'],'allocation',node),'source_symbol':uid,'type_spelling':typ,
            'expression_id':'expr:'+identity(info['path'],'expression',node),
            'type_candidates':targets,'factory':factory,'callback':any(p.type=='lambda_expression' for p in parents(node)),
            'enclosing_allocation':'allocation:'+identity(info['path'],'allocation',parent_factory) if parent_factory else None,
            'conditions':predicates(node),'arguments':[self.expr(a,uid,info) for a in arguments(node)],
            'path':info['path'],'line':node.start_point[0]+1,'evidence':[self.evidence(info['path'],node)]})

    def build(self):
        for uid,info in self.x.functions_by_id.items():
            if not self.x.nodes[uid]['definition']:continue
            returns=[];calls=[];controls=[]
            for node in walk(info['container']):
                self.collect_access(node,uid,info);self.allocation(node,uid,info)
                if node.type=='return_statement' and node.named_children:
                    returns.append({'value':self.expr(node.named_children[0],uid,info),'conditions':predicates(node),
                                    'callback_return':enclosing_function(node).type=='lambda_expression' if enclosing_function(node) else False})
                if node.type=='call_expression':
                    targets=self.targets(node,uid,info)
                    function=node.child_by_field_name('function')
                    calls.append({'call_site':'cpp:'+identity(info['path'],'call_site',node),'targets':targets,
                                  'resolution':self.types.call(node,uid,info),
                                  'expression':text(node),'path':info['path'],'line':node.start_point[0]+1,'conditions':predicates(node),
                                  'receiver':self.expr(function.child_by_field_name('argument'),uid,info) if function and function.type=='field_expression' else None})
                    if function and function.type=='identifier':
                        field=self.receiver_field(function,uid,info)
                        if field and field['type'].startswith('std::function<'):
                            self.callbacks.append({'kind':'invoke','member':field['id'],'owner':field['owner'],'source_symbol':uid,
                                'path':info['path'],'line':node.start_point[0]+1,'conditions':predicates(node),'evidence':[self.evidence(info['path'],node)]})
                if node.type=='field_initializer':
                    field=self.field(text(node.named_children[0]),'::'.join(info['scope'])) if node.named_children else None
                    args=next((c for c in node.named_children if c.type=='argument_list'),None)
                    if field and field['type'].startswith('std::function<') and args and len(args.named_children)==1:
                        value=args.named_children[0]
                        if value.type=='call_expression' and text(value.child_by_field_name('function'))=='std::move' and len(arguments(value))==1:value=arguments(value)[0]
                        names=[text(declared_name(p)) for p in info['parameter_nodes']]
                        if text(value) in names:
                            self.callbacks.append({'kind':'bind_constructor_parameter','member':field['id'],'owner':field['owner'],'source_symbol':uid,
                                'parameter_index':names.index(text(value)),'path':info['path'],'line':node.start_point[0]+1,
                                'evidence':[self.evidence(info['path'],node)]})
                if node.type in {'if_statement','switch_statement'}:
                    controls.append({'kind':node.type,'test':self.expr(node.child_by_field_name('condition'),uid,info),'conditions':predicates(node)})
                if node.type=='conditional_expression':
                    self.selections.append({'id':'selection:'+identity(info['path'],'selection',node),'source_symbol':uid,
                        'path':info['path'],'line':node.start_point[0]+1,'value':self.expr(node,uid,info),'conditions':predicates(node)})
            self.summaries.append({'source_symbol':uid,'name':self.x.nodes[uid]['name'],'path':info['path'],'line':self.x.nodes[uid]['line'],
                'parameters':[{'name':text(declared_name(p)),'type':parameter_type(p)} for p in info['parameter_nodes']],
                'return_type':info['return_type'],'returns':returns,'calls':calls,'controls':controls})
        from adapters.cpp_instances import extract_instances
        instances=extract_instances(self)
        from adapters.cpp_field_flow import FieldFlow
        field_engine=FieldFlow(self);field_flow=field_engine.build()
        from adapters.cpp_serialization import Serialization
        serializer=Serialization(self);serialization=serializer.build()
        from adapters.cpp_response_routing import ResponseRouting
        routing=ResponseRouting(self,field_engine,serializer.protocol).build()
        field_flow['roots']=list(field_engine.roots.values());field_flow['locations']=list(field_engine.locations.values())
        from adapters.cpp_member_effects import extract_member_effects
        return {'facts':self.facts,'data':{'version':'0.6.0','storages':[f for f in self.fields.values() if f['container']],
            'accesses':self.accesses,'allocations':self.allocations,'selections':self.selections,'summaries':self.summaries,
            'callbacks':self.callbacks,
            'instances':instances,
            'field_flow':field_flow,
            'member_effects':extract_member_effects(self),
            'serialization':serialization,
            'response_routing':routing,
            'diagnostics':self.diagnostics,'limits':['source_type_candidates','member_instance_aliasing_unresolved','runtime_keys_not_observed',
                'bounded_expression_dependencies','switch_entries_are_source_candidates','exceptions_goto_and_path_feasibility_not_solved']}}


def analyze_data(sources,parser):return DataExtractor(sources,parser).build()
