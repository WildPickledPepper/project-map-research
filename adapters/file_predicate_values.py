"""Pure evaluation of bounded file predicates; no source code or I/O executes."""
from dataclasses import dataclass
from adapters.path_values import expression_from_dag,normalize,literal,unknown
from adapters.path_patterns import root_identity


@dataclass(frozen=True)
class Missing:
    reason:str


PATH_OPS={'source_file','python_join','join','python_dirname','python_realpath','python_parent','to_path_buf',
    'borrow','clone','as_path','some','unwrap','parent','pop','set_file_name','set_extension'}


def truth(value):
    if isinstance(value,Missing):return value
    if isinstance(value,dict):
        if value.get('resolution')=='constant' and isinstance(value.get('path'),str):return bool(value['path'])
        return Missing('structured_value_truth_not_known')
    return bool(value)


def evaluate(expression,*,style,bindings=None,host_system=None,artifact_path=None,artifact_kind=None,environment=None):
    bindings=bindings or {};host_system=host_system or {};memo={};substituted={}
    try:term=expression_from_dag(expression) if expression.get('schema') else expression
    except (ValueError,KeyError,TypeError):return {'known':False,'reason':'invalid_predicate_expression'}
    def primitive(value):
        return value is None or type(value) in {bool,int,float,str} or isinstance(value,(tuple,list)) and all(primitive(v) for v in value)
    def rewrite(current):
        key=id(current)
        if key in substituted:return substituted[key]
        op=current['op']
        if op=='entry_name':result=literal(bindings[current['variable']]) if current['variable'] in bindings else unknown(current['source'],'directory_variable_not_bound')
        elif op in {'host_system','host_os_name','host_sys_platform','env_value'} or op.startswith('string_'):
            value=walk(current);result=unknown(current.get('source'),value.reason) if isinstance(value,Missing) else literal(value)
        else:
            result={**current}
            if 'args' in current:result['args']=[rewrite(a) for a in current['args']]
            if 'choices' in current:result['choices']=[{**c,'value':rewrite(c['value'])} for c in current['choices']]
        substituted[key]=result;return result
    def path(value):
        if isinstance(value,dict) and 'segments' in value:return value
        if isinstance(value,str):return normalize(literal(value),style)[0]
        return None
    def compare(left,right,op):
        if isinstance(left,Missing):return left
        if isinstance(right,Missing):return right
        if not (primitive(left) and primitive(right)):return Missing('nonprimitive_comparison_not_expanded')
        if op in {'Is','IsNot'}:
            if left is not None and right is not None and type(left) is not bool and type(right) is not bool:return Missing('object_identity_not_expanded')
            result=left is right;return result if op=='Is' else not result
        try:
            return {'Eq':lambda:left==right,'NotEq':lambda:left!=right,'Lt':lambda:left<right,'LtE':lambda:left<=right,
                'Gt':lambda:left>right,'GtE':lambda:left>=right,'In':lambda:left in right,'NotIn':lambda:left not in right}[op]()
        except (KeyError,TypeError,ValueError):return Missing('comparison_type_or_operator_not_supported')
    def walk(current):
        key=id(current)
        if key in memo:return memo[key]
        memo[key]=Missing('predicate_expression_cycle');op=current.get('op');args=current.get('args',[])
        if op=='literal':value=current['value']
        elif op=='unknown':value=Missing(current['reason'])
        elif op=='symbol':value=Missing('runtime_parameter_not_supplied')
        elif op=='entry_name':value=bindings.get(current['variable'],Missing('directory_variable_not_bound'))
        elif op=='choice':
            values=[walk(c['value']) for c in current['choices']]
            value=values[0] if values and all(not isinstance(v,Missing) and type(v)==type(values[0]) and v==values[0] for v in values) else Missing('choice_not_selected')
        elif op in {'host_system','host_os_name','host_sys_platform'}:
            name=host_system.get('name');styles=host_system.get('path_style')
            value=(name if name in {'Windows','Linux','Darwin'} else Missing('python_host_system_name_not_bound')) if op=='host_system' else (
                {'windows':'nt','posix':'posix'}.get(styles,Missing('python_host_os_name_not_bound')) if op=='host_os_name' else
                {'Windows':'win32','Linux':'linux','Darwin':'darwin'}.get(name,Missing('python_sys_platform_not_bound')))
        elif op=='env_value':
            name=walk(args[0]);value=Missing('runtime_environment_not_supplied')
            if isinstance(name,str) and environment is not None and name in environment:
                supplied=environment[name];value=walk(args[1]) if supplied is None else supplied if isinstance(supplied,str) else Missing('invalid_environment_value')
        elif op in {'tuple','list'}:
            items=[walk(a) for a in args];value=(tuple(items) if op=='tuple' else items) if not any(isinstance(v,Missing) for v in items) else Missing('collection_item_not_known')
        elif op in {'boolean_and','boolean_or'}:
            value=Missing('boolean_operand_not_known')
            for arg in args:
                value=walk(arg);selected=truth(value)
                if isinstance(selected,Missing):value=selected;break
                if (op=='boolean_and' and not selected) or (op=='boolean_or' and selected):break
        elif op=='boolean_not':
            item=truth(walk(args[0]));value=item if isinstance(item,Missing) else not item
        elif op=='compare':
            values=[walk(a) for a in args];results=[compare(a,b,o) for a,b,o in zip(values,values[1:],current['operators'])]
            value=False if any(r is False for r in results) else Missing('comparison_operand_not_known') if any(isinstance(r,Missing) for r in results) else all(results)
        elif op.startswith('string_'):
            values=[walk(a) for a in args];receiver=values[0];method=op.removeprefix('string_')
            if any(isinstance(v,Missing) for v in values):value=Missing('string_operand_not_known')
            elif isinstance(receiver,str):
                try:value=getattr(str,method)(receiver,*values[1:]) if method in {'endswith','startswith','lower','upper'} else Missing('string_method_not_supported')
                except (TypeError,ValueError):value=Missing('string_arguments_not_supported')
            elif isinstance(receiver,dict) and 'segments' in receiver and method=='endswith' and len(values)==2 and isinstance(values[1],str) and '/' not in values[1] and '\\' not in values[1]:
                tail=receiver['segments'][-1] if receiver['segments'] else ''
                value=tail.endswith(values[1]) if isinstance(tail,str) and len(values[1])<=len(tail) else Missing('symbolic_string_prefix_not_known')
            else:value=Missing('string_value_not_concrete')
        elif op=='filesystem_test':
            selected=path(walk(args[0]));value=Missing('filesystem_state_not_supplied')
            if selected and artifact_path and selected['style']==artifact_path['style'] and root_identity(selected)==root_identity(artifact_path):
                exact=selected['segments']==artifact_path['segments'];parent=len(selected['segments'])<len(artifact_path['segments']) and artifact_path['segments'][:len(selected['segments'])]==selected['segments']
                kind=artifact_kind if exact else 'directory' if parent else None
                if kind in {'file','directory'}:value={'isdir':kind=='directory','isfile':kind=='file','exists':True}[current['test']]
        elif op=='ignore_patterns':
            values=[walk(a) for a in args];value={'kind':'ignore_patterns','patterns':values} if all(isinstance(v,str) for v in values) else Missing('ignore_pattern_not_known')
        elif op in PATH_OPS:
            try:
                rows=normalize(rewrite(current),style);value=rows[0] if len(rows)==1 and not rows[0]['unresolved'] else Missing('predicate_path_not_bound')
            except (KeyError,ValueError,TypeError):value=Missing('invalid_predicate_path')
        else:value=Missing('predicate_operation_not_supported:'+str(op))
        memo[key]=value;return value
    try:result=walk(term)
    except (KeyError,TypeError,ValueError,AttributeError,RecursionError):return {'known':False,'reason':'invalid_or_unexpanded_predicate'}
    return {'known':False,'reason':result.reason} if isinstance(result,Missing) else {'known':True,'value':result}


