"""Propagate native artifacts through conditional, source-bound copy contracts."""
from collections import defaultdict,deque,Counter
import json
from urllib.parse import quote
from adapters.path_values import normalize
from adapters.path_patterns import match,root_identity
from adapters.file_copy_contracts import map_member


DESTRUCTIVE={'shutil.move','os.rename','os.replace'}


def before(left,right,nodes,left_value=None,right_value=None):
    """Prove lexical order only within the same resolved root invocation."""
    if left['root_function']!=right['root_function']:return None
    a=left.get('execution_address');b=right.get('execution_address')
    if not a or not b:return None
    def items(value):
        return {(c['loop']['path'],c['loop']['line'],c['variable']):c['index'] for c in (value or {}).get('value',{}).get('conditions',[])
            if c['kind']=='literal_iteration_item' and 'loop' in c}
    li=items(left_value);ri=items(right_value)
    for x,y in zip(a,b):
        if x.get('loop_scopes')!=y.get('loop_scopes'):return None
        for loop in reversed(x.get('loop_scopes',[])):
            prefix=(loop['path'],loop['line']);variables={k for k in li.keys()&ri.keys() if k[:2]==prefix}
            if len(variables)!=1:return None
            key=next(iter(variables))
            if li[key]!=ri[key]:return li[key]<ri[key]
        x=(x['path'],x['line'],x['column']);y=(y['path'],y['line'],y['column'])
        if x==y:continue
        return x[1:]<y[1:] if x[0]==y[0] else None
    return None


def path_key(value):return json.dumps([root_identity(value),value['segments'],value['style']],sort_keys=True,separators=(',',':'))


