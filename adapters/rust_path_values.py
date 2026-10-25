"""Source-positioned path values over native-bound Rust APIs and source calls.

The adapter slices path storage backwards at each consumer. Structured branches
and bounded literal-array loops retain conditions; unsupported effects stay gaps.
"""
from collections import defaultdict
import json
from pathlib import Path
import re

from adapters.path_values import expression_dag,literal,normalize,operation,symbol,unknown
from adapters.rust_facts import CALLABLES,conditions,pattern_names
from adapters.rust_project import binary,tool_output
from adapters.syntax_supplement import parents,text,walk


def string_value(source):
    source=source.replace('\r\n','\n')
    if source.startswith('r'):
        found=re.fullmatch(r'r(\#*)"(.*)"\1',source,re.S)
        if found:return found[2]
    if not source.startswith('"') or not source.endswith('"'):raise ValueError('not a Rust string')
    body=source[1:-1];result=[];index=0;simple={'n':'\n','r':'\r','t':'\t','0':'\0','\\':'\\','"':'"',"'":"'"}
    while index<len(body):
        if body[index]!='\\':result.append(body[index]);index+=1;continue
        index+=1
        if index>=len(body):raise ValueError('unfinished escape')
        char=body[index]
        if char in simple:result.append(simple[char]);index+=1
        elif char in '\r\n':
            while index<len(body) and body[index] in ' \t\r\n':index+=1
        elif char=='x':
            if not re.fullmatch(r'[0-9a-fA-F]{2}',body[index+1:index+3]):raise ValueError('invalid hex escape')
            value=int(body[index+1:index+3],16)
            if value>127:raise ValueError('non-ASCII Rust string hex escape')
            result.append(chr(value));index+=3
        elif char=='u':
            found=re.match(r'u\{([0-9a-fA-F_]+)\}',body[index:])
            if not found:raise ValueError('invalid Unicode escape')
            value=int(found[1].replace('_',''),16)
            if 0xD800<=value<=0xDFFF:raise ValueError('surrogate scalar')
            result.append(chr(value));index+=len(found[0])
        else:raise ValueError('unsupported string escape')
    return ''.join(result)


