"""Loop value origins from native binding identities and import-bound iterators."""
import ast
from urllib.parse import quote
from adapters.path_values import unknown


class Iterations:
    def __init__(self,paths):self.paths=paths;self.bindings={}

    def loop(self,binding):
        target=self.paths.ast.get(binding);parent=self.paths.parents.get(id(target))
        while isinstance(parent,(ast.Tuple,ast.List,ast.Starred)):
            target=parent;parent=self.paths.parents.get(id(target))
        return parent if isinstance(parent,(ast.For,ast.AsyncFor)) and parent.target is target else None

    def contains(self,node,body):
        while node is not None:
            if node in body:return True
            node=self.paths.parents.get(id(node))
        return False

    def value(self,binding,read,frame,seen):
        paths=self.paths;loop=self.loop(binding)
        if loop is None:return None
        owner=paths.nodes[binding].get('enclosing_symbol');point=paths.storage.point(read,owner,frame)
        if point is None or not self.contains(paths.ast.get(point),loop.body):return unknown(binding,'python_loop_binding_read_outside_iteration')
        if isinstance(loop,ast.AsyncFor) or not isinstance(loop.target,ast.Name):return unknown(binding,'python_iteration_binding_projection_not_expanded')
        iterator=paths.ast_ids.get(id(loop.iter))
        if iterator is None:return unknown(binding,'python_iteration_source_not_indexed')
        if isinstance(loop.iter,(ast.List,ast.Tuple)):
            items=paths.children(iterator,'elts')
            if len(items)>32:return unknown(binding,'python_literal_iteration_budget')
            variable=binding+':'+paths.calls.identity(frame)
            return {'op':'choice','source':binding,'choices':[{'value':paths.evaluate(item,frame,seen),
                'conditions':[{'kind':'literal_iteration_item','variable':variable,'index':index,'source':item}]} for index,item in enumerate(items)]}
        apis=set().union(*(paths.context_api(t,frame) for t in paths.targets(iterator,{'CALLS_EXPRESSION'})))
        if 'os.listdir' not in apis:return unknown(binding,'python_iteration_source_not_modeled')
        args=paths.argument(iterator,0,('path',))
        if len(args)!=1:return unknown(binding,'python_listdir_default_cwd_or_argument_shape_not_bound')
        if any(e.get('spread') for e in paths.out[iterator] if e['kind']=='CALL_ARGUMENT'):return unknown(binding,'python_listdir_argument_expansion_not_bound')
        owner_frame=frame
        while owner_frame['function']!=owner and owner_frame['parent']:owner_frame=owner_frame['parent']
        if owner_frame['function']!=owner:return unknown(binding,'python_iteration_creation_context_not_bound')
        context=paths.calls.identity(owner_frame);uid=binding+':directory-iteration:'+quote(context,safe='')+':'+paths.style
        if uid not in paths.nodes:
            source=paths.nodes[binding]
            row={'id':uid,'kind':'path_iteration','name':source['name'],'path':source['path'],'line':loop.lineno,
                'column':source['column'],'language':'python','family':'directory_enumeration','binding':binding,
                'iterator':iterator,'directory':args[0],'call_context':context,'path_style':paths.style,
                'api_candidates':['os.listdir'],'runtime_execution':'not_observed'}
            paths.nodes[uid]=row;paths.added.append(row)
            paths.link(uid,binding,'ITERATION_BINDING');paths.link(uid,iterator,'ITERATION_SOURCE')
            paths.link(uid,args[0],'ITERATION_DIRECTORY')
            for call in owner_frame['calls']:paths.link(uid,call,'ITERATION_CALL_CONTEXT')
        return {'op':'entry_name','source':binding,'variable':binding+':'+context,'iteration':uid,
            'name':paths.nodes[binding]['name'],'args':[paths.evaluate(args[0],owner_frame,seen)]}
