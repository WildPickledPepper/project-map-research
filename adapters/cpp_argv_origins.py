"""Contextual argv-to-string-decoder provenance over existing C++ source facts.

Selectors and preparation operations are retained. Origin completeness describes
source tracing, not an observed argument index or equality of prepared values.
"""
from collections import defaultdict,Counter
from copy import deepcopy
import json
import re
from urllib.parse import quote

from adapters.cpp_data import arguments,enclosing_function
from adapters.cpp_facts import declared_name,parameter_type
from adapters.cpp_field_flow import declaration_mode
from adapters.cpp_string_decoders import Decoders
from adapters.cpp_value_types import split_template
from adapters.syntax_supplement import identity,parents,text,walk
from adapters.cpp_control import predicates


ADAPTER_VERSION='cpp_contextual_entry_argv_provenance/0.2.0'


def uid(*parts):return 'cpp-argv:'+':'.join(quote(str(p),safe='') for p in parts)


def result(kind='unknown',gap=None,**fields):
    return {'value_kind':kind,'origins':[],'steps':[],'gaps':[gap] if gap else [],**fields}


class Origins(Decoders):
    def __init__(self,data,protocol,*,max_depth=16,max_frames=128,max_states=20000):
        super().__init__(data,protocol)
        self.max_depth=max_depth;self.max_frames=max_frames;self.max_states=max_states;self.states=0;self.stack=set()
        self.calls=defaultdict(list);self.entries={};self.functions={k:v for k,v in self.x.functions_by_id.items() if self.x.nodes[k]['definition']}
        self.ast={};self.effects={}
        for path,unit in self.x.units.items():
            for node in walk(unit['tree'].root_node):self.ast[(path,node.start_byte,node.end_byte)]=node
        for owner,info in self.functions.items():
            params=info['parameter_nodes']
            if info['signature'][0]=='main' and not info['scope'] and info['return_type']=='int' and len(params)>=2:
                token=params[1].child_by_field_name('type')
                declarator=params[1].child_by_field_name('declarator')
                declarations=list(walk(declarator)) if declarator is not None else []
                pointer_levels=sum(n.type in {'array_declarator','pointer_declarator'} for n in declarations)
                if text(token)=='char' and pointer_levels==2 and text(params[0].child_by_field_name('type'))=='int':
                    self.entries[owner]=params[1]
            own=[n for n in walk(info['container']) if enclosing_function(n)==info['container']]
            self.effects[owner]=[n for n in own if n.type in {'call_expression','assignment_expression','update_expression'}]
            for call in own:
                if call.type!='call_expression':continue
                for target in self.d.targets(call,owner,info):
                    if target in self.functions:self.calls[target].append((owner,call))

    def shape(self,spelling,path,scope,seen=()):
        raw=re.sub(r'\b(const|volatile|typename|class|struct)\b','',spelling).strip().strip('&* ').strip()
        key=(raw,path,tuple(scope))
        if key in seen or len(seen)>12:return None
        head,args=split_template(raw);library=self.libraries.resolve(head,path,scope)
        if library&{'std::string','std::string_view'}:return 'string'
        if 'std::vector' in library and len(args)==1 and self.shape(args[0],path,scope,seen+(key,))=='string':return 'string_vector'
        visible=self.x.visibility.get(path,{path})
        for length in range(len(scope),-1,-1):
            name='::'.join(scope[:length]+[head]);choices=[a for a in self.libraries.aliases[name] if a['path'] in visible]
            if choices:
                options={self.shape(a['target'],a['path'],a['scope'],seen+(key,)) for a in choices}
                return next(iter(options)) if len(options)==1 else None
        return None

    def node_shape(self,node,owner):
        info=self.functions[owner];var=self.variable(node,owner,info)
        if var:
            spelling=parameter_type(var['node'],preserve_space=True) if var['node'] in info['parameter_nodes'] else var['type']
            if spelling!='auto':return self.shape(spelling,info['path'],info['scope'])
        inferred=self.d.types.infer(node,owner,info)
        return self.shape(inferred.get('spelling',''),info['path'],info['scope'])

    def storage_root(self,node,owner,seen=()):
        if node is None:return None
        if node.type in {'parenthesized_expression','pointer_expression'}:
            return self.storage_root(node.named_children[-1],owner,seen) if node.named_children else None
        if node.type=='subscript_expression':return self.storage_root(node.child_by_field_name('argument'),owner,seen)
        info=self.functions[owner];var=self.variable(node,owner,info)
        if not var:return None
        declaration=var['node'];key=(info['path'],declaration.start_byte,declaration.end_byte)
        if key in seen:return None
        if declaration_mode(declaration)=='reference' and declaration not in info['parameter_nodes'] and var['value'] is not None:
            return self.storage_root(var['value'],owner,seen+(key,))
        return key

    def frames(self,function,seen=()):
        if function in seen or len(seen)>=self.max_depth:
            self.diagnostics.append({'kind':'cpp_argv_origin_unresolved','reason':'caller_recursion_or_depth_budget',
                'path':self.x.nodes[function]['path'],'line':self.x.nodes[function]['line'],'required':True});return []
        if function in self.entries:return [{'function':function,'entry':function,'arguments':{},'calls':[],'conditions':[]}]
        rows=[]
        for owner,call in self.calls[function]:
            for parent in self.frames(owner,seen+(function,)):
                rows.append(self.frame(call,function,parent))
                if len(rows)>=self.max_frames:
                    self.diagnostics.append({'kind':'cpp_argv_origin_unresolved','reason':'caller_frame_budget',
                        'path':self.x.nodes[function]['path'],'line':self.x.nodes[function]['line'],'required':True});return rows
        return rows

    def frame(self,call,target,parent):
        info=self.functions[target];actuals=arguments(call)
        return {'function':target,'entry':parent['entry'],
            'arguments':{(p.start_byte,p.end_byte):(a,parent) for p,a in zip(info['parameter_nodes'],actuals)},
            'calls':parent['calls']+['cpp:'+identity(self.functions[parent['function']]['path'],'call_site',call)],
            'conditions':parent['conditions']+predicates(call)+[{'kind':'source_call_target_selected','target':target,
                'call':'cpp:'+identity(self.functions[parent['function']]['path'],'call_site',call)}]}

    def step(self,row,node,frame,kind,**fields):
        row=deepcopy(row);info=self.functions[frame['function']]
        row['steps'].append({'kind':kind,'source_symbol':frame['function'],'call_stack':frame['calls'],
            'evidence':self.d.evidence(info['path'],node),'conditions':predicates(node),**fields})
        return row

    def evaluate(self,node,frame):
        self.states+=1
        if node is None:return result(gap='missing_source_expression')
        key=(frame['function'],tuple(frame['calls']),node.start_byte,node.end_byte)
        if self.states>self.max_states or len(self.stack)>=64 or key in self.stack:return result(gap='value_recursion_or_state_budget')
        self.stack.add(key)
        try:return self._evaluate(node,frame)
        finally:self.stack.remove(key)

    def _evaluate(self,node,frame):
        owner=frame['function'];info=self.functions[owner]
        if node.type=='parenthesized_expression' and node.named_children:return self.evaluate(node.named_children[-1],frame)
        if node.type=='identifier':
            var=self.variable(node,owner,info)
            if var:
                declaration=var['node'];key=(declaration.start_byte,declaration.end_byte)
                if key in frame['arguments']:
                    actual,parent=frame['arguments'][key]
                    value=self.evaluate(actual,parent)
                    return self.step(self.prepare(value,node,frame,declaration),node,frame,'formal_argument_source')
                if owner in self.entries and declaration==self.entries[owner]:
                    source=uid('source',owner)
                    return self.prepare(result('argv_array',origins=[{'entry':owner,'source':source,'selectors':[]}]),node,frame,declaration)
                if self.node_shape(node,owner)=='string_vector':return self.collection(node,frame,var)
                source=self.source(node,owner,info)
                if source is not None:
                    return self.step(self.prepare(self.evaluate(source,frame),node,frame,declaration),node,frame,'local_initializer_or_reaching_assignment')
                return result(gap='binding_source_not_selected')
            literal,_=self.constant(node,owner,info)
            return result('literal',literal=literal) if isinstance(literal,str) else result(gap='unbound_identifier_or_member')
        if node.type in {'string_literal','concatenated_string'}:
            literal,_=self.constant(node,owner,info)
            return result('literal',literal=literal) if isinstance(literal,str) else result(gap='literal_not_decoded')
        if node.type=='subscript_expression':
            base=node.child_by_field_name('argument');value=self.evaluate(base,frame)
            if value['value_kind'] not in {'argv_array','collection'}:return result(gap='indexed_source_not_argv_or_string_collection')
            indices=node.child_by_field_name('indices')
            return self.select(value,node,frame,'argv_index' if value['value_kind']=='argv_array' else 'collection_index',text(indices))
        if node.type=='call_expression':
            function=node.child_by_field_name('function');args=arguments(node)
            if function is not None and function.type=='field_expression':
                receiver=function.child_by_field_name('argument');method=text(function.child_by_field_name('field'))
                if method=='at' and len(args)==1 and self.node_shape(receiver,owner)=='string_vector':
                    value=self.evaluate(receiver,frame)
                    return self.select(value,node,frame,'collection_at',text(args[0]))
                if method in {'data','c_str'} and not args and self.node_shape(receiver,owner)=='string':
                    return self.step(self.evaluate(receiver,frame),node,frame,'standard_string_borrow')
            if function is not None and self.libraries.resolve(text(function),info['path'],info['scope'])&{'std::string','std::string_view'} and len(args)==1:
                value=self.evaluate(args[0],frame)
                if value['value_kind']=='argv_word':return self.step(value,node,frame,'standard_string_from_argv_word')
                if value['value_kind']=='literal':return value
                return result(gap='string_constructor_source_not_word')
            targets=self.d.targets(node,owner,info)
            if len(targets)==1 and targets[0] in self.functions:
                callee=self.functions[targets[0]]
                returns=[r for r in walk(callee['container']) if r.type=='return_statement' and enclosing_function(r)==callee['container']]
                if len(returns)==1 and returns[0].named_children:
                    return self.step(self.evaluate(returns[0].named_children[0],self.frame(node,targets[0],frame)),node,frame,'source_return_value')
            return result(gap='call_value_not_expanded')
        return result(gap='expression_not_expanded')

    def select(self,value,node,frame,kind,selector):
        row=self.step(value,node,frame,kind,selector=selector);row['value_kind']='argv_word'
        for origin in row['origins']:origin['selectors'].append({'kind':kind,'expression':selector,
            'path':self.functions[frame['function']]['path'],'line':node.start_point[0]+1,'call_stack':frame['calls'],
            'conditions':predicates(node)})
        return row

    def prior_effects(self,reference,frame,declaration):
        owner=frame['function'];root=self.storage_root(reference,owner)
        return [n for n in self.effects[owner] if declaration.end_byte<=n.start_byte<reference.start_byte and
            not n.start_byte<=reference.start_byte<n.end_byte and enclosing_function(n)==self.functions[owner]['container']],root

    def loop_carried(self,reference,frame,declaration):
        owner=frame['function'];root=self.storage_root(reference,owner)
        loops=[p for p in parents(reference) if p.type in {'for_statement','for_range_loop','while_statement','do_statement'} and declaration.end_byte<=p.start_byte]
        for operation in self.effects[owner]:
            if operation.start_byte<=reference.start_byte or not any(p in list(parents(operation)) for p in loops):continue
            if operation.type=='call_expression':
                function=operation.child_by_field_name('function')
                target=function.child_by_field_name('argument') if function is not None and function.type=='field_expression' else None
                method=text(function.child_by_field_name('field')) if target is not None else None
                if method in {'size','length','empty','find','rfind','substr','compare','starts_with','ends_with','c_str','data','at','capacity','begin','end','cbegin','cend'}:continue
            else:target=operation.child_by_field_name('left') or operation.child_by_field_name('argument')
            if self.storage_root(target,owner)==root:return True
        return False

    def prepare(self,value,reference,frame,declaration):
        row=deepcopy(value);owner=frame['function'];info=self.functions[owner]
        if self.loop_carried(reference,frame,declaration):row['gaps'].append('loop_carried_mutation_not_expanded')
        effects,root=self.prior_effects(reference,frame,declaration)
        for operation in effects:
            if operation.type in {'assignment_expression','update_expression'}:
                target=operation.child_by_field_name('left') if operation.type=='assignment_expression' else operation.child_by_field_name('argument')
                if self.storage_root(target,owner)==root:row['gaps'].append('input_has_reaching_write_or_update')
                continue
            function=operation.child_by_field_name('function')
            if function is None:continue
            if function.type!='field_expression':
                if any(self.storage_root(a,owner)==root for a in arguments(operation)):row['gaps'].append('input_may_escape_to_intervening_call')
                continue
            receiver=function.child_by_field_name('argument');method=text(function.child_by_field_name('field'))
            # Collect the outermost call of a standard append chain exactly once.
            chain=[];base=operation
            while base is not None and base.type=='call_expression':
                f=base.child_by_field_name('function')
                if f is None or f.type!='field_expression':break
                chain.append((base,text(f.child_by_field_name('field'))));base=f.child_by_field_name('argument')
            if self.storage_root(base,owner)!=root:continue
            if any(p.type=='call_expression' for p in list(parents(operation))[:2]):
                parent=next((p for p in parents(operation) if p.type=='call_expression'),None)
                if parent is not None and parent.start_byte==operation.start_byte:continue
            if self.node_shape(reference,owner)!='string':continue
            for call,name in reversed(chain):
                args=arguments(call)
                if name=='append' and len(args)==1:
                    appended=self.evaluate(args[0],frame)
                    row=self.step(row,call,frame,'standard_string_append',operand=appended,preserves_existing_prefix=True)
                    row['origins'].extend(appended['origins']);row['gaps'].extend(appended['gaps'])
                elif name not in {'size','length','empty','find','rfind','substr','compare','starts_with','ends_with','c_str','data','at'}:
                    row['gaps'].append('string_mutation_not_expanded:'+name)
        return row

    def collection(self,reference,frame,var):
        owner=frame['function'];info=self.functions[owner];row=result('collection');declaration=var['node']
        if self.loop_carried(reference,frame,declaration):row['gaps'].append('loop_carried_mutation_not_expanded')
        if var.get('value') is not None:
            row['gaps'].append('collection_initializer_not_expanded')
        effects,root=self.prior_effects(reference,frame,declaration)
        for operation in effects:
            if operation.type!='call_expression':
                target=operation.child_by_field_name('left') or operation.child_by_field_name('argument')
                if self.storage_root(target,owner)==root:row['gaps'].append('collection_has_reaching_write_or_update')
                continue
            function=operation.child_by_field_name('function')
            if function is None:continue
            if function.type!='field_expression':
                if any(self.storage_root(a,owner)==root for a in arguments(operation)):row['gaps'].append('collection_may_escape_to_intervening_call')
                continue
            receiver=function.child_by_field_name('argument');method=text(function.child_by_field_name('field'))
            if self.storage_root(receiver,owner)!=root:continue
            args=arguments(operation)
            if method in {'emplace_back','push_back'} and len(args)==1:
                value=self.evaluate(args[0],frame)
                row['origins'].extend(value['origins']);row['gaps'].extend(value['gaps']);row['steps'].extend(value['steps'])
                row=self.step(row,operation,frame,'standard_vector_append_word')
                if not value['origins']:row['gaps'].append('collection_has_non_argv_element_candidate')
            elif method not in {'size','empty','capacity','reserve','at','data','begin','end','cbegin','cend'}:
                row['gaps'].append('collection_mutation_not_expanded:'+method)
        if not row['origins']:row['gaps'].append('collection_has_no_recorded_argv_elements')
        return row

    def augment(self,graph):
        added=[];edges=[];counts=Counter();decoder_gaps=[]
        for entry,parameter in self.entries.items():
            source=uid('source',entry);symbol=self.x.nodes[entry]
            added.append({'id':source,'kind':'cpp_entry_argv','name':text(declared_name(parameter)),'path':symbol['path'],
                'line':parameter.start_point[0]+1,'entry':entry,'parameter_index':1,'declared_type':parameter_type(parameter,preserve_space=True),
                'language':'cpp','runtime_execution':'not_observed','entry_status':'source_main_candidate_requires_build_target_binding'})
            edges.append({'source':entry,'target':source,'kind':'CPP_ENTRY_ARGV','status':'source_candidate','runtime_execution':'not_observed',
                'evidence':[self.d.evidence(symbol['path'],parameter)],'conditions':[{'kind':'recorded_narrow_main_signature_is_process_entry'}]})
        for decoder in [n for n in graph['nodes'] if n['kind']=='string_key_decoder']:
            owner=decoder['source_symbol'];location=decoder.get('input_reference')
            if location:
                reference=self.ast.get((location['path'],location['start_byte'],location['end_byte']))
                if reference is None:raise ValueError('Decoder input reference is missing from source')
            else:
                variable=decoder['input_storage'];node=self.ast.get((variable['path'],variable['start_byte'],variable['end_byte']))
                if node is None:raise ValueError('Decoder input declaration is missing from source')
                search=next((n for n in walk(self.functions[owner]['container']) if
                    n.type=='call_expression' and 'cpp:'+identity(variable['path'],'call_site',n)==decoder['search_call']),None)
                reference=search.child_by_field_name('function').child_by_field_name('argument') if search is not None else None
            rows=[]
            for frame in self.frames(owner):
                value=self.evaluate(reference,frame);value['gaps']=sorted(set(value['gaps']))
                binding=uid('binding',decoder['id'],frame['entry'],json.dumps(frame['calls'],separators=(',',':')))
                complete=bool(value['origins']) and not value['gaps'];source=uid('source',frame['entry'])
                row={'id':binding,'kind':'cpp_argv_decoder_binding','name':decoder['key'],'path':decoder['path'],'line':decoder['line'],
                    'language':'cpp','entry':frame['entry'],'argv_source':source,'decoder':decoder['id'],'call_stack':frame['calls'],
                    'origin_complete':complete,'value':value,'conditions':frame['conditions']+decoder['conditions']+[
                        {'kind':'recorded_source_calls_and_loop_iterations_reached'},
                        {'kind':'selected_argv_and_collection_elements_exist'},
                        {'kind':'no_unmodeled_alias_effects_before_argument_consumption'},
                        {'kind':'entry_and_preparation_belong_to_selected_link_image'}],
                    'runtime_execution':'not_observed','status':'source_origin_candidate'}
                rows.append(binding);added.append(row);counts['bindings']+=1;counts['complete_origins']+=int(complete)
                for left,right,kind in [(source,binding,'ARGV_FLOW_CANDIDATE'),(binding,decoder['id'],'BINDS_ARGV_DECODER_CANDIDATE')]:
                    edges.append({'source':left,'target':right,'kind':kind,'status':'source_origin_candidate','conditions':row['conditions'],
                        'evidence':decoder['evidence'],'runtime_execution':'not_observed','origin_complete':complete})
                if not complete:decoder_gaps.append({'kind':'cpp_argv_origin_unresolved','reason':'decoder_input_not_fully_traced',
                    'source':binding,'path':row['path'],'line':row['line'],'reasons':value['gaps'],'required':True})
            decoder['argv_bindings']=rows
            if rows:decoder['argv_origin']='source_origin_candidates'
            else:counts['unbound_decoders']+=1
        graph['nodes'].extend(added);graph['edges'].extend(edges);graph['diagnostics'].extend(self.diagnostics+decoder_gaps)
        graph['cpp_argv_origins']={'adapter':ADAPTER_VERSION,'entry_candidates':len(self.entries),'counts':dict(counts),
            'required_gaps':len(self.diagnostics+decoder_gaps),'runtime_execution':'not_observed'}
        return graph


def augment(graph,data,protocol,**budgets):
    if 'cpp_argv_origins' in graph:raise ValueError('Argv provenance already present')
    return Origins(data,protocol,**budgets).augment(graph)
