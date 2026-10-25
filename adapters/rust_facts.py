"""Positioned Rust source facts over the existing Tree-sitter Rust grammar.

Syntax records are separate from native semantic navigation. No spelling-based
global call resolution or analyzed-code execution is performed here.
"""
from collections import defaultdict
from pathlib import PurePosixPath
from urllib.parse import quote

from adapters.syntax_supplement import walk,parents,text

CALLABLES={'function_item','function_signature_item','closure_expression'}
TYPES={'struct_item','enum_item','trait_item','type_item'}


def conditions(node):
    result=[]
    for current in [node,*parents(node)]:
        sibling=current.prev_named_sibling
        while sibling is not None and sibling.type in {'attribute_item','line_comment','block_comment'}:
            if sibling.type=='attribute_item' and any(c in text(sibling) for c in ('cfg(', 'cfg_attr(')):
                result.append({'kind':'rust_attribute','expression':text(sibling),'line':sibling.start_point[0]+1})
            sibling=sibling.prev_named_sibling
        if current.type=='if_expression':
            predicate=current.child_by_field_name('condition');yes=current.child_by_field_name('consequence')
            if predicate is not None and yes is not None and node.start_byte>=yes.start_byte:
                result.append({'kind':'rust_if','expression':text(predicate),
                    'polarity':node.end_byte<=yes.end_byte,'line':predicate.start_point[0]+1})
        if current.type=='match_arm':
            pattern=current.child_by_field_name('pattern')
            result.append({'kind':'rust_match_arm','expression':text(pattern),'line':current.start_point[0]+1})
    unique={str(value):value for value in result}
    return list(unique.values())


def pattern_names(node):
    if node is None:return []
    if node.type in {'identifier','field_identifier','shorthand_field_identifier','self'}:return [node]
    blocked={c.id for key in ('type','path','name') if (c:=node.child_by_field_name(key)) is not None}
    return [name for child in node.named_children if child.id not in blocked for name in pattern_names(child)]


def callee_token(node):
    current=node.child_by_field_name('function') if node.type=='call_expression' else node
    while current is not None and current.type not in {'identifier','field_identifier','self','type_identifier'}:
        current=current.child_by_field_name('field') or current.child_by_field_name('name') or current.child_by_field_name('function')
    return current


