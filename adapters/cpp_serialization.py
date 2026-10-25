"""Infer RapidJSON field mappings through source wrappers and JSON builders.

Application names and field keys are source inputs. Library behavior is limited
to typed RapidJSON construction/AddMember/PushBack and explicit std accessors.
"""
from copy import deepcopy
import json
import re

from adapters.cpp_data import arguments
from adapters.cpp_control import predicates
from adapters.cpp_facts import declared_name
from adapters.cpp_library_types import LibraryTypes
from adapters.cpp_protocol import ProtocolExtractor
from adapters.syntax_supplement import text
from adapters.cpp_value_types import split_template


class Serialization:
    def __init__(self,data,*,max_steps=10000,max_mapping_visits=10000,max_depth=12):
        if min(max_steps,max_mapping_visits,max_depth)<1:raise ValueError('analysis budgets must be positive')
        self.max_steps=max_steps;self.max_mapping_visits=max_mapping_visits;self.max_depth=max_depth
        self.d=data;self.x=data.x;self.types=LibraryTypes(self.x);self.cache={};self.active=set()
        self.protocol=ProtocolExtractor(None,None,extractor=self.x,facts=data.facts,value_types=data.types)
        self.eligible={uid for uid,info in self.x.functions_by_id.items() if self.x.nodes[uid]['definition'] and
            (self.types.is_json(info['return_type'],info['path'],info['scope']) or
             any(self.types.is_json(text(p.child_by_field_name('type')),info['path'],info['scope']) for p in info['parameter_nodes']))}

    @staticmethod
    def unknown(reason):return {'kind':'unknown','reason':reason}

    def type_family(self,value,path,scope):
        if value.get('kind')=='json' or value.get('json_type'):return 'json'
        if value.get('kind')=='literal':return 'text' if value.get('literal_type')=='string' else 'scalar'
        spelling=re.sub(r'\b(const|volatile)\b','',value.get('value_type','')).strip().strip('&* ').strip()
        path=value.get('type_path',path);scope=value.get('type_scope',scope)
        head,args=split_template(spelling)
        if head in {'std::vector','std::optional'}:return head
        if self.types.is_json(spelling,path,scope):return 'json'
        if self.types.resolve(spelling,path,scope)&{'std::string','std::string_view'}:return 'text'
        if re.fullmatch(r'(?:std::)?(?:u?int(?:8|16|32|64)_t|size_t|float|double|bool|char|int|short|long)',spelling):return 'scalar'
        if re.fullmatch(r'(?:(?:unsigned|signed)\s+)?(?:short|long|long long)(?:\s+int)?|(?:unsigned|signed)(?:\s+int)?',spelling):return 'scalar'
        return None

    @staticmethod
    def value_key(value,seen=None):
        """Dependency identity without copying repeated source evidence."""
        seen=set() if seen is None else seen
        if not isinstance(value,dict):return value
        if id(value) in seen:return ('cycle',)
        kind=value['kind']
        if kind=='source':return (kind,value['parameter'],tuple(value['selectors']),value.get('cast_type'),value.get('receiver_type'),value.get('conversion'))
        if kind=='literal':return (kind,value['value'])
        if kind=='unknown':return (kind,value['reason'])
        if kind=='alternatives':return (kind,tuple(Serialization.value_key(v,seen|{id(value)}) for v in value['values']))
        return (kind,tuple((op['kind'],Serialization.value_key(op.get('key'),seen|{id(value)}),
            Serialization.value_key(op['value'],seen|{id(value)}),Serialization.value_key(op.get('iteration'),seen|{id(value)}),
            json.dumps(op.get('conditions',[]),sort_keys=True),
            tuple((r['family'],Serialization.value_key(r['value'],seen|{id(value)})) for r in op.get('type_requirements',[]))) for op in value.get('entries',[])))

    def analyze(self,uid):
        if uid in self.cache:return self.cache[uid]
        if uid in self.active or len(self.active)>=self.max_depth:return {'operations':[],'returns':[],'gaps':[{'kind':'recursive_or_depth_limited'}]}
        self.active.add(uid);info=self.x.functions_by_id[uid];path=info['path'];env={};operations=[];returns=[];gaps=[];steps=0
        ev=lambda n:self.d.evidence(path,n)
        guards=lambda n:[{**c,'path':path} for c in predicates(n)]
        params=[]
        owner='::'.join(info['scope'])
        implicit_receiver=not info['parameter_nodes'] and owner in self.x.classes and 'static' not in text(info['container']).split('{',1)[0].split()
        if implicit_receiver:
            params.append({'name':'this','type':owner,'implicit_receiver':True})
            env['this']={'kind':'source','parameter':0,'selectors':[],'root_type':owner,'value_type':owner,
                'receiver_type':owner,'receiver_type_path':path,'receiver_type_scope':info['scope'],
                'type_path':path,'type_scope':info['scope'],'json_type':False,'evidence':[ev(info['container'])]}
        for i,p in enumerate(info['parameter_nodes']):
            typ=text(p.child_by_field_name('type'));params.append({'name':text(declared_name(p)),'type':typ})
            env[text(declared_name(p))]={'kind':'source','parameter':i,'selectors':[],
                'root_type':typ,'value_type':typ,'type_path':path,'type_scope':info['scope'],
                'json_type':self.types.is_json(typ,path,info['scope']),'evidence':[ev(p)]}

        def substitute(value,actuals,seen=None):
            if not isinstance(value,dict):return value
            seen=set() if seen is None else seen
            if id(value) in seen:return self.unknown('cyclic_json_value')
            if value['kind']=='source':
                if value['parameter']>=len(actuals):return self.unknown('argument_missing')
                actual=actuals[value['parameter']]
                if value['selectors']:
                    if actual['kind']!='source':return self.unknown('field_of_non_source_argument')
                    actual={**actual,'selectors':actual['selectors']+value['selectors'],'value_type':value['value_type'],
                        'type_path':value.get('type_path',path),'type_scope':value.get('type_scope',info['scope']),
                        'evidence':actual.get('evidence',[])+value.get('evidence',[])}
                if value.get('cast_type'):actual={**actual,'cast_type':value['cast_type']}
                if value.get('receiver_type'):actual={**actual,**{k:value[k] for k in ('receiver_type','receiver_type_path','receiver_type_scope')}}
                if value.get('conversion'):actual={**actual,'conversion':value['conversion']}
                return actual
            if value['kind']=='json':
                cloned={**value,'entries':[]}
                for op in value['entries']:
                    converted={**op,**{k:substitute(op[k],actuals,seen|{id(value)}) for k in ['key','value','iteration'] if k in op}}
                    converted['type_requirements']=[{**r,'value':substitute(r['value'],actuals,seen|{id(value)})} for r in op.get('type_requirements',[])]
                    if not any(self.type_family(r['value'],path,info['scope']) not in {None,r['family']} for r in converted['type_requirements']):
                        converted['type_requirements']=[r for r in converted['type_requirements'] if self.type_family(r['value'],path,info['scope']) is None]
                        cloned['entries'].append(converted)
                return cloned
            if value['kind']=='alternatives':return {**value,'values':[substitute(v,actuals,seen|{id(value)}) for v in value['values']]}
            return deepcopy(value)

        def apply(destination,op):
            if destination['kind']=='json':destination['entries'].append(op)
            elif destination['kind']=='source' and destination.get('json_type'):
                operations.append({**op,'destination':destination})
            else:gaps.append({'kind':'json_destination_unresolved','evidence':op['evidence']})

        def targets(node):
            found=set(self.d.targets(node,uid,info));fn=node.child_by_field_name('function')
            if fn and fn.type=='field_expression':
                receiver=self.d.types.infer(fn.child_by_field_name('argument'),uid,info)
                for variant in self.d.types.variants(receiver):
                    for cls in self.d.types.dereference(variant).get('names',[]):
                        for group in self.x.members(cls,text(fn.child_by_field_name('field'))):found.update(group)
            if fn and fn.type in {'template_function','qualified_identifier','identifier'}:
                spelling=text(fn)
                for q in self.protocol.qnames(spelling,path,info['scope'],self.protocol.functions):
                    found.update(t for t,f in self.protocol.functions[q] if len(f['parameter_nodes'])==len(arguments(node)))
            expanded=set(found)
            for target in found:expanded.update(self.protocol.reachable_factory(target))
            return sorted(expanded&self.eligible)

        def evaluate(node,scope,loops):
            nonlocal steps
            steps+=1
            if steps>self.max_steps:
                if steps==self.max_steps+1:gaps.append({'kind':'analysis_budget_exhausted','max_steps':self.max_steps})
                return self.unknown('analysis_budget_exhausted')
            if node is None:return self.unknown('missing_expression')
            kind=node.type
            if kind=='this' and 'this' in scope:return scope['this']
            if kind in {'identifier','qualified_identifier'}:
                if text(node) in scope:return scope[text(node)]
                member=self.d.field(text(node),owner,path=path) if implicit_receiver else None
                if member:return {**scope['this'],'selectors':['member:'+text(node)],'value_type':member['type'],
                    'type_path':member['path'],'type_scope':member['owner'].split('::'),'evidence':[ev(node)]}
                value,evidence=self.protocol.constant(node,path,info['scope'])
                return {'kind':'literal','value':value,'literal_type':'string','evidence':evidence} if value is not None else self.unknown('unresolved_identifier')
            if kind=='string_literal':
                try:return {'kind':'literal','value':json.loads(text(node)),'literal_type':'string','evidence':[ev(node)]}
                except ValueError:return self.unknown('unsupported_string_literal')
            if kind in {'number_literal','true','false','null'}:return {'kind':'literal','value':text(node),'evidence':[ev(node)]}
            if kind in {'parenthesized_expression','pointer_expression'}:
                return evaluate(node.named_children[-1],scope,loops) if node.named_children else self.unknown('empty_expression')
            if kind=='field_expression':
                base=evaluate(node.child_by_field_name('argument'),scope,loops);member=text(node.child_by_field_name('field'))
                if base['kind']!='source':return self.unknown('member_base_unresolved')
                typ=base.get('value_type','');head,args=split_template(typ)
                if text(node.child_by_field_name('operator'))=='->' and head in {'std::optional','std::unique_ptr','std::shared_ptr'} and len(args)==1:typ=args[0]
                receiver_type=self.d.types.type(typ,base.get('type_path',path),base.get('type_scope',info['scope']))
                owners=receiver_type.get('names',[])
                fields=[self.d.field(member,owner,path=path) for owner in owners];fields=[f for f in fields if f]
                typ=fields[0]['type'] if len(fields)==1 else ''
                bound=receiver_type.get('template_bindings',{}).get(fields[0]['owner'],{}).get(typ) if len(fields)==1 else None
                if bound:typ=bound.get('spelling',typ)
                return {**base,'selectors':base['selectors']+['member:'+member],'value_type':typ,
                    'type_path':bound.get('path',path) if bound else fields[0]['path'] if len(fields)==1 else path,
                    'type_scope':base.get('type_scope',info['scope']) if bound else fields[0]['owner'].split('::') if len(fields)==1 else info['scope'],
                    'json_type':self.types.is_json(typ,path,info['scope']),'evidence':base.get('evidence',[])+[ev(node)]}
            if kind=='compound_literal_expression':
                typ=text(node.child_by_field_name('type'));value=node.child_by_field_name('value')
                if typ.startswith('std::optional<') and value and len(value.named_children)==1:return evaluate(value.named_children[0],scope,loops)
            if kind=='call_expression':
                fn=node.child_by_field_name('function');spelling=text(fn);args=arguments(node)
                head,type_args=split_template(spelling)
                if head=='std::optional' and len(type_args)==1 and len(args)==1:
                    return evaluate(args[0],scope,loops)
                if spelling in {'std::move','std::forward'} or spelling.startswith('std::forward<'):
                    return evaluate(args[0],scope,loops) if args else self.unknown('empty_forward')
                if spelling.startswith(('dynamic_cast<','static_cast<','const_cast<')) and len(args)==1:
                    value=evaluate(args[0],scope,loops);cast=spelling[spelling.find('<')+1:-1]
                    return {**value,'cast_type':cast,'value_type':cast,'type_path':path,'type_scope':info['scope']}
                if spelling=='rapidjson::StringRef' and args:return evaluate(args[0],scope,loops)
                if self.types.is_json(spelling,path,info['scope']):return {'kind':'json','entries':[],'evidence':[ev(node)]}
                if fn and fn.type=='field_expression':
                    receiver=evaluate(fn.child_by_field_name('argument'),scope,loops);method=text(fn.child_by_field_name('field'))
                    native=receiver['kind']=='json' or receiver.get('json_type')
                    if native and method in {'AddMember','PushBack'}:
                        values=[evaluate(a,scope,loops) for a in args]
                        if len(values)<(3 if method=='AddMember' else 2):return self.unknown('invalid_native_call')
                        op={'kind':'put' if method=='AddMember' else 'append','value':values[1] if method=='AddMember' else values[0],
                            'evidence':[ev(node)],'conditions':guards(node),'source_functions':[uid]}
                        if method=='AddMember':op['key']=values[0]
                        elif loops:op['iteration']=loops[-1]
                        apply(receiver,op);return receiver
                    if native and method=='SetString' and args:
                        return {**evaluate(args[0],scope,loops),'conversion':'RapidJSON_SetString'}
                    if method in {'data','c_str'} and self.types.resolve(receiver.get('value_type',''),path,info['scope'])&{'std::string','std::string_view'}:return receiver
                    head,type_args=split_template(receiver.get('value_type',''))
                    if method=='value' and head=='std::optional' and len(type_args)==1:
                        return {**receiver,'value_type':type_args[0],'conversion':'optional_value'}
                    if native and method=='GetAllocator':return self.unknown('library_metadata')
                    if native:
                        gaps.append({'kind':'json_operation_unmodeled','operation':method,'evidence':[ev(node)]})
                candidates=targets(node)
                if candidates:
                    actuals=[evaluate(a,scope,loops) for a in args];result=[];applied={}
                    for target in candidates:
                        callee=self.x.functions_by_id[target]
                        summary=self.analyze(target)
                        target_actuals=actuals
                        if summary.get('implicit_receiver'):
                            if fn is None or fn.type!='field_expression':continue
                            target_actuals=[evaluate(fn.child_by_field_name('argument'),scope,loops),*actuals]
                        requirements=[];incompatible=False
                        for a,p in zip(actuals,callee['parameter_nodes']):
                            expected=self.type_family({'value_type':text(p.child_by_field_name('type'))},callee['path'],callee['scope'])
                            actual=self.type_family(a,path,info['scope'])
                            if expected and actual and expected!=actual:incompatible=True;break
                            if expected and not actual:requirements.append({'value':a,'family':expected})
                        if incompatible:continue
                        for operation in summary['operations']:
                            op={**operation,**{k:substitute(operation[k],target_actuals) for k in ['key','value','iteration'] if k in operation},
                                'evidence':[ev(node),*operation['evidence']],
                                'conditions':guards(node)+operation['conditions'],
                                'source_functions':[uid,*operation['source_functions']]}
                            destination=substitute(operation['destination'],target_actuals);op.pop('destination',None)
                            needed=[{**r,'value':substitute(r['value'],target_actuals)} for r in operation.get('type_requirements',[])]+requirements
                            if any(self.type_family(r['value'],path,info['scope']) not in {None,r['family']} for r in needed):continue
                            op['type_requirements']=[r for r in needed if self.type_family(r['value'],path,info['scope']) is None]
                            if op['kind']=='append' and loops:op.setdefault('iteration',loops[-1])
                            nonempty=[c for c in op['conditions'] if c.get('conditions',c)]
                            semantic=(id(destination) if destination['kind']=='json' else self.value_key(destination),
                                op['kind'],self.value_key(op.get('key')),self.value_key(op['value']),self.value_key(op.get('iteration')),
                                json.dumps(nonempty,sort_keys=True),tuple((r['family'],self.value_key(r['value'])) for r in op['type_requirements']))
                            if semantic in applied:
                                kept=applied[semantic]
                                kept['source_functions']=sorted(set(kept['source_functions']+op['source_functions']))
                                known={json.dumps(e,sort_keys=True) for e in kept['evidence']}
                                kept['evidence'] += [e for e in op['evidence'] if json.dumps(e,sort_keys=True) not in known]
                            else:apply(destination,op);applied[semantic]=op
                        for returned in summary['returns']:
                            result.append(substitute(returned['value'],target_actuals))
                        if summary['gaps']:gaps.append({'kind':'callee_has_unresolved_steps','callee':target,'evidence':[ev(node)]})
                    if len(result)==1:return result[0]
                    if result and all(self.value_key(r)==self.value_key(result[0]) for r in result):return result[0]
                    if result:return {'kind':'alternatives','values':result}
                    return self.unknown('ambiguous_or_void_source_return')
                if any(evaluate(a,scope,loops).get('kind')=='json' for a in args):
                    gaps.append({'kind':'unknown_call_may_mutate_json','evidence':[ev(node)]})
            return self.unknown('unsupported_expression:'+kind)

        def statement(node,scope,loops):
            if node is None:return False
            if node.type=='compound_statement':
                local=dict(scope);declared=set();stopped=False
                for child in node.named_children:
                    if child.type=='declaration':declared.add(text(declared_name(child)))
                    if statement(child,local,loops):stopped=True;break
                for name in scope:
                    if name not in declared:scope[name]=local[name]
                return stopped
            if node.type=='declaration':
                name=text(declared_name(node));typ=text(node.child_by_field_name('type'));d=node.child_by_field_name('declarator')
                value=d.child_by_field_name('value') if d else None
                if self.types.is_json(typ,path,info['scope']) and value is None:
                    # Tree-sitter can parse enum constructor arguments as a declarator.
                    if d and d.type=='function_declarator' and not any(k in text(d) for k in ['kArrayType','kObjectType']):return False
                    scope[name]={'kind':'json','entries':[],'evidence':[ev(node)]}
                else:scope[name]=evaluate(value,scope,loops)
                return False
            if node.type=='expression_statement':
                for expression in node.named_children:statement(expression,scope,loops)
            elif node.type=='assignment_expression':
                left=node.child_by_field_name('left');value=evaluate(node.child_by_field_name('right'),scope,loops)
                if left and left.type=='identifier':scope[text(left)]=value
                else:gaps.append({'kind':'member_assignment_not_modeled','evidence':[ev(node)]})
            elif node.type=='call_expression':evaluate(node,scope,loops)
            elif node.type=='for_range_loop':
                collection=evaluate(node.child_by_field_name('right'),scope,loops);local=dict(scope)
                name=text(declared_name(node))
                typ=self.d.types.elements(self.d.types.type(collection.get('value_type',''),collection.get('type_path',path),collection.get('type_scope',info['scope'])))
                local[name]={**collection,'selectors':collection['selectors']+['element'],'value_type':typ.get('spelling',''),'json_type':False} if collection['kind']=='source' else self.unknown('range_source_unresolved')
                statement(node.child_by_field_name('body'),local,loops+[collection])
                for name in scope:
                    if local.get(name)!=scope[name]:scope[name]=self.unknown('loop_assignment_unresolved')
            elif node.type=='if_statement':
                yes=dict(scope);no=dict(scope)
                statement(node.child_by_field_name('consequence'),yes,loops)
                statement(node.child_by_field_name('alternative'),no,loops)
                for name in scope:
                    if yes[name]!=no[name]:scope[name]=self.unknown('branch_assignment_unresolved')
                    else:scope[name]=yes[name]
            elif node.type=='else_clause':
                for child in node.named_children:statement(child,scope,loops)
            elif node.type=='return_statement':
                if node.named_children:returns.append({'value':evaluate(node.named_children[0],scope,loops),'conditions':guards(node),'evidence':[ev(node)]})
                return True
            elif node.type=='try_statement':
                gaps.append({'kind':'exception_paths_not_expanded','evidence':[ev(node)]})
                return statement(node.child_by_field_name('body'),scope,loops)
            elif node.type not in {'comment','break_statement','continue_statement'}:
                gaps.append({'kind':'statement_not_modeled','statement':node.type,'evidence':[ev(node)]})
            return False

        statement(info['container'].child_by_field_name('body'),env,[])
        result={'source_symbol':uid,'parameters':params,'implicit_receiver':implicit_receiver,'operations':operations,'returns':returns,'gaps':gaps}
        self.cache[uid]=result;self.active.remove(uid);return result

    def mappings(self,summary):
        records=[];gaps=[];visits=0
        def visit(value,wire,evidence,conditions,seen):
            nonlocal visits
            visits+=1
            if visits>self.max_mapping_visits:
                if visits==self.max_mapping_visits+1:gaps.append({'kind':'mapping_budget_exhausted','max_visits':self.max_mapping_visits})
                return
            if id(value) in seen:gaps.append({'kind':'cyclic_json_builder'});return
            if value['kind']=='alternatives':
                for alternative in value['values']:visit(alternative,wire,evidence,conditions+[{'kind':'source_virtual_or_overload_candidate'}],seen|{id(value)})
                return
            if value['kind']=='source':
                records.append({'wire_path':wire,'source':value,'relation':'value_dependency',
                    'evidence':evidence+value.get('evidence',[]),'conditions':conditions});return
            if value['kind']=='unknown':gaps.append({'kind':'value_source_unresolved','wire_path':wire,'reason':value['reason']});return
            if value['kind']!='json':return
            for op in value['entries']:
                evs=evidence+op['evidence'];conds=conditions+op['conditions']
                conds=conds+[{'kind':'unresolved_overload_requirement',**r} for r in op.get('type_requirements',[])]
                if op['kind']=='put':
                    key=op['key']
                    if key['kind']!='literal' or not isinstance(key['value'],str):gaps.append({'kind':'wire_key_unresolved','evidence':evs});continue
                    visit(op['value'],wire+[key['value']],evs,conds,seen|{id(value)})
                else:
                    source=op.get('iteration')
                    if source and source['kind']=='source':records.append({'wire_path':wire,'source':source,'relation':'array_iteration_source','evidence':evs+source.get('evidence',[]),'conditions':conds})
                    visit(op['value'],wire+['*'],evs,conds,seen|{id(value)})
        for ret in summary['returns']:visit(ret['value'],[],ret['evidence'],ret['conditions'],set())
        unique={json.dumps(r,sort_keys=True):r for r in records}
        return list(unique.values()),gaps

    def build(self):
        functions=[]
        for uid in sorted(self.eligible):
            summary=self.analyze(uid);mappings,gaps=self.mappings(summary)
            info=self.x.functions_by_id[uid]
            for mapping in mappings:
                source=mapping['source'];source['root_types']=self.x.resolve_type(source.get('receiver_type',source.get('cast_type',source['root_type'])),
                    source.get('receiver_type_path',info['path']),source.get('receiver_type_scope',info['scope']))['names']
            if mappings or summary['operations'] or summary['gaps'] or gaps or any(r['value']['kind']=='json' for r in summary['returns']):
                functions.append({'source_symbol':uid,'name':self.x.nodes[uid]['name'],'parameters':summary['parameters'],
                    'field_mappings':mappings,'wrapper_operation_count':len(summary['operations']),
                    'gaps':summary['gaps']+gaps,'status':'source_serialization_candidate'})
        self.protocol.collect_registries();serializers={f['source_symbol'] for f in functions if f['field_mappings']}
        registrations=[r for r in self.protocol.registrations if set(r['functions'])&serializers]
        return {'version':'0.1.0','library_model':'RapidJSON_typed_builder/0.1.0','functions':functions,'registrations':registrations,
            'budgets':{'max_steps':self.max_steps,'max_mapping_visits':self.max_mapping_visits,'max_depth':self.max_depth},
            'limits':['source_overload_candidates','conditional_builder_operations','unknown_calls_and_transformations_remain_gaps',
                'source_range_loop_cardinality_not_observed','runtime_serialization_and_delivery_not_observed','local_type_aliases_not_expanded']}
