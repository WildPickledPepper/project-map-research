"""Class-scoped C++ data members, with conditional declaration alternatives."""
from collections import defaultdict

from adapters.syntax_supplement import cpp_scope,identity,parents,text,walk


ADAPTER_VERSION='cpp_source_member_declaration_alternatives/0.1.1'


def preprocessor_conditions(node):
    guards=[]
    for parent in reversed(list(parents(node))):
        if parent.type not in {'preproc_if','preproc_ifdef','preproc_elif','preproc_elifdef'}:continue
        alternative=parent.child_by_field_name('alternative')
        yes=not (alternative is not None and alternative.start_byte<=node.start_byte<alternative.end_byte)
        name=parent.child_by_field_name('name');condition=parent.child_by_field_name('condition')
        if name is not None:
            expression='defined('+text(name)+')'
            if text(parent.children[0]) in {'#ifndef','#elifndef'}:yes=not yes
        else:expression=text(condition)
        guards.append({'kind':'preprocessor','expression':expression,'when':yes,'line':parent.start_point[0]+1})
    return guards


def selected_declaration(field):
    declarations=field.get('declarations',[])
    if not any(d['conditions'] for d in declarations):return []
    return [{'kind':'member_declaration_selected','member':field['id'],
        'alternatives':[{'path':d['path'],'line':d['line'],'conditions':d['conditions']} for d in declarations]}]


def project(members):
    nodes=[];edges=[];declaration_count=0;conditional=0
    for member in members:
        nodes.append({**member,'kind':'source_member_storage','name':member['owner']+'::'+member['name']})
        edges.append({'source':member['class_source'],'target':member['id'],'kind':'DECLARES_SOURCE_MEMBER','status':'candidate',
            'evidence':member['evidence'],'conditions':selected_declaration(member),'runtime_selection':'unknown'})
        conditional+=int(any(d['conditions'] for d in member['declarations']))
        for index,declaration in enumerate(member['declarations']):
            did=member['id']+':declaration:'+str(index);declaration_count+=1
            nodes.append({'id':did,**declaration,'kind':'cpp_member_declaration','name':member['name']})
            edges.append({'source':member['id'],'target':did,'kind':'HAS_MEMBER_DECLARATION','status':'candidate',
                'evidence':[declaration['evidence']],'conditions':declaration['conditions'],'runtime_selection':'unknown'})
    return {'nodes':nodes,'edges':edges,'summary':{'adapter':ADAPTER_VERSION,'members':len(members),'declarations':declaration_count,
        'conditional_members':conditional,'configuration_selection':'not_performed'}}


def declarator_child(node):
    return node.child_by_field_name('declarator') or next((c for c in node.named_children if c.type in {
        'identifier','field_identifier','pointer_declarator','reference_declarator','array_declarator',
        'parenthesized_declarator','function_declarator'}),None)


def method_declaration(node):
    current=node
    while current is not None:
        if current.type=='function_declarator':
            inner=current.child_by_field_name('declarator')
            return inner is None or inner.type!='parenthesized_declarator' or any(n.type=='function_declarator' for n in walk(inner))
        if current.type in {'identifier','field_identifier'}:return False
        current=declarator_child(current)
    return False


def declarator_name(node):
    current=node
    while current is not None:
        if current.type in {'identifier','field_identifier'}:return current
        current=declarator_child(current)
    return None


def discover(data):
    from adapters.cpp_data import canonical
    from adapters.cpp_facts import scoped_name
    import re
    data.fields={};data.member_candidates=defaultdict(list);groups=defaultdict(list)
    for path,unit in data.x.units.items():
        for cls in walk(unit['tree'].root_node):
            if cls.type not in {'class_specifier','struct_specifier','union_specifier'}:continue
            name=cls.child_by_field_name('name');body=cls.child_by_field_name('body')
            if body is None:continue
            if name is None or cls.type=='union_specifier':
                data.diagnostics.append({'kind':'cpp_member_declaration_unresolved','reason':'anonymous_or_union_member_scope_not_expanded',
                    'required':True,**data.evidence(path,cls)});continue
            owner=scoped_name(canonical('::'.join(cpp_scope(cls)+[text(name)])),path)
            class_id='cpp:'+identity(path,'type',cls)
            for member in walk(body):
                if member.type!='field_declaration':continue
                nearest=next((p for p in parents(member) if p.type in {'class_specifier','struct_specifier','union_specifier'}),None)
                if nearest!=cls:continue
                declarators=member.children_by_field_name('declarator')
                for declaration in declarators:
                    # Function prototypes are callable declarations. Parenthesized
                    # pointer declarators are data members with callable types.
                    if method_declaration(declaration):continue
                    named=declarator_name(declaration)
                    if named is None:
                        data.diagnostics.append({'kind':'cpp_member_declaration_unresolved','reason':'member_declarator_not_expanded',
                            'required':True,**data.evidence(path,member)});continue
                    typ=text(member.child_by_field_name('type'));match=re.match(r'std::(\w+)\s*<',typ)
                    shape=declaration.text[:named.start_byte-declaration.start_byte]+declaration.text[named.end_byte-declaration.start_byte:]
                    default=None;started=False
                    for child in member.named_children:
                        if child==declaration:started=True;continue
                        if started and child in declarators:break
                        if started and child in member.children_by_field_name('default_value'):default=child;break
                    evidence=data.evidence(path,member);conditions=preprocessor_conditions(member)
                    row={'id':'storage:'+identity(path,'member',member if len(declarators)==1 else declaration),'owner':owner,'name':text(named),
                        'path':path,'line':member.start_point[0]+1,'type':typ,'declarator_shape':shape.decode('utf-8'),
                        'container':match[1] if match and match[1] in data.CONTAINERS else None,
                        'class_source':class_id,'instance_identity':'class_member_instance_unresolved','evidence':[evidence],
                        'declarations':[{'path':path,'line':member.start_point[0]+1,'type':typ,'declarator_shape':shape.decode('utf-8'),
                            'default_expression':text(default) if default is not None else None,
                            'qualifiers':[text(c) for c in member.named_children if c.type=='type_qualifier'],
                            'conditions':conditions,'evidence':evidence}]}
                    groups[(owner,text(named),class_id)].append(row)
    for key,variants in groups.items():
        row=dict(variants[0]);row['declarations']=[d for v in variants for d in v['declarations']]
        if len(variants)>1:
            row['id']+=':alternatives';row['evidence']=[e for v in variants for e in v['evidence']]
            types={(re.sub(r'\s+','',v['type']),re.sub(r'\s+','',v['declarator_shape'])) for v in variants}
            if len(types)>1:
                row.update(type='',container=None,type_status='configuration_dependent')
                data.diagnostics.append({'kind':'cpp_member_declaration_unresolved','reason':'member_type_selection_requires_configuration',
                    'required':True,'path':row['path'],'line':row['line'],'member':row['id']})
            else:row['type_status']='same_source_type_across_declarations'
        else:row['type_status']='single_source_declaration'
        data.fields[key]=row;data.member_candidates[(row['owner'],row['name'])].append(row)
