"""Source-bound argv/cwd/settings and environment writes for Python processes."""
import ast
from adapters.path_values import expression_dag,literal,normalize,operation,unknown
from adapters.python_boundaries import PROCESS_START
from adapters.python_process_values import string_candidates
from adapters.artifact_copy_graph import before
from adapters.file_predicate_values import evaluate


ENV_CALLS={'os.putenv','os.unsetenv','os.environ.update','os.environ.clear','os.environ.pop','os.environ.setdefault',
    'os.environ.popitem','os.environ.__setitem__','os.environ.__delitem__','os.environ.__ior__'}


class ProcessCalls:
    def __init__(self,paths):
        self.p=paths;self.effects=[];self.invocations=[];self.sequence_safety={};self.patches={}
        for uid,syntax in list(paths.ast.items()):
            if not isinstance(syntax,ast.Attribute) or not isinstance(syntax.ctx,(ast.Store,ast.Del)):continue
            receiver=paths.ast_ids.get(id(syntax.value))
            if not receiver:continue
            for frame in paths.calls.frames(self.owner(uid)):
                for module in paths.predicates.exact_api(receiver,frame):
                    api=module+'.'+syntax.attr
                    self.patches.setdefault(api,[]).append({'id':uid,'root_function':frame['root_function'],
                        'call_stack':frame['calls'],'execution_address':paths.execution_address(uid,frame)})

    def member_writes(self,apis,context):
        return sorted({w['id'] for api in apis for w in self.patches.get(api,[]) if before(w,context,self.p.nodes) is not False})

    def owner(self,uid):
        p=self.p
        if uid in p.calls.owners:return p.calls.owner(uid)
        child=p.ast.get(uid)
        while child is not None:
            parent=p.parents.get(id(child))
            if isinstance(parent,(ast.FunctionDef,ast.AsyncFunctionDef,ast.Lambda,ast.ClassDef)):
                return p.ast_ids.get(id(parent),p.calls.owner(uid))
            child=parent
        return p.calls.owner(uid)

    def context(self,uid,frame,kind,style):
        p=self.p;n=p.nodes[uid]
        return {'id':uid+':'+kind+':'+p.calls.identity(frame)+':'+style,'kind':kind,
            **{k:n[k] for k in ('path','line','column','language','name')},'call':uid,'call_stack':frame['calls'],
            'root_function':frame['root_function'],'execution_address':p.execution_address(uid,frame),'path_style':style,
            'conditions':p.predicates.enrich(frame['conditions']+n.get('conditions',[])+p.guard_conditions(uid,frame)),
            'gaps':list(frame['gaps'])+(['python_definition_time_effect_scope_not_expanded'] if p.nodes.get(frame['function'],{}).get('kind')=='type' else []),'runtime_execution':'not_observed'}

    def words(self,term):
        p=self.p;strings=string_candidates(term,p.style)
        if all(text is not None for text,_ in strings):
            rows=[{'text':text,'path_value':normalize(literal(text),p.style)[0],'conditions':guards} for text,guards in strings]
        else:rows=[{'text':None,'path_value':value,'conditions':value['conditions']} for value in normalize(term,p.style)]
        for row in rows:
            row['conditions']=p.predicates.enrich(row['conditions']);row['path_value']={k:v for k,v in row['path_value'].items() if k!='conditions'}
        return rows

    def readonly_sequence(self,origin):
        if origin in self.sequence_safety:return self.sequence_safety[origin]
        p=self.p;pending=[origin];seen=set();reason=None
        while pending and reason is None:
            uid=pending.pop()
            if uid in seen:continue
            seen.add(uid)
            if len(seen)>512:reason='python_process_sequence_alias_budget';break
            n=p.nodes[uid];syntax=p.ast.get(uid);pending.extend(p.mappings.reverse[uid])
            pending.extend(e['target'] for e in p.out[uid] if e['kind']=='BINDS_ARGUMENT')
            if n['kind']=='binding':
                pending.extend(p.storage.groups[(n.get('enclosing_symbol'),n['name'])]);continue
            if not isinstance(syntax,(ast.Name,ast.Attribute,ast.List)):continue
            parent=p.parents.get(id(syntax))
            if isinstance(parent,(ast.Assign,ast.AnnAssign)) and parent.value is syntax:
                targets=parent.targets if isinstance(parent,ast.Assign) else [parent.target]
                if len(targets)==1 and isinstance(targets[0],ast.Name):continue
            if isinstance(parent,ast.Subscript) and parent.value is syntax and isinstance(parent.ctx,ast.Load):continue
            if isinstance(parent,ast.For) and parent.iter is syntax:continue
            call=parent if isinstance(parent,ast.Call) else p.parents.get(id(parent)) if isinstance(parent,ast.keyword) else None
            if isinstance(call,ast.Call):
                call_id=p.ast_ids.get(id(call))
                if any(e['kind']=='BINDS_ARGUMENT' and e.get('call')==call_id for e in p.out[uid]):continue
                if call_id and p.called_api(call_id)&PROCESS_START and not any(p.nodes[t]['kind'] in {'callable','type'} for t in p.targets(call_id,{'STATIC_CALL_TARGET','STATIC_CALL_CANDIDATE'})):
                    frames=p.calls.frames(self.owner(call_id));apis=p.called_api(call_id)&PROCESS_START
                    if not any(self.member_writes(apis,{'root_function':f['root_function'],'execution_address':p.execution_address(call_id,f)}) for f in frames):continue
                if isinstance(call.func,ast.Attribute) and call.func.attr=='join' and isinstance(call.func.value,ast.Constant) and isinstance(call.func.value.value,str):continue
            reason='python_process_sequence_mutation_or_escape_not_expanded'
        self.sequence_safety[origin]=reason;return reason

    def sequences(self,term,guards=()):
        if term['op']=='choice':
            rows=[r for c in term['choices'] for r in self.sequences(c['value'],list(guards)+c.get('conditions',[]))]
            return rows if len(rows)<=32 else [([],list(guards),['python_process_sequence_candidate_budget'],'unknown')]
        if term['op']=='python_sequence':
            reason=self.readonly_sequence(term['source']) if term['container']=='list' else None
            return [(term['args'],list(guards),[reason] if reason else [],'sequence')]
        if term['op'] in {'unknown','symbol','python_dictionary'}:
            return [([],list(guards),[term.get('reason','python_process_argument_shape_not_proven')],'unknown')]
        return [([term],list(guards),[],'single_command_string')]

    def api(self,call,frame):
        p=self.p
        return set().union(*(p.predicates.exact_api(t,frame) for t in p.targets(call,{'CALLS_EXPRESSION'})))

    def setting(self,uid,frame,name,index,default):
        p=self.p;args=p.argument(uid,index,(name,))
        return {'sources':args,'provided':bool(args),'expression':p.predicates.serialized(args[0],frame) if len(args)==1 else
            expression_dag(unknown(uid,'duplicate_process_setting') if args else literal(default))}

    def emit(self,node):
        p=self.p;p.nodes[node['id']]=node;p.added.append(node)
        p.link(node['call'],node['id'],'PROCESS_CONTEXT' if node['kind']=='python_process_invocation' else 'ENVIRONMENT_EFFECT')
        for call in node['call_stack']:p.link(node['id'],call,'PROCESS_CALL_STACK')
        if node['gaps']:p.errors.append({'kind':'python_process_context_unresolved','path':node['path'],'line':node['line'],
            'source':node['call'],'context':node['id'],'reasons':node['gaps'],'required':True})
        slots=([('argument',i,rows) for i,rows in enumerate(node['command_parts'])]+[('cwd',None,node['working_directories'])]
            if node['kind']=='python_process_invocation' else [('environment',None,node['value_candidates'])])
        for role,index,values in slots:
            for value in values:
                if value['path_value']['unresolved']:p.errors.append({'kind':'python_process_value_unresolved','path':node['path'],'line':node['line'],
                    'source':node['call'],'context':node['id'],'role':role,'index':index,'reasons':value['path_value']['unresolved'],
                    'conditions':value['conditions'],'required':True})

    def environment_call(self,uid,frame,api):
        p=self.p;node=self.context(uid,frame,'python_environment_effect',p.style)
        key=p.argument(uid,0,('key',));value=p.argument(uid,1,('value',))
        node.update(api=api,effect='set' if api=='os.putenv' else 'unset' if api=='os.unsetenv' else 'unknown_mapping_effect',
            also_updates_os_environ=False if api in {'os.putenv','os.unsetenv'} else True,
            key_expression=p.predicates.serialized(key[0],frame) if len(key)==1 else expression_dag(unknown(uid,'environment_key_not_bound')),
            value_candidates=self.words(p.evaluate(value[0],frame)) if api=='os.putenv' and len(value)==1 else [])
        node['library_member_writes']=self.member_writes({api},node)
        if node['library_member_writes']:node['gaps'].append('environment_library_member_write_not_resolved')
        if node['effect']=='unknown_mapping_effect':node['gaps'].append('environment_mapping_method_effect_not_expanded')
        self.effects.append(node);self.emit(node)
        for source in key+value:p.link(node['id'],source,'ENVIRONMENT_EFFECT_SOURCE')

    def environment_item(self,uid,frame):
        p=self.p;syntax=p.ast[uid];receivers=p.children(uid,'value');keys=p.children(uid,'slice')
        if len(receivers)!=1 or self.p.predicates.exact_api(receivers[0],frame)!={'os.environ'}:return
        parent=p.parents.get(id(syntax));value=getattr(parent,'value',None) if isinstance(parent,(ast.Assign,ast.AnnAssign)) else None
        source=p.ast_ids.get(id(value)) if value is not None else None
        node=self.context(uid,frame,'python_environment_effect',p.style)
        node.update(api='os.environ.item',effect='unset' if isinstance(syntax.ctx,ast.Del) else 'set',also_updates_os_environ=True,
            key_expression=p.predicates.serialized(keys[0],frame) if len(keys)==1 else expression_dag(unknown(uid,'environment_key_not_bound')),
            value_candidates=self.words(p.evaluate(source,frame)) if source else [])
        node['library_member_writes']=self.member_writes({'os.environ'},node)
        if node['library_member_writes']:node['gaps'].append('environment_mapping_binding_write_not_resolved')
        if node['effect']=='set' and not source:node['gaps'].append('environment_assignment_value_not_bound')
        self.effects.append(node);self.emit(node)
        for target in keys+([source] if source else []):p.link(node['id'],target,'ENVIRONMENT_EFFECT_SOURCE')

    def invocation(self,uid,frame,apis):
        p=self.p;api=next(iter(apis)) if len(apis)==1 else None
        base=self.context(uid,frame,'python_process_invocation',p.style);args=[e for e in p.out[uid] if e['kind']=='CALL_ARGUMENT']
        base['api_candidates']=sorted(apis);base['conditions']=p.predicates.enrich(base['conditions'])
        base['library_member_writes']=self.member_writes(apis,base)
        if base['library_member_writes']:base['gaps'].append('process_library_member_write_not_resolved')
        if any(e.get('spread') for e in args):base['gaps'].append('python_process_argument_expansion_not_bound')
        if not api:base['gaps'].append('python_process_api_not_unique')
        source_targets=[t for t in p.targets(uid,{'STATIC_CALL_TARGET','STATIC_CALL_CANDIDATE'}) if p.nodes[t]['kind'] in {'callable','type'}]
        if source_targets:base['gaps'].append('python_process_api_has_source_replacement')
        base['settings']={name:self.setting(uid,frame,name,index,default) for name,index,default in
            [('shell',8,False),('cwd',9,None),('env',10,None),('executable',2,None),('preexec_fn',6,None)]}
        command=p.argument(uid,0,('args','program','cmd'))
        term=p.evaluate(command[0],frame) if len(command)==1 else unknown(uid,'python_process_command_argument_not_bound')
        variants=self.sequences(term)
        if api=='asyncio.create_subprocess_exec':
            positional=sorted((e for e in args if e.get('keyword') is None),key=lambda e:e['index'])
            variants=[([p.evaluate(e['target'],frame) for e in positional],[],[],'sequence')]
        if api and api.startswith('asyncio.'):
            base['settings']={name:self.setting(uid,frame,name,-1,default) for name,default in [('shell',api.endswith('_shell')),
                ('cwd',None),('env',None),('executable',None),('preexec_fn',None)]}
        cwd=base['settings']['cwd'];base['working_directory_mode']='explicit' if cwd['provided'] else 'inherited'
        if cwd['sources'] and len(cwd['sources'])==1:
            t=p.evaluate(cwd['sources'][0],frame)
            evaluated=evaluate(cwd['expression'],style=p.style)
            if evaluated['known'] and evaluated['value'] is None:base['working_directory_mode']='inherited'
            base['working_directories']=self.words(t) if base['working_directory_mode']=='explicit' else []
        else:base['working_directories']=[]
        for index,(words,guards,gaps,form) in enumerate(variants):
            node={**base,'id':base['id']+':'+str(index),'command_parts':[self.words(t) for t in words],
                'argument_form':form,'conditions':base['conditions']+p.predicates.enrich(guards),'gaps':base['gaps']+gaps,
                'environment_coverage':'source_effect_candidates_runtime_environment_not_observed'}
            try:node['command_expression']=expression_dag(operation('python_sequence',*words,source=uid,container=form))
            except (ValueError,RecursionError):node['command_expression']=expression_dag(unknown(uid,'python_process_expression_budget'));node['gaps'].append('python_process_expression_budget')
            if not words:node['gaps'].append('python_process_command_empty_or_unresolved')
            self.invocations.append(node);self.emit(node)
            for target in command:p.link(node['id'],target,'PROCESS_ARGUMENT_SOURCE')
            for target in sorted({t['source'] for t in node['command_expression']['terms'] if t.get('source') in p.nodes}):
                p.link(node['id'],target,'PROCESS_ARGUMENT_COMPONENT')
            for target in cwd['sources']:p.link(node['id'],target,'PROCESS_WORKING_DIRECTORY')
            for name,setting in node['settings'].items():
                for target in setting['sources']:p.link(node['id'],target,'PROCESS_SETTING_SOURCE',setting=name)
            boundary=uid+':boundary:process_start'
            if boundary in p.nodes:p.link(node['id'],boundary,'PROCESS_BOUNDARY')

    def run(self):
        p=self.p
        for n in list(p.nodes.values()):
            uid=n['id'];syntax=p.ast.get(uid)
            if n['kind']=='call_site':selected=p.called_api(uid)&(PROCESS_START|ENV_CALLS)
            elif isinstance(syntax,ast.Subscript) and isinstance(syntax.ctx,(ast.Store,ast.Del)):selected={'environment_item'}
            else:continue
            if not selected:continue
            for frame in p.calls.frames(self.owner(uid)):
                for style in ('windows','posix'):
                    p.style=style
                    if selected=={'environment_item'}:self.environment_item(uid,frame);continue
                    apis=self.api(uid,frame)
                    if apis&ENV_CALLS:
                        for api in sorted(apis&ENV_CALLS):self.environment_call(uid,frame,api)
                    if selected&PROCESS_START:self.invocation(uid,frame,apis&PROCESS_START)
        for invocation in self.invocations:
            for effect in self.effects:
                if effect['path_style']==invocation['path_style'] and effect['root_function']==invocation['root_function']:
                    order=before(effect,invocation,p.nodes)
                    if order is not False:p.link(invocation['id'],effect['id'],'PROCESS_ENVIRONMENT_EFFECT',ordering='before' if order else 'unresolved')
