"""Bind sourced command words to argv decoders in their deployed native target.

The source literal establishes a candidate decoder key. Prepared payload values
and runtime argument occurrences remain separate from this identity binding.
"""
from collections import defaultdict,Counter
import json
from urllib.parse import quote


ADAPTER_VERSION='deployed_target_command_word_argv_binding/0.2.0'
LINK_COMMANDS={'target_link_libraries','target_sources','link_libraries'}
CODE_TARGETS={'STATIC_LIBRARY','SHARED_LIBRARY','OBJECT_LIBRARY','INTERFACE_LIBRARY'}
WORD_STEPS={'argv_index','collection_index','collection_at','standard_string_from_argv_word','standard_vector_append_word',
    'formal_argument_source','local_initializer_or_reaching_assignment','standard_string_append','standard_string_borrow','source_return_value'}


def identity(*parts):return 'process-argument:'+':'.join(quote(str(p),safe='') for p in parts)


def known_prefix(template,nodes):
    return word_literal(template,nodes)[0]


def word_literal(template,nodes):
    parts=[]
    for part in template['parts']:
        if isinstance(part.get('literal'),str):parts.append(part['literal']);continue
        value=nodes.get(part.get('slot'),{})
        if part.get('format_spec')=='' and isinstance(value.get('literal'),str):parts.append(value['literal']);continue
        return ''.join(parts),False
    return ''.join(parts),bool(template['complete'])


def nested_rows(value):
    if isinstance(value,dict):
        yield value
        for child in value.values():yield from nested_rows(child)
    elif isinstance(value,list):
        for child in value:yield from nested_rows(child)