def augment(graph,*,max_steps=8,max_derived=256,max_attempts=100000):
    if 'artifact_copy_flow' in graph:raise ValueError('Artifact copy projection already present')
    nodes={n['id']:n for n in graph['nodes']};by_context=defaultdict(lambda:defaultdict(list));added=[];edges=[];diagnostics=[];seen_gaps=set();stats=Counter()
    contexts={n['id']:n for n in nodes.values() if n['kind']=='file_operation_context'}
    for n in nodes.values():
        if n['kind']=='path_value' and n.get('operation_context') in contexts:by_context[n['operation_context']][n['role']].append(n)
    def gap(reason,source,context=None):
        key=(reason,source,context)
        if key in seen_gaps:return
        seen_gaps.add(key);n=nodes[source]
        diagnostics.append({'kind':'artifact_copy_flow_gap','reason':reason,'source':source,'context':context,
            'path':n['path'],'line':n['line'],'required':True})
    pairs=[];barriers=[]
    for uid,roles in sorted(by_context.items()):
        context=contexts[uid]
        if set(context['api_candidates'])&DESTRUCTIVE:
            barriers.extend((context,s) for s in roles['source']);gap('destructive_file_effect_not_expanded',uid);continue
        for s in roles['source']:
            for d in roles['destination']:
                if s['value']['style']==d['value']['style']:pairs.append((context,s,d))
    queue=deque()
    for origin in sorted((n for n in nodes.values() if n['kind']=='build_artifact'),key=lambda n:n['id']):
        context=nodes.get(origin['build_context']);system=context.get('target_system',{}) if context else {}
        if system.get('status')!='available' or not system.get('host_path_style'):
            gap('native_artifact_host_context_not_bound',origin['id']);continue
        loc=origin['location'];style=system['host_path_style']
        if loc['root']!='source':gap('native_artifact_root_not_bound_to_source_layout',origin['id']);continue
        value=normalize({'op':'source_file','source':origin['id'],'path':loc['path']},style)[0]
        queue.append({'id':origin['id'],'origin':origin,'value':value,'host':{'name':system['host_name'],'path_style':style},
            'target_system':system,'steps':[],'visited_paths':{path_key(value)},'conditions':context.get('conditions',[])+origin.get('conditions',[])+[
                {'kind':'native_artifact_successfully_materialized_as_regular_file','artifact':origin['id'],'build_context':origin['build_context']}]})
        stats['native_seeds']+=1
    stopped=False
    while queue and not stopped:
        state=queue.popleft()
        for context,source,destination in pairs:
            stats['attempts']+=1
            if stats['attempts']>max_attempts:
                gap('artifact_copy_attempt_budget',state['origin']['id']);stopped=True;break
            # A source operation cannot create content for an earlier operation
            # in the same root invocation. Different roots retain an order condition.
            if any(before(context,contexts[step['context']],nodes,source,nodes[step['source']]) is True for step in state['steps']):continue
            result=map_member(context,source,destination,state['value'],host_system=state['host'])
            stats[result['status']]+=1
            if result['status']=='gap':gap(result['reason'],context['id'],state['origin']['id'])
            if not result['mappings']:continue
            obstructed=False
            for barrier,barrier_source in barriers:
                if before(barrier,context,nodes,barrier_source,source) is False or barrier_source['value']['style']!=state['value']['style']:continue
                if match(barrier_source['value'],state['value'],prefix=True) is not None:
                    gap('source_lifetime_requires_destructive_effect_resolution',context['id'],barrier['id']);obstructed=True;break
            if obstructed:continue
            if any(step['context']==context['id'] for step in state['steps']):
                gap('repeated_copy_operation_requires_iteration_effects',context['id'],state['origin']['id']);continue
            for index,mapping in enumerate(result['mappings']):
                value=mapping['destination'];key=path_key(value)
                if key in state['visited_paths']:
                    gap('artifact_copy_path_cycle',context['id'],state['origin']['id']);continue
                if len(state['steps'])>=max_steps or len(added)>=max_derived:
                    gap('artifact_copy_depth_or_candidate_budget',context['id'],state['origin']['id']);continue
                step={'context':context['id'],'source':source['id'],'destination':destination['id'],'variant':index}
                steps=state['steps']+[step];uid=state['origin']['id']+':copy:'+quote(json.dumps(steps,sort_keys=True,separators=(',',':')),safe='')
                evidence=[{'path':context['path'],'line':context['line'],'column':context.get('column',0)}]
                conditions=state['conditions']+mapping['conditions']+[
                    {'kind':'source_artifact_lineage_not_replaced_between_operations','context':context['id']},
                    {'kind':'copy_source_predicates_hold','context':context['id'],'guards':mapping['guards']},
                    {'kind':'copy_path_conditions_hold','context':context['id'],'conditions':mapping['path_conditions']}]
                row={'id':uid,'kind':'copied_artifact','name':value['relative_path'],'path':context['path'],'line':context['line'],
                    'language':'python','value':value,'origin_artifact':state['origin']['id'],'build_context':state['origin']['build_context'],
                    'target_system':state['target_system'],'host_system':state['host'],'copy_steps':steps,'conditions':conditions,
                    'content_relation':'conditional_copy_of_native_artifact','materialization':'not_verified','runtime_execution':'not_observed'}
                added.append(row)
                base={'status':'conditional_candidate','evidence':evidence,'build_context':row['build_context'],'runtime_execution':'not_observed'}
                edges.append({'source':state['id'],'target':uid,'kind':'COPIES_ARTIFACT_TO',**base,
                    'operation_context':context['id'],'mapping':mapping,'conditions':conditions})
                for kind,target in [('COPY_OPERATION',context['id']),('COPY_SOURCE_PATH',source['id']),('COPY_DESTINATION_PATH',destination['id'])]:
                    edges.append({'source':uid,'target':target,'kind':kind,**base})
                queue.append({**state,'id':uid,'value':value,'steps':steps,'conditions':conditions,'visited_paths':state['visited_paths']|{key}})
    graph['nodes'].extend(added);graph['edges'].extend(edges);graph.setdefault('diagnostics',[]).extend(diagnostics)
    graph['artifact_copy_flow']={'adapter':'native_artifact_conditional_python_copy/0.1.0','counts':dict(stats),
        'copied_artifacts':len(added),'required_gaps':len(diagnostics),'budget':{'steps':max_steps,'derived':max_derived,'attempts':max_attempts},
        'runtime_execution':'not_observed','scope':'native_source_layout_regular_artifacts_and_import_bound_python_copies'}
    return graph
