"""Conservative C++ source relations over existing Tree-sitter grammars.

No compiler emulation: declarations, inheritance and exact spelling matches are
source facts; inferred receiver/member targets are candidates with evidence.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
from pathlib import PurePosixPath
import posixpath
import re

from adapters.syntax_supplement import cpp_callable, cpp_scope, extract, identity, parents, span, text, walk


def compact(value):
    return re.sub(r'\s+', '', value)


def scoped_name(value, path):
    # Anonymous scopes have translation-unit identity, even at the same line.
    token = hashlib.sha256(path.encode()).hexdigest()[:12]
    return re.sub(r'<anonymous@(\d+)>', lambda m: f'<anonymous@{m[1]}:{token}>', value)


def declared_name(node):
    current = node.child_by_field_name('declarator')
    while current is not None:
        if current.type in {'identifier','field_identifier'}:
            return current
        current = current.child_by_field_name('declarator') or next(
            (c for c in current.named_children if c.type in {'identifier','field_identifier','pointer_declarator','reference_declarator'}),None)
    return None


def parameter_type(node):
    named = declared_name(node)
    end = node.child_by_field_name('default_value')
    raw = node.text[:end.start_byte-node.start_byte].rstrip(b' =') if end else node.text
    if named:
        start, finish = named.start_byte-node.start_byte, named.end_byte-node.start_byte
        raw = raw[:start]+raw[finish:]
    return compact(raw.decode('utf-8'))


class Extractor:
    def __init__(self, sources, parser):
        self.sources = sources
        self.nodes = {}
        self.edges = []
        self.diagnostics = []
        self.units = {}
        self.classes = defaultdict(list)
        self.namespaces = defaultdict(set)
        self.functions = defaultdict(list)
        self.functions_by_id = {}
        self.base_names = defaultdict(set)
        for path, source in sorted(sources.items()):
            data = source.replace(b'\r\n',b'\n')
            tree = parser.parse(data)
            syntax = extract(data,path,'cpp',parser,tree=tree)
            unit = self.units[path] = {'tree':tree,'syntax':syntax,'using':[],'includes':[],'variables':[]}
            self.diagnostics.extend(dict(d,path=path) for d in syntax['diagnostics'])
            symbols = {s['id']:s for s in syntax['symbols']}
            for n in walk(tree.root_node):
                if n.type == 'namespace_definition':
                    named = n.child_by_field_name('name')
                    if named is not None:
                        parts = '::'.join(cpp_scope(n)+[text(named)]).split('::')
                        for count in range(1, len(parts)+1):
                            self.namespaces['::'.join(parts[:count])].add(path)
                if n.type in {'class_specifier','struct_specifier'}:
                    named = n.child_by_field_name('name')
                    if named is None or named.has_error:continue
                    name = scoped_name('::'.join(cpp_scope(n)+[text(named)]),path)
                    uid = 'cpp:'+identity(path,'type',n)
                    bases = next((c for c in n.named_children if c.type=='base_class_clause'),None)
                    self.nodes[uid] = {'id':uid,'kind':'type','path':path,'line':named.start_point[0]+1,
                                      'name':name,'source_sha256':syntax['sha256_lf_utf8'],
                                      'base_spellings':[text(c) for c in bases.named_children if c.type not in {'access_specifier','virtual_specifier'}] if bases else [],
                                      'evidence_kind':'source_syntax','conditions':self.conditions(n)}
                    self.classes[name].append(uid)
                elif n.type=='using_declaration' and re.match(r'using\s+namespace\s',text(n)):
                    value = re.sub(r'^using\s+namespace\s+|;\s*$','',text(n)).strip()
                    if any(p.type=='compound_statement' for p in parents(n)):
                        self.diagnostics.append({'path':path,'line':n.start_point[0]+1,'kind':'local_using_namespace_not_resolved'})
                    else:
                        unit['using'].append(([scoped_name(p,path) for p in cpp_scope(n)],value))
                elif n.type=='preproc_include':
                    include = text(n.child_by_field_name('path'))
                    unit['includes'].append((include.strip('"<>'),include.startswith('"'),n.start_point[0]+1))
                elif n.type=='function_declarator':
                    rec = cpp_callable(n)
                    if rec is None:continue
                    container, named, _ = rec
                    key = identity(path,'callable',container)
                    if key not in symbols:continue
                    s = dict(symbols[key])
                    s['qualified_name'] = scoped_name(s['qualified_name'],path)
                    uid = 'cpp:'+key
                    params = n.child_by_field_name('parameters')
                    parameter_nodes = [p for p in params.named_children if p.type in {'parameter_declaration','optional_parameter_declaration'}] if params else []
                    types = [parameter_type(p) for p in parameter_nodes]
                    signature = (s['qualified_name'],tuple(types),tuple(c.type+':'+text(c) for c in n.named_children if c.type in {'type_qualifier','ref_qualifier'}))
                    return_type = text(container.child_by_field_name('type'))
                    info = {'node':n,'container':container,'path':path,'scope':s['qualified_name'].split('::')[:-1],
                            'return_type':return_type,'signature':signature,'parameter_nodes':parameter_nodes}
                    self.functions[signature].append(uid)
                    self.functions_by_id[uid] = info
                    self.nodes[uid] = {'id':uid,'kind':'callable','path':path,'line':s['line'],
                                      'name':s['qualified_name'],'parameters':types,'definition':s['definition'],
                                      'pure_virtual':s['pure_virtual'],'virtual_spelling':s['virtual'],
                                      'override_spelling':bool(re.search(r'\boverride\b',s['signature_spelling'])),
                                      'return_type_spelling':return_type,'signature_spelling':s['signature_spelling'],
                                      'source_sha256':syntax['sha256_lf_utf8'],'evidence_kind':'source_syntax',
                                      'conditions':self.conditions(container)}
                    for p in parameter_nodes:
                        var = declared_name(p)
                        if var is not None:
                            unit['variables'].append({'name':text(var),'node':p,'range':(container.start_byte,container.end_byte),
                                                      'type':parameter_type(p),'value':None,'owner':uid})
                elif n.type=='declaration':
                    declarator = n.child_by_field_name('declarator')
                    var = declared_name(n)
                    if var is None or declarator is None:continue
                    if any(c.type=='function_declarator' for c in walk(declarator)):continue
                    lexical = next((p for p in parents(n) if p.type in {'compound_statement','for_statement','if_statement'}),tree.root_node)
                    unit['variables'].append({'name':text(var),'node':n,'range':(lexical.start_byte,lexical.end_byte),
                                              'type':text(n.child_by_field_name('type')),
                                              'value':declarator.child_by_field_name('value'),'owner':None})
        self.include_targets = {}
        for path,unit in self.units.items():
            targets = self.include_targets[path] = []
            for inc,local,line in unit['includes']:
                direct = posixpath.normpath((PurePosixPath(path).parent/inc).as_posix())
                candidates = [direct] if local and direct in self.units else [p for p in self.units if p==inc or p.endswith('/'+inc)]
                if len(candidates)==1:targets.append(candidates[0])
                elif local:
                    self.diagnostics.append({'path':path,'line':line,'kind':'include_ambiguous' if candidates else 'include_outside_input',
                                             'include':inc,'candidates':candidates})
        self.visibility = {p:self.include_closure(p,set()) for p in self.units}
        self._type_cache = {}
        self._functions_by_name = defaultdict(list)
        for signature, group in self.functions.items():
            self._functions_by_name[signature[0]].append(group)
        self._variables_by_name = {}
        for path, unit in self.units.items():
            index = defaultdict(list)
            for variable in unit['variables']:index[variable['name']].append(variable)
            self._variables_by_name[path] = index
        self._assignments = {}
        for uid, info in self.functions_by_id.items():
            index = defaultdict(list)
            for node in walk(info['container']):
                if node.type == 'assignment_expression':
                    index[text(node.child_by_field_name('left'))].append(node.start_byte)
            self._assignments[uid] = index

    @staticmethod
    def conditions(node):
        return [text(p).splitlines()[0] for p in reversed(list(parents(node))) if p.type.startswith('preproc_if')]

    def evidence(self, uid):
        n = self.nodes[uid]
        return {'path':n['path'],'line':n['line'],'node':uid}

    def edge(self,a,b,kind,status='source_relation',extra=None,evidence=None):
        self.edges.append({'source':a,'target':b,'kind':kind,'status':status,
                           'evidence':evidence or [self.evidence(a),self.evidence(b)],**(extra or {})})

    def include_closure(self,path,seen):
        if path in seen:return seen
        seen.add(path)
        for target in self.include_targets[path]:self.include_closure(target,seen)
        return seen

    def resolve_type(self,spelling,path,scope):
        key = (spelling,path,tuple(scope))
        if key not in self._type_cache:
            result = self._resolve_type(spelling,path,scope)
            self._type_cache[key] = (tuple(result['names']),result['wrapper'])
        names,wrapper = self._type_cache[key]
        return {'names':list(names),'wrapper':wrapper,'evidence':[]}

    def _resolve_type(self,spelling,path,scope):
        atom = re.sub(r'\b(const|volatile|struct|class|typename)\b','',spelling).strip().strip('&* ').strip()
        wrapper = 'value'
        match = re.fullmatch(r'std::(shared_ptr|unique_ptr)\s*<\s*([^,<>]+)\s*>',atom)
        if match:wrapper,atom = match.groups()
        visible = self.visibility.get(path,{path})
        def exists(q):return any(self.nodes[x]['path'] in visible for x in self.classes.get(q,[]))
        if atom.startswith('::'):names = [atom[2:]] if exists(atom[2:]) else []
        else:
            names = []
            for length in range(len(scope),-1,-1):
                q = '::'.join(scope[:length]+[atom])
                if exists(q):names=[q];break
            if not names:
                for p in visible:
                    for prefix,namespace in self.units[p]['using']:
                        # A using directive applies within its namespace and children.
                        joined = '::'.join(prefix)
                        if joined and not '::'.join(scope).startswith(joined+'::') and '::'.join(scope)!=joined:continue
                        # Relative namespace names are resolved where the using
                        # directive is declared. The nearest namespace may hide
                        # an outer namespace even when it lacks the requested type.
                        resolved = namespace[2:] if namespace.startswith('::') else None
                        if resolved is None:
                            for length in range(len(prefix), -1, -1):
                                candidate = '::'.join(prefix[:length]+[namespace])
                                if self.namespaces.get(candidate, set()) & visible:
                                    resolved = candidate; break
                        if resolved is None: continue
                        q = resolved+'::'+atom
                        if exists(q):names.append(q)
        return {'names':sorted(set(names)),'wrapper':wrapper,'evidence':[]}

    def members(self,owner,name,seen=None):
        seen = set() if seen is None else seen
        if owner in seen:return []
        seen.add(owner)
        own = self._functions_by_name.get(owner+'::'+name,[])
        if own:return own
        return [group for base in sorted(self.base_names[owner]) for group in self.members(base,name,seen)]

    def relations(self):
        for name,ids in self.classes.items():
            for uid in ids:
                n = self.nodes[uid]
                for base in n['base_spellings']:
                    refs = self.resolve_type(base,n['path'],name.split('::')[:-1])
                    for q in refs['names']:
                        for target in self.classes[q]:
                            self.edge(uid,target,'INHERITS','candidate' if len(refs['names'])>1 else 'source_relation')
                            self.base_names[name].add(q)
        for signature,ids in self.functions.items():
            declarations = [i for i in ids if not self.nodes[i]['definition']]
            definitions = [i for i in ids if self.nodes[i]['definition']]
            for a in declarations:
                for b in definitions:
                    self.edge(a,b,'DECLARES_DEFINITION','candidate',
                              {'basis':'same_qualified_owner_parameter_spelling_and_cvref','types_checked':False,
                               'identity_condition':'same_program_and_compatible_types','build_linkage':'not_validated'})
            owner, _, method = signature[0].rpartition('::')
            for uid in ids:
                for cls in self.classes.get(owner,[]):self.edge(cls,uid,'DECLARES_MEMBER')
            for base in sorted(self.base_names[owner]):
                for group in self.members(base,method):
                    for parent in group:
                        if tuple(self.nodes[parent]['parameters'])!=signature[1]:continue
                        if self.functions_by_id[parent]['signature'][2]!=signature[2]:continue
                        if not (self.nodes[parent]['pure_virtual'] or self.nodes[parent]['virtual_spelling']):continue
                        for child in declarations or definitions:
                            self.edge(parent,child,'OVERRIDE_CANDIDATE','candidate',
                                      {'basis':'inheritance_and_matching_parameter_spelling','runtime_selection':'unknown'})

    def variables(self,name,node,path,owner):
        found = [v for v in self._variables_by_name[path].get(name,[]) if v['range'][0]<=node.start_byte<v['range'][1]
                 and v['node'].start_byte<=node.start_byte and (v['owner'] is None or v['owner']==owner)]
        return sorted(found,key=lambda v:(v['range'][1]-v['range'][0],-v['node'].start_byte))

    def infer(self,node,path,scope,owner,depth=0):
        empty = {'names':[],'wrapper':'unknown','evidence':[]}
        if node is None or depth>12:return empty
        infer = lambda n:self.infer(n,path,scope,owner,depth+1)
        if node.type=='identifier':
            variables = self.variables(text(node),node,path,owner)
            if not variables:return self.resolve_type(text(node),path,scope)
            var = variables[0]
            # Reassignments require dataflow analysis; do not keep a stale initializer.
            function = self.functions_by_id.get(owner,{}).get('container')
            if function is not None:
                if any(var['node'].end_byte<offset<node.start_byte
                       for offset in self._assignments.get(owner,{}).get(text(node),[])):
                    return empty
            result = infer(var['value']) if var['type']=='auto' else self.resolve_type(var['type'],path,scope)
            return {**result,'evidence':result['evidence']+[{'path':path,'line':var['node'].start_point[0]+1,'basis':'declared_or_initialized_variable'}]}
        if node.type=='this':return {'names':['::'.join(scope)],'wrapper':'pointer','evidence':[]}
        if node.type in {'parenthesized_expression','pointer_expression'}:
            return infer(node.named_children[-1]) if node.named_children else empty
        if node.type=='conditional_expression':
            branches = [infer(node.child_by_field_name(k)) for k in ('consequence','alternative')]
            if any(not b['names'] for b in branches):return empty
            return {'names':sorted(set(q for b in branches for q in b['names'])),
                    'wrapper':branches[0]['wrapper'] if branches[0]['wrapper']==branches[1]['wrapper'] else 'unknown',
                    'evidence':[e for b in branches for e in b['evidence']]+[{'path':path,'line':node.start_point[0]+1,
                                'condition':text(node.child_by_field_name('condition')),'basis':'both_conditional_branches'}]}
        if node.type=='call_expression':
            groups, receiver = self.targets(node,path,scope,owner,depth+1)
            fn = node.child_by_field_name('function')
            if fn and fn.type=='field_expression' and text(fn.child_by_field_name('field'))=='get' and receiver['wrapper'] in {'shared_ptr','unique_ptr'}:
                return {**receiver,'wrapper':'pointer'}
            inferred = []
            for group in groups:
                for uid in group:
                    info = self.functions_by_id[uid]
                    value = self.resolve_type(info['return_type'],info['path'],info['scope'])
                    if value['names']:inferred.append({**value,'evidence':[self.evidence(uid)]})
            if not inferred:return empty
            return {'names':sorted(set(q for v in inferred for q in v['names'])),
                    'wrapper':inferred[0]['wrapper'] if len({v['wrapper'] for v in inferred})==1 else 'unknown',
                    'evidence':[e for v in inferred for e in v['evidence']]}
        return empty

    def targets(self,call,path,scope,owner,depth=0):
        empty = {'names':[],'wrapper':'unknown','evidence':[]}
        if depth>12:return [],empty
        fn = call.child_by_field_name('function')
        if fn is None:return [],empty
        receiver = empty
        if fn.type=='field_expression':
            receiver = self.infer(fn.child_by_field_name('argument'),path,scope,owner,depth+1)
            name = text(fn.child_by_field_name('field'))
            if receiver['wrapper'] in {'shared_ptr','unique_ptr'} and name in {'get','reset','use_count'}:
                return [],receiver
        elif fn.type=='qualified_identifier':
            value = text(fn)
            owner_name,_,name = value.rpartition('::')
            receiver = self.resolve_type(owner_name,path,scope)
        else:return [],receiver
        groups = [g for q in receiver['names'] for g in self.members(q,name)]
        args = call.child_by_field_name('arguments')
        args = list(args.named_children) if args else []
        result = []
        for group in groups:
            info = self.functions_by_id[group[0]]
            ps = info['parameter_nodes']
            minimum = sum(p.child_by_field_name('default_value') is None for p in ps)
            if not minimum<=len(args)<=len(ps):continue
            types = self.nodes[group[0]]['parameters']
            # Exclude a proven nonzero integer -> pointer mismatch; leave other
            # conversions unresolved instead of implementing C++ overload rules.
            if any(a.type=='number_literal' and re.fullmatch(r'[1-9][0-9]*',text(a)) and '*' in t for a,t in zip(args,types)):continue
            result.append(group)
        return result,receiver

    def build(self):
        self.relations()
        for path,unit in self.units.items():
            ast_calls = {(n.start_byte,n.end_byte):n for n in walk(unit['tree'].root_node) if n.type=='call_expression'}
            for call in unit['syntax']['calls']:
                uid = 'cpp:'+call['id']
                owner = 'cpp:'+call['owner_id'] if call['owner_id'] else None
                self.nodes[uid] = {'id':uid,'kind':'call_site','path':path,'line':call['line'],
                                  'name':call['callee_spelling'],'arguments':call['argument_spellings'],
                                  'resolution':'unresolved','reason':'receiver_or_member_not_resolved',
                                  'evidence_kind':'source_syntax','source_sha256':unit['syntax']['sha256_lf_utf8']}
                if owner in self.nodes:self.edge(owner,uid,'OBSERVES_CALL')
                ast = ast_calls.get((call['start_byte'],call['end_byte']))
                if ast is None:continue
                scope = self.functions_by_id[owner]['scope'] if owner in self.functions_by_id else [scoped_name(p,path) for p in cpp_scope(ast)]
                groups, receiver = self.targets(ast,path,scope,owner)
                if not groups:
                    if receiver['wrapper'] in {'shared_ptr','unique_ptr'}:
                        self.nodes[uid]['reason']='standard_smart_pointer_member_no_project_target'
                    continue
                self.nodes[uid].update(resolution='candidate',receiver_types=receiver['names'],
                                       reason='source_type_inference_without_compiler_context')
                for group in groups:
                    preferred = [i for i in group if not self.nodes[i]['definition']] or group
                    for target in preferred:
                        self.edge(uid,target,'MEMBER_TARGET_CANDIDATE','candidate',
                                  {'basis':'lexical_receiver_type_and_member_lookup','runtime_dispatch':'unknown',
                                   'receiver_types':receiver['names']},
                                  [self.evidence(uid),*receiver['evidence'],self.evidence(target)])
        return {'schema_version':1,'extractor':'cpp_facts','version':'0.1.0',
                'nodes':list(self.nodes.values()),'edges':self.edges,'diagnostics':self.diagnostics,
                'coverage':[{'path':p,'status':'syntax_errors' if u['syntax']['diagnostics'] else 'parsed'} for p,u in self.units.items()],
                'limits':['preprocessor_not_evaluated','no_compiler_type_check','receiver_targets_are_candidates',
                          'exact_parameter_spelling_links_do_not_expand_aliases','runtime_implementation_selection_unknown']}


def analyze(sources,parser):
    return Extractor(sources,parser).build()
