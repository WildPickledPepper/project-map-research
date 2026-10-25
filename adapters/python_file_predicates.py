"""Typed, source-bound predicate expressions for file operation conditions."""
import ast
from adapters.path_values import expression_dag,literal,operation,unknown


def string_term(term):
    op=term['op']
    if op=='literal':return isinstance(term['value'],str)
    if op in {'entry_name','python_join','python_dirname','python_realpath','string_lower','string_upper','host_system'}:return True
    if op=='env_value':return string_term(term['args'][1])
    if op=='choice':return bool(term['choices']) and all(string_term(c['value']) for c in term['choices'])
    return False


class Predicates:
    def __init__(self,paths):self.paths=paths;self.memo={}

    def exact_api(self,uid,frame,seen=()):
        """Require all reaching origins to identify the same library member."""
        p=self.paths;key=(uid,frame['key'])
        if key in seen or len(seen)>=48:return set()
        seen=seen+(key,);node=p.nodes[uid]
        if node['kind']=='module_reference' and not node['resolution'].startswith('source_') and not node.get('level'):
            return p.context_api(uid,frame)
        if node['kind']=='parameter':
            ref=p.calls.parameter(uid,frame)
            return self.exact_api(ref['uid'],ref['frame'],seen) if 'uid' in ref else set()
        receivers=p.children(uid,'value') if node.get('member') else []
        if len(receivers)==1:return {name+'.'+node['member'] for name in self.exact_api(receivers[0],frame,seen)}
        results=[]
        for ref in p.storage.sources(uid,frame):
            if 'reason' in ref or ref.get('conditions'):return set()
            scope=p.calls.scope(p.nodes[ref['uid']].get('enclosing_symbol'),frame) if p.nodes[ref['uid']]['kind']=='binding' else frame
            if p.nodes[ref['uid']]['kind']=='binding' and p.guard_conditions(ref['uid'],scope):return set()
            results.append(self.exact_api(ref['uid'],scope,seen))
        return results[0] if results and all(r==results[0] for r in results) else set()

    def serialized(self,uid,frame):
        try:return expression_dag(self.expression(uid,frame))
        except (ValueError,RecursionError):return expression_dag(unknown(uid,'predicate_expression_budget'))

    def expression(self,uid,frame,seen=()):
        p=self.paths;key=(p.style,uid,frame['key'])
        if key in seen or len(seen)>=48:return unknown(uid,'predicate_expression_cycle_or_depth')
        if key in self.memo:return self.memo[key]
        seen=seen+(key,);node=p.nodes[uid];syntax=p.ast.get(uid)
        ev=lambda v:self.expression(v,frame,seen)
        if node.get('literal_type') in {'str','int','bool','NoneType'}:result={**literal(node['literal']),'source':uid}
        elif node['kind']=='parameter':
            reference=p.calls.parameter(uid,frame)
            result=self.expression(reference['uid'],reference['frame'],seen) if 'uid' in reference else unknown(uid,reference.get('reason','runtime_parameter_value'))
        elif isinstance(syntax,ast.UnaryOp) and isinstance(syntax.op,ast.Not):
            result=operation('boolean_not',ev(p.children(uid,'operand')[0]),source=uid)
        elif isinstance(syntax,ast.BoolOp):
            result=operation('boolean_and' if isinstance(syntax.op,ast.And) else 'boolean_or',*[ev(v) for v in p.children(uid,'values')],source=uid)
        elif isinstance(syntax,ast.Compare):
            terms=[ev(p.children(uid,'left')[0]),*[ev(v) for v in p.children(uid,'comparators')]]
            result=operation('compare',*terms,operators=[type(o).__name__ for o in syntax.ops],source=uid)
        elif isinstance(syntax,(ast.Tuple,ast.List)):
            result=operation('tuple' if isinstance(syntax,ast.Tuple) else 'list',*[ev(v) for v in p.children(uid,'elts')],source=uid)
        elif node['kind']=='call_site':result=self.call(uid,frame,ev)
        elif node.get('identifier')=='__file__':result=p.evaluate(uid,frame)
        else:
            apis=self.exact_api(uid,frame)
            if 'os.name' in apis:result={'op':'host_os_name','source':uid}
            elif 'sys.platform' in apis:result={'op':'host_sys_platform','source':uid}
            elif apis&{'shutil.copyfile','shutil.copy','shutil.copy2'}:
                result={'op':'literal','value':{'kind':'library_callable','api':sorted(apis&{'shutil.copyfile','shutil.copy','shutil.copy2'})},'source':uid}
            else:
                choices=[]
                for reference in p.storage.sources(uid,frame):
                    from_iteration=False
                    scope=p.calls.scope(p.nodes[reference['uid']].get('enclosing_symbol'),frame) if p.nodes[reference['uid']]['kind']=='binding' else frame
                    if 'reason' in reference:value=unknown(reference['uid'],reference['reason'])
                    else:
                        value=p.iterations.value(reference['uid'],uid,frame,seen)
                        from_iteration=value is not None
                        if value is None:
                            value=self.expression(reference['uid'],scope,seen)
                    guards=reference.get('conditions',[])
                    if p.nodes[reference['uid']]['kind']=='binding':guards=guards+p.guard_conditions(reference['uid'],scope)
                    # Scalar selection through conditional writes requires a
                    # reaching-definition proof, not just a matching value.
                    if guards and not from_iteration:value=unknown(reference['uid'],'conditional_predicate_binding_not_selected')
                    choices.append({'value':value,'conditions':guards})
                result={'op':'choice','source':uid,'choices':choices} if choices else unknown(uid,'predicate_value_not_modeled')
        self.memo[key]=result;return result

    def call(self,uid,frame,ev):
        p=self.paths;apis=set().union(*(self.exact_api(t,frame) for t in p.targets(uid,{'CALLS_EXPRESSION'})))
        def arg(index,keys=(),default=None):
            rows=p.argument(uid,index,keys)
            return p.choice([ev(v) for v in rows],uid) if rows else literal(default)
        if 'platform.system' in apis:return {'op':'host_system','source':uid}
        if 'os.getenv' in apis:return operation('env_value',arg(0,('key',)),arg(1,('default',)),source=uid)
        if apis&{'os.path.isdir','os.path.isfile','os.path.exists'}:
            return operation('filesystem_test',arg(0,('path','s')),test=sorted(apis&{'os.path.isdir','os.path.isfile','os.path.exists'})[0].rsplit('.',1)[1],source=uid)
        if 'shutil.ignore_patterns' in apis:
            arguments=[e for e in p.out[uid] if e['kind']=='CALL_ARGUMENT']
            if any(e.get('spread') or e.get('keyword') is not None for e in arguments):return unknown(uid,'ignore_patterns_arguments_not_expanded')
            return operation('ignore_patterns',*[ev(e['target']) for e in sorted(arguments,key=lambda e:e['index'])],source=uid)
        callees=p.targets(uid,{'CALLS_EXPRESSION'})
        if len(callees)==1:
            callee=p.nodes[callees[0]];receivers=p.children(callees[0],'value');member=callee.get('member')
            if len(receivers)==1 and member in {'endswith','startswith','lower','upper'}:
                receiver=ev(receivers[0]);arguments=[e for e in p.out[uid] if e['kind']=='CALL_ARGUMENT']
                if string_term(receiver) and not any(e.get('spread') or e.get('keyword') is not None for e in arguments):
                    args=[ev(e['target']) for e in sorted(arguments,key=lambda e:e['index'])]
                    if (member in {'lower','upper'} and not args) or member in {'endswith','startswith'} and 1<=len(args)<=3:
                        return operation('string_'+member,receiver,*args,source=uid)
        # Source helpers and path operations retain the existing native binding
        # and path rules. Unknown calls remain expressions, never executed code.
        return p.evaluate(uid,frame)

    def enrich(self,conditions):
        rows=[]
        for condition in conditions:
            frame=self.paths.calls.registry.get(condition.get('evaluation_context'));predicates=[]
            refs=([condition] if condition.get('test') else [])+condition.get('when',[])
            if frame:
                for ref in refs:
                    if ref.get('test') not in self.paths.nodes:continue
                    dag=self.serialized(ref['test'],frame)
                    predicates.append({'source':ref['test'],'polarity':ref['polarity'],'expression':dag})
            expected=1 if condition['kind']=='enclosing_source_branch' else len(condition.get('when',[]))
            rows.append({**condition,**({'predicate_expressions':predicates,'predicate_complete':len(predicates)==expected} if frame else {})})
        return rows