def augment(graph,*,visibility=None,max_bindings=2048,max_scope_targets=4096):
    if 'process_argument_bindings' in graph:raise ValueError('Process argument bindings already present')
    nodes={n['id']:n for n in graph['nodes']};out=defaultdict(list);by_command=defaultdict(list)
    for edge in graph['edges']:
        out[edge['source']].append(edge)
        if edge['kind']=='RESOLVES_EXECUTABLE_TARGET_CANDIDATE':
            path=nodes[edge['source']];by_command[path['consumer']].append((path,edge))
    bindings=[n for n in nodes.values() if n['kind']=='cpp_argv_decoder_binding']
    by_entry=defaultdict(list)
    for row in bindings:by_entry[row['entry']].append(row)
    added=[];edges=[];diagnostics=[];gap_keys=set();emitted=set();counts=Counter();scopes={}
    def gap(reason,template,required=True,**extra):
        key=(reason,template['id'],json.dumps(extra,sort_keys=True))
        if key in gap_keys:return
        gap_keys.add(key);diagnostics.append({'kind':'process_argument_binding_unresolved','reason':reason,'source':template['id'],
            'path':template['path'],'line':template['line'],'required':required,**extra})
    def source_scope(provider):
        if provider['id'] in scopes:return scopes[provider['id']]
        context=provider['build_context'];pending=[provider['id']];seen=set();paths=defaultdict(set)
        while pending and len(seen)<max_scope_targets:
            target=pending.pop()
            if target in seen:continue
            seen.add(target)
            for edge in out[target]:
                if edge.get('build_context')!=context:continue
                value=nodes[edge['target']]
                if edge['kind']=='COMPILES_SOURCE' and value.get('location',{}).get('root')=='source':
                    path=value['location']['path'];paths[path].add(path)
                    if visibility:
                        for header in visibility.get(path,[]):paths[header].add(path)
                if edge['kind']=='LINKS_BUILD_TARGET' and value.get('build_context')==context and value.get('target_type') in CODE_TARGETS:
                    commands=[r['command'] for r in edge.get('evidence',[]) if r.get('command')]
                    if commands and commands[0] in LINK_COMMANDS:pending.append(value['id'])
        scopes[provider['id']]={'targets':sorted(seen),'paths':dict(paths),'complete':not pending}
        return scopes[provider['id']]
    def context_compatible(template,path):
        raw=nodes[path['source_path_value']]
        return path['analysis_context']==template['analysis_context'] and raw.get('root_function')==template.get('root_function') and \
            raw.get('call_stack')==template.get('call_stack')
    for template in [n for n in nodes.values() if n['kind']=='boundary_argument_template' and n['role'].startswith('process_argument')]:
        context=template['analysis_context'];programs=[]
        for command in out[template['consumer']]:
            if command['kind']!='USES_COMMAND' or command.get('analysis_contexts') and context not in command['analysis_contexts']:continue
            programs.extend((path,edge) for path,edge in by_command[command['target']] if context_compatible(template,path))
        if not programs:
            counts['words_without_bound_program']+=1
            gap('command_provider_not_bound_in_this_graph',template,required=False);continue
        counts['words_with_bound_program']+=1;prefix,complete_word=word_literal(template,nodes);matches=[]
        if template['role']!='process_argument':gap('argument_sequence_not_expanded',template);continue
        if not prefix:gap('argument_literal_prefix_unavailable',template);continue
        for path,match in programs:
            provider=nodes[match['target']];scope=source_scope(provider)
            if not scope['complete']:gap('native_source_scope_budget',template,provider=provider['id']);continue
            entries={e['target'] for e in out[provider['id']] if e['kind']=='EXECUTABLE_ENTRY_CANDIDATE' and e.get('build_context',provider['build_context'])==provider['build_context']}
            candidates=[binding for entry in entries for binding in by_entry[entry]]
            if not candidates:gap('provider_argv_decoder_entry_unavailable',template,provider=provider['id']);continue
            for binding in candidates:
                decoder=nodes[binding['decoder']]
                mode=decoder.get('match_mode');key=decoder.get('key')
                if not key:continue
                if mode=='string_equality':
                    if not complete_word:
                        if key.startswith(prefix):gap('argument_equality_word_value_unresolved',template,decoder=decoder['id'])
                        continue
                    if key!=prefix:continue
                elif mode!='substring_search' or key not in prefix:continue
                if not binding['origin_complete'] or binding['value']['gaps']:
                    gap('decoder_argv_origin_incomplete',template,argv_binding=binding['id']);continue
                if not binding['value']['origins'] or any(o['entry']!=binding['entry'] for o in binding['value']['origins']):
                    gap('decoder_argv_entry_origin_differs',template,argv_binding=binding['id']);continue
                preparations=[r for r in nested_rows(binding['value']) if 'kind' in r and 'source_symbol' in r]
                if any(r['kind'] not in WORD_STEPS or r['kind']=='standard_string_append' and not r.get('preserves_existing_prefix') for r in preparations):
                    gap('decoder_preparation_not_word_preserving',template,argv_binding=binding['id']);continue
                if mode=='string_equality' and any(r['kind']=='standard_string_append' and
                    isinstance(r.get('operand',{}).get('literal'),str) and r['operand']['literal'] and
                    not any(c.get('kind') in {'branch','preprocessor','switch_label'} for c in r.get('conditions',[])) for r in preparations):
                    gap('literal_switch_changed_by_unconditional_append',template,argv_binding=binding['id']);continue
                symbols=[binding['entry'],decoder['source_symbol'],*binding['call_stack'],*decoder.get('targets',[]),
                    *(r['source_symbol'] for r in preparations)]
                footprint={nodes[s]['path'] for s in symbols if s in nodes}
                missing=sorted(footprint-set(scope['paths']))
                if missing:
                    gap('decoder_sources_outside_selected_native_link_scope',template,argv_binding=binding['id'],provider=provider['id'],paths=missing);continue
                if len(added)>=max_bindings:gap('process_argument_binding_budget',template);break
                uid=identity(template['id'],path['id'],provider['id'],binding['id'],match.get('artifact',''))
                if uid in emitted:continue
                emitted.add(uid)
                conditions=match.get('conditions',[])+template['conditions']+binding['conditions']+[
                    {'kind':'selected_cpp_argv_occurrence_supplied_by_command_template','template':template['id']},
                    {'kind':'os_argv_encoding_preserves_sourced_literal_key'},
                    {'kind':'configured_cpp_preprocessor_and_source_type_context_applies','build_context':provider['build_context']},
                    {'kind':'recorded_native_link_dependencies_supply_decoder_code'},
                    {'kind':'decoder_branch_reached_for_selected_prepared_word'}]
                if mode=='string_equality':conditions.append({'kind':'prepared_input_equals_literal_switch_key','key':key})
                row={'id':uid,'kind':'process_argument_binding','name':decoder['key'],'path':template['path'],'line':template['line'],
                    'template':template['id'],'consumer':template['consumer'],'command':path['consumer'],'deployment_path':path['id'],
                    'provider':provider['id'],'provider_context':provider['build_context'],'argv_binding':binding['id'],'decoder':decoder['id'],
                    'analysis_context':context,'literal_prefix':prefix,'payload_source_complete':template['complete'],
                    'word_match_basis':'full_source_word' if mode=='string_equality' else 'known_literal_prefix',
                    'payload_source_gaps':template['gaps'],'prepared_value_relation':'argument_word_may_contribute_to_decoded_input',
                    'payload_equivalence':'not_established','source_scope':{p:sorted(scope['paths'][p]) for p in sorted(footprint)},
                    'conditions':conditions,'status':'conditional_source_candidate','runtime_execution':'not_observed'}
                added.append(row);matches.append(row);counts['matches']+=1
                evidence=[{'path':template['path'],'line':template['line']},*decoder['evidence']]
                for left,right,kind in [(template['id'],uid,'BIND_PROCESS_ARGUMENT'),(uid,binding['id'],'MATCHES_ARGV_DECODER_CANDIDATE'),
                    (uid,provider['id'],'ARGUMENT_PROVIDER_TARGET'),(uid,path['id'],'ARGUMENT_DEPLOYMENT_SOURCE')]:
                    edges.append({'source':left,'target':right,'kind':kind,'status':'conditional_source_candidate','conditions':conditions,
                        'analysis_contexts':[context],'evidence':evidence,'runtime_execution':'not_observed'})
                if not template['complete']:gap('argument_payload_source_unresolved',template,argv_binding=binding['id'])
        if not matches:counts['unmatched_words']+=1;gap('no_decoder_for_sourced_word_in_bound_program',template,literal_prefix=prefix)
        if len(matches)>1:
            counts['ambiguous_words']+=1
            for row in matches:row['match_status']='multiple_conditional_matches'
        elif matches:matches[0]['match_status']='single_conditional_decoder'
    graph['nodes'].extend(added);graph['edges'].extend(edges);graph['diagnostics'].extend(diagnostics)
    graph['process_argument_bindings']={'adapter':ADAPTER_VERSION,'counts':dict(counts),'required_gaps':sum(d['required'] for d in diagnostics),
        'runtime_execution':'not_observed','payload_equivalence':'not_established',
        'scope':'bound_command_deployment_target_entry_and_native_source_dependencies'}
    return graph
