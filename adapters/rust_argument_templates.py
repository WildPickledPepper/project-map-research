"""Native-bound Rust boundary strings and contextual scalar source identities.

Reuse Rust source/call frames and the existing grammar. Symbols describe one
source evaluation, not an invented runtime port or a globally equal name.
"""
from collections import Counter,defaultdict
import json
from pathlib import Path
import re
from string import Formatter
from urllib.parse import quote

from adapters.rust_path_values import Paths,string_value
from adapters.syntax_supplement import parents,walk,text
from adapters.rust_cfg import conditions_active


ADAPTER_VERSION='rust_native_boundary_argument_templates/0.1.0'


def identity(*parts):return 'rust-value:'+':'.join(quote(str(p),safe='') for p in parts)


class Arguments(Paths):
    def __init__(self,root,graph,parser):
        super().__init__(root,graph,parser)
        self.parser=parser;self.added={};self.value_edges=[];self.gaps=[];self.scalar_stack=set();self.template_stack=set();self.counts=Counter()
        self.positions={(n['path'],n['start_byte'],n['end_byte']):n['id'] for n in self.nodes.values() if 'start_byte' in n and 'end_byte' in n}
        self.raw={p:(Path(root)/p).read_bytes() for p in self.units};self.written=defaultdict(set)
        for e in graph['edges']:
            if e['kind']!='WRITES_VALUE':continue
            refs=[x for x in self.out[e['source']] if x['kind']=='READS_BINDING']
            for ref in refs:
                for context in ref.get('analysis_contexts',[]):self.written[context].add(ref['target'])
        for e in graph['edges']:
            if e['kind']!='EXTERNAL_CALL_REFERENCE':continue
            declaration=self.nodes[e['target']]['external_declaration']
            if not (declaration.get('package') in {'std','core','alloc'} and (declaration.get('container') or '').split('<')[0]=='String' and
                declaration.get('name') in {'push','push_str','insert','insert_str','clear','truncate','pop','remove','replace_range','retain','extend'}):continue
            receiver=self.nodes[e['source']].get('receiver')
            for read in self.out.get(receiver,[]):
                if read['kind']=='READS_BINDING':
                    for context in e['analysis_contexts']:self.written[context].add(read['target'])

    def frame(self,call,target,parent):
        child=super().frame(call,target,parent);child['captured_frames']=parent.get('captured_frames',[])
        child['conditions'].extend(self.nodes[call].get('conditions',[]))
        child['inactive']=parent.get('inactive',False) or conditions_active(self.nodes[call].get('conditions',[]),self.context) is False
        return child

    def frames(self,function,seen=()):
        if function and conditions_active(self.nodes[function].get('conditions',[]),self.context) is False:return []
        frames=super().frames(function,seen)
        syntax=self.ast.get(function)
        if not syntax or syntax[1].type!='closure_expression' or any(f['calls'] for f in frames):return frames
        owner=self.owner(*syntax)
        if owner is None or owner in seen:return frames
        result=[]
        for outer in self.frames(owner,seen+(function,)):
            result.append({**outer,'args':{},'captured_frames':[(owner,outer),*outer.get('captured_frames',[])],
                'conditions':outer['conditions']+[{'kind':'closure_invoked_with_recorded_capture_environment','closure':function}]})
        return result or frames

    def symbol(self,uid,frame,kind,*,gap=None,conditions=()):
        scope={'calls':frame['calls'],'root_function':frame['root_function']}
        row={'kind':kind,'source':uid,'scope':scope,'analysis_context':self.context['id']}
        if gap:row['gap']=gap
        key=identity('scalar',json.dumps(row,sort_keys=True,separators=(',',':')))
        source=self.nodes[uid]
        if key not in self.added:
            self.added[key]={'id':key,'kind':'source_scalar_value','name':source.get('name',source.get('expression','value')),
                'path':source['path'],'line':source['line'],'language':'rust','source':uid,'value':row,
                'conditions':list(conditions),'runtime_execution':'not_observed'}
            self.value_edges.append({'source':key,'target':uid,'kind':'SCALAR_VALUE_SOURCE','status':'source_projection',
                'analysis_contexts':[self.context['id']],'evidence':[{'path':source['path'],'line':source['line']}],'runtime_execution':'not_observed'})
        return {'value':key,'complete':gap is None,'gaps':[gap] if gap else [],'conditions':list(conditions)}

    def scalar(self,uid,frame):
        key=(uid,id(frame))
        if key in self.scalar_stack or len(self.scalar_stack)>=64:return self.symbol(uid,frame,'unknown',gap='scalar_recursion_or_depth_budget')
        self.scalar_stack.add(key)
        try:return self._scalar(uid,frame)
        finally:self.scalar_stack.remove(key)

    def _scalar(self,uid,frame):
        n=self.nodes[uid];syntax=n.get('syntax')
        if frame['gaps']:return self.symbol(uid,frame,'unknown',gap='caller_context_incomplete')
        if syntax=='field_expression':return self.symbol(uid,frame,'unknown',gap='instance_field_requires_receiver_identity')
        if n['kind'] in {'parameter','binding'} and uid in self.written[self.context['id']]:
            return self.symbol(uid,frame,'unknown',gap='scalar_reaching_write_not_selected')
        if n['kind']=='parameter':
            if uid in frame['args']:
                value,parent=frame['args'][uid];return self.scalar(value,parent)
            owner=self.owner(*self.ast[uid]) if uid in self.ast else None
            for function,captured in frame.get('captured_frames',[]):
                if function==owner:return self.scalar(uid,captured)
            return self.symbol(uid,frame,'parameter')
        if n['kind']=='binding':
            if n.get('binding_kind')=='field_declaration':return self.symbol(uid,frame,'unknown',gap='instance_field_requires_receiver_identity')
            if uid in self.ast and any(p.type in {'for_expression','while_expression','loop_expression'} for p in parents(self.ast[uid][1])):
                return self.symbol(uid,frame,'unknown',gap='scalar_iteration_instance_not_bound')
            origins=self.edges(uid,'VALUE_SOURCE') or self.edges(uid,'PATTERN_VALUE_SOURCE')
            if len(origins)==1:
                if origins[0]['kind']=='PATTERN_VALUE_SOURCE':
                    return self.symbol(uid,frame,'binding_projection',conditions=[{'kind':'rust_pattern_projection_selected','binding':uid,'pattern':n.get('pattern')}])
                return self.scalar(origins[0]['target'],frame)
            return self.symbol(uid,frame,'unknown',gap='binding_source_not_unique')
        reads=self.edges(uid,'READS_BINDING')
        if len(reads)==1:return self.scalar(reads[0]['target'],frame)
        if len(reads)>1:return self.symbol(uid,frame,'unknown',gap='native_binding_not_unique')
        if syntax in {'reference_expression','parenthesized_expression','try_expression'}:
            child=self.wrapped(uid)
            if child:return self.scalar(child,frame)
        if syntax in {'string_literal','raw_string_literal','integer_literal','boolean_literal'}:
            result=self.symbol(uid,frame,'literal');value=None
            try:
                if syntax in {'string_literal','raw_string_literal'}:value=string_value(n['expression'])
                elif syntax=='boolean_literal':value=n['expression']=='true'
                else:
                    literal=re.sub(r'(?:[iu](?:8|16|32|64|128|size))$','',n['expression']).replace('_','')
                    value=int(literal,0) if literal.startswith(('0x','0b','0o')) else int(literal)
                self.added[result['value']]['literal']=value
            except (ValueError,OverflowError):return self.symbol(uid,frame,'unknown',gap='unsupported_scalar_literal')
            return result
        if n['kind']=='call_site':
            if any(a.get('package') in {'std','core','alloc'} and a.get('name') in {'as_str','clone','to_owned'} and
                (a.get('container') or '').split('<')[0] in {'String','str','ToOwned'} for a in self.api(uid)) and n.get('receiver'):
                return self.scalar(n['receiver'],frame)
            if uid in self.ast and any(p.type in {'for_expression','while_expression','loop_expression'} for p in parents(self.ast[uid][1])):
                return self.symbol(uid,frame,'unknown',gap='scalar_iteration_instance_not_bound')
            return self.symbol(uid,frame,'call_result',conditions=[{'kind':'source_call_produces_recorded_value','call':uid}])
        return self.symbol(uid,frame,'unknown',gap='scalar_expression_not_expanded')

    def operand(self,path,node,offset):
        start=node.start_byte+offset;end=node.end_byte+offset;key=(path,start,end)
        if key in self.positions:return self.positions[key]
        uid=identity('format-operand',path,start,end);raw=self.raw[path];expression=raw[start:end].decode('utf-8')
        row={'id':uid,'kind':'value','name':expression,'expression':expression,'path':path,'line':raw[:start].count(b'\n')+1,
            'start_byte':start,'end_byte':end,'syntax':node.type,'language':'rust','runtime_execution':'not_observed'}
        self.nodes[uid]=row;self.added[uid]=row;self.positions[key]=uid;return uid

    def template(self,uid,frame):
        key=(uid,id(frame))
        if key in self.template_stack or len(self.template_stack)>=64:
            return {'parts':[],'complete':False,'gaps':['template_recursion_or_depth_budget'],'conditions':[]}
        self.template_stack.add(key)
        try:return self._template(uid,frame)
        finally:self.template_stack.remove(key)

    def _template(self,uid,frame):
        n=self.nodes[uid]
        if n['kind']=='parameter' and uid in frame['args'] and uid not in self.written[self.context['id']]:
            actual,parent=frame['args'][uid];return self.template(actual,parent)
        reads=self.edges(uid,'READS_BINDING')
        if len(reads)==1 and n.get('syntax')!='field_expression':return self.template(reads[0]['target'],frame)
        if n['kind']=='binding' and uid not in self.written[self.context['id']]:
            origins=self.edges(uid,'VALUE_SOURCE')
            if len(origins)==1:return self.template(origins[0]['target'],frame)
        if n['kind']=='call_site' and n.get('receiver') and any(a.get('package') in {'std','core','alloc'} and
            a.get('name') in {'as_str','clone'} and (a.get('container') or '').split('<')[0] in {'String','str'} for a in self.api(uid)):
            return self.template(n['receiver'],frame)
        if n['kind']=='call_site':
            returns=[(target,e['target']) for target in self.targets(uid) for e in self.edges(target,'RETURNS_VALUE')]
            if len(returns)==1:
                target,value=returns[0];child=self.frame(uid,target,frame);result=self.template(value,child)
                result['conditions']=result['conditions']+child['conditions']+self.nodes[value].get('conditions',[])
                return result
        if n['kind']!='macro_site':
            value=self.scalar(uid,frame);literal=self.added[value['value']].get('literal')
            return {'parts':[{'literal':literal}] if isinstance(literal,str) else [{'slot':value['value'],'format_spec':''}],
                'complete':value['complete'],'gaps':value['gaps'],'conditions':value['conditions']}
        verified=any(self.nodes[e['target']].get('external_declaration',{}).get('package') in {'std','core','alloc'} and
            self.nodes[e['target']]['external_declaration'].get('name') in {'format','format_args'} for e in self.edges(uid,'MACRO_DEFINITION_ORIGIN'))
        if not verified:return {'parts':[],'complete':False,'gaps':['macro_not_native_standard_format'],'conditions':[]}
        path,ast=self.ast[uid];tokens=next((c for c in ast.named_children if c.type=='token_tree'),None)
        if tokens is None:return {'parts':[],'complete':False,'gaps':['format_token_tree_missing'],'conditions':[]}
        prefix=b'fn __project_map_format_probe(){(';surrogate=prefix+tokens.text[1:-1]+b');}'
        tree=self.parser.parse(surrogate)
        expression=next((c for c in walk(tree.root_node) if c.type in {'tuple_expression','parenthesized_expression'}),None)
        operands=list(expression.named_children) if expression else []
        if tree.root_node.has_error or not operands or operands[0].type not in {'string_literal','raw_string_literal'}:
            return {'parts':[],'complete':False,'gaps':['format_argument_syntax_not_supported'],'conditions':[]}
        offset=tokens.start_byte+1-len(prefix);positional=[];named={};implicit=defaultdict(list)
        for operand in operands[1:]:
            if operand.type=='assignment_expression':
                name=operand.child_by_field_name('left');value=operand.child_by_field_name('right')
                if name is not None and name.type=='identifier' and value is not None:named[text(name)]=self.operand(path,value,offset)
                else:return {'parts':[],'complete':False,'gaps':['format_named_argument_not_supported'],'conditions':[]}
            else:positional.append(self.operand(path,operand,offset))
        for e in self.edges(uid,'FORMAT_ARGUMENT'):
            value=self.nodes[e['target']]
            if value.get('syntax')=='format_capture':implicit[value['name']].append(value['id'])
        parts=[];gaps=[];conditions=[];next_position=0
        try:
            source=string_value(text(operands[0]))
            for literal,field,spec,conversion in Formatter().parse(source):
                if literal:parts.append({'literal':literal})
                if field is None:continue
                if conversion is not None or any(c in spec for c in '{}$*'):raise ValueError('dynamic_format_options_not_expanded')
                if field=='':index=next_position;next_position+=1;values=[positional[index]] if index<len(positional) else []
                elif field.isdecimal():index=int(field);values=[positional[index]] if index<len(positional) else []
                elif field.isidentifier():values=[named[field]] if field in named else implicit[field]
                else:raise ValueError('format_field_not_supported')
                resolved=[self.scalar(value,frame) for value in values]
                if len({r['value'] for r in resolved})!=1:raise ValueError('format_operand_not_uniquely_bound')
                value=resolved[0];parts.append({'slot':value['value'],'format_spec':spec,'source_values':values})
                gaps.extend(value['gaps']);conditions.extend(value['conditions'])
        except (ValueError,IndexError) as error:gaps.append(str(error))
        return {'parts':parts,'complete':not gaps,'gaps':sorted(set(gaps)),'conditions':conditions}

    def run_arguments(self):
        for context in [n for n in self.nodes.values() if n['kind']=='analysis_context']:
            self.context=context
            requests=[]
            for n in list(self.nodes.values()):
                if n['kind']!='rust_boundary' or context['id'] not in n.get('analysis_contexts',[]):continue
                if conditions_active(n.get('conditions',[]),context) is False:continue
                if n['family']=='process_start':
                    options={e['option_call']:e for e in self.edges(n['id'],'COMMAND_OPTION_SOURCE')}
                    for call in sorted(options,key=lambda c:self.nodes[c]['start_byte']):
                        if conditions_active(self.nodes[call].get('conditions',[]),context) is False:continue
                        api=self.api(call);methods={a['name'] for a in api if a.get('package')=='std' and (a.get('container') or '').split('<')[0]=='Command'}
                        if 'arg' in methods:
                            requests.extend((n,arg,'process_argument',call) for arg in self.nodes[call]['arguments'])
                        elif 'args' in methods:
                            for argument in self.nodes[call]['arguments']:
                                source=self.nodes[argument]
                                if source.get('collection_kind')=='array':
                                    requests.extend((n,e['target'],'process_argument',call) for e in self.edges(argument,'VALUE_COMPONENT') if e.get('collection_role')=='element')
                                else:requests.append((n,argument,'process_argument_sequence_unexpanded',call))
                elif n['family'] in {'frontend_loader','network_client','network_listener','resource_protocol_registration'}:
                    requests.extend((n,arg,n['family'],n['call']) for arg in n['arguments'][:1])
            for boundary,argument,role,call in requests:
                syntax=self.ast.get(boundary['call']);owner=self.owner(*syntax) if syntax else None
                for frame in self.frames(owner):
                    if frame.get('inactive'):continue
                    value=self.template(argument,frame)
                    if role.endswith('_unexpanded'):value.update(complete=False,gaps=value['gaps']+['argument_sequence_not_expanded'])
                    uid=identity('boundary-template',boundary['id'],call,argument,context['id'],json.dumps(frame['calls']))
                    source=self.nodes[argument];conditions=boundary.get('conditions',[])+frame['conditions']+value['conditions']+[
                        {'kind':'boundary_operation_reached_with_recorded_call_and_capture_context'},
                        {'kind':'no_unmodeled_operand_mutation_before_evaluation'},
                        {'kind':'no_unmodeled_command_builder_mutation_before_start'}]
                    self.added[uid]={'id':uid,'kind':'boundary_argument_template','name':role,'path':source['path'],'line':source['line'],
                        'language':'rust','consumer':boundary['id'],'argument':argument,'option_call':call,'role':role,
                        'analysis_context':context['id'],'root_function':frame['root_function'],'call_stack':frame['calls'],
                        'parts':value['parts'],'complete':value['complete'],'gaps':value['gaps'],'conditions':conditions,'runtime_execution':'not_observed'}
                    evidence=[{'path':source['path'],'line':source['line']}]
                    for a,b,kind in [(boundary['id'],uid,'BOUNDARY_ARGUMENT_TEMPLATE'),(uid,argument,'ARGUMENT_TEMPLATE_SOURCE')]:
                        self.value_edges.append({'source':a,'target':b,'kind':kind,'status':'source_candidate','analysis_contexts':[context['id']],
                            'evidence':evidence,'runtime_execution':'not_observed'})
                    for part in value['parts']:
                        if 'slot' in part:self.value_edges.append({'source':uid,'target':part['slot'],'kind':'TEMPLATE_VALUE_SLOT','status':'source_projection',
                            'analysis_contexts':[context['id']],'evidence':evidence,'format_spec':part['format_spec'],'runtime_execution':'not_observed'})
                    if not value['complete']:self.gaps.append({'kind':'rust_argument_template_unresolved','source':uid,'reasons':value['gaps'],'required':True})
                    self.counts['templates']+=1;self.counts['complete_source_templates']+=int(value['complete'])
        self.graph['nodes'].extend(self.added.values());self.graph['edges'].extend(self.value_edges);self.graph['diagnostics'].extend(self.gaps)
        self.graph['rust_argument_templates']={'adapter':ADAPTER_VERSION,'counts':dict(self.counts),'runtime_execution':'not_observed'}
        return self.graph


def augment(root,graph,parser):
    if 'rust_argument_templates' in graph:raise ValueError('Rust argument templates already present')
    return Arguments(root,graph,parser).run_arguments()
