"""Typed member reads/assignments; class identity never proves instance identity."""
from adapters.cpp_control import predicates
from adapters.cpp_data import enclosing_function
from adapters.syntax_supplement import identity, text, walk
from adapters.cpp_member_declarations import selected_declaration


def extract_member_effects(data):
    effects=[]
    for uid,info in data.x.functions_by_id.items():
        if not data.x.nodes[uid]['definition']:continue
        for node in walk(info['container']):
            if enclosing_function(node)!=info['container']:continue
            if node.type not in {'identifier','field_expression'}:continue
            field=data.receiver_field(node,uid,info)
            if not field:continue
            parent=node.parent
            # Declaration/type/member-name positions are not value reads.
            if parent and parent.type in {'field_declaration','init_declarator','parameter_declaration','function_declarator','qualified_identifier'}:continue
            if parent and parent.type=='field_expression' and parent.child_by_field_name('field')==node:continue
            if parent and parent.type=='call_expression' and parent.child_by_field_name('function')==node:continue
            assignment=parent and parent.type=='assignment_expression' and parent.child_by_field_name('left')==node
            operation=text(parent.child_by_field_name('operator')) if assignment else 'read_value'
            # Receiver use can mutate through a call; it is not classified as a pure read.
            receiver_use=parent and parent.type=='field_expression' and parent.child_by_field_name('argument')==node and parent.parent and parent.parent.type=='call_expression'
            role='write' if assignment else 'receiver_use' if receiver_use else 'read'
            evidence_node=parent if assignment or receiver_use else node
            effects.append({'id':'member-effect:'+identity(info['path'],'member_effect',node),'member':field['id'],
                'source_symbol':uid,'role':role,'operation':operation,
                'value':data.expr(parent.child_by_field_name('right'),uid,info) if assignment else None,
                'receiver':text(node.child_by_field_name('argument')) if node.type=='field_expression' else 'implicit_this',
                'conditions':predicates(node)+selected_declaration(field),'evidence':[data.evidence(info['path'],evidence_node)],
                'instance_identity':'unresolved','status':'source_member_effect_candidate'})
    used={e['member'] for e in effects}
    return {'version':'0.1','members':[f for f in data.fields.values() if f['id'] in used], 'effects':effects,
        'limits':['class_member_identity_is_not_object_identity','receiver_use_may_read_or_write',
                  'compound_assignment_also_reads','lifetime_lock_order_and_runtime_occupancy_not_proved']}