def conditions(guards,**context):
    """Return false for a proven exclusion, otherwise retain unresolved guards."""
    residual=[];proof=[]
    for guard in guards:
        if guard['kind']=='later_storage_assignment_not_selected':
            residual.append({'condition':guard,'reason':'reaching_definition_selection_not_expanded'});continue
        if guard['kind'] not in {'enclosing_source_branch','preceding_control_transfer_not_taken','mapping_entry_selected'}:continue
        rows=guard.get('predicate_expressions')
        if rows is None or not guard.get('predicate_complete',False):
            residual.append({'condition':guard,'reason':'predicate_context_not_bound'});continue
        verdicts=[]
        for row in rows:
            result=evaluate(row['expression'],**context)
            selected=truth(result['value']) if result['known'] else Missing(result['reason'])
            verdicts.append(selected==row['polarity'] if not isinstance(selected,Missing) else None)
        selected=False if False in verdicts else None if None in verdicts else True
        permitted=(not selected if selected is not None else None) if guard['kind']=='preceding_control_transfer_not_taken' else selected
        if permitted is False:return {'permitted':False,'excluded_by':guard,'proof':proof,'residual':residual}
        if permitted is None:residual.append({'condition':guard,'reason':'runtime_or_unexpanded_predicate'})
        else:proof.append({'condition':guard,'permitted':True})
    return {'permitted':True,'proof':proof,'residual':residual}
