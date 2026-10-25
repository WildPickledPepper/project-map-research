"""Source path predicates, including early exits and switch entry candidates."""
from adapters.syntax_supplement import parents,text


def statements(node):
    return [c for c in node.named_children if c.type not in {'comment','number_literal','identifier','qualified_identifier'}] if node else []


def exits(node,switch=False):
    if node is None:return False
    if node.type in {'return_statement','throw_statement','co_return_statement'}:return True
    if switch and node.type=='break_statement':return True
    if node.type in {'compound_statement','case_statement','else_clause'}:
        body=statements(node);return bool(body) and exits(body[-1],switch)
    if node.type=='if_statement':return exits(node.child_by_field_name('consequence'),switch) and exits(node.child_by_field_name('alternative'),switch)
    return False


def switch_entries(case,switch):
    siblings=[c for c in case.parent.named_children if c.type=='case_statement'];index=siblings.index(case)
    labels=[text(case.child_by_field_name('value')) or 'default'];conditional=False
    for previous in reversed(siblings[:index]):
        if exits(previous,switch=True):break
        labels.insert(0,text(previous.child_by_field_name('value')) or 'default')
        if any(n.type=='if_statement' for n in statements(previous)):conditional=True
    excluded=[text(c.child_by_field_name('value')) for c in siblings if c.child_by_field_name('value')]
    return labels,excluded,conditional


def predicates(node):
    result=[]
    for parent in reversed(list(parents(node))):
        if parent.type in {'if_statement','conditional_expression'}:
            condition=parent.child_by_field_name('condition');yes=parent.child_by_field_name('consequence');no=parent.child_by_field_name('alternative')
            branch=True if yes and yes.start_byte<=node.start_byte<yes.end_byte else False if no and no.start_byte<=node.start_byte<no.end_byte else None
            if branch is not None:result.append({'kind':'branch','expression':text(condition),'when':branch,'line':condition.start_point[0]+1})
        elif parent.type=='compound_statement':
            for previous in parent.named_children:
                if previous.end_byte>node.start_byte:break
                if previous.type!='if_statement':continue
                yes=exits(previous.child_by_field_name('consequence'));no=exits(previous.child_by_field_name('alternative'))
                if not yes and not no:continue
                condition=previous.child_by_field_name('condition')
                result.append({'kind':'unreachable_after_exit' if yes and no else 'early_exit_guard',
                               'expression':text(condition),'when':not yes,'line':condition.start_point[0]+1})
        elif parent.type=='case_statement':
            switch=next((p for p in parents(parent) if p.type=='switch_statement'),None)
            if switch:
                condition=switch.child_by_field_name('condition');value=parent.child_by_field_name('value')
                labels,excluded,conditional=switch_entries(parent,switch)
                result.append({'kind':'switch_label','expression':text(condition),'label':text(value) if value else 'default',
                    'entry_labels':labels,'default_excludes':excluded if 'default' in labels else [],
                    'line':parent.start_point[0]+1,'fallthrough':'source_entry_candidates',
                    'extra_conditions':'conditional_transfer_unresolved' if conditional else None})
        elif parent.type in {'while_statement','for_statement','for_range_loop','do_statement'}:
            condition=parent.child_by_field_name('condition')
            result.append({'kind':'loop','expression':text(condition) or text(parent).splitlines()[0],
                           'line':parent.start_point[0]+1,'iteration':'runtime_unknown'})
    from adapters.cpp_member_declarations import preprocessor_conditions
    result.extend(preprocessor_conditions(node))
    return result
