"""Typed standard-string equality branches and their source-controlled effects."""
from collections import Counter

from adapters.cpp_data import enclosing_function
from adapters.cpp_control import predicates
from adapters.cpp_string_decoders import Decoders
from adapters.syntax_supplement import identity,text,walk


ADAPTER_VERSION='cpp_typed_string_equality_branches/0.1.0'


def augment(graph,data,protocol):
    if 'cpp_string_switches' in graph:raise ValueError('String switches already present')
    decoder=Decoders(data,protocol);known={n['id']:n for n in graph['nodes']};added=[];edges=[];diagnostics=[];counts=Counter()
    effects={n['id']:n for n in graph['nodes'] if n['kind']=='source_member_effect'}
    def gap(reason,path,node):
        diagnostics.append({'kind':'cpp_string_switch_unresolved','reason':reason,'required':True,**data.evidence(path,node)})
    for uid,info in data.x.functions_by_id.items():
        if not data.x.nodes[uid]['definition']:continue
        path=info['path']
        for guard in walk(info['container']):
            if guard.type!='if_statement' or enclosing_function(guard)!=info['container']:continue
            condition=guard.child_by_field_name('condition')
            if condition is not None and condition.type=='condition_clause':condition=condition.child_by_field_name('value')
            while condition is not None and condition.type=='parenthesized_expression' and condition.named_children:
                condition=condition.named_children[0]
            if condition is None:continue
            comparisons=[n for n in walk(condition) if n.type=='binary_expression' and text(n.child_by_field_name('operator')) in {'==','!='}
                and any(decoder.string(n.child_by_field_name(side),uid,info) for side in ('left','right'))]
            if not comparisons:continue
            if len(comparisons)!=1 or comparisons[0]!=condition:
                gap('compound_string_condition_not_expanded',path,condition);continue
            choices=[]
            for side,key_side in [('left','right'),('right','left')]:
                value=condition.child_by_field_name(side);key=condition.child_by_field_name(key_side)
                if not decoder.string(value,uid,info):continue
                literal,evidence=decoder.constant(key,uid,info)
                if isinstance(literal,str):choices.append((value,literal,evidence))
            if len(choices)!=1:
                gap('string_equality_input_or_key_unresolved',path,condition);continue
            value,key,key_evidence=choices[0];operator=text(condition.child_by_field_name('operator'))
            body=guard.child_by_field_name('consequence' if operator=='==' else 'alternative')
            if body is None:
                gap('equality_branch_has_no_explicit_body',path,condition);continue
            controlled=[];calls=[]
            for node in walk(body):
                if enclosing_function(node)!=info['container']:continue
                eid='member-effect:'+identity(path,'member_effect',node)
                if eid in effects and effects[eid]['role']=='write':controlled.append(eid)
                if node.type=='call_expression':
                    cid='cpp:'+identity(path,'call_site',node)
                    if cid in known:calls.append(cid)
            storage=decoder.storage(value,uid,info)
            row={'id':'string-decoder:'+identity(path,'string_equality_branch',condition),'kind':'string_key_decoder','name':key,
                'path':path,'line':condition.start_point[0]+1,'language':'cpp','source_symbol':uid,'key':key,'match_mode':'string_equality',
                'input_reference':{'path':path,'start_byte':value.start_byte,'end_byte':value.end_byte},
                'input_storage':{'path':storage[0],'start_byte':storage[1],'end_byte':storage[2]} if storage else None,
                'comparison_operator':operator,'equality_branch':'consequence' if operator=='==' else 'alternative',
                'controlled_member_effects':sorted(set(controlled)),'controlled_calls':sorted(set(calls)),'targets':[],
                'evidence':[data.evidence(path,condition),*key_evidence],
                'conditions':predicates(body)+[{'kind':'source_standard_string_equality_selects_recorded_branch','key':key},
                    {'kind':'comparison_resolves_to_standard_string_equality'},
                    {'kind':'source_key_constants_and_default_member_initializers_apply_to_receiver'},
                    {'kind':'no_unmodeled_alias_mutation_before_decoding'},
                    {'kind':'controlled_site_requires_its_recorded_path_and_call_conditions'}],
                'argv_origin':'not_bound','runtime_execution':'not_observed','status':'source_candidate'}
            added.append(row);counts['decoders']+=1;counts['controlled_member_writes']+=len(row['controlled_member_effects'])
            links=[(uid,row['id'],'DECLARES_STRING_DECODER')]
            links.extend((row['id'],eid,'STRING_BRANCH_MEMBER_WRITE_CANDIDATE') for eid in row['controlled_member_effects'])
            links.extend((row['id'],cid,'STRING_BRANCH_CALL_CANDIDATE') for cid in row['controlled_calls'])
            for source,target,kind in links:
                edges.append({'source':source,'target':target,'kind':kind,'status':'source_candidate','evidence':row['evidence'],
                    'conditions':row['conditions']+known.get(target,{}).get('conditions',[]),'runtime_execution':'not_observed'})
    graph['nodes'].extend(added);graph['edges'].extend(edges);graph['diagnostics'].extend(diagnostics)
    graph['cpp_string_switches']={'adapter':ADAPTER_VERSION,'counts':dict(counts),'required_gaps':len(diagnostics),
        'object_instances_selected':False,'runtime_execution':'not_observed'}
    return graph
