"""Typed string search/slice dispatch, retaining source guards and target scope.

This discovers decoding operations. An argv origin or a socket listener requires
separate value and executable bindings; an equal key alone supplies neither.
"""
from collections import Counter

from adapters.cpp_data import arguments,enclosing_function
from adapters.cpp_facts import declared_name
from adapters.cpp_control import predicates
from adapters.cpp_library_types import LibraryTypes
from adapters.syntax_supplement import cpp_scope,identity,parents,text,walk


ADAPTER_VERSION='cpp_typed_string_key_slice_dispatch/0.1.0'


class Decoders:
    def __init__(self,data,protocol):
        self.d=data;self.x=data.x;self.p=protocol;self.libraries=LibraryTypes(self.x);self.members={};self.diagnostics=[];self.overridden=set()
        for path,unit in self.x.units.items():
            for node in walk(unit['tree'].root_node):
                if node.type!='field_declaration' or not any(c.type=='type_qualifier' and text(c) in {'const','constexpr'} for c in node.children):continue
                value=node.child_by_field_name('default_value');name=declared_name(node)
                if value is not None and name is not None:self.members['storage:'+identity(path,'member',node)]=(path,node,value)
        for uid,info in self.x.functions_by_id.items():
            if not self.x.nodes[uid]['definition']:continue
            for node in walk(info['container']):
                if node.type!='field_initializer' or not node.named_children:continue
                for owner in {tuple(info['scope']),tuple(cpp_scope(node))}:
                    field=self.d.field(text(node.named_children[0]),'::'.join(owner))
                    if field:self.overridden.add(field['id'])

    def variable(self,node,uid,info):
        if node is None or node.type!='identifier':return None
        values=self.x.variables(text(node),node,info['path'],uid)
        return values[0] if values else None

    def storage(self,node,uid,info):
        var=self.variable(node,uid,info)
        if var:return (info['path'],var['node'].start_byte,var['node'].end_byte)
        return None

    def string(self,node,uid,info):
        value=self.d.types.infer(node,uid,info)
        spelling=value.get('spelling')
        return bool(spelling and self.libraries.resolve(spelling,info['path'],info['scope'])&{'std::string','std::string_view'})

    def source(self,node,uid,info):
        """Select only a single reaching local assignment on the same block path."""
        var=self.variable(node,uid,info)
        if not var:return None
        decl=var['node'];initial=var.get('value');writes=[]
        for candidate in walk(info['container']):
            if candidate.type!='assignment_expression' or enclosing_function(candidate)!=info['container']:continue
            if not decl.end_byte<=candidate.start_byte<node.start_byte:continue
            if self.storage(candidate.child_by_field_name('left'),uid,info)==self.storage(node,uid,info):writes.append(candidate)
        if writes:
            last=max(writes,key=lambda n:n.start_byte)
            statement=last.parent
            if statement is None or statement.type!='expression_statement' or statement.parent not in list(parents(node)):return None
            if text(last.child_by_field_name('operator'))!='=':return None
            return last.child_by_field_name('right')
        return initial

    def constant(self,node,uid,info,seen=()):
        if node is None or len(seen)>12:return None,[]
        key=(info['path'],node.start_byte,node.end_byte)
        if key in seen:return None,[]
        var=self.variable(node,uid,info)
        if var:
            source=self.source(node,uid,info)
            return self.constant(source,uid,info,seen+(key,)) if source is not None else (None,[])
        field=self.d.receiver_field(node,uid,info)
        if field:
            record=self.members.get(field['id'])
            if record is None:return None,[]
            if field['id'] in self.overridden:return None,[]
            path,declaration,value=record
            value,evidence=self.p.constant(value,path,field['owner'].split('::'))
            return value,[self.d.evidence(path,declaration),*evidence]
        return self.p.constant(node,info['path'],info['scope'])

    @staticmethod
    def method(node,name):
        if node is None or node.type!='call_expression':return None
        function=node.child_by_field_name('function')
        if function is None or function.type!='field_expression' or text(function.child_by_field_name('field'))!=name:return None
        return function.child_by_field_name('argument')

    def search(self,position,uid,info):
        source=self.source(position,uid,info)
        receiver=self.method(source,'find')
        if receiver is None or not self.string(receiver,uid,info):return None
        args=arguments(source)
        if len(args)!=1:return None
        key,evidence=self.constant(args[0],uid,info)
        if not isinstance(key,str) or not key:return None
        return {'call':source,'receiver':receiver,'key':key,'key_expression':args[0],'key_evidence':evidence}

    def build(self):
        records=[];counts=Counter()
        for uid,info in self.x.functions_by_id.items():
            if not self.x.nodes[uid]['definition']:continue
            for guard in walk(info['container']):
                if guard.type!='if_statement' or enclosing_function(guard)!=info['container']:continue
                condition=guard.child_by_field_name('condition')
                if condition is not None and condition.type=='condition_clause':condition=condition.child_by_field_name('value')
                if condition is None or condition.type!='binary_expression':continue
                if text(condition.child_by_field_name('operator'))!='!=':continue
                left=condition.child_by_field_name('left');right=condition.child_by_field_name('right')
                if right is not None and right.type=='identifier':left,right=right,left
                if left is None or left.type!='identifier' or right is None or right.type!='qualified_identifier':continue
                owner,separator,name=text(right).rpartition('::')
                if not separator or name!='npos':continue
                search=self.search(left,uid,info)
                if search is None:continue
                # npos belongs to a known standard string type, not a homonym.
                if not self.libraries.resolve(owner,info['path'],info['scope'])&{'std::string','std::string_view'}:continue
                body=guard.child_by_field_name('consequence')
                if body is None:continue
                for slice_call in walk(body):
                    receiver=self.method(slice_call,'substr')
                    if receiver is None or enclosing_function(slice_call)!=info['container']:continue
                    if self.storage(receiver,uid,info)!=self.storage(search['receiver'],uid,info) or self.storage(receiver,uid,info) is None:continue
                    if not self.string(receiver,uid,info):continue
                    args=arguments(slice_call)
                    if len(args)!=1:continue
                    offset=args[0];valid=False
                    if offset.type=='binary_expression' and text(offset.child_by_field_name('operator'))=='+':
                        pairs=[(offset.child_by_field_name('left'),offset.child_by_field_name('right')),
                            (offset.child_by_field_name('right'),offset.child_by_field_name('left'))]
                        for position,size in pairs:
                            if self.storage(position,uid,info)!=self.storage(left,uid,info):continue
                            size_receiver=self.method(size,'length')
                            if size_receiver is None:size_receiver=self.method(size,'size')
                            if size_receiver is None or arguments(size) or not self.string(size_receiver,uid,info):continue
                            key,_=self.constant(size_receiver,uid,info)
                            if key==search['key']:valid=True
                    if not valid:
                        self.diagnostics.append({'kind':'cpp_string_decoder_unresolved','reason':'slice_offset_not_proven_as_find_plus_key_length',
                            'required':True,**self.d.evidence(info['path'],slice_call)});continue
                    # The position/input must retain the same source storage until slicing.
                    intervening=[n for n in walk(info['container']) if search['call'].end_byte<=n.start_byte<slice_call.start_byte and
                        enclosing_function(n)==info['container'] and n.type in {'assignment_expression','update_expression','call_expression'}]
                    uncertain=[]
                    for operation in intervening:
                        target=operation.child_by_field_name('left') if operation.type=='assignment_expression' else operation.child_by_field_name('argument')
                        if operation.type=='call_expression':
                            function=operation.child_by_field_name('function')
                            target=function.child_by_field_name('argument') if function is not None and function.type=='field_expression' else None
                        if self.storage(target,uid,info) in {self.storage(left,uid,info),self.storage(receiver,uid,info)}:uncertain.append(operation)
                    if uncertain:
                        self.diagnostics.append({'kind':'cpp_string_decoder_unresolved','reason':'input_or_offset_may_change_after_search',
                            'required':True,**self.d.evidence(info['path'],slice_call)});continue
                    forwarding=next((p for p in parents(slice_call) if p.type in {'call_expression','function_definition','lambda_expression'}),None)
                    if forwarding is None or forwarding.type!='call_expression':continue
                    targets=self.d.targets(forwarding,uid,info)
                    indexes=[i for i,arg in enumerate(arguments(forwarding)) if arg==slice_call]
                    if len(indexes)!=1:continue
                    evidence=[self.d.evidence(info['path'],search['call']),self.d.evidence(info['path'],guard.child_by_field_name('condition')),
                        self.d.evidence(info['path'],slice_call),*search['key_evidence']]
                    record={'id':'string-decoder:'+identity(info['path'],'key_slice_dispatch',slice_call),'kind':'string_key_decoder',
                        'name':search['key'],'path':info['path'],'line':slice_call.start_point[0]+1,'language':'cpp','source_symbol':uid,
                        'key':search['key'],'search_call':'cpp:'+identity(info['path'],'call_site',search['call']),
                        'slice_call':'cpp:'+identity(info['path'],'call_site',slice_call),
                        'forward_call':'cpp:'+identity(info['path'],'call_site',forwarding),'targets':targets,'parameter_index':indexes[0],
                        'input_storage':{'path':info['path'],'start_byte':self.storage(receiver,uid,info)[1],'end_byte':self.storage(receiver,uid,info)[2]},
                        'match_mode':'substring_search','slice_mode':'find_result_plus_key_length','evidence':evidence,
                        'conditions':predicates(slice_call)+[{'kind':'source_string_search_reaches_guard'},
                            {'kind':'input_and_position_storage_unchanged_between_search_and_slice'},
                            {'kind':'source_key_constants_and_default_member_initializers_apply_to_receiver'},
                            {'kind':'no_unmodeled_alias_mutation_before_decoding'},
                            {'kind':'source_receiver_types_equal_recorded_standard_string_types'},
                            {'kind':'target_selected_from_source_candidates'}],
                        'argv_origin':'not_bound','runtime_execution':'not_observed','status':'source_candidate'}
                    records.append(record);counts['decoders']+=1
                    if not targets:self.diagnostics.append({'kind':'cpp_string_decoder_unresolved','reason':'forward_target_unresolved',
                        'required':True,**self.d.evidence(info['path'],forwarding)})
        return {'adapter':ADAPTER_VERSION,'records':records,'counts':dict(counts),'diagnostics':self.diagnostics}


