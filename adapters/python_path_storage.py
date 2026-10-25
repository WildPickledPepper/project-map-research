"""Positioned writes within native-resolved Python declaration scopes."""
import ast
from collections import defaultdict


class StorageVersions:
    def __init__(self,paths):
        self.paths=paths;self.groups=defaultdict(list)
        for node in paths.nodes.values():
            if node['kind']=='binding':self.groups[(node.get('enclosing_symbol'),node['name'])].append(node['id'])

    def point(self,uid,owner,frame):
        if frame['function']==owner:return uid
        current=frame
        while current['parent']:
            if current['parent']['function']==owner:return current['calls'][-1]
            current=current['parent']
        return None

    def definition_in_progress(self,binding,point):
        target=self.paths.ast.get(binding);value=self.paths.ast.get(point)
        statement=self.paths.parents.get(id(target))
        if not isinstance(statement,(ast.Assign,ast.AnnAssign,ast.NamedExpr,ast.AugAssign)):return False
        while value is not None:
            if value is statement:return True
            value=self.paths.parents.get(id(value))
        return False

    def sources(self,uid,frame):
        paths=self.paths;rows=[];handled=set()
        for edge in paths.out[uid]:
            if edge['kind']!='READS_BINDING' or paths.nodes[edge['target']]['kind']!='binding':
                if edge['kind'] in {'READS_BINDING','VALUE_SOURCE','DEFAULT_VALUE','IMPORTS_SYMBOL'}:rows.append({'uid':edge['target'],'conditions':edge.get('conditions',[])})
                continue
            target=paths.nodes[edge['target']];key=(target.get('enclosing_symbol'),target['name'])
            if key in handled:continue
            handled.add(key);bindings=self.groups[key];point=self.point(uid,key[0],frame)
            if point is None and len(bindings)>1:
                rows.append({'reason':'python_storage_read_context_not_bound','uid':uid});continue
            if point:
                location=paths.nodes[point]
                bindings=[bid for bid in bindings if paths.nodes[bid]['path']==location['path'] and
                    (paths.nodes[bid]['line'],paths.nodes[bid]['column'])<=(location['line'],location['column']) and not self.definition_in_progress(bid,point)]
            available=[]
            for bid in sorted(bindings,key=lambda v:(paths.nodes[v]['line'],paths.nodes[v]['column'])):
                values=[e for e in paths.out[bid] if e['kind']=='VALUE_SOURCE']
                conditional=not values or any(e.get('conditions') for e in values)
                loop=paths.iterations.loop(bid)
                if loop is not None and point and paths.iterations.contains(paths.ast.get(point),loop.body):conditional=False
                if not conditional:available=[]
                else:
                    for prior in available:prior['conditions']=prior['conditions']+[{'kind':'later_storage_assignment_not_selected','binding':bid}]
                available.append({'uid':bid,'conditions':[]})
            if not available:rows.append({'uid':uid,'reason':'python_binding_not_available_at_read'})
            rows.extend(available)
        return rows
