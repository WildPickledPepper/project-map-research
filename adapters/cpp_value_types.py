"""Bounded source type propagation for standard containers and template receivers.

This supplements compiler-free candidates; it never chooses a runtime object.
"""
import re
from adapters.cpp_facts import declared_name,scoped_name,parameter_type
from adapters.syntax_supplement import cpp_scope,parents,text,walk


def split_template(spelling):
    spelling=spelling.strip();start=spelling.find('<')
    if start<0 or not spelling.endswith('>'):return spelling,[]
    parts=[];depth=0;begin=start+1
    for i in range(begin,len(spelling)-1):
        char=spelling[i]
        if char in '<([':depth+=1
        elif char in '>)]':depth-=1
        elif char==',' and not depth:parts.append(spelling[begin:i].strip());begin=i+1
    parts.append(spelling[begin:-1].strip())
    return spelling[:start].strip(),parts


class ValueTypes:
    MAPS={'std::map','std::unordered_map','std::multimap','std::unordered_multimap'}
    SEQUENCES={'std::deque','std::vector','std::list','std::set','std::unordered_set'}
    POINTERS={'std::shared_ptr','std::unique_ptr'}

    def __init__(self,data):
        self.d=data;self.x=data.x;self.templates={};self.cache={};self.in_progress=set();self.unresolved_keys=set()
        for path,unit in self.x.units.items():
            for node in walk(unit['tree'].root_node):
                if node.type not in {'class_specifier','struct_specifier'}:continue
                name=node.child_by_field_name('name')
                if name is None:continue
                owner=scoped_name('::'.join(cpp_scope(node)+[text(name)]),path)
                parent=node.parent
                if parent and parent.type=='template_declaration':
                    params=parent.child_by_field_name('parameters')
                    names=[]
                    for param in params.named_children if params else []:
                        named=param.child_by_field_name('name') or next((n for n in param.named_children if n.type=='type_identifier'),None)
                        if named:names.append(text(named))
                    self.templates[owner]=names

    def type(self,spelling,path,scope,bindings=None,depth=0):
        if depth>10:return {'kind':'unknown','reason':'type_depth_limit'}
        bindings=bindings or {};raw=spelling
        spelling=re.sub(r'\b(const|volatile|typename|class|struct)\b','',spelling).strip().strip('&* ').strip()
        if spelling in bindings:return bindings[spelling]
        head,args=split_template(spelling)
        parsed=[self.type(a,path,scope,bindings,depth+1) for a in args]
        if head in self.POINTERS|self.MAPS|self.SEQUENCES:
            return {'kind':'standard','name':head,'arguments':parsed,'spelling':raw,'path':path}
        names=self.x.resolve_type(head,path,scope)['names']
        return {'kind':'object' if names else 'unknown','names':names,'arguments':parsed,'spelling':raw,'path':path,
                'template_bindings':{owner:dict(zip(self.templates.get(owner,[]),parsed)) for owner in names}}

    @staticmethod
    def unknown(reason):return {'kind':'unknown','reason':reason}

    def dereference(self,value):
        while value.get('kind')=='standard' and value['name'] in self.POINTERS and value['arguments']:
            value=value['arguments'][0]
        return value

    def elements(self,value):
        if value.get('kind')!='standard':return self.unknown('not_a_standard_container')
        args=value['arguments']
        if value['name'] in self.MAPS and len(args)>1:return {'kind':'pair','first':args[0],'second':args[1]}
        if value['name'] in self.SEQUENCES and args:return args[0]
        return self.unknown('container_element_unknown')

    def variants(self,value):return value.get('variants',[]) if value.get('kind')=='union' else [value]

    def field_type(self,node,uid,info,bindings,depth,seen):
        field=self.d.receiver_field(node,uid,info,bindings=bindings,depth=depth,seen=seen)
        return self.type(field['type'],field['path'],field['owner'].split('::'),bindings) if field else None

    def unresolved(self,reason,node,uid,info):
        key=(reason,uid,node.start_byte,node.end_byte)
        if key not in self.unresolved_keys:
            self.unresolved_keys.add(key)
            self.d.diagnostics.append({'kind':'cpp_value_type_unresolved','reason':reason,'required':True,
                'source_symbol':uid,**self.d.evidence(info['path'],node)})
        return self.unknown(reason)

    def infer(self,node,uid,info,bindings=None,depth=0,seen=None):
        if node is None:return self.unknown('value_depth_limit_or_missing')
        if depth>24:return self.unresolved('value_depth_limit',node,uid,info)
        bindings=bindings or {};seen=set() if seen is None else seen
        infer=lambda n:self.infer(n,uid,info,bindings,depth+1,seen)
        kind=node.type
        if kind=='this':return self.type('::'.join(info['scope']),info['path'],info['scope'],bindings)
        if kind in {'parenthesized_expression','pointer_expression'}:return infer(node.named_children[-1]) if node.named_children else self.unknown('empty_expression')
        if kind=='identifier':
            variables=self.x.variables(text(node),node,info['path'],uid)
            if variables:
                var=variables[0];key=(info['path'],var['node'].start_byte)
                if key in seen:return self.unresolved('recursive_initializer',node,uid,info)
                if var['type']!='auto':
                    spelling=parameter_type(var['node'],preserve_space=True) if var['node'].type in {'parameter_declaration','optional_parameter_declaration'} else var['type']
                    return self.type(spelling,info['path'],info['scope'],bindings)
                writes=[n for n in walk(info['container']) if n.type=='assignment_expression' and text(n.child_by_field_name('left'))==text(node)
                        and var['node'].end_byte<=n.start_byte<node.start_byte]
                origins=[var['value']] if var['value'] is not None else []
                for write in writes:
                    conditional=any(p.type in {'if_statement','conditional_expression','switch_statement','for_statement','while_statement','lambda_expression'}
                                    for p in parents(write) if p.start_byte>=info['container'].start_byte)
                    if not conditional:origins=[]
                    origins.append(write.child_by_field_name('right'))
                values=[self.infer(o,uid,info,bindings,depth+1,seen|{key}) for o in origins]
                return values[0] if len(values)==1 else {'kind':'union','variants':values} if values else self.unknown('uninitialized_auto')
            for loop in parents(node):
                if loop.type!='for_range_loop':continue
                declarator=loop.child_by_field_name('declarator')
                structured=next((n for n in walk(declarator) if n.type=='structured_binding_declarator'),None) if declarator else None
                names=[text(n) for n in structured.named_children] if structured else [text(declared_name(loop))]
                if text(node) not in names:continue
                if any(loop.start_byte<offset<node.start_byte for offset in self.x._assignments.get(uid,{}).get(text(node),[])):
                    return self.unknown('range_binding_reassigned')
                element=self.elements(infer(loop.child_by_field_name('right')))
                if structured:
                    if element.get('kind')!='pair' or len(names)!=2:return self.unknown('structured_range_element_unknown')
                    return element['first' if names.index(text(node))==0 else 'second']
                return element
            return self.field_type(node,uid,info,bindings,depth,seen) or self.unknown('unresolved_identifier')
        if kind=='conditional_expression':return {'kind':'union','variants':[infer(node.child_by_field_name(k)) for k in ['consequence','alternative']]}
        if kind=='field_expression':
            direct=self.field_type(node,uid,info,bindings,depth,seen)
            if direct:return direct
            base=infer(node.child_by_field_name('argument'));field=text(node.child_by_field_name('field'));out=[]
            for value in self.variants(base):
                if value.get('kind')=='iterator':value=value['element']
                out.append(value.get(field,self.unknown('unresolved_member')) if value.get('kind')=='pair' and field in {'first','second'} else self.unknown('unresolved_member'))
            return out[0] if len(out)==1 else {'kind':'union','variants':out}
        if kind=='subscript_expression':
            base=infer(node.child_by_field_name('argument'));element=self.elements(base)
            return element['second'] if element.get('kind')=='pair' else element
        if kind=='call_expression':
            f=node.child_by_field_name('function');args=node.child_by_field_name('arguments');args=list(args.named_children) if args else []
            head,type_args=split_template(text(f))
            if head in {'std::make_unique','std::make_shared'} and len(type_args)==1:
                pointer='std::unique_ptr' if head=='std::make_unique' else 'std::shared_ptr'
                return self.type(pointer+'<'+type_args[0]+'>',info['path'],info['scope'],bindings)
            if head in {'dynamic_cast','static_cast','const_cast'} and len(type_args)==1:
                return self.type(type_args[0],info['path'],info['scope'],bindings)
            if text(f) in {'std::move','std::forward'} and args:return infer(args[0])
            if text(f)=='std::find_if' and args:return infer(args[0])
            if f and f.type=='field_expression':
                receiver=infer(f.child_by_field_name('argument'));name=text(f.child_by_field_name('field'));out=[]
                for value in self.variants(receiver):
                    if value.get('kind')=='standard' and value['name'] in self.POINTERS and name=='get':out.append(self.dereference(value))
                    elif value.get('kind')=='standard' and value['name'] in self.MAPS|self.SEQUENCES:
                        element=self.elements(value)
                        if name in {'find','begin','end'}:out.append({'kind':'iterator','element':element,'container':value})
                        elif name in {'at','front','back'}:out.append(element['second'] if element.get('kind')=='pair' else element)
                if out:return out[0] if len(out)==1 else {'kind':'union','variants':out}
            resolution=self.call(node,uid,info,bindings,depth+1)
            out=[]
            for target in resolution['candidates']:
                t=self.x.functions_by_id[target['target']]
                out.append(self.type(t['return_type'],t['path'],t['scope'],target['template_bindings']))
            return out[0] if len(out)==1 else {'kind':'union','variants':out} if out else self.unknown('unresolved_call_return')
        return self.unknown('unsupported_expression_type')

    def call(self,node,uid,info,bindings=None,depth=0):
        import json
        bindings=bindings or {};key=(uid,node.start_byte,node.end_byte,json.dumps(bindings,sort_keys=True))
        if key in self.cache:return self.cache[key]
        if key in self.in_progress or depth>24:return {'targets':[],'candidates':[],'gaps':['recursive_or_depth_limited_call']}
        self.in_progress.add(key)
        try:
            f=node.child_by_field_name('function');args=node.child_by_field_name('arguments');argc=len(args.named_children) if args else 0
            candidates=[];gaps=[];receivers=[]
            if f and f.type=='field_expression':
                value=self.infer(f.child_by_field_name('argument'),uid,info,bindings,depth+1)
                for v in self.variants(value):
                    v=self.dereference(v);receivers.append(v)
                    if v.get('kind')=='unknown':gaps.append('receiver_type_unknown');continue
                    for owner in v.get('names',[]):
                        # Do not collapse a visible specialization onto a generic body.
                        special=[n for n in self.x.classes if n.startswith(owner+'<')]
                        if special:gaps.append('template_specialization_not_resolved');continue
                        pending=[owner];seen=set()
                        while pending:
                            cls=pending.pop()
                            if cls in seen:continue
                            seen.add(cls)
                            matching=[(tid,t) for tid,t in self.d.by_owner.get(cls,[]) if t['signature'][0].rsplit('::',1)[-1]==text(f.child_by_field_name('field'))
                                      and sum(p.child_by_field_name('default_value') is None for p in t['parameter_nodes'])<=argc<=len(t['parameter_nodes'])]
                            if matching:
                                candidates.extend({'target':tid,'template_bindings':v.get('template_bindings',{}).get(owner,bindings),
                                                   'basis':'source_receiver_container_and_template_type'} for tid,_ in matching)
                            else:pending.extend(self.x.base_names.get(cls,[]))
            # P1 retains lexical and non-template receiver facts as a fallback.
            # An unknown mutation/specialization must not silently restore a stale type.
            if not candidates and not gaps:
                candidates=[{'target':target,'template_bindings':bindings,'basis':'lexical_or_p1_receiver_type'} for target in self.d.base_targets(node,uid,info)]
            unique={json.dumps(v,sort_keys=True):v for v in candidates};candidates=list(unique.values())
            result={'targets':sorted({v['target'] for v in candidates}),'candidates':candidates,'receiver_types':receivers,
                    'gaps':sorted(set(gaps)),'status':'source_type_candidate','runtime_instance':'unknown'}
            # A nested lookup may exhaust its caller's depth budget. Do not let
            # that partial result poison a later independent top-level lookup.
            if depth==0:self.cache[key]=result
            return result
        finally:self.in_progress.remove(key)