def augment(graph,data,protocol):
    if 'cpp_string_decoders' in graph:raise ValueError('String decoder facts already present')
    result=Decoders(data,protocol).build();known={n['id'] for n in graph['nodes']};edges=[]
    for row in result['records']:
        if row['source_symbol'] not in known:raise ValueError('Decoder owner is missing from graph')
        graph['nodes'].append(row)
        for source,target,kind in [(row['source_symbol'],row['id'],'DECLARES_STRING_DECODER'),
            (row['id'],row['search_call'],'STRING_DECODER_SEARCH'),(row['id'],row['slice_call'],'STRING_DECODER_SLICE'),
            (row['id'],row['forward_call'],'STRING_DECODER_FORWARD'),
            *((row['id'],target,'DECODED_VALUE_TARGET_CANDIDATE') for target in row['targets'])]:
            if target not in known and target!=row['id']:raise ValueError('Decoder source target is missing')
            edges.append({'source':source,'target':target,'kind':kind,'status':'source_candidate','evidence':row['evidence'],
                'conditions':row['conditions'],'runtime_execution':'not_observed'})
    graph['edges'].extend(edges);graph['diagnostics'].extend(result['diagnostics'])
    graph['cpp_string_decoders']={k:v for k,v in result.items() if k not in {'records','diagnostics'}}
    graph['cpp_string_decoders']['required_gaps']=len(result['diagnostics'])
    return graph
