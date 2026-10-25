"""Import-bound Python paths and file operations over AST/Jedi source identities.

Runtime path styles are explicit alternatives, independent of the analysis host.
File operations retain destination semantics and source conditions for later
artifact propagation; this pass does not execute copies or pair artifacts.
"""
import ast
from collections import defaultdict
from pathlib import Path
import tokenize

from adapters.python_boundaries import Boundaries
from adapters.path_values import expression_dag,literal,normalize,operation,symbol,unknown

PATH_TYPES={'pathlib.Path','pathlib.PurePath','pathlib.PureWindowsPath','pathlib.PurePosixPath'}
FILE_APIS={'shutil.copyfile':('copy_file','exact_path'),
    'shutil.copy':('copy_file','file_or_existing_directory'),'shutil.copy2':('copy_file','file_or_existing_directory'),
    'shutil.copytree':('copy_tree','directory_root'),'shutil.move':('move_path','path_or_existing_directory'),
    'os.rename':('rename_path','exact_path'),'os.replace':('replace_path','exact_path')}


class Paths(Boundaries):
    def __init__(self,root,facts):
        super().__init__(facts);self.root=Path(root).resolve();self.memo={};self.parents={};self.ast={}
        self.added=[];self.links=[];self.errors=[];self.serial=0
        by_position=defaultdict(list)
        for node in self.nodes.values():
            by_position[(node['path'],node['line'],node.get('column'),node.get('end_line'),node.get('end_column'))].append(node)
        for row in facts['coverage']:
            if row['status']!='parsed' or not row['path'].endswith(('.py','.pyi')):continue
            path=row['path'];target=(self.root/path).resolve()
            if not target.is_relative_to(self.root):raise ValueError('Python path source escaped export')
            with tokenize.open(target) as stream:code=stream.read().replace('\r\n','\n')
            tree=ast.parse(code,filename=path);lines=code.splitlines()
            for parent in ast.walk(tree):
                for child in ast.iter_child_nodes(parent):self.parents[id(child)]=parent
                if not hasattr(parent,'lineno'):continue
                column=len(lines[parent.lineno-1].encode('utf-8')[:parent.col_offset].decode('utf-8'))+1
                end_column=len(lines[parent.end_lineno-1].encode('utf-8')[:parent.end_col_offset].decode('utf-8'))+1
                for node in by_position.get((path,parent.lineno,column,parent.end_lineno,end_column),[]):
                    if node.get('expression_kind')==type(parent).__name__ or node['kind']=='call_site' and isinstance(parent,ast.Call):
                        self.ast[node['id']]=parent

    def api(self,uid,seen=None):
        if seen and uid in seen:return set()
        result=super().api(uid,seen)
        visited=(seen or set())|{uid}
        if self.nodes[uid]['kind']=='call_site':
            for callee in self.targets(uid,{'CALLS_EXPRESSION'}):
                identities=super().api(callee,visited)
                result.update(identities&PATH_TYPES)
                result.update(p for p in PATH_TYPES if p+'.joinpath' in identities)
        elif self.nodes[uid].get('expression_kind')=='BinOp' and isinstance(getattr(self.ast.get(uid),'op',None),ast.Div):
            for left in self.children(uid,'left'):result.update(self.api(left,visited)&PATH_TYPES)
        elif self.nodes[uid].get('member')=='parent':
            for receiver in self.children(uid,'value'):result.update(self.api(receiver,visited)&PATH_TYPES)
        return result

    def children(self,uid,field):
        return [e['target'] for e in sorted(self.out[uid],key=lambda e:e.get('index',0))
                if e['kind']=='VALUE_COMPONENT' and e.get('field')==field]

    def choice(self,rows,uid):
        if not rows:return unknown(uid,'python_binding_without_path_source')
        if len(rows)==1:return rows[0]
        return {'op':'choice','source':uid,'choices':[{'value':v} for v in rows]}

    def evaluate(self,uid,seen=()):
        if uid in seen:return unknown(uid,'recursive_python_path_value')
        if len(seen)>=48:return unknown(uid,'python_path_expression_depth')
        key=(self.style,uid)
        if key in self.memo:return self.memo[key]
        node=self.nodes[uid];seen=seen+(uid,)
        ev=lambda v:self.evaluate(v,seen)
        if node.get('literal_type')=='str':result={**literal(node['literal']),'source':uid}
        elif node['kind']=='parameter':result=symbol(uid)
        elif node.get('identifier')=='__file__' and not self.targets(uid,{'READS_BINDING'}):
            result={'op':'source_file','source':uid,'path':node['path']}
        elif node['kind']=='call_site':result=self.call(uid,ev)
        elif node.get('expression_kind')=='IfExp':
            result={'op':'choice','source':uid,'choices':[{'value':ev(t),
                'conditions':[{'kind':'python_conditional_expression','source':uid,'branch':field}]} for field in ('body','orelse') for t in self.children(uid,field)]}
        elif node.get('expression_kind')=='BinOp' and isinstance(getattr(self.ast.get(uid),'op',None),ast.Div):
            left=self.children(uid,'left');right=self.children(uid,'right')
            result=operation('join',ev(left[0]),ev(right[0]),source=uid) if left and right and self.api(left[0])&PATH_TYPES else unknown(uid,'unproven_path_division_receiver')
        elif node.get('member')=='parent' and any(self.api(v)&PATH_TYPES for v in self.children(uid,'value')):
            result=operation('python_parent',ev(self.children(uid,'value')[0]),source=uid)
        else:
            sources=[e for e in self.out[uid] if e['kind'] in {'READS_BINDING','VALUE_SOURCE','DEFAULT_VALUE','IMPORTS_SYMBOL'}]
            # Parameters remain per-function symbols. Combining every incoming
            # BINDS_ARGUMENT here would mix independent callers.
            choices=[{'value':ev(e['target']),'conditions':e.get('conditions',[])} for e in sources]
            result=({'op':'choice','source':uid,'choices':choices} if choices else unknown(uid,'python_binding_without_path_source'))
        self.memo[key]=result
        return result

    def call(self,uid,ev):
        apis=self.called_api(uid);node=self.nodes[uid]
        def arg(index,keywords=()):
            rows=self.argument(uid,index,keywords)
            return self.choice([ev(t) for t in rows],uid)
        if apis&PATH_TYPES:
            selected=apis&PATH_TYPES
            if self.style=='posix' and 'pathlib.PureWindowsPath' in selected or self.style=='windows' and 'pathlib.PurePosixPath' in selected:
                return unknown(uid,'explicit_python_path_style_mismatch')
            args=[e for e in self.out[uid] if e['kind']=='CALL_ARGUMENT']
            if any(e.get('keyword') is not None or e.get('spread') for e in args):return unknown(uid,'python_path_constructor_argument_shape')
            values=[ev(e['target']) for e in sorted(args,key=lambda e:e['index'])]
            result=values[0] if values else literal('.')
            for value in values[1:]:result=operation('join',result,value,source=uid)
            return operation('to_path_buf',result,source=uid)
        if apis&{'os.path.join'}:
            args=[e for e in self.out[uid] if e['kind']=='CALL_ARGUMENT']
            if not args or any(e.get('keyword') is not None or e.get('spread') for e in args):return unknown(uid,'python_join_argument_shape')
            values=[ev(e['target']) for e in sorted(args,key=lambda e:e['index'])]
            return operation('python_join',*values,source=uid)
        if 'os.path.dirname' in apis:return operation('python_dirname',arg(0,('p',)),source=uid)
        if 'os.path.realpath' in apis:return operation('python_realpath',arg(0,('filename',)),source=uid)
        if apis&{p+'.joinpath' for p in PATH_TYPES}:
            callee=self.targets(uid,{'CALLS_EXPRESSION'});receivers=[v for c in callee for v in self.children(c,'value')]
            if len(receivers)!=1:return unknown(uid,'python_path_receiver_not_unique')
            args=[e for e in self.out[uid] if e['kind']=='CALL_ARGUMENT']
            if any(e.get('keyword') is not None or e.get('spread') for e in args):return unknown(uid,'python_join_argument_shape')
            result=ev(receivers[0])
            for edge in sorted(args,key=lambda e:e['index']):result=operation('join',result,ev(edge['target']),source=uid)
            return result
        if self.targets(uid,{'STATIC_CALL_TARGET','STATIC_CALL_CANDIDATE'}):return unknown(uid,'python_source_path_call_context_not_expanded')
        return unknown(uid,'python_path_call_not_modeled')

    def link(self,source,target,kind,**extra):
        node=self.nodes[source]
        self.links.append({'source':source,'target':target,'kind':kind,'status':'candidate',
            'evidence':[{'path':node['path'],'line':node['line']}],'runtime_execution':'not_observed',**extra})

    def publish(self,operation_node,argument,role):
        for style in ('windows','posix'):
            self.style=style;term=self.evaluate(argument)
            try:dag=expression_dag(term)
            except ValueError:term=unknown(argument,'python_path_expression_node_budget');dag=expression_dag(term)
            for value in normalize(term,style):
                self.serial+=1;uid=argument+':path:'+str(self.serial)
                row={'id':uid,'kind':'path_value','name':value.get('relative_path') or value.get('path') or 'unresolved path',
                    **{k:operation_node[k] for k in ('path','line','column','language','conditions')},
                    'origin':argument,'consumer':operation_node['id'],'role':role,'expression':dag,'value':value,
                    'path_context':{'style':style,'basis':'unselected_runtime_path_style_candidate'},'runtime_execution':'not_observed',
                    'control_flow_status':'enclosing_syntax_conditions_only'}
                self.added.append(row);self.nodes[uid]=row;self.link(argument,uid,'PATH_VALUE_CANDIDATE',path_style=style)
                for source in sorted({t['source'] for t in dag['terms'] if t.get('source') in self.nodes}):
                    self.link(uid,source,'PATH_COMPONENT_SOURCE',path_style=style)
                if value['unresolved']:self.errors.append({'kind':'python_path_value_unresolved','path':row['path'],'line':row['line'],
                    'source':argument,'path_style':style,'reasons':value['unresolved'],'required':True})

    def run(self):
        for call in list(self.nodes.values()):
            if call['kind']!='call_site':continue
            selected=self.called_api(call['id'])&FILE_APIS.keys()
            if not selected:continue
            args=[e for e in self.out[call['id']] if e['kind']=='CALL_ARGUMENT']
            bid=call['id']+':file_operation'
            node={'id':bid,'kind':'python_file_operation',**{k:call[k] for k in ('path','line','column','name','language','conditions')},
                'call':call['id'],'api_candidates':sorted(selected),'operation_candidates':sorted({FILE_APIS[a][0] for a in selected}),
                'destination_semantics':sorted({FILE_APIS[a][1] for a in selected}),
                'option_values':[{k:e[k] for k in ('target','keyword','index','spread') if k in e} for e in args if e.get('keyword') not in {None,'src','dst'} or e.get('index',0)>1],
                'mapping_status':'requires_control_flow_options_and_destination_context','runtime_execution':'not_observed'}
            self.added.append(node);self.nodes[bid]=node;self.link(call['id'],bid,'DECLARES_FILE_OPERATION')
            if any(e.get('spread') for e in args):
                self.errors.append({'kind':'python_file_operation_argument_expansion','path':call['path'],'line':call['line'],'source':call['id'],'required':True});continue
            for role,index,keyword in [('source',0,'src'),('destination',1,'dst')]:
                arguments=self.argument(call['id'],index,(keyword,))
                for argument in arguments:
                    self.link(bid,argument,'FILE_'+role.upper());self.publish(node,argument,role)
                if not arguments:self.errors.append({'kind':'python_file_operation_missing_argument','role':role,
                    'path':call['path'],'line':call['line'],'source':call['id'],'required':True})
        self.facts['nodes'].extend(self.added);self.facts['edges'].extend(self.links);self.facts['diagnostics'].extend(self.errors)
        self.facts['limits'].extend(['python_path_styles_are_explicit_runtime_candidates',
            'python_file_operations_require_control_flow_options_destination_and_deployment_context',
            'python_path_caller_frames_and_directory_enumeration_not_expanded'])
        return self.facts


def augment(root,facts):return Paths(root,facts).run()
