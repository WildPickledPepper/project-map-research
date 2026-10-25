"""Python source facts using the standard AST and unchanged Jedi inference APIs.

AST positions identify entities. Jedi resolves references in an explicit source
root context; inference is evidence about source, never observed execution.
"""
from __future__ import annotations

import ast
from collections import defaultdict
import importlib.metadata
import io
from pathlib import Path, PurePosixPath
import re
import sys
import threading
import tokenize
from urllib.parse import quote

FUNCTIONS=(ast.FunctionDef,ast.AsyncFunctionDef,ast.Lambda)
_JEDI_LOCK=threading.Lock()


def syntax_facts(raw,path):
    """File-local discovery projection; semantic linking runs once in analyze()."""
    encoding,_=tokenize.detect_encoding(io.BytesIO(raw).readline)
    code=raw.decode(encoding).replace('\r\n','\n')
    result={'path':path,'language':'python','status':'parsed','symbols':[],'types':[],'interfaces':[],
            'calls':[],'imports':[],'registrations':[],'resources':[],'entries':[],'diagnostics':[],
            'limits':['file_local_ast_not_semantic_linking','source_only_no_product_execution']}
    try:tree=ast.parse(code,filename=path,type_comments=True)
    except SyntaxError as error:
        result.update(status='syntax_errors',diagnostics=[{'kind':'python_parse_error','line':error.lineno or 1,'message':error.msg}])
        return result
    lines=code.splitlines()
    def loc(node):return {'line':node.lineno,'column':len(lines[node.lineno-1].encode('utf-8')[:node.col_offset].decode('utf-8'))+1,'end_line':node.end_lineno}
    def text(node):return ast.get_source_segment(code,node) or ''
    def walk(node,scope):
        if isinstance(node,(*FUNCTIONS,ast.ClassDef)):
            name=getattr(node,'name',f'<lambda@{node.lineno}:{node.col_offset}>')
            record={'name':name,'qualified_name':'.'.join(scope+[name]),'definition':not path.endswith('.pyi'),
                    'kind':type(node).__name__,**loc(node)}
            result['types' if isinstance(node,ast.ClassDef) else 'symbols'].append(record)
            for decorator in getattr(node,'decorator_list',[]):
                result['registrations'].append({'kind':'decorator_reference','expression':text(decorator),**loc(decorator)})
            scope=scope+[name]
        elif isinstance(node,ast.Call):
            result['calls'].append({'callee':text(node.func),'arguments':[text(a) for a in node.args],**loc(node)})
        elif isinstance(node,(ast.Import,ast.ImportFrom)):
            result['imports'].append({'expression':text(node),'module':getattr(node,'module',None),'level':getattr(node,'level',0),**loc(node)})
        elif isinstance(node,ast.If) and isinstance(node.test,ast.Compare):
            test=node.test
            if isinstance(test.left,ast.Name) and test.left.id=='__name__' and len(test.ops)==1 and isinstance(test.ops[0],ast.Eq) and any(isinstance(c,ast.Constant) and c.value=='__main__' for c in test.comparators):
                result['entries'].append({'kind':'python_main_guard',**loc(node)})
        for child in ast.iter_child_nodes(node):walk(child,scope)
    walk(tree,[])
    return result


