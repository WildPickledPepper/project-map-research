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


def project(result):
    members={m['id']:m for m in result['members']};nodes=[];edges=[]
    for effect in result['effects']:
        location=effect['evidence'][0];member=members[effect['member']]
        nodes.append({**effect,'kind':'source_member_effect','name':member['owner']+'::'+member['name']+' '+effect['role'],
            'path':location['path'],'line':location['line'],'runtime_execution':'not_observed'})
        links=[(effect['source_symbol'],effect['id'],'OBSERVES_MEMBER_'+effect['role'].upper())]
        if effect['role']=='write':links.append((effect['id'],effect['member'],'WRITES_SOURCE_MEMBER_CANDIDATE'))
        elif effect['role']=='read':links.extend([(effect['member'],effect['id'],'SOURCE_MEMBER_READ_BY'),
            (effect['id'],effect['source_symbol'],'AFFECTS_MEMBER_READER')])
        else:links.append((effect['id'],effect['member'],'MEMBER_RECEIVER_CANDIDATE'))
        for source,target,kind in links:
            edges.append({'source':source,'target':target,'kind':kind,'status':'source_member_effect_candidate',
                'evidence':effect['evidence'],'conditions':effect['conditions']+[
                    {'kind':'member_declaration_identity_does_not_select_object_instance'}],
                'instance_identity':effect['instance_identity'],'runtime_execution':'not_observed'})
    return {'nodes':nodes,'edges':edges,'summary':{'adapter':'cpp_source_member_effect_graph/0.1.0',
        'effects':len(nodes),'object_instances_selected':False}}