class Extractor:
    def __init__(self,sources,parser):
        self.parser=parser;self.units={};self.nodes={};self.edges=[];self.diagnostics=[];self.coverage=[]
        self.ids={};self.syntax={};self.points=defaultdict(set);self.parameters=defaultdict(list);self.references={}
        for path,raw in sorted(sources.items()):
            if PurePosixPath(path).is_absolute() or '\\' in path or '..' in PurePosixPath(path).parts:
                raise ValueError('Rust source paths must remain inside the export')
            try:raw.decode('utf-8')
            except UnicodeError:
                self.coverage.append({'path':path,'status':'invalid_encoding'})
                self.diagnostics.append({'path':path,'kind':'rust_encoding_error','required':True});continue
            tree=parser.parse(raw);self.units[path]={'raw':raw,'tree':tree,'lines':raw.splitlines(keepends=True)}
            self.add(path,tree.root_node,'code_module',path,declaration=tree.root_node)
            self.coverage.append({'path':path,'status':'syntax_errors' if tree.root_node.has_error else 'parsed'})
            for node in walk(tree.root_node):
                if node.type=='ERROR' or node.is_missing:
                    self.diagnostics.append({'path':path,'kind':'rust_syntax_error','line':node.start_point[0]+1,'required':True})
        for path,unit in self.units.items():self.declarations(path,unit['tree'].root_node)
        for path,unit in self.units.items():self.relations(path,unit['tree'].root_node)

    def position(self,path,node):
        before=self.units[path]['lines'][node.start_point[0]][:node.start_point[1]] if self.units[path]['lines'] else b''
        return {'line':node.start_point[0],'character':len(before.decode('utf-8').encode('utf-16-le'))//2}

    def add(self,path,node,kind,name,*,declaration=None,**fields):
        key=(path,node.id)
        uid=self.ids.get(key)
        if uid is not None:return uid
        uid=f'rust:{quote(path,safe="/")}:{kind}:{node.start_byte}:{node.end_byte}'
        before=self.units[path]['lines'][node.start_point[0]][:node.start_point[1]] if self.units[path]['lines'] else b''
        self.nodes[uid]={'id':uid,'kind':kind,'name':name or kind,'path':path,'line':node.start_point[0]+1,
            'column':len(before.decode('utf-8'))+1,'start_byte':node.start_byte,'end_byte':node.end_byte,
            'language':'rust','syntax':node.type,'conditions':conditions(node),'runtime_execution':'not_observed',**fields}
        self.ids[key]=uid;self.syntax[uid]=(path,node)
        if declaration is not None:
            pos=self.position(path,declaration)
            self.points[(path,pos['line'],pos['character'])].add(uid)
        return uid

    def edge(self,source,target,kind,node,path,**fields):
        self.edges.append({'source':source,'target':target,'kind':kind,'status':'source_relation',
            'evidence':[{'path':path,'line':node.start_point[0]+1}],
            'runtime_execution':'not_observed',**fields})

    def owner(self,path,node,*,callable_only=False):
        return next((self.ids[(path,a.id)] for a in parents(node) if (path,a.id) in self.ids and
            (a.type in CALLABLES if callable_only else a.type in CALLABLES|TYPES|{'source_file','mod_item','impl_item'})),
            self.ids[(path,self.units[path]['tree'].root_node.id)])

    def qualified(self,node,name):
        scopes=[]
        for ancestor in reversed(list(parents(node))):
            if ancestor.type in CALLABLES|TYPES|{'mod_item','impl_item'}:
                named=ancestor.child_by_field_name('type' if ancestor.type=='impl_item' else 'name')
                scopes.append(text(named) or f'<closure@{ancestor.start_point[0]+1}:{ancestor.start_point[1]+1}>')
        return '::'.join([*scopes,name])

    def declarations(self,path,root):
        for node in walk(root):
            name=node.child_by_field_name('name')
            if node.type in CALLABLES|TYPES|{'impl_item','mod_item'}:
                kind='callable' if node.type in CALLABLES else 'type' if node.type in TYPES else 'implementation' if node.type=='impl_item' else 'module_reference' if node.child_by_field_name('body') is None else 'module'
                if node.type=='impl_item':name=node.child_by_field_name('type')
                label=text(name) or f'<closure@{node.start_point[0]+1}:{node.start_point[1]+1}>'
                uid=self.add(path,node,kind,self.qualified(node,label),declaration=name or node,
                    simple_name=label,definition=node.type!='function_signature_item',
                    resolution='requires_native_context' if kind=='module_reference' else 'source_declaration')
                if node.type!='source_file':self.edge(self.owner(path,node),uid,'CONTAINS_SYMBOL',node,path)
                if node.type in CALLABLES:
                    self.nodes[uid]['trait_signature']=node.type=='function_signature_item'
                    params=node.child_by_field_name('parameters')
                    for i,param in enumerate(params.named_children if params else []):
                        pattern=param.child_by_field_name('pattern') or (param if param.type in {'identifier','self_parameter'} else None)
                        for named in pattern_names(pattern):
                            parameter=self.add(path,named,'parameter',text(named),declaration=named,index=i,
                                declared_type=text(param.child_by_field_name('type')),self_parameter=param.type=='self_parameter')
                            self.parameters[uid].append(parameter)
                            self.edge(uid,parameter,'HAS_PARAMETER',named,path,index=i)
            elif node.type in {'let_declaration','const_item','static_item','field_declaration'}:
                pattern=node.child_by_field_name('pattern') or node.child_by_field_name('name')
                for named in pattern_names(pattern):
                    uid=self.add(path,named,'binding',text(named),declaration=named,
                        declared_type=text(node.child_by_field_name('type')),binding_kind=node.type,
                        pattern=text(pattern),pattern_projection=pattern is not None and pattern.type!='identifier')
                    self.edge(self.owner(path,node),uid,'DECLARES_BINDING',named,path)
            elif node.type=='use_declaration':
                self.imports(path,node,node.child_by_field_name('argument'),'')

    def imports(self,path,declaration,node,prefix):
        if node is None:return
        if node.type=='use_list':
            for child in node.named_children:self.imports(path,declaration,child,prefix)
            return
        if node.type=='scoped_use_list':
            base=text(node.child_by_field_name('path'));base='::'.join(p for p in (prefix,base) if p)
            self.imports(path,declaration,node.child_by_field_name('list'),base);return
        alias=node.child_by_field_name('alias') if node.type=='use_as_clause' else None
        target=node.child_by_field_name('path') if alias is not None else node
        token=callee_token(target)
        if token is None:
            token=next((c for c in reversed(node.named_children) if c.type in {'self','super','crate','identifier'}),None)
        if token is None:
            uid=self.add(path,node,'module_reference',text(node),resolution='wildcard_or_module_requires_native_context')
        else:
            expression='::'.join(p for p in (prefix,text(target)) if p)
            uid=self.add(path,node,'module_reference',text(alias) if alias is not None else text(token),
                module_expression=expression,resolution='requires_native_context')
            self.references[uid]=(path,token)
        self.edge(self.owner(path,declaration),uid,'CONTAINS_IMPORT',node,path)

    def value(self,path,node):
        if node is None:return None
        if (path,node.id) in self.ids:return self.ids[(path,node.id)]
        kind='call_site' if node.type=='call_expression' else 'macro_site' if node.type=='macro_invocation' else 'value'
        function=node.child_by_field_name('function')
        uid=self.add(path,node,kind,text(function) if function is not None else text(node)[:180],
            expression=text(node),resolution='requires_native_context' if kind!='value' else 'source_expression')
        if kind=='call_site':
            self.edge(self.owner(path,node,callable_only=True),uid,'OBSERVES_CALL',node,path)
            self.nodes[uid]['arguments']=[]
            arguments=node.child_by_field_name('arguments')
            for i,argument in enumerate(arguments.named_children if arguments else []):
                source=self.value(path,argument);self.nodes[uid]['arguments'].append(source)
                self.edge(uid,source,'CALL_ARGUMENT',argument,path,index=i)
            if function is not None and function.type=='field_expression':
                receiver=self.value(path,function.child_by_field_name('value'))
                self.edge(uid,receiver,'CALL_RECEIVER',function,path);self.nodes[uid]['receiver']=receiver
            token=callee_token(node)
            if token is not None:self.references[uid]=(path,token)
        elif kind=='macro_site':
            self.edge(self.owner(path,node,callable_only=True),uid,'OBSERVES_MACRO',node,path)
            macro=node.child_by_field_name('macro')
            if macro is not None:self.references[uid]=(path,callee_token(macro) or macro)
            for child in walk(node):
                if child.type in {'identifier','string_literal','raw_string_literal'} and child.id!=(macro.id if macro else None):
                    self.edge(uid,self.value(path,child),'MACRO_TOKEN',child,path,status='requires_macro_semantics')
        else:
            if node.type in {'identifier','self','field_expression','scoped_identifier'}:
                token=callee_token(node)
                if token is not None:self.references[uid]=(path,token)
            if node.type=='field_expression':
                receiver=node.child_by_field_name('value')
                if receiver is not None:self.edge(uid,self.value(path,receiver),'VALUE_COMPONENT',receiver,path,component=text(node.child_by_field_name('field')))
            elif node.type not in {'identifier','scoped_identifier','self','string_literal','raw_string_literal','type_identifier'}:
                for child in node.named_children:
                    if child.type in {'type_arguments','primitive_type','type_identifier'}:continue
                    self.edge(uid,self.value(path,child),'VALUE_COMPONENT',child,path,component=child.type)
        return uid

    def relations(self,path,root):
        for node in walk(root):
            if node.type in {'call_expression','macro_invocation'}:self.value(path,node)
            elif node.type in {'let_declaration','const_item','static_item','assignment_expression'}:
                pattern=node.child_by_field_name('pattern') or node.child_by_field_name('name') or node.child_by_field_name('left')
                value=node.child_by_field_name('value') or node.child_by_field_name('right')
                if value is None:continue
                origin=self.value(path,value)
                for named in pattern_names(pattern):
                    uid=self.ids.get((path,named.id))
                    if uid is None:uid=self.value(path,named)
                    self.edge(uid,origin,'PATTERN_VALUE_SOURCE' if node.type!='assignment_expression' and pattern.type!='identifier' else
                        'WRITES_VALUE' if node.type=='assignment_expression' else 'VALUE_SOURCE',node,path,
                        pattern=text(pattern),status='source_projection' if pattern.type!='identifier' else 'source_relation')
            elif node.type in CALLABLES:
                uid=self.ids[(path,node.id)];body=node.child_by_field_name('body')
                if body is None:continue
                tail=body.named_children[-1] if body.type=='block' and body.named_children else body if body.type!='block' else None
                if tail is not None and not (tail.type in {'let_declaration','item'} or text(tail).rstrip().endswith(';')):
                    self.edge(uid,self.value(path,tail),'RETURNS_VALUE',tail,path,return_kind='tail_expression')
            elif node.type=='return_expression' and node.named_children:
                self.edge(self.owner(path,node,callable_only=True),self.value(path,node.named_children[-1]),'RETURNS_VALUE',node,path,return_kind='return_expression')
            elif node.type=='impl_item':
                for field,kind in [('trait','IMPLEMENTS_TRAIT'),('type','IMPLEMENTS_TYPE')]:
                    target=node.child_by_field_name(field)
                    if target is not None:
                        value=self.value(path,target);token=callee_token(target)
                        if token is not None:self.references[value]=(path,token)
                        self.edge(self.ids[(path,node.id)],value,kind,target,path)

    def build(self):
        return {'schema_version':1,'extractor':'rust_tree_sitter_syntax','version':'0.1.0',
            'nodes':list(self.nodes.values()),'edges':self.edges,'coverage':self.coverage,'diagnostics':self.diagnostics,
            'limits':['rust_syntax_is_not_runtime_execution','macro_tokens_require_expansion_or_verified_macro_semantics',
                'rust_native_semantics_requires_crate_context','source_bindings_are_not_per_runtime_instance']}


def syntax_facts(raw,path,parser):
    x=Extractor({path:raw},parser);result=x.build();nodes=result['nodes']
    return {'path':path,'language':'rust','status':result['coverage'][0]['status'],
        'symbols':[n for n in nodes if n['kind']=='callable'],'types':[n for n in nodes if n['kind'] in {'type','implementation'}],
        'imports':[n for n in nodes if n['kind']=='module_reference'],'calls':[n for n in nodes if n['kind']=='call_site'],
        'registrations':[],'resources':[],'interfaces':[],'entries':[n for n in nodes if n['kind']=='callable' and n['name']=='main'],
        'diagnostics':result['diagnostics'],'limits':result['limits']}
