"""Bounded source-call frames from native Python target and argument facts."""
import json
from collections import defaultdict
from urllib.parse import quote


class CallContexts:
    def __init__(self,paths,max_depth=12,max_contexts=32):
        self.paths=paths;self.nodes=paths.nodes;self.out=paths.out
        self.max_depth=max_depth;self.max_contexts=max_contexts
        self.owners={};self.parameter_owners={};self.callers=defaultdict(list);self.bindings=defaultdict(list)
        self.modules={n['path']:n['id'] for n in self.nodes.values() if n['kind']=='code_module'}
        self.registry={}
        for edge in paths.facts['edges']:
            if edge['kind']=='OBSERVES_CALL':self.owners[edge['target']]=edge['source']
            elif edge['kind']=='HAS_PARAMETER':self.parameter_owners[edge['target']]=edge['source']
            elif edge['kind'] in {'STATIC_CALL_TARGET','STATIC_CALL_CANDIDATE'}:self.callers[edge['target']].append(edge['source'])
            elif edge['kind']=='BINDS_ARGUMENT':self.bindings[edge['call']].append(edge)

    def root(self,function,reason=None):
        frame={'function':function,'root_function':function,'calls':[],'arguments':{},'parent':None,
            'root_basis':'no_resolved_static_callers','conditions':[],'gaps':[reason] if reason else [],'key':(function,())}
        self.registry[self.identity(frame)]=frame;return frame

    def scope(self,owner,frame):
        current=frame
        while current:
            if current['function']==owner:return current
            current=current['parent']
        return self.root(owner) if owner in self.nodes else frame

    def owner(self,uid):return self.owners.get(uid,self.modules.get(self.nodes[uid]['path']))

    def parameters(self,function):
        return [e['target'] for e in self.out[function] if e['kind']=='HAS_PARAMETER']

    def descend(self,call,function,parent):
        conditions=parent['conditions']+[{'kind':'source_call_context','call':call,'target':function}]+self.nodes[call].get('conditions',[])+self.paths.guard_conditions(call,parent)
        child={'function':function,'root_function':parent['root_function'],'calls':parent['calls']+[call],
            'arguments':{},'parent':parent,'root_basis':parent['root_basis'],'conditions':conditions,'gaps':list(parent['gaps'])}
        child['key']=(function,tuple(child['calls']))
        if len(child['calls'])>self.max_depth:child['gaps'].append('python_path_call_depth_budget')
        ancestor=parent
        while ancestor:
            if ancestor['function']==function:
                child['gaps'].append('recursive_python_path_call');break
            ancestor=ancestor['parent']
        status=self.nodes[call].get('argument_binding_status')
        if status!='explicit_arguments_mapped':child['gaps'].append('python_path_call_arguments_not_explicitly_bound')
        for edge in self.bindings[call]:
            if edge['target'] not in self.parameters(function):continue
            pid=edge['target']
            if pid in child['arguments']:child['gaps'].append('duplicate_python_path_argument_binding')
            child['arguments'][pid]={'uid':edge['source'],'frame':parent,'basis':'native_call_argument_binding','call':call}
        target=self.nodes[function];enclosing=self.nodes.get(target.get('enclosing_symbol'),{})
        for pid in self.parameters(function):
            if pid in child['arguments']:continue
            parameter=self.nodes[pid];defaults=[e['target'] for e in self.out[pid] if e['kind']=='DEFAULT_VALUE']
            if len(defaults)==1:
                # Defaults are captured at definition time. Only literal values
                # have no unresolved definition-time environment in this pass.
                if self.nodes[defaults[0]].get('expression_kind')=='Constant':
                    child['arguments'][pid]={'uid':defaults[0],'frame':self.root(target['enclosing_symbol']),
                        'basis':'literal_default_argument','call':call}
                else:child['arguments'][pid]={'reason':'python_default_definition_context_not_expanded'}
            elif parameter['parameter_kind'].startswith('var_'):
                child['arguments'][pid]={'reason':'python_variadic_path_argument_not_expanded'}
            elif enclosing.get('kind')=='type' and parameter['parameter_index']==0:
                child['arguments'][pid]={'reason':'python_implicit_receiver_identity_not_expanded'}
            else:child['gaps'].append('missing_python_path_call_argument')
        self.registry[self.identity(child)]=child;return child

    def frames(self,function,seen=()):
        if function is None:return []
        if function in seen:return [self.root(function,'recursive_python_path_caller_context')]
        if len(seen)>=self.max_depth:return [self.root(function,'python_path_caller_depth_budget')]
        calls=sorted(set(self.callers[function]))
        if not calls:return [self.root(function)]
        rows=[]
        for call in calls:
            for parent in self.frames(self.owner(call),seen+(function,)):
                if len(rows)>=self.max_contexts:return rows+[self.root(function,'python_path_caller_context_budget')]
                rows.append(self.descend(call,function,parent))
        return rows

    def parameter(self,uid,frame):
        owner=self.parameter_owners.get(uid);current=frame
        while current and current['function']!=owner:current=current['parent']
        if current is None:return {'reason':'python_captured_parameter_context_not_available'}
        if uid in current['arguments']:return current['arguments'][uid]
        if not current['calls']:return {'symbol':uid}
        return {'reason':'python_path_parameter_binding_missing'}

    @staticmethod
    def identity(frame):
        return 'py:path-context:'+quote(json.dumps([frame['root_function'],frame['function'],frame['calls'],frame['gaps']],separators=(',',':')),safe='')
