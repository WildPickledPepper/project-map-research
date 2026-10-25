"""Conditional regular-file mappings for import-bound Python shutil APIs.

Contracts follow CPython 3.11.9. No analyzed function or filesystem is accessed.
The caller supplies the producer's host context and expected member identity.
"""
import fnmatch
import ntpath
from adapters.path_patterns import match,instantiate,root_identity
from adapters.file_predicate_values import evaluate,conditions


TREE_OPTIONS=['symlinks','ignore','copy_function','ignore_dangling_symlinks','dirs_exist_ok']
STANDARD_COPY={'shutil.copy','shutil.copy2','shutil.copyfile'}


def option_values(rows,api,**context):
    defaults=({'symlinks':False,'ignore':None,'copy_function':{'kind':'library_callable','api':['shutil.copy2']},
        'ignore_dangling_symlinks':False,'dirs_exist_ok':False} if api=='shutil.copytree' else {'follow_symlinks':True})
    seen=set();values=dict(defaults)
    for row in rows:
        name=row.get('keyword')
        if name is None:
            index=row.get('index',-1)-2
            if api!='shutil.copytree' or not 0<=index<len(TREE_OPTIONS):return None,'invalid_positional_copy_option'
            name=TREE_OPTIONS[index]
        if row.get('spread') or name not in defaults or name in seen:return None,'unsupported_or_duplicate_copy_option'
        seen.add(name);result=evaluate(row['expression'],**context)
        if not result['known']:return None,'copy_option_not_known:'+name+':'+result['reason']
        values[name]=result['value']
    for name in ('symlinks','ignore_dangling_symlinks','dirs_exist_ok','follow_symlinks'):
        if name in values and type(values[name]) is not bool:return None,'copy_option_boolean_not_expanded:'+name
    if api=='shutil.copytree':
        copier=values['copy_function']
        if not isinstance(copier,dict) or copier.get('kind')!='library_callable' or not copier.get('api') or not set(copier['api'])<=STANDARD_COPY:
            return None,'custom_copy_function_content_contract_unknown'
        ignore=values['ignore']
        if ignore is not None and (not isinstance(ignore,dict) or ignore.get('kind')!='ignore_patterns' or
                not isinstance(ignore.get('patterns'),list) or not all(isinstance(p,str) for p in ignore['patterns'])):
            return None,'custom_ignore_contract_unknown'
    return values,None


def compatible_iteration_items(left,right):
    items={}
    for c in left+right:
        if c['kind']!='literal_iteration_item':continue
        if c['variable'] in items and items[c['variable']]!=c['index']:return False
        items[c['variable']]=c['index']
    return True


def map_member(context,source,destination,artifact,*,host_system,artifact_kind='file',environment=None):
    """Map one expected member; all output mappings retain success conditions."""
    def outcome(status,reason,**extra):return {'status':status,'reason':reason,'mappings':[],**extra}
    src=source['value'];dst=destination['value'];style=src['style']
    if source.get('operation_context')!=context['id'] or destination.get('operation_context')!=context['id']:
        return outcome('gap','copy_pair_call_context_mismatch')
    if dst['style']!=style or artifact['style']!=style:return outcome('not_matched','path_style_mismatch')
    if not host_system.get('path_style'):return outcome('gap','host_path_style_not_bound')
    if host_system['path_style']!=style:return outcome('not_matched','inactive_host_path_style')
    apis=context['api_candidates']
    if len(apis)!=1:return outcome('gap','copy_api_not_unique')
    api=apis[0]
    if api not in STANDARD_COPY|{'shutil.copytree'}:return outcome('gap','file_operation_contract_not_supported')
    if context.get('gaps'):return outcome('gap','file_operation_call_context_incomplete')
    if not compatible_iteration_items(src['conditions'],dst['conditions']):return outcome('not_matched','different_literal_iteration_items')
    if src['unresolved'] or dst['unresolved']:return outcome('gap','copy_path_unresolved')
    matched=match(src,artifact,prefix=api=='shutil.copytree')
    if matched is None:return outcome('not_matched','full_source_path_does_not_match')
    if artifact_kind!='file':return outcome('gap','non_regular_artifact_kind_not_expanded')
    if api=='shutil.copytree' and not matched['suffix']:return outcome('excluded','copytree_source_is_regular_file')
    inputs={'style':style,'bindings':matched['bindings'],'host_system':host_system,'artifact_path':artifact,
        'artifact_kind':artifact_kind,'environment':environment}
    guards=conditions(src['conditions']+dst['conditions'],**inputs)
    if not guards['permitted']:return outcome('excluded','source_predicate_rejects_member',guards=guards)
    if any(r['reason'] in {'reaching_definition_selection_not_expanded','predicate_context_not_bound'} for r in guards['residual']):
        return outcome('gap','copy_guard_static_context_incomplete',guards=guards)
    options,gap=option_values(source.get('option_expressions',[]),api,**inputs)
    if gap:return outcome('gap',gap,guards=guards)
    if api=='shutil.copytree' and options['ignore']:
        norm=ntpath.normcase if style=='windows' else lambda x:x
        for member in matched['suffix']:
            for pattern in options['ignore']['patterns']:
                if fnmatch.fnmatchcase(norm(member),norm(pattern)):
                    return outcome('excluded','copytree_ignored_member_or_parent',ignored={'member':member,'pattern':pattern},guards=guards)
    target=instantiate(dst,matched['bindings'],suffix=matched['suffix'] if api=='shutil.copytree' else ())
    if target is None:return outcome('gap','copy_destination_variable_not_bound',guards=guards)
    obligations=[{'kind':'file_operation_succeeds','context':context['id']},
        {'kind':'source_member_regular_file_and_directory_layout','path':artifact},
        {'kind':'operation_reached_after_producer_and_before_consumer','context':context['id']}]
    if api=='shutil.copytree':
        obligations.append({'kind':'copytree_destination_state','destination':target,'dirs_exist_ok':options['dirs_exist_ok']})
    else:obligations.append({'kind':'copy_destination_writable_and_distinct_from_source'})
    candidates=[{'destination':target,'conditions':obligations}]
    if api in {'shutil.copy','shutil.copy2'}:
        candidates[0]['conditions']=obligations+[{'kind':'destination_is_existing_directory','value':False,'destination':target}]
        candidates.append({'destination':instantiate(target,{},suffix=[artifact['segments'][-1]]),
            'conditions':obligations+[{'kind':'destination_is_existing_directory','value':True,'destination':target}]})
    mappings=[]
    for candidate in candidates:
        dest=candidate['destination']
        if root_identity(dest)==root_identity(artifact) and dest['segments']==artifact['segments']:continue
        mappings.append({**candidate,'membership_conditions':matched['membership_conditions'],'bindings':matched['bindings'],
            'guards':guards,'options':options,'api':api,'status':'conditional_candidate','runtime_execution':'not_observed'})
    return {'status':'mapped' if mappings else 'excluded','reason':'copy_content_contract' if mappings else 'same_lexical_file', 'mappings':mappings}
