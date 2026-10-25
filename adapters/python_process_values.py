"""Pure selection of source-extracted process arguments and environment effects."""
import ntpath
import posixpath
from adapters.path_values import literal,normalize
from adapters.file_predicate_values import conditions,evaluate
from adapters.artifact_copy_graph import before


STATIC_GAPS={'predicate_context_not_bound','reaching_definition_selection_not_expanded'}


def string_candidates(term,style,max_candidates=32):
    """Preserve argument bytes represented as strings, including empty and './'."""
    memo={}
    def walk(t):
        key=id(t)
        if key in memo:return memo[key]
        op=t['op'];rows=[(None,[])]
        if op=='literal' and isinstance(t.get('value'),str):rows=[(t['value'],[])]
        elif op=='choice':rows=[(v,c+item.get('conditions',[])) for item in t['choices'] for v,c in walk(item['value'])]
        elif op=='python_join':
            rows=[('',[])]
            for a in t['args']:
                rows=[((ntpath if style=='windows' else posixpath).join(x,y) if x is not None and y is not None else None,c+d)
                    for x,c in rows for y,d in walk(a)]
                if len(rows)>max_candidates:break
        elif op=='python_dirname':rows=[((ntpath if style=='windows' else posixpath).dirname(v) if v is not None else None,c) for v,c in walk(t['args'][0])]
        if len(rows)>max_candidates:rows=[(None,[{'kind':'process_argument_candidate_budget'}])]
        memo[key]=rows;return rows
    return walk(term)


def select_values(values,host_system,assumed=()):
    assumed=list(assumed);selected=[]
    for value in values:
        guards=[g for g in value['conditions'] if g not in assumed]
        result=conditions(guards,style=host_system['path_style'],host_system=host_system)
        if result['permitted']:selected.append({**value,'guard_result':result})
    return selected


def resolve(invocation,host_system):
    if invocation['path_style']!=host_system.get('path_style'):return {'status':'inactive_path_style'}
    guard=conditions(invocation['conditions'],style=host_system['path_style'],host_system=host_system)
    if not guard['permitted']:return {'status':'excluded','guards':guard}
    gaps=list(invocation['gaps']);settings={}
    for name in ('shell','env','executable','preexec_fn','cwd'):
        settings[name]=evaluate(invocation['settings'][name]['expression'],style=host_system['path_style'],host_system=host_system)
    if not settings['shell']['known'] or settings['shell']['value'] is not False:gaps.append('shell_command_interpretation_not_expanded')
    for name in ('executable','preexec_fn'):
        if not settings[name]['known'] or settings[name]['value'] is not None:gaps.append('process_'+name+'_changes_execution_context')
    if invocation['argument_form']=='single_command_string' and host_system['path_style']=='windows':gaps.append('windows_command_string_parsing_not_expanded')
    argv=[]
    for word in invocation['command_parts']:
        values=select_values(word,host_system,invocation['conditions'])
        argv.append(values)
        if len(values)!=1 or any(v['path_value']['unresolved'] or any(r['reason'] in STATIC_GAPS for r in v['guard_result']['residual']) for v in values):
            gaps.append('process_argument_not_uniquely_resolved')
    cwd=select_values(invocation['working_directories'],host_system,invocation['conditions'])
    inherited=settings['cwd']['known'] and settings['cwd']['value'] is None
    if invocation['working_directory_mode']=='explicit' and not inherited and (len(cwd)!=1 or any(v['path_value']['unresolved'] or any(r['reason'] in STATIC_GAPS for r in v['guard_result']['residual']) for v in cwd)):
        gaps.append('process_working_directory_not_uniquely_resolved')
    if any(r['reason'] in STATIC_GAPS for r in guard['residual']):gaps.append('process_guard_static_context_incomplete')
    return {'status':'gap' if gaps else 'conditional_candidate','argv':argv,'cwd':cwd,'settings':settings,'guards':guard,
        'gaps':sorted(set(gaps)),'runtime_execution':'not_observed'}


def environment_value(invocation,effects,key,host_system,*,initial_values=None):
    """Bind one inherited process variable, conditional on this invocation.

    initial_values describes values at this root invocation's entry. Missing keys
    stay unknown. No analysis-process environment or filesystem is read.
    """
    chosen=resolve(invocation,host_system)
    if chosen['status'] in {'inactive_path_style','excluded'}:return {'known':False,'reason':'invocation_not_selected'}
    env=chosen['settings']['env']
    if not env['known'] or env['value'] is not None:return {'known':False,'reason':'explicit_child_environment_mapping_not_expanded'}
    candidates=[];node_map={e['id']:e for e in effects}
    normalize_key=lambda value:value.upper() if isinstance(value,str) and host_system['path_style']=='windows' else value
    for effect in effects:
        if effect['path_style']!=invocation['path_style'] or effect['root_function']!=invocation['root_function']:continue
        order=before(effect,invocation,node_map)
        if order is False:continue
        guards=[g for g in effect['conditions'] if g not in invocation['conditions']]
        verdict=conditions(guards,style=host_system['path_style'],host_system=host_system)
        if not verdict['permitted']:continue
        name=evaluate(effect['key_expression'],style=host_system['path_style'],host_system=host_system)
        if name['known'] and normalize_key(name['value'])!=normalize_key(key) and not effect.get('library_member_writes'):continue
        candidates.append((effect,order,name,verdict))
    if not candidates:
        supplied=[v for k,v in (initial_values or {}).items() if normalize_key(k)==normalize_key(key)]
        if len(supplied)>1:return {'known':False,'reason':'ambiguous_root_entry_environment_key'}
        if supplied:
            raw=supplied[0]
            if raw is not None and not isinstance(raw,str):return {'known':False,'reason':'invalid_root_entry_environment_value'}
            return {'known':True,'value':None if raw is None else {'text':raw,'path_value':normalize(literal(raw),host_system['path_style'])[0]},'basis':'explicit_root_entry_environment'}
        return {'known':False,'reason':'root_entry_environment_not_supplied'}
    latest=[c for c in candidates if all(c is other or before(other[0],c[0],node_map) is True for other in candidates)]
    if len(latest)!=1:return {'known':False,'reason':'environment_effect_order_not_proven','writers':[c[0]['id'] for c in candidates]}
    effect,order,name,verdict=latest[0]
    if order is not True or not name['known'] or verdict['residual'] or effect['gaps']:
        return {'known':False,'reason':'environment_write_condition_or_context_not_proven','writer':effect['id']}
    if effect['effect']=='unset':value=None
    elif effect['effect']=='set':
        values=select_values(effect['value_candidates'],host_system,invocation['conditions'])
        if len(values)!=1 or values[0]['path_value']['unresolved'] or values[0]['guard_result']['residual']:
            return {'known':False,'reason':'environment_value_not_uniquely_resolved','writer':effect['id']}
        value={k:values[0][k] for k in ('text','path_value')}
    else:return {'known':False,'reason':'environment_mapping_effect_not_expanded','writer':effect['id']}
    return {'known':True,'value':value,'writer':effect['id'],'basis':'same_root_resolved_source_order_conditional_on_invocation',
        'source_conditions':values[0]['conditions'] if effect['effect']=='set' else [],
        'conditions':['source_environment_operation_succeeds','no_unmodeled_environment_write_before_child_start'],'runtime_execution':'not_observed'}
