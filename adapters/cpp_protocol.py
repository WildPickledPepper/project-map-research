"""Discover constant-key registries and object-factory groups from C++ AST.

No project method, field, class, command or module names are matching rules.
Uses P1's lexical/type candidates; output remains conditional source evidence.
"""
from collections import defaultdict
import json

from adapters.cpp_facts import Extractor, declared_name, scoped_name
from adapters.syntax_supplement import cpp_scope, identity, parents, text, walk


def args(n):
    value=n.child_by_field_name('arguments') if n else None
    return list(value.named_children) if value else []


def make_type(n):
    if n is None or n.type!='call_expression':return None
    function=n.child_by_field_name('function')
    if not text(function).startswith(('std::make_unique<','std::make_shared<')):return None
    template=next((x for x in walk(function) if x.type=='template_argument_list'),None)
    return text(template.named_children[0]) if template and len(template.named_children)==1 else None


class ProtocolExtractor:
    def __init__(self,sources,parser):
        self.x=Extractor(sources,parser)
        self.facts=self.x.build()
        self.constants=defaultdict(list)
        self.functions=defaultdict(list)
        self.registrations=[];self.lookups=[];self.groups=[];self.diagnostics=[]
        self.reference_writes={};self.field_writes=[]
        self.class_nodes={}
        for path,unit in self.x.units.items():
            for n in walk(unit['tree'].root_node):
                if n.type in {'class_specifier','struct_specifier'} and n.child_by_field_name('name'):
                    q=scoped_name('::'.join(cpp_scope(n)+[text(n.child_by_field_name('name'))]),path)
                    self.class_nodes[q]=n
                if n.type=='declaration' and not any(p.type in {'function_definition','compound_statement'} for p in parents(n)):
                    name=declared_name(n);value=n.child_by_field_name('declarator')
                    value=value.child_by_field_name('value') if value else None
                    if name is not None and value is not None and any(c.type=='type_qualifier' and text(c) in {'const','constexpr'} for c in n.children):
                        q='::'.join(cpp_scope(n)+[text(name)])
                        self.constants[q].append({'path':path,'node':value,'scope':cpp_scope(n),'evidence':self.ev(path,n)})
        for uid,info in self.x.functions_by_id.items():
            if self.x.nodes[uid]['definition']:
                self.functions[info['signature'][0]].append((uid,info))
        self.callers=defaultdict(list)
        for uid,info in self.x.functions_by_id.items():
            if not self.x.nodes[uid]['definition']:continue
            for call in walk(info['container']):
                if call.type=='call_expression':
                    for target,callee in self.resolve_function(call,info):self.callers[target].append((call,uid,info))

    @staticmethod
    def ev(path,node):return {'path':path,'line':node.start_point[0]+1,'expression':text(node)[:500]}

    def qnames(self,spelling,path,scope,available):
        visible=self.x.visibility.get(path,{path})
        def exists(q):return q in available
        if spelling.startswith('::'):return [spelling[2:]] if exists(spelling[2:]) else []
        for length in range(len(scope),-1,-1):
            q='::'.join(scope[:length]+[spelling])
            if exists(q):return [q]
        result=[]
        for p in visible:
            for prefix,namespace in self.x.units[p]['using']:
                prefix=[part for segment in prefix for part in segment.split('::')]
                if scope[:len(prefix)]!=prefix:continue
                for length in range(len(prefix),-1,-1):
                    q='::'.join(prefix[:length]+[namespace,spelling])
                    if exists(q):result.append(q)
        return sorted(set(result))

    def constant(self,node,path,scope,env=None,depth=0):
        if node is None or depth>10:return None,[]
        env=env or {}
        if node.type=='string_literal':
            try:return json.loads(text(node)),[self.ev(path,node)]
            except ValueError:return None,[]
        if node.type in {'identifier','qualified_identifier','namespace_identifier'}:
            if text(node) in env:return env[text(node)]
            choices=[]
            for q in self.qnames(text(node),path,scope,self.constants):
                for rec in self.constants[q]:
                    contexts=[p for p,v in self.x.visibility.items() if p.endswith(('.cpp','.cc','.cxx')) and path in v and rec['path'] in v]
                    if rec['path'] in self.x.visibility.get(path,{path}) or contexts:
                        value,evidence=self.constant(rec['node'],rec['path'],rec['scope'],depth=depth+1)
                        if value is not None:choices.append((value,[rec['evidence'],*evidence,*([{'path':path,'translation_unit_candidates':contexts}] if rec['path'] not in self.x.visibility.get(path,{path}) else [])]))
            if len({x[0] for x in choices})==1:return choices[0]
        return None,[]

    def resolve_function(self,call,info):
        function=call.child_by_field_name('function');spelling=text(function)
        if function is None:return []
        if function.type not in {'identifier','qualified_identifier'}:return []
        candidates=[]
        for q in self.qnames(spelling,info['path'],info['scope'],self.functions):
            candidates.extend((uid,f) for uid,f in self.functions[q] if len(f['parameter_nodes'])==len(args(call)))
        if not candidates and function.type=='identifier':
            for cls in self.lineage('::'.join(info['scope'])):
                candidates.extend((uid,f) for uid,f in self.functions.get(cls+'::'+spelling,[]) if len(f['parameter_nodes'])==len(args(call)))
        return candidates

    def field_owner(self,cls,field,seen=None):
        seen=set() if seen is None else seen
        if cls in seen:return None
        seen.add(cls);node=self.class_nodes.get(cls)
        if node:
            body=node.child_by_field_name('body')
            for member in body.named_children if body else []:
                if member.type=='field_declaration' and text(declared_name(member))==field:return cls+'::'+field
        for base in sorted(self.x.base_names.get(cls,[])):
            result=self.field_owner(base,field,seen)
            if result:return result
        return None

    def local_initializer(self,name,node,info):
        candidates=[]
        for d in walk(info['container']):
            if d.type=='declaration' and text(declared_name(d))==name and d.start_byte<node.start_byte:
                scope=next((p for p in parents(d) if p.type=='compound_statement'),info['container'])
                if not scope.start_byte<=node.start_byte<scope.end_byte:continue
                init=d.child_by_field_name('declarator');value=init.child_by_field_name('value') if init else None
                if value:candidates.append((scope.end_byte-scope.start_byte,-d.start_byte,value))
        if not candidates:return None
        value=sorted(candidates,key=lambda x:x[:2])[0][2]
        # An intervening write invalidates the initializer, including branch writes.
        if any(d.type=='assignment_expression' and text(d.child_by_field_name('left'))==name and value.end_byte<d.start_byte<node.start_byte for d in walk(info['container'])):return None
        return value

    def origins(self,node,uid,info,env=None,depth=0):
        """Trace registry-key dependencies to source JSON/member fields."""
        if node is None or depth>8:return []
        env=env or {};path=info['path'];kind=node.type
        if kind=='identifier':
            name=text(node)
            if name in env:return env[name]
            writes=self.reference_writes.get((uid,name),[])
            before=[w for w in writes if w['position']<node.start_byte]
            if before:return before[-1]['origins']
            init=self.local_initializer(name,node,info)
            if init:return self.origins(init,uid,info,env,depth+1)
            ps=[text(declared_name(p)) for p in info['parameter_nodes']]
            if name in ps:
                index=ps.index(name);found=[]
                for call,caller,caller_info in self.callers.get(uid,[]):
                    found.extend(self.origins(args(call)[index],caller,caller_info,depth=depth+1))
                return found
        if kind=='field_expression':
            receiver=self.x.infer(node.child_by_field_name('argument'),path,info['scope'],uid)
            return [{'field':text(node.child_by_field_name('field')),'owner_types':receiver['names'],'kind':'member_read','evidence':[self.ev(path,node)]}]
        if kind=='conditional_expression':
            return [dict(o,condition=text(node.child_by_field_name('condition'))) for key in ['consequence','alternative'] for o in self.origins(node.child_by_field_name(key),uid,info,env,depth+1)]
        if kind=='subscript_expression':
            indices=node.child_by_field_name('indices');key=indices.named_children[0] if indices and indices.named_children else None
            value,evidence=self.constant(key,path,info['scope'])
            if value is not None:return [{'field':value,'kind':'json_subscript','evidence':[self.ev(path,node),*evidence]}]
            if key:
                found=self.origins(key,uid,info,env,depth+1)
                return [{**r,'kind':'json_subscript','evidence':[self.ev(path,node),*r['evidence']]} for r in found if r['kind']=='literal_key_argument']
        if kind=='call_expression':
            f=node.child_by_field_name('function')
            if f and f.type=='field_expression' and not args(node) and text(f.child_by_field_name('field')) in {'data','c_str','GetString','value'}:
                # Explicit library accessor models; arbitrary transformations do
                # not preserve a registry key. RapidJSON is a declared adapter.
                return self.origins(f.child_by_field_name('argument'),uid,info,env,depth+1)
            found=[]
            for target,callee in self.resolve_function(node,info):
                values={text(declared_name(p)):self.origins(a,uid,info,env,depth+1) for p,a in zip(callee['parameter_nodes'],args(node))}
                for p,a in zip(callee['parameter_nodes'],args(node)):
                    value,evidence=self.constant(a,path,info['scope'])
                    if value is not None:values[text(declared_name(p))]=[{'field':value,'kind':'literal_key_argument','evidence':evidence}]
                for ret in walk(callee['container']):
                    if ret.type=='return_statement' and ret.named_children:
                        found.extend(self.origins(ret.named_children[0],target,callee,values,depth+1))
            return found
        return []

    def allocated(self,node,info):
        spelling=make_type(node)
        if spelling:return self.x.resolve_type(spelling,info['path'],info['scope'])['names'],[self.ev(info['path'],node)]
        if node and node.type=='call_expression' and text(node.child_by_field_name('function'))=='std::move' and len(args(node))==1:
            name=text(args(node)[0]);init=self.local_initializer(name,node,info)
            if init:
                targets,evidence=self.allocated(init,info);return targets,[self.ev(info['path'],node),*evidence]
        return [],[]

    def factory_method(self,node,info):
        if node is None:return None
        if node.type=='identifier':return self.factory_method(self.local_initializer(text(node),node,info),info)
        if node.type=='call_expression':
            f=node.child_by_field_name('function')
            if text(f)=='std::move' and len(args(node))==1:return self.factory_method(args(node)[0],info)
            if f and f.type=='field_expression' and not args(node):return text(f.child_by_field_name('field'))
        return None

    def collect_registries(self):
        for uid,info in self.x.functions_by_id.items():
            if not self.x.nodes[uid]['definition']:continue
            cls='::'.join(info['scope']);path=info['path']
            for n in walk(info['container']):
                if n.type=='call_expression':
                    f=n.child_by_field_name('function')
                    if f is None or f.type!='field_expression':continue
                    receiver=text(f.child_by_field_name('argument'));operation=text(f.child_by_field_name('field'));a=args(n)
                    registry=self.field_owner(cls,receiver)
                    if not registry:continue
                    if operation=='emplace' and len(a)==2:
                        value,evidence=self.constant(a[0],path,info['scope'])
                        targets,allocation=self.allocated(a[1],info)
                        target_functions=[]
                        if not targets:
                            for q in self.qnames(text(a[1]),path,info['scope'],self.functions):target_functions.extend(t for t,_ in self.functions[q])
                        self.registrations.append({'id':'registry:'+identity(path,'registration',n),'owner':cls,'registry':registry,
                            'key':value,'key_expression':text(a[0]),'value_expression':text(a[1]),'objects':targets,'functions':target_functions,
                            'factory_method':self.factory_method(a[1],info),
                            'path':path,'line':n.start_point[0]+1,'source_symbol':uid,'conditions':self.x.conditions(n),
                            'evidence':[self.ev(path,n),*evidence,*allocation]})
                    if operation in {'at','find'} and len(a)==1:
                        origins=self.origins(a[0],uid,info)
                        self.lookups.append({'registry':registry,'path':path,'line':n.start_point[0]+1,'source_symbol':uid,'key_origins':origins,'evidence':[self.ev(path,n)]})
                elif n.type=='subscript_expression':
                    registry=self.field_owner(cls,text(n.child_by_field_name('argument')))
                    ix=n.child_by_field_name('indices')
                    if registry and ix and ix.named_children:self.lookups.append({'registry':registry,'path':path,'line':n.start_point[0]+1,'source_symbol':uid,
                        'key_origins':self.origins(ix.named_children[0],uid,info),'evidence':[self.ev(path,n)]})

    def collect_groups(self):
        # A source class that constructs two registered components supplies the
        # common scope. Names of the class and factory methods are irrelevant.
        for cls,node in self.class_nodes.items():
            methods=[(uid,f) for uid,f in self.x.functions_by_id.items() if ('::'.join(f['scope'])==cls or node in parents(f['container'])) and self.x.nodes[uid]['definition']]
            returned=[];keys=[]
            for uid,f in methods:
                for n in walk(f['container']):
                    if n.type=='return_statement' and n.named_children:
                        targets,evidence=self.allocated(n.named_children[0],f)
                        for target in targets:returned.append({'class':target,'source_symbol':uid,'method':self.x.nodes[uid]['name'].rsplit('::',1)[-1],'evidence':evidence})
                    if n.type=='field_initializer':
                        arguments=next((c for c in n.named_children if c.type=='argument_list'),None)
                        if arguments:
                            for arg in arguments.named_children:
                                value,evidence=self.constant(arg,f['path'],f['scope'])
                                if isinstance(value,str):keys.append({'value':value,'evidence':evidence})
            registered={r['owner'] for r in self.registrations}
            returned=[r for r in returned if r['class'] in registered]
            if len({r['class'] for r in returned})<2:continue
            creations=[]
            for path,unit in self.x.units.items():
                for n in walk(unit['tree'].root_node):
                    spelling=make_type(n)
                    if spelling and cls in self.x.resolve_type(spelling,path,cpp_scope(n))['names']:
                        if not any(p.type=='function_definition' for p in parents(n)):creations.append(self.ev(path,n))
            self.groups.append({'class':cls,'keys':keys,'components':returned,'static_constructions':creations})

    def lineage(self,cls):
        found={cls};todo=[cls]
        while todo:
            for base in self.x.base_names.get(todo.pop(),[]):
                if base not in found:found.add(base);todo.append(base)
        return found

    def collect_field_writes(self):
        """Source summaries for reference arguments; keys and member names may differ."""
        def visit(uid,info,env,aliases,seen):
            if uid in seen or len(seen)>5:return []
            result=[];seen=seen|{uid}
            for n in walk(info['container']):
                if n.type=='assignment_expression':
                    left=n.child_by_field_name('left');target=aliases.get(text(left),(uid,info,left))
                    result.append((target,self.origins(n.child_by_field_name('right'),uid,info,env),self.ev(info['path'],n)))
                elif n.type=='call_expression':
                    for cid,callee in self.resolve_function(n,info):
                        ce={};ca={}
                        for p,a in zip(callee['parameter_nodes'],args(n)):
                            name=text(declared_name(p));ce[name]=self.origins(a,uid,info,env)
                            v,e=self.constant(a,info['path'],info['scope'])
                            if v is not None:ce[name]=[{'field':v,'kind':'literal_key_argument','evidence':e}]
                            # Follow only reference parameters as writes to caller.
                            if '&' in text(p):ca[name]=aliases.get(text(a),(uid,info,a))
                        result.extend(visit(cid,callee,ce,ca,seen))
            return result
        for uid,info in self.x.functions_by_id.items():
            if not self.x.nodes[uid]['definition']:continue
            # Two passes allow a reference write to a local, then a member copy.
            for _ in range(2):
                for (tid,tinfo,target),origins,evidence in visit(uid,info,{}, {},set()):
                    wire=[o for o in origins if o['kind']=='json_subscript']
                    if not wire or tid!=uid or target is None:continue
                    if target.type=='identifier':
                        self.reference_writes.setdefault((uid,text(target)),[]).append({'position':target.start_byte,'origins':wire})
                    if target.type=='field_expression':
                        receiver=self.x.infer(target.child_by_field_name('argument'),tinfo['path'],tinfo['scope'],tid)
                        self.field_writes.append({'member':text(target.child_by_field_name('field')),'owner_types':receiver['names'],
                            'wire_fields':sorted({o['field'] for o in wire}),'source_symbol':tid,
                            'conditions':self.x.conditions(target),'evidence':[self.ev(tinfo['path'],target),evidence,*[e for o in wire for e in o['evidence']]]})
        self.field_writes=list({json.dumps(w,sort_keys=True):w for w in self.field_writes}.values())

    def dispatch_methods(self,handler):
        """Follow calls on a registry-selected object, then its inherited wrappers."""
        starts=[]
        for lookup in self.lookups:
            if lookup['registry']!=handler['registry']:continue
            info=self.x.functions_by_id[lookup['source_symbol']]
            for call in walk(info['container']):
                if call.type!='call_expression':continue
                f=call.child_by_field_name('function')
                if f is None or f.type!='field_expression':continue
                receiver=f.child_by_field_name('argument');init=self.local_initializer(text(receiver),call,info)
                selected=init if init is not None else receiver
                if selected is None or selected.type!='call_expression':continue
                sf=selected.child_by_field_name('function')
                if sf is None or sf.type!='field_expression':continue
                if self.field_owner('::'.join(info['scope']),text(sf.child_by_field_name('argument')))==handler['registry'] and text(sf.child_by_field_name('field'))=='at':
                    starts.append((text(f.child_by_field_name('field')),[self.ev(info['path'],call)]))
        methods=[]
        for cls in handler['objects']:
            lineage=self.lineage(cls);todo=list(starts);seen=set()
            while todo:
                name,evidence=todo.pop()
                if name in seen or name.startswith('~'):continue
                seen.add(name)
                for uid,f in self.x.functions_by_id.items():
                    if '::'.join(f['scope']) not in lineage or f['signature'][0].rsplit('::',1)[-1]!=name:continue
                    if not self.x.nodes[uid]['definition']:continue
                    path=evidence+[self.ev(f['path'],f['container'])]
                    if '::'.join(f['scope'])==cls:methods.append({'id':uid,'evidence':path,'status':'source_dispatch_candidate'})
                    else:
                        for call in walk(f['container']):
                            if call.type!='call_expression':continue
                            cf=call.child_by_field_name('function')
                            if cf and cf.type=='identifier':todo.append((text(cf),path+[self.ev(f['path'],call)]))
        return list({m['id']:m for m in methods}.values())

    def build(self):
        self.collect_field_writes();self.collect_registries();self.collect_groups()
        providers=[]
        for group in self.groups:
            handlers=[r for r in self.registrations if r['owner'] in {c['class'] for c in group['components']} and r['objects']]
            json_registries={r['registry'] for r in self.lookups if any(o['kind']=='json_subscript' for o in r['key_origins'])}
            decoders=[r for r in self.registrations if r['owner'] in {c['class'] for c in group['components']} and r['functions'] and r['registry'] in json_registries]
            for handler in handlers:
                matches=[r for r in decoders if r['key']==handler['key'] and r['key'] is not None]
                for decoder in matches:
                    key_fields=sorted({o['field'] for r in self.lookups if r['registry']==decoder['registry'] for o in r['key_origins'] if o['kind']=='json_subscript'})
                    component_methods={c['method'] for c in group['components'] if c['class']==decoder['owner']}
                    scope_registrations=[r for r in self.registrations if r['factory_method'] in component_methods]
                    scope_lookups=[r for r in self.lookups if r['registry'] in {x['registry'] for x in scope_registrations} and any(o['kind']=='json_subscript' for o in r['key_origins'])]
                    scope_fields=sorted({o['field'] for r in scope_lookups for o in r['key_origins'] if o['kind']=='json_subscript'})
                    methods=self.dispatch_methods(handler)
                    member_reads=[o for r in self.lookups if r['registry']==handler['registry'] for o in r['key_origins'] if o['kind']=='member_read']
                    mapping=[w for w in self.field_writes if any(w['member']==o['field'] and set(w['owner_types'])&set(o['owner_types']) for o in member_reads)]
                    providers.append({'id':'provider:'+handler['id']+':'+decoder['id'],'path':handler['path'],'line':handler['line'],
                        'name':handler['value_expression'],'command':handler['key'],'command_fields':key_fields,'scope_values':sorted({k['value'] for k in group['keys']}),
                        'scope_fields':scope_fields,'scope_registrations':scope_registrations,'scope_lookups':scope_lookups,
                        'factory_group':group,'handler_registration':handler,'decoder_registration':decoder,
                        'handler_methods':[m['id'] for m in methods],'dispatch_evidence':methods,
                        'decoded_key_mappings':mapping,'decoded_key_status':'source_mapping_candidate' if any(set(w['wire_fields'])&set(key_fields) for w in mapping) else 'unresolved',
                        'status':'registered_candidate' if group['static_constructions'] else 'factory_not_instantiated'})
        return {'facts':self.facts,'protocol':{'version':'0.2.0','registrations':self.registrations,'lookups':self.lookups,'factory_groups':self.groups,
                'providers':providers,'field_mappings':self.field_writes,'diagnostics':self.diagnostics,'limits':['source_type_candidates','registry_value_must_be_const_key','preprocessor_conditions_not_evaluated','object_factory_group_is_source_scope','RapidJSON_string_accessor_model','reference_write_summaries_are_candidates']}}


def analyze_protocol(sources,parser):return ProtocolExtractor(sources,parser).build()
