"""Bounded builtin-dictionary path selection over native Python value origins."""
import ast
from collections import defaultdict
from adapters.file_predicate_values import evaluate
from adapters.path_values import expression_dag,literal,operation,unknown


def hashable_value(value):
    return value is None or type(value) in {str,int,bool} or isinstance(value,tuple) and all(hashable_value(v) for v in value)


def hashable_term(term):
    op=term['op']
    if op=='literal':return hashable_value(term['value'])
    if op in {'host_system','host_os_name','host_sys_platform','string_lower','string_upper','string_endswith','string_startswith'}:return True
    if op=='tuple':return all(hashable_term(t) for t in term['args'])
    if op=='choice':return bool(term['choices']) and all(hashable_term(c['value']) for c in term['choices'])
    return False


class MappingPaths:
    def __init__(self,paths):
        self.paths=paths;self.reverse=defaultdict(list);self.safety={}
        for e in paths.facts['edges']:
            if e['kind'] in {'VALUE_SOURCE','READS_BINDING','IMPORTS_SYMBOL'}:self.reverse[e['target']].append(e['source'])

    def readonly(self,origin):
        if origin in self.safety:return self.safety[origin]
        p=self.paths;pending=[origin];seen=set();reason=None
        while pending and reason is None:
            uid=pending.pop()
            if uid in seen:continue
            seen.add(uid)
            if len(seen)>512:reason='python_dictionary_alias_budget';break
            node=p.nodes[uid];syntax=p.ast.get(uid)
            pending.extend(self.reverse[uid])
            pending.extend(e['target'] for e in p.out[uid] if e['kind']=='BINDS_ARGUMENT')
            if node['kind']=='binding':
                pending.extend(p.storage.groups[(node.get('enclosing_symbol'),node['name'])]);continue
            if not isinstance(syntax,(ast.Name,ast.Attribute,ast.Dict)):continue
            parent=p.parents.get(id(syntax))
            if isinstance(parent,(ast.Assign,ast.AnnAssign)) and parent.value is syntax:
                targets=parent.targets if isinstance(parent,ast.Assign) else [parent.target]
                if len(targets)==1 and isinstance(targets[0],ast.Name):continue
            if isinstance(parent,ast.Subscript) and parent.value is syntax and isinstance(parent.ctx,ast.Load):continue
            if isinstance(parent,ast.Attribute) and parent.value is syntax and parent.attr=='get':
                call=p.parents.get(id(parent))
                if isinstance(call,ast.Call) and call.func is parent:continue
            call=parent if isinstance(parent,ast.Call) else p.parents.get(id(parent)) if isinstance(parent,ast.keyword) else None
            if isinstance(call,ast.Call):
                call_id=p.ast_ids.get(id(call))
                if any(e['kind']=='BINDS_ARGUMENT' and e.get('call')==call_id for e in p.out[uid]):continue
            reason='python_dictionary_mutation_or_escape_not_expanded'
        self.safety[origin]=reason;return reason

    def literal(self,uid,frame,ev):
        p=self.paths;syntax=p.ast[uid]
        if len(syntax.keys)>32:return unknown(uid,'python_dictionary_entry_budget')
        if any(k is None for k in syntax.keys):return unknown(uid,'python_dictionary_unpack_not_expanded')
        reason=self.readonly(uid)
        if reason:return unknown(uid,reason)
        keys=p.children(uid,'keys');values=p.children(uid,'values')
        if len(keys)!=len(syntax.keys) or len(keys)!=len(values):return unknown(uid,'python_dictionary_native_components_missing')
        args=[]
        for key,value in zip(keys,values):args.extend([p.predicates.expression(key,frame),ev(value)])
        return operation('python_dictionary',*args,source=uid)

    def select(self,uid,table,key,key_source,default,conditions=()):
        p=self.paths
        if table['op']=='choice':
            return {'op':'choice','source':uid,'choices':[{'value':self.select(uid,c['value'],key,key_source,default,list(conditions)+c.get('conditions',[]))}
                for c in table['choices']]}
        if table['op']!='python_dictionary':return unknown(uid,table.get('reason','python_lookup_receiver_not_proven_dictionary'))
        if not hashable_term(key):return unknown(uid,'python_dictionary_lookup_key_type_not_proven')
        entries={};args=table['args']
        for index in range(0,len(args),2):
            result=evaluate(args[index],style=p.style)
            if not result['known'] or not hashable_value(result['value']):return unknown(uid,'python_dictionary_key_not_constant_hashable')
            entries[result['value']]=(args[index],args[index+1])
        def guard(test,selection):
            complete=True
            try:expression=expression_dag(test)
            except (ValueError,RecursionError):expression=expression_dag(unknown(uid,'python_dictionary_guard_budget'));complete=False
            return {'kind':'mapping_entry_selected','lookup':uid,'mapping':table['source'],'key_source':key_source,'selection':selection,
                'predicate_complete':complete,'predicate_expressions':[{'source':key_source,'polarity':True,'expression':expression}]}
        choices=[]
        for entry_key,value in entries.values():
            test=operation('compare',key,entry_key,operators=['Eq'],source=uid)
            choices.append({'value':value,'conditions':list(conditions)+[guard(test,'present')]})
        keys=operation('tuple',*[e[0] for e in entries.values()])
        missing=operation('compare',key,keys,operators=['NotIn'],source=uid)
        value=default if default is not None else unknown(uid,'python_dictionary_subscription_missing_key')
        choices.append({'value':value,'conditions':list(conditions)+[guard(missing,'missing')]})
        return {'op':'choice','source':uid,'choices':choices}

    def subscript(self,uid,frame,ev):
        p=self.paths;receivers=p.children(uid,'value');keys=p.children(uid,'slice')
        if len(receivers)!=len(keys) or len(keys)!=1:return unknown(uid,'python_dictionary_subscript_shape')
        return self.select(uid,ev(receivers[0]),p.predicates.expression(keys[0],frame),keys[0],None)

    def call(self,uid,frame,ev):
        p=self.paths;callees=p.targets(uid,{'CALLS_EXPRESSION'})
        if len(callees)!=1 or p.nodes[callees[0]].get('member')!='get':return None
        receivers=p.children(callees[0],'value')
        if len(receivers)!=1:return unknown(uid,'python_dictionary_get_receiver_shape')
        args=[e for e in p.out[uid] if e['kind']=='CALL_ARGUMENT']
        if len(args) not in {1,2} or any(e.get('spread') or e.get('keyword') is not None for e in args):
            return unknown(uid,'python_dictionary_get_argument_shape')
        args=sorted(args,key=lambda e:e['index']);default=ev(args[1]['target']) if len(args)==2 else literal(None)
        table=ev(receivers[0])
        def supported(term):
            return term['op']=='python_dictionary' or term['op']=='unknown' and term['reason'].startswith('python_dictionary_') or term['op']=='choice' and any(supported(c['value']) for c in term['choices'])
        if not supported(table):return None
        return self.select(uid,table,p.predicates.expression(args[0]['target'],frame),args[0]['target'],default)