class Paths:
    def __init__(self,root,graph,parser,max_loop_steps=32):
        self.root=Path(root);self.graph=graph;self.nodes={n['id']:n for n in graph['nodes']};self.out=defaultdict(list)
        for edge in graph['edges']:self.out[edge['source']].append(edge)
        self.by_position={(n['path'],n['start_byte'],n['end_byte']):n['id'] for n in graph['nodes'] if 'start_byte' in n and 'end_byte' in n}
        self.ast={};self.units={};self.max_loop_steps=max_loop_steps;self.serial=0;self.diagnostics=[]
        for row in graph['coverage']:
            path=row['path']
            if not path.endswith('.rs'):continue
            tree=parser.parse((self.root/path).read_bytes());self.units[path]=tree
            for node in walk(tree.root_node):
                uid=self.by_position.get((path,node.start_byte,node.end_byte))
                if uid:self.ast[uid]=(path,node)
        self.functions={uid:node for uid,(path,node) in self.ast.items() if node.type in CALLABLES and node.child_by_field_name('body') is not None}
        self.calls_by_owner=defaultdict(list)
        for uid,(path,node) in self.ast.items():
            if node.type=='call_expression':self.calls_by_owner[self.owner(path,node)].append(uid)
        self.context=None;self.context_index=0;self.stack=set();self.cfg=[]

    def uid(self,path,node):return self.by_position.get((path,node.start_byte,node.end_byte)) if node is not None else None
    def owner(self,path,node):return next((self.uid(path,p) for p in parents(node) if p.type in CALLABLES),None)
    def edges(self,uid,kind):return [e for e in self.out.get(uid,[]) if e['kind']==kind and (not e.get('analysis_contexts') or self.context['id'] in e['analysis_contexts'])]
    def api(self,uid):return [self.nodes[e['target']]['external_declaration'] for e in self.edges(uid,'EXTERNAL_CALL_REFERENCE')]
    def std(self,uid,container,name):return any(a.get('package') in {'std','core','alloc'} and
        (a.get('container') or '').split('<')[0]==container and a.get('name')==name for a in self.api(uid))
    def result(self,uid,reason):return unknown(uid,reason)
    def frame(self,call,target,parent):
        arguments=list(self.nodes[call].get('arguments',[]));params=self.edges(target,'HAS_PARAMETER')
        params.sort(key=lambda e:e.get('index',0))
        if params and self.nodes[params[0]['target']].get('self_parameter') and self.nodes[call].get('receiver'):
            arguments.insert(0,self.nodes[call]['receiver'])
        return {'args':{e['target']:(argument,parent) for e,argument in zip(params,arguments)},
                'loops':{},'calls':parent['calls']+[call], 'root_function':parent.get('root_function'),
                'gaps':parent.get('gaps',[]),'conditions':parent.get('conditions',[])+[{'kind':'source_call_context','call':call,'target':target}]}
    def targets(self,uid):
        return sorted({e['target'] for kind in ('STATIC_CALL_TARGET','STATIC_CALL_CANDIDATE') for e in self.edges(uid,kind) if e['target'] in self.functions})
    def wrapped(self,uid):
        if uid in self.ast:
            path,node=self.ast[uid]
            value=node.child_by_field_name('value')
            if value is not None:return self.uid(path,value)
        values=[e['target'] for e in self.edges(uid,'VALUE_COMPONENT') if self.nodes[e['target']].get('syntax') not in {'mutable_specifier','line_comment','block_comment'}]
        return values[0] if len(values)==1 else None
    def mutable_argument(self,uid,seen=None):
        if not uid:return False
        seen=set() if seen is None else seen
        if uid in seen:return False
        seen=seen|{uid};node=self.nodes[uid]
        if re.match(r'&\s*mut\b',node.get('expression','')):return True
        if re.search(r'&\s*(?:\'[A-Za-z_]\w*\s*)?mut\b|\*\s*mut\b',node.get('declared_type','')):return True
        return any(self.mutable_argument(e['target'],seen) for kind in ('READS_BINDING','VALUE_SOURCE') for e in self.edges(uid,kind))

    def storage(self,uid,seen=None):
        if not uid:return None
        seen=set() if seen is None else seen
        if uid in seen:return None
        seen=seen|{uid};node=self.nodes[uid]
        if node['kind'] in {'binding','parameter'}:
            if node.get('binding_kind')=='field_declaration':return None
            origins=self.edges(uid,'VALUE_SOURCE')
            if len(origins)==1:
                value=self.nodes[origins[0]['target']]
                if value.get('syntax') in {'identifier','reference_expression','parenthesized_expression'}:
                    return self.storage(value['id'],seen)
            return uid
        if node.get('syntax')=='field_expression':return None
        reads=self.edges(uid,'READS_BINDING')
        if len(reads)==1:return self.storage(reads[0]['target'],seen)
        if node.get('syntax') in {'reference_expression','parenthesized_expression','unary_expression'}:
            return self.storage(self.wrapped(uid),seen)
        if node['kind']=='call_site' and any(self.std(uid,'PathBuf',n) or self.std(uid,'Path',n) for n in ('as_path','as_ref')):
            return self.storage(node.get('receiver'),seen)
        return None

    def evaluate(self,uid,frame,position=None):
        if uid is None:return self.result('', 'unindexed_expression')
        node=self.nodes[uid];position=node.get('start_byte',0) if position is None else position
        key=(uid,position,tuple(frame['calls']),json.dumps(frame['loops'],sort_keys=True))
        if key in self.stack or len(self.stack)>64:return self.result(uid,'path_recursion_or_depth_budget')
        self.stack.add(key)
        try:return self._evaluate(uid,node,frame,position)
        finally:self.stack.remove(key)

    def _evaluate(self,uid,node,frame,position):
        if uid in frame['loops']:return frame['loops'][uid]
        if node['kind'] in {'binding','parameter'}:
            root=self.storage(uid)
            if root and root!=uid:return self.evaluate(root,frame,position)
            if uid in frame['args']:
                argument,parent=frame['args'][uid];value=self.evaluate(argument,parent)
            else:
                origins=self.edges(uid,'VALUE_SOURCE') or self.edges(uid,'PATTERN_VALUE_SOURCE')
                value=self.evaluate(origins[0]['target'],frame) if len(origins)==1 else symbol(uid) if node['kind']=='parameter' else self.result(uid,'binding_value_unknown')
                if len(origins)==1 and origins[0]['kind']=='PATTERN_VALUE_SOURCE':
                    value=operation('assume_pattern',value,source=uid,pattern=node.get('pattern'))
            syntax=self.ast.get(uid)
            if syntax:
                path,ast=syntax;owner=self.owner(path,ast)
                if owner in self.functions:return self.transfer(path,self.functions[owner].child_by_field_name('body'),value,uid,position,frame)
            return value
        syntax=node.get('syntax')
        if node['kind']=='external_symbol':
            declaration=node.get('external_declaration',{})
            if declaration.get('package') in {'std','core'} and declaration.get('name')=='None' and '::Option::' in declaration.get('canonical',''):
                return {'op':'none'}
        if syntax in {'string_literal','raw_string_literal'}:
            try:return {**literal(string_value(node['expression'])),'source':uid}
            except (ValueError,OverflowError):return self.result(uid,'unsupported_Rust_string_literal')
        if node.get('collection_kind'):
            members=self.edges(uid,'VALUE_COMPONENT');members.sort(key=lambda e:e.get('index',0))
            if len(members)>self.max_loop_steps:return self.result(uid,'array_literal_path_budget')
            elements=[self.evaluate(e['target'],frame) for e in members if e.get('collection_role')=='element']
            if node['collection_kind']=='array_repeat':
                lengths=[self.nodes[e['target']].get('expression','') for e in members if e.get('collection_role')=='repeat_count']
                if len(lengths)!=1 or not re.fullmatch(r'[0-9_]+',lengths[0]):return self.result(uid,'dynamic_array_repeat_count')
                count=int(lengths[0].replace('_',''))
                if count>self.max_loop_steps:return self.result(uid,'array_repeat_budget')
                elements=elements*count
            return {'op':'array','items':elements}
        if syntax in {'reference_expression','try_expression','parenthesized_expression'}:
            child=self.wrapped(uid)
            return self.evaluate(child,frame) if child else self.result(uid,'ambiguous_expression_wrapper')
        if node['kind']=='call_site':return self.call(uid,frame)
        reads=self.edges(uid,'READS_BINDING')
        if len(reads)==1:return self.evaluate(reads[0]['target'],frame,position)
        if syntax=='block':
            children=self.edges(uid,'VALUE_COMPONENT')
            if children:return self.evaluate(children[-1]['target'],frame)
        return self.result(uid,'path_expression_not_resolved')

    def call(self,uid,frame):
        node=self.nodes[uid];arguments=node.get('arguments',[]);receiver=node.get('receiver');apis=self.api(uid)
        argument=lambda index:self.evaluate(arguments[index],frame) if index<len(arguments) else self.result(uid,'missing_path_argument')
        if any(a.get('canonical')=='std::env::current_exe' for a in apis):
            return {'op':'current_executable','source':uid,'workspace':self.context.get('workspace'),'call_stack':frame['calls']}
        if any(a.get('package') in {'std','core'} and a.get('name')=='Some' and '::Option::' in a.get('canonical','') for a in apis):
            return operation('some',argument(0),source=uid)
        if any(a.get('package') in {'std','core'} and
            ((a.get('container') or '').split('<')[0] in {'Option','Result'} or a.get('module') in {'src/option.rs','src/result.rs'})
            and a.get('name') in {'unwrap','expect'} for a in apis):
            return operation('unwrap',self.evaluate(receiver,frame),source=uid)
        for container in ('Path','PathBuf'):
            for name in ('new','from','clone','to_path_buf','as_path','as_ref','join','with_extension','with_file_name','parent'):
                if not self.std(uid,container,name):continue
                if name in {'new','from'}:return literal('') if name=='new' and container=='PathBuf' else argument(0)
                base=self.evaluate(receiver,frame)
                if name in {'join','with_extension','with_file_name'}:
                    return operation({'join':'join','with_extension':'set_extension','with_file_name':'set_file_name'}[name],base,argument(0),source=uid)
                return operation('as_path' if name=='as_ref' else name,base,source=uid)
        candidates=[]
        for target in self.targets(uid):
            child=self.frame(uid,target,frame)
            if len(child['calls'])>12:return self.result(uid,'path_call_context_budget')
            for edge in self.edges(target,'RETURNS_VALUE'):
                candidates.append({'value':self.evaluate(edge['target'],child),
                    'conditions':self.nodes[edge['target']].get('conditions',[])+[{'kind':'source_return','call':uid,'return':edge['target']}]})
        if candidates:return {'op':'choice','choices':candidates}
        return self.result(uid,'path_call_result_unknown')

    def active(self,node):
        # Evaluate only predicates established by this compiler context. Unknown
        # custom cfg/features stay conditional; no project names are recognized.
        results=[]
        for guard in conditions(node):
            if guard['kind']!='rust_attribute':continue
            match=re.fullmatch(r'#\s*\[\s*cfg\((.*)\)\s*\]',guard['expression'],re.S)
            if not match:results.append(None);continue
            expression=re.sub(r'\s+','',match[1])
            if expression in self.cfg:results.append(True)
            elif expression in {'windows','unix','test','debug_assertions','proc_macro'}:results.append(False)
            elif expression.startswith('target_') and '=' in expression:results.append(False)
            elif expression.startswith('feature='):
                name=expression.partition('=')[2].strip('"')
                results.append(True if any(f.rsplit('/',1)[-1]==name for f in self.context.get('features',[])) else None)
            else:results.append(None)
        return False if False in results else None if None in results else True

    def transfer(self,path,node,value,binding,position,frame):
        if node is None or node.start_byte>=position:return value
        if node.type in CALLABLES:return value
        if not self.touches(path,node,binding,position):return value
        enabled=self.active(node)
        if enabled is False:return value
        before=value
        if node.type=='if_expression':
            consequence=node.child_by_field_name('consequence');alternative=node.child_by_field_name('alternative')
            condition=node.child_by_field_name('condition');guard={'kind':'path_branch','path':path,'start_byte':condition.start_byte,'expression':text(condition)}
            if node.start_byte<position<node.end_byte:
                branch=consequence if consequence and consequence.start_byte<=position<=consequence.end_byte else alternative
                return self.transfer(path,branch,value,binding,position,frame)
            if text(condition) in {'true','false'}:
                return self.transfer(path,consequence if text(condition)=='true' else alternative,value,binding,position,frame)
            left=self.transfer(path,consequence,value,binding,position,frame)
            right=self.transfer(path,alternative,value,binding,position,frame)
            return value if left==right else {'op':'choice','choices':[{'value':left,'conditions':[{**guard,'polarity':True}]},{'value':right,'conditions':[{**guard,'polarity':False}]}]}
        if node.type in {'while_expression','loop_expression'}:
            return self.result(self.uid(path,node),'unbounded_iteration_path_effect')
        if node.type=='for_expression':
            if node.start_byte<position<node.end_byte:return self.result(self.uid(path,node),'path_read_within_iteration_needs_iteration_context')
            if any(c.type in {'break_expression','continue_expression','return_expression'} for c in walk(node.child_by_field_name('body'))):
                return self.result(self.uid(path,node),'loop_control_requires_path_flow_analysis')
            values=self.evaluate(self.uid(path,node.child_by_field_name('value')),frame)
            if values['op']!='array' or len(values['items'])>self.max_loop_steps:
                return self.result(self.uid(path,node),'dynamic_iteration_path_effect')
            names=pattern_names(node.child_by_field_name('pattern'))
            if len(names)!=1:return self.result(self.uid(path,node),'iteration_pattern_projection_not_expanded')
            for item in values['items']:
                child={**frame,'loops':{**frame['loops'],self.uid(path,names[0]):item}}
                value=self.transfer(path,node.child_by_field_name('body'),value,binding,position,child)
            return value
        for child in node.named_children:value=self.transfer(path,child,value,binding,position,frame)
        uid=self.uid(path,node)
        if node.type=='assignment_expression' and node.end_byte<=position:
            target=self.uid(path,node.child_by_field_name('left'))
            source=self.uid(path,node.child_by_field_name('right'))
            if self.storage(target)==binding or self.storage(source)==binding:
                return self.result(target,'path_reassignment_needs_storage_version_identity')
        if node.type=='macro_invocation' and node.end_byte<=position:
            return self.result(uid or '', 'macro_path_effect_not_expanded')
        if node.type=='call_expression' and node.end_byte<=position and uid:
            value=self.effect(uid,value,binding,frame)
        if enabled is None and value!=before:
            return {'op':'choice','choices':[{'value':value,'conditions':[{'kind':'unresolved_cfg','path':path,'line':node.start_point[0]+1}]},{'value':before,'conditions':[{'kind':'unresolved_cfg_not_selected','path':path,'line':node.start_point[0]+1}]}]}
        return value

    def touches(self,path,node,binding,position):
        if node.start_byte>=position or node.type in CALLABLES:return False
        uid=self.uid(path,node)
        if node.type=='assignment_expression' and binding in {
            self.storage(self.uid(path,node.child_by_field_name('left'))),self.storage(self.uid(path,node.child_by_field_name('right')))}:return True
        if node.type=='macro_invocation' and uid:
            if any(self.storage(e['target'])==binding for e in self.edges(uid,'MACRO_TOKEN')):return True
        if node.type=='call_expression' and uid:
            record=self.nodes[uid]
            if self.storage(record.get('receiver'))==binding:
                readonly={'clone','to_path_buf','as_path','as_os_str','as_ref','parent','join','with_extension','with_file_name',
                    'display','to_str','to_string_lossy','exists','try_exists','is_file','is_dir','file_name','file_stem','extension',
                    'capacity','is_empty','components','iter','has_root','is_absolute','starts_with','ends_with','strip_prefix','metadata','canonicalize'}
                if not any(a.get('package') in {'std','core','alloc'} and a.get('name') in readonly for a in self.api(uid)):return True
            for argument in record.get('arguments',[]):
                if self.storage(argument)==binding and self.mutable_argument(argument):return True
            for target in self.targets(uid):
                body=self.functions[target].child_by_field_name('body')
                # Captured outer path storage can be modified by a closure/local
                # helper even when it has no explicit &mut parameter.
                if body is not None and any(self.nodes[c].get('receiver') and self.storage(self.nodes[c]['receiver'])==binding
                    for c in self.calls_by_owner.get(target,[])):return True
        return any(self.touches(path,child,binding,position) for child in node.named_children)

    def effect(self,uid,value,binding,frame):
        node=self.nodes[uid];receiver=node.get('receiver');arguments=node.get('arguments',[])
        if self.storage(receiver)==binding:
            for name in ('push','set_extension','set_file_name','clear','pop'):
                if not self.std(uid,'PathBuf',name):continue
                if name=='clear':return literal('')
                if name=='pop':return operation('pop',value,source=uid)
                argument=self.evaluate(arguments[0],frame) if arguments else self.result(uid,'missing_path_mutation_argument')
                return operation({'push':'join','set_extension':'set_extension','set_file_name':'set_file_name'}[name],value,argument,source=uid)
        effects=[]
        for target in self.targets(uid):
            child=self.frame(uid,target,frame)
            for parameter,(argument,parent) in child['args'].items():
                parameter_type=self.nodes[parameter].get('declared_type','')
                if self.nodes[parameter].get('self_parameter') and parameter in self.ast:
                    parameter_type=text(self.ast[parameter][1].parent)
                if re.search(r'&\s*(?:\'[A-Za-z_][A-Za-z_0-9]*\s*)?mut\b',parameter_type) and self.storage(argument)==binding:
                    if len(child['calls'])>12:return self.result(uid,'mutable_path_call_context_budget')
                    return_type=self.functions[target].child_by_field_name('return_type')
                    result=self.result(uid,'reference_return_may_escape_path_storage') if return_type is not None and return_type.type=='reference_type' else self.evaluate(parameter,child,self.functions[target].end_byte)
                    effects.append({'value':result,'conditions':[{'kind':'source_mutable_call','call':uid,'target':target}]})
            if any(self.storage(self.nodes[c].get('receiver'))==binding for c in self.calls_by_owner.get(target,[])):
                effects.append({'value':self.result(uid,'captured_path_effect_requires_call_storage_context'),'conditions':[{'kind':'source_call','call':uid,'target':target}]})
        if effects:return {'op':'choice','choices':effects}
        if self.storage(receiver)==binding:return self.result(uid,'unmodeled_path_receiver_effect')
        if any(self.storage(argument)==binding and self.mutable_argument(argument) for argument in arguments):
            return self.result(uid,'unresolved_mutable_path_argument')
        return value

    def frames(self,function,seen=()):
        root={'args':{},'loops':{},'calls':[],'root_function':function,'gaps':[],'conditions':[]}
        if function is None:return [root]
        if function in seen or len(seen)>=12:return [{**root,'gaps':['recursive_path_caller_context']}]
        callers=[]
        for owner,calls in self.calls_by_owner.items():
            for call in calls:
                if function in self.targets(call):callers.append((owner,call))
        if not callers:return [root]
        results=[]
        for owner,call in sorted(callers,key=lambda pair:pair[1]):
            for parent in self.frames(owner,seen+(function,)):
                results.append(self.frame(call,function,parent))
                if len(results)>=32:return results+[{**root,'gaps':['path_caller_context_budget']}]
        return results

    def run(self):
        added=[];edges=[]
        contexts=[n for n in self.nodes.values() if n['kind']=='analysis_context']
        for index,context in enumerate(contexts):
            self.context=context;self.context_index=index
            self.cfg=[re.sub(r'\s+','',c) for c in context.get('cfg',[])]
            if not self.cfg:
                try:self.cfg=tool_output([binary('rustc'),'--print','cfg','--target',context['target']],self.root).splitlines()
                except (ValueError,OSError):self.cfg=[]
            style='windows' if 'windows' in self.cfg else 'posix' if 'unix' in self.cfg else 'unknown'
            consumers=[]
            for node in self.nodes.values():
                if node['kind']=='rust_boundary' and context['id'] in node.get('analysis_contexts',[]) and node['family'] in {'command_constructor','file_read'}:
                    consumers.extend((node,argument) for argument in node['arguments'][:1])
            for boundary,argument in consumers:
                origin=self.ast.get(boundary['call']);owner=self.owner(*origin) if origin else None
                for frame in self.frames(owner):
                    term=self.evaluate(argument,frame) if not frame['gaps'] else self.result(argument,frame['gaps'][0])
                    try:serialized=expression_dag(term)
                    except ValueError:
                        term=self.result(argument,'path_expression_node_budget');serialized=expression_dag(term)
                    for value in normalize(term,style):
                        self.publish(added,edges,boundary,argument,frame,serialized,value,index,context)
        self.graph['nodes'].extend(added);self.graph['edges'].extend(edges);self.graph['diagnostics'].extend(self.diagnostics)
        self.graph['limits'].extend(['path_values_are_source_candidates_not_execution',
            'unexpanded_path_macros_storage_reassignment_and_dynamic_loops_remain_explicit_gaps'])
        return self.graph

    def publish(self,added,edges,boundary,argument,frame,term,value,index,context):
        self.serial+=1;uid=argument+':path:'+str(index)+':'+str(self.serial)
        value={**value,'conditions':value['conditions']+frame['conditions']}
        row={'id':uid,'kind':'path_value','name':value.get('relative_path') or value.get('path') or 'unresolved path',
            'path':self.nodes[argument]['path'],'line':self.nodes[argument]['line'],'language':'rust',
            'origin':argument,'consumer':boundary['id'],'analysis_contexts':[context['id']],
            'expression':term,'value':value,'call_stack':frame['calls'],'root_function':frame['root_function'],'runtime_execution':'not_observed',
            'control_flow_status':'source_order_and_structured_path_effects_not_execution'}
        added.append(row)
        edges.append({'source':argument,'target':uid,'kind':'PATH_VALUE_CANDIDATE','status':'candidate',
            'analysis_contexts':[context['id']],'evidence':[{'path':row['path'],'line':row['line']}],
            'runtime_execution':'not_observed','basis':'native_bound_path_API_and_positioned_source_effects'})
        sources={t['source'] for t in term['terms'] if t.get('source') in self.nodes}
        for source in sorted(sources):
            edges.append({'source':uid,'target':source,'kind':'PATH_COMPONENT_SOURCE','status':'source_relation',
                'analysis_contexts':[context['id']],'evidence':[{'path':self.nodes[source]['path'],'line':self.nodes[source]['line']}],
                'runtime_execution':'not_observed','basis':'path_expression_source_origin'})
        for source in frame['calls']:
            edges.append({'source':uid,'target':source,'kind':'PATH_CALL_CONTEXT','status':'candidate',
                'analysis_contexts':[context['id']],'evidence':[{'path':self.nodes[source]['path'],'line':self.nodes[source]['line']}],
                'runtime_execution':'not_observed'})
        if value['unresolved']:
            self.diagnostics.append({'kind':'rust_path_value_unresolved','path':row['path'],'line':row['line'],
                'source':argument,'analysis_context':context['id'],'reasons':value['unresolved'],'required':True})


def augment(root,graph,parser):return Paths(root,graph,parser).run()