class Extractor:
    def __init__(self,root,paths):
        import jedi
        self.jedi=jedi;self.root=Path(root).resolve();self.paths=set(paths)
        self.units={};self.nodes={};self.edges=[];self.diagnostics=[];self.coverage=[]
        self.points=defaultdict(set);self.ast_ids={};self.owners={};self.parents={};self.inference={};self.parameters={}
        self.script_path=None;self.script=None
        self.environment=jedi.create_environment(sys.executable,safe=True)
        for path in sorted(self.paths):
            if PurePosixPath(path).suffix not in {'.py','.pyi'}:continue
            target=(self.root/path).resolve()
            if PurePosixPath(path).is_absolute() or '\\' in path or '..' in PurePosixPath(path).parts or not target.is_relative_to(self.root):
                raise ValueError('Python source must remain inside the supplied export')
            try:
                # tokenize.open honors Python encoding declarations; no import or execution.
                with tokenize.open(target) as stream:code=stream.read().replace('\r\n','\n')
                tree=ast.parse(code,filename=path,type_comments=True)
            except (SyntaxError,UnicodeError,LookupError) as error:
                self.coverage.append({'path':path,'status':'syntax_errors'})
                self.diagnostics.append({'kind':'python_parse_error','path':path,
                    'line':getattr(error,'lineno',None) or 1,'message':str(error)})
                continue
            roots=self.source_roots(path)
            self.units[path]={'code':code,'lines':code.splitlines(keepends=True),'tree':tree,'roots':roots,
                             'path':target}
            uid=self.add(path,tree,'code_module',path,analysis_roots=roots,root_basis='package_ancestors_and_repository',runtime_execution='not_observed')
            self.ast_ids[id(tree)]=uid;self.coverage.append({'path':path,'status':'parsed'})
            self.index(path,tree,uid,[])

    def source_roots(self,path):
        parent=PurePosixPath(path).parent
        while (parent/'__init__.py').as_posix() in self.paths:parent=parent.parent
        roots=[parent.as_posix()]
        if '.' not in roots:roots.append('.')
        return roots

    def location(self,path,node,end=False):
        line=getattr(node,'end_lineno' if end else 'lineno',1) or 1
        offset=getattr(node,'end_col_offset' if end else 'col_offset',0) or 0
        rows=self.units[path]['lines'];value=rows[line-1] if line<=len(rows) else ''
        column=len(value.encode('utf-8')[:offset].decode('utf-8'))
        return {'path':path,'line':line,'column':column+1}

    def spelling(self,path,node):
        return ast.get_source_segment(self.units[path]['code'],node) or ''

    def add(self,path,node,kind,name,**extra):
        loc=self.location(path,node);end=self.location(path,node,True)
        uid='py:'+quote(path,safe='/')+f":{kind}:{loc['line']}:{loc['column']}:{end['line']}:{end['column']}"
        if uid not in self.nodes:
            self.nodes[uid]={'id':uid,'kind':kind,**loc,'end_line':end['line'],'end_column':end['column'],
                'name':name or '<expression>','language':'python','evidence_kind':'python_ast',**extra}
        return uid

    def edge(self,source,target,kind,node=None,path=None,status='source_relation',**extra):
        if source==target:return
        evidence=[self.location(path,node)] if node is not None else []
        self.edges.append({'source':source,'target':target,'kind':kind,'status':status,
                           'evidence':evidence,'runtime_execution':'not_observed',**extra})

    def point(self,path,node,uid,name=None):
        loc=self.location(path,node);self.points[(path,loc['line'],loc['column']-1)].add(uid)
        # Jedi returns the identifier token, while AST declarations start at def/class.
        if name and isinstance(node,(*FUNCTIONS,ast.ClassDef)) and not isinstance(node,ast.Lambda):
            line=self.units[path]['lines'][node.lineno-1]
            match=re.search(r'\b(?:def|class)\s+('+re.escape(name)+r')\b',line)
            if match:self.points[(path,node.lineno,match.start(1))].add(uid)
        if isinstance(node,ast.Attribute):
            end=self.location(path,node,True)
            self.points[(path,end['line'],end['column']-1-len(node.attr))].add(uid)

    def index(self,path,node,owner,scope):
        self.owners[id(node)]=owner
        if isinstance(node,(*FUNCTIONS,ast.ClassDef)):
            name=getattr(node,'name',f'<lambda@{node.lineno}:{node.col_offset}>')
            uid=self.add(path,node,'type' if isinstance(node,ast.ClassDef) else 'callable','.'.join(scope+[name]),
                definition=not path.endswith('.pyi'),asynchronous=isinstance(node,ast.AsyncFunctionDef),
                decorators=[self.spelling(path,n) for n in getattr(node,'decorator_list',[])])
            self.ast_ids[id(node)]=uid;self.point(path,node,uid,name)
            self.edge(owner,uid,'CONTAINS_SYMBOL',node,path)
            self.nodes[uid]['enclosing_symbol']=owner
            if isinstance(node,FUNCTIONS):
                args=node.args;parameters=[*args.posonlyargs,*args.args,*args.kwonlyargs]
                if args.vararg:parameters.append(args.vararg)
                if args.kwarg:parameters.append(args.kwarg)
                self.nodes[uid]['parameters']=[a.arg for a in parameters]
                self.parameters[uid]=[]
                for index,arg in enumerate(parameters):
                    kind=('positional_only' if arg in args.posonlyargs else 'positional_or_keyword' if arg in args.args else
                          'keyword_only' if arg in args.kwonlyargs else 'var_positional' if arg is args.vararg else 'var_keyword')
                    pid=self.add(path,arg,'parameter',arg.arg,parameter_index=index,
                        parameter_kind=kind,
                        annotation=self.spelling(path,arg.annotation) if arg.annotation else None)
                    self.parameters[uid].append(pid)
                    self.ast_ids[id(arg)]=pid;self.point(path,arg,pid)
                    self.edge(uid,pid,'HAS_PARAMETER',arg,path)
            for field,value in ast.iter_fields(node):
                for child in value if isinstance(value,list) else [value]:
                    if not isinstance(child,ast.AST):continue
                    self.parents[id(child)]=node
                    in_body=field=='body'
                    self.index(path,child,uid if in_body else owner,scope+[name] if in_body else scope)
            return
        if isinstance(node,(ast.Name,ast.Attribute)) and isinstance(node.ctx,ast.Store):
            uid=self.add(path,node,'binding',self.spelling(path,node),enclosing_symbol=owner)
            self.ast_ids[id(node)]=uid;self.point(path,node,uid)
            self.edge(owner,uid,'WRITES_BINDING',node,path)
        if isinstance(node,ast.alias):
            uid=self.add(path,node,'module_reference',node.asname or node.name,imported_name=node.name,
                         bound_name=node.asname or node.name.split('.')[0],aliased=bool(node.asname),
                         resolution='unresolved',reason='module_or_symbol_not_in_export')
            self.ast_ids[id(node)]=uid
            # An import alias's definition is its final token.
            end=self.location(path,node,True);name=node.asname or node.name.split('.')[0]
            column=end['column']-1-len(name) if node.asname else self.location(path,node)['column']-1
            self.points[(path,end['line'],column)].add(uid)
            self.edge(self.ast_ids[id(self.units[path]['tree'])],uid,'CONTAINS_IMPORT',node,path)
        for child in ast.iter_child_nodes(node):
            self.parents[id(child)]=node;self.index(path,child,owner,scope)

    def infer(self,path,node,method='infer'):
        pos=self.location(path,node,True);key=(path,pos['line'],pos['column'],method)
        if key not in self.inference:
            try:
                if self.script_path!=path:
                    unit=self.units[path]
                    project=self.jedi.Project(self.root,sys_path=[str(self.root/r) for r in unit['roots']],
                                              smart_sys_path=False,load_unsafe_extensions=False)
                    self.script=self.jedi.Script(unit['code'],path=unit['path'],project=project,environment=self.environment)
                    self.script_path=path
                script=self.script
                values=getattr(script,method)(pos['line'],pos['column']-1)
                records=[]
                for value in values:
                    target=value.module_path.resolve() if value.module_path else None
                    relative=target.relative_to(self.root).as_posix() if target and target.is_relative_to(self.root) else None
                    record={'path':relative,'line':value.line,'column':value.column,'type':value.type,
                                    'name':value.name,'qualified_name':value.full_name,
                                    'input':bool(relative in self.units),
                                    'origin_scope':'parsed_input' if relative in self.units else 'unparsed_or_unselected_export' if relative else 'external_or_builtin'}
                    if method=='infer' and record['input'] and value.type=='function':
                        record['signature_parameters']=[[p.name for p in s.params] for s in value.get_signatures()]
                    records.append(record)
                self.inference[key]=records
            except Exception as error:
                self.diagnostics.append({'kind':'python_inference_error',**self.location(path,node),
                                         'operation':method,'error_type':type(error).__name__,'message':str(error)})
                self.inference[key]=[]
        return self.inference[key]

    def targets(self,records,kinds=None):
        return sorted({uid for r in records if r['input'] for uid in self.points.get((r['path'],r['line'],r['column']),())
                       if kinds is None or self.nodes[uid]['kind'] in kinds})

    def value(self,path,node):
        if id(node) in self.ast_ids:return self.ast_ids[id(node)]
        if isinstance(node,ast.Call):
            uid=self.add(path,node,'call_site',self.spelling(path,node.func),
                arguments=[self.spelling(path,a) for a in node.args],
                keyword_arguments=[{'name':k.arg,'expression':self.spelling(path,k.value)} for k in node.keywords],
                resolution='unresolved',reason='no_input_callable',conditions=self.conditions(path,node))
        else:
            spelling=self.spelling(path,node)
            uid=self.add(path,node,'value',spelling[:1000],expression_kind=type(node).__name__,
                         expression_truncated=len(spelling)>1000,conditions=self.conditions(path,node))
            if isinstance(node,ast.Constant):
                value=node.value
                self.nodes[uid].update(literal=value if isinstance(value,(str,int,bool)) or value is None else repr(value),literal_type=type(value).__name__)
            elif isinstance(node,ast.Name):self.nodes[uid]['identifier']=node.id
            elif isinstance(node,ast.Attribute):self.nodes[uid]['member']=node.attr
        self.ast_ids[id(node)]=uid
        if isinstance(node,ast.Call):
            owner=self.owners[id(node)];self.edge(owner,uid,'OBSERVES_CALL',node,path)
            self.edge(uid,self.value(path,node.func),'CALLS_EXPRESSION',node.func,path)
            records=self.infer(path,node.func);targets=self.targets(records,{'callable','type'})
            self.nodes[uid]['inference']=records
            if targets:
                self.nodes[uid]['resolution']='inferred_unique' if len(targets)==1 else 'candidate'
                self.nodes[uid].pop('reason',None)
                for target in targets:
                    kind='STATIC_CALL_TARGET' if len(targets)==1 else 'STATIC_CALL_CANDIDATE'
                    self.edge(uid,target,kind,node,path,status='inferred' if len(targets)==1 else 'candidate',basis='jedi_infer',
                              target_kind=self.nodes[target]['kind'])
            else:
                self.nodes[uid]['reason']=('external_or_builtin_callable' if records and all(r['origin_scope']=='external_or_builtin' for r in records) else
                    'input_declaration_not_indexed_or_parse_error' if any(r['origin_scope']!='external_or_builtin' for r in records) else 'no_input_callable_or_dynamic_binding')
            for index,arg in enumerate(node.args):
                aid=self.value(path,arg);self.edge(uid,aid,'CALL_ARGUMENT',arg,path,index=index,keyword=None,spread=isinstance(arg,ast.Starred))
                self.callbacks(path,uid,arg,index=index)
            for keyword in node.keywords:
                aid=self.value(path,keyword.value);self.edge(uid,aid,'CALL_ARGUMENT',keyword.value,path,keyword=keyword.arg,spread=keyword.arg is None)
                self.callbacks(path,uid,keyword.value,keyword=keyword.arg)
            self.bind_arguments(path,node,uid,targets,records)
        else:
            if isinstance(node,(ast.Name,ast.Attribute)) and isinstance(node.ctx,ast.Load):
                records=self.infer(path,node,'goto');targets=self.targets(records)
                self.nodes[uid].update(resolution='source_binding' if targets else 'unresolved',binding_candidates=targets)
                if not targets:self.nodes[uid]['reason']='binding_not_in_export_or_dynamic'
                for target in targets:self.edge(uid,target,'READS_BINDING',node,path,status='candidate' if len(targets)>1 else 'source_relation')
            for field,value in ast.iter_fields(node):
                for index,child in enumerate(value if isinstance(value,list) else [value]):
                    if isinstance(child,ast.expr):
                        self.edge(uid,self.value(path,child),'VALUE_COMPONENT',child,path,field=field,index=index)
        return uid

    def bind_arguments(self,path,node,uid,targets,records):
        if len(targets)!=1 or self.nodes[targets[0]]['kind']!='callable':return
        if any(isinstance(a,ast.Starred) for a in node.args) or any(k.arg is None for k in node.keywords):
            self.nodes[uid]['argument_binding_status']='spread_requires_value_expansion';return
        signatures={tuple(s) for r in records for s in r.get('signature_parameters',[])}
        if len(signatures)!=1:
            self.nodes[uid]['argument_binding_status']='signature_not_unique';return
        names=next(iter(signatures));parameters={self.nodes[p]['name']:p for p in self.parameters.get(targets[0],[])}
        positional=[name for name in names if name in parameters and self.nodes[parameters[name]]['parameter_kind'] in {'positional_only','positional_or_keyword'}]
        self.nodes[uid]['argument_binding_status']='explicit_arguments_mapped'
        for index,arg in enumerate(node.args):
            if index>=len(positional):
                self.nodes[uid]['argument_binding_status']='varargs_or_arity_requires_expansion';continue
            self.edge(self.value(path,arg),parameters[positional[index]],'BINDS_ARGUMENT',arg,path,status='inferred',call=uid,index=index)
        for keyword in node.keywords:
            pid=parameters.get(keyword.arg)
            if pid and self.nodes[pid]['parameter_kind']!='positional_only':
                self.edge(self.value(path,keyword.value),pid,'BINDS_ARGUMENT',keyword.value,path,status='inferred',call=uid,keyword=keyword.arg)
            else:self.nodes[uid]['argument_binding_status']='kwargs_or_invalid_keyword_requires_expansion'

    def callbacks(self,path,call,arg,**extra):
        if not isinstance(arg,(ast.Name,ast.Attribute,ast.Lambda)):return
        targets=[self.ast_ids[id(arg)]] if isinstance(arg,ast.Lambda) else self.targets(self.infer(path,arg),{'callable'})
        for target in targets:self.edge(call,target,'PASSES_CALLBACK',arg,path,status='value_reference',**extra)

    def conditions(self,path,node):
        rows=[];child=node
        while id(child) in self.parents:
            parent=self.parents[id(child)]
            if isinstance(parent,(ast.If,ast.IfExp,ast.While)):
                value=self.spelling(path,parent.test)
                if isinstance(parent,ast.IfExp):branch='true' if child is parent.body else 'false' if child is parent.orelse else 'test'
                else:branch='body' if child in parent.body else 'else' if child in parent.orelse else 'test'
                rows.append({'kind':type(parent).__name__,'expression':value,'branch':branch,**self.location(path,parent)})
            elif isinstance(parent,ast.ExceptHandler):
                rows.append({'kind':'exception','expression':self.spelling(path,parent.type) if parent.type else 'BaseException',**self.location(path,parent)})
            child=parent
        return rows

    def build(self,emit=None):
        for path,unit in self.units.items():
            for node in ast.walk(unit['tree']):
                if isinstance(node,ast.expr):self.value(path,node)
                if isinstance(node,(ast.Assign,ast.AnnAssign,ast.NamedExpr)):
                    value=node.value
                    if value is not None:
                        for target in node.targets if isinstance(node,ast.Assign) else [node.target]:
                            # Tuple unpacking requires per-element correspondence; don't alias each element to the whole RHS.
                            if isinstance(target,(ast.Name,ast.Attribute)):
                                self.edge(self.ast_ids[id(target)],self.value(path,value),'VALUE_SOURCE',node,path,conditions=self.conditions(path,node))
                elif isinstance(node,ast.Return) and node.value:
                    self.edge(self.owners[id(node)],self.value(path,node.value),'RETURNS_VALUE',node,path)
                elif isinstance(node,ast.Await):
                    self.edge(self.owners[id(node)],self.value(path,node.value),'AWAITS',node,path)
                elif isinstance(node,ast.withitem) and isinstance(node.optional_vars,(ast.Name,ast.Attribute)):
                    self.edge(self.ast_ids[id(node.optional_vars)],self.value(path,node.context_expr),'CONTEXT_VALUE_SOURCE',node.context_expr,path,
                              limitation='context_manager_enter_may_transform_value')
                elif isinstance(node,(ast.Import,ast.ImportFrom)):
                    for alias in node.names:
                        uid=self.ast_ids[id(alias)];record=self.nodes[uid]
                        record.update(module=getattr(node,'module',None),level=getattr(node,'level',0),syntax=type(node).__name__)
                        results=self.infer(path,alias)
                        targets=self.targets(results)
                        module_targets={self.ast_ids[id(self.units[r['path']]['tree'])] for r in results if r['input']}
                        for target in sorted(module_targets):self.edge(uid,target,'IMPORTS_MODULE',alias,path)
                        for target in targets:self.edge(uid,target,'IMPORTS_SYMBOL',alias,path)
                        if module_targets:record.update(resolution='source_module_or_symbol');record.pop('reason',None)
                        record['inference']=results
                elif isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                    uid=self.ast_ids[id(node)]
                    for decorator in node.decorator_list:
                        self.edge(uid,self.value(path,decorator),'USES_DECORATOR',decorator,path,status='source_relation')
                    if isinstance(node,ast.ClassDef):
                        for base in node.bases:
                            for target in self.targets(self.infer(path,base),{'type'}):self.edge(uid,target,'INHERITS',base,path,status='inferred')
                    else:
                        positional=[*node.args.posonlyargs,*node.args.args]
                        defaults=list(zip(positional[-len(node.args.defaults):],node.args.defaults)) if node.args.defaults else []
                        defaults.extend((a,d) for a,d in zip(node.args.kwonlyargs,node.args.kw_defaults) if d is not None)
                        for parameter,default in defaults:
                            self.edge(self.ast_ids[id(parameter)],self.value(path,default),'DEFAULT_VALUE',default,path)
            if emit:emit({'path':path,'nodes':len(self.nodes),'edges':len(self.edges)})
        return {'schema_version':1,'extractor':'python_ast_jedi','version':'0.1.0',
            'components':{'jedi':self.jedi.__version__,'parso':importlib.metadata.version('parso'),'python':sys.version.split()[0]},
            'nodes':list(self.nodes.values()),'edges':self.edges,'diagnostics':self.diagnostics,'coverage':self.coverage,
            'limits':['inference_is_not_runtime_execution','explicit_derived_source_roots_not_product_environment',
                      'dynamic_imports_and_runtime_monkey_patching_not_resolved','tuple_unpacking_and_star_argument_binding_not_expanded',
                      'missing_external_packages_remain_boundary_references']}


def analyze(root,paths,*,emit=None):
    import jedi
    # Consume one Script at a time against immutable exported files. All returned
    # definitions are projected immediately; no live Name objects cross files.
    with _JEDI_LOCK:
        previous=jedi.settings.fast_parser;jedi.settings.fast_parser=True
        try:return Extractor(root,paths).build(emit)
        finally:jedi.settings.fast_parser=previous
