"""Attach data evidence to the portable graph without merging instance identities."""
from copy import deepcopy
from collections import defaultdict
import json

from adapters.protocol_graph import PROTOCOL_KINDS

IMPLEMENTATION_KINDS={'OBSERVES_CALL','MEMBER_TARGET_CANDIDATE','OVERRIDE_CANDIDATE','DECLARES_DEFINITION'}
END_TO_END_KINDS=PROTOCOL_KINDS|IMPLEMENTATION_KINDS
RESOURCE_IMPACT_KINDS={'OBSERVES_STORAGE_WRITE','POTENTIALLY_READ_BY','AFFECTS_READER'}
INSTANCE_IMPACT_KINDS={'OBSERVES_INSTANCE_WRITE','INSTANCE_VALUE_READ_BY','AFFECTS_INSTANCE_READER'}


def literal_key(value):
    if not value:return None
    if value.get('kind')=='identifier':return literal_key(value.get('initializer'))
    if value.get('kind') in {'number_literal','string_literal','true','false'}:
        try:return ('constant',json.loads(value['expression']))
        except ValueError:return None
    return None


def keys_compatible(a,b):
    left,right=literal_key(a.get('key')),literal_key(b.get('key'))
    return left is None or right is None or left==right


def expression_ids(value):
    if isinstance(value,dict):
        if 'expression_id' in value:yield value['expression_id']
        for item in value.values():yield from expression_ids(item)
    elif isinstance(value,list):
        for item in value:yield from expression_ids(item)


def augment(base,cpp,paths):
    graph=deepcopy(base);facts=cpp['facts'];data=cpp['data']
    by_id={n['id']:n for n in graph['nodes']};by_id.update({n['id']:n for n in facts['nodes']})
    edges=[e for e in graph['edges'] if not(e['source'].startswith('cpp:') and e['target'].startswith('cpp:'))]+facts['edges']
    def node(rec,kind,name):by_id[rec['id']]={**rec,'kind':kind,'name':name}
    def edge(a,b,kind,evidence,conditions=None):
        edges.append({'source':a,'target':b,'kind':kind,'status':'candidate','evidence':evidence,
                      'conditions':conditions or [],'runtime_selection':'unknown'})
    for storage in data['storages']:node(storage,'storage_member',storage['owner']+'::'+storage['name'])
    for access in data['accesses']:
        node(access,'storage_access',access['operation'])
        uid=access['source_symbol'];sid=access['storage'];aid=access['id'];e=access['evidence']
        conditions=[*access['conditions'],'same_runtime_instance','matching_runtime_key']
        edge(uid,aid,'OBSERVES_STORAGE_'+access['role'].upper(),e,access['conditions'])
        if access['role']=='write':edge(aid,sid,'WRITES_RESOURCE',e,conditions)
        else:
            edge(sid,aid,'RESOURCE_READ_BY',e,conditions)
            edge(aid,uid,'AFFECTS_READER',e,conditions)
            if access.get('implicit_write'):
                edge(uid,aid,'OBSERVES_STORAGE_WRITE',e,[*conditions,access['implicit_write']])
                edge(aid,sid,'MAY_INITIALIZE_RESOURCE',e,[*conditions,access['implicit_write']])
    allocations={a['id']:a for a in data['allocations']}
    allocation_exprs={a['expression_id']:a['id'] for a in data['allocations']}
    for allocation in data['allocations']:
        node(allocation,'factory_allocation',allocation['type_spelling'])
        edge(allocation['source_symbol'],allocation['id'],'DECLARES_ALLOCATION',allocation['evidence'],allocation['conditions'])
        if allocation['enclosing_allocation'] in allocations:
            edge(allocation['enclosing_allocation'],allocation['id'],'PASSES_FACTORY_ALLOCATION',allocation['evidence'],
                 [*allocation['conditions'],'constructor_callback_invocation_required'])
    readers_by_storage=defaultdict(list)
    for reader in data['accesses']:
        if reader['role']=='read':readers_by_storage[reader['storage']].append(reader)
    for writer in data['accesses']:
        if writer['role']!='write' and not writer.get('implicit_write'):continue
        for reader in readers_by_storage.get(writer['storage'],[]):
            if not keys_compatible(writer,reader):continue
            edge(writer['id'],reader['id'],'POTENTIALLY_READ_BY',writer['evidence']+reader['evidence'],
                 ['same_runtime_instance','matching_runtime_key','write_reaches_read_without_intervening_update'])
    instances=data.get('instances',{});objects={o['id']:o for o in instances.get('objects',[])}
    accesses={a['id']:a for a in data['accesses']};contextual=[]
    for obj in objects.values():node(obj,'source_object_instance',obj['name'])
    for context in instances.get('accesses',[]):
        access=accesses[context['access']];oid=context['instance'];uid=access['source_symbol']
        rec={**access,'id':access['id']+':'+oid,'instance':oid,'instance_scope':objects[oid]['identity_scope']}
        node(rec,'instance_storage_access',rec['operation']);contextual.append(rec)
        conditions=[objects[oid]['identity_scope'],*access['conditions']]
        edge(rec['id'],oid,'REFERS_TO_INSTANCE',objects[oid]['evidence'],conditions)
        if access['role']=='write' or access.get('implicit_write'):edge(uid,rec['id'],'OBSERVES_INSTANCE_WRITE',access['evidence'],conditions)
        if access['role']=='read':edge(rec['id'],uid,'AFFECTS_INSTANCE_READER',access['evidence'],conditions)
    readers_by_instance=defaultdict(list)
    for reader in contextual:
        if reader['role']=='read':readers_by_instance[(reader['instance'],reader['storage'])].append(reader)
    for writer in contextual:
        if writer['role']!='write' and not writer.get('implicit_write'):continue
        for reader in readers_by_instance.get((writer['instance'],writer['storage']),[]):
            if not keys_compatible(writer,reader):continue
            edge(writer['id'],reader['id'],'INSTANCE_VALUE_READ_BY',writer['evidence']+reader['evidence'],
                 [writer['instance_scope'],'matching_runtime_key','write_reaches_read_without_intervening_update'])
    for access in data['accesses']:
        if access['role']!='write' or not access['value']:continue
        for expr in sorted(set(expression_ids(access['value']))):
            if expr in allocation_exprs:
                edge(access['id'],allocation_exprs[expr],'STORED_ALLOCATION_CANDIDATE',access['evidence'],
                     [*access['conditions'],'reaching_definition_and_successful_insertion_required'])
    for summary in data['summaries']:
        for call in summary['calls']:
            if call['call_site'] not in by_id:continue
            for target in call['targets']:
                edge(call['call_site'],target,'SOURCE_CALL_CANDIDATE',[{k:call[k] for k in ['path','line','expression']}],call['conditions'])
                resolution=call.get('resolution',{})
                edges[-1]['type_evidence']={'receiver_types':resolution.get('receiver_types',[]),
                    'candidates':[c for c in resolution.get('candidates',[]) if c['target']==target],
                    'gaps':resolution.get('gaps',[])}
    flow=data.get('field_flow',{});roots={r['id']:r for r in flow.get('roots',[])}
    for root in roots.values():
        evidence=root['evidence'][0]
        node({**root,'path':evidence['path'],'line':evidence['line']},'object_binding',root['name'])
        edge(root['source_symbol'],root['id'],'DECLARES_OBJECT_BINDING',root['evidence'])
    for location in flow.get('locations',[]):
        root=roots[location['root']];evidence=root['evidence'][0]
        node({**location,'path':evidence['path'],'line':evidence['line']},'object_path',root['name']+'/'+('/'.join(location['selectors'])))
        edge(root['id'],location['id'],'HAS_OBJECT_PATH',root['evidence'],['source_binding_scope'])
    for write in flow.get('writes',[]):
        evidence=write['evidence'][0]
        node({**write,'path':evidence['path'],'line':evidence['line']},'field_write',write['operation'])
        edge(write['source_symbol'],write['id'],'OBSERVES_FIELD_WRITE',write['evidence'],write['conditions'])
        edge(write['id'],write['location'],'WRITES_OBJECT_PATH',write['evidence'],write['conditions'])
    # Cross-call effects are composed by field_queries using each invocation's
    # argument bindings; a global formal-parameter join would mix callers.
    for serializer in data.get('serialization',{}).get('functions',[]):
        uid=serializer['source_symbol'];symbol=by_id[uid]
        for mapping in serializer['field_mappings']:
            source=mapping['source'];wire=mapping['wire_path']
            suffix=json.dumps([source['parameter'],source['selectors']],separators=(',',':'))
            pid='serialization-source:'+uid+':'+suffix
            wid='wire-field:'+uid+':'+json.dumps(wire,separators=(',',':'))
            location={'path':symbol['path'],'line':symbol['line'],'source_symbol':uid}
            node({'id':pid,**location,'parameter':source['parameter'],'selectors':source['selectors'],
                  'root_types':source.get('root_types',[])},'serialization_parameter_path',suffix)
            node({'id':wid,**location,'wire_path':wire},'serialized_field','/'.join(wire))
            edge(uid,pid,'READS_SERIALIZATION_SOURCE',mapping['evidence'],mapping['conditions'])
            edge(pid,wid,'COLLECTION_SERIALIZED_AS' if mapping['relation']=='array_iteration_source' else 'VALUE_SERIALIZED_AS',
                 mapping['evidence'],mapping['conditions'])
            edges[-1]['conversion']=source.get('conversion');edges[-1]['relation']=mapping['relation']
    for registration in data.get('serialization',{}).get('registrations',[]):
        rid='serialization:'+registration['id']
        node({**registration,'id':rid},'serializer_registration',registration['key'])
        for uid in registration['functions']:
            edge(rid,uid,'REGISTERS_SERIALIZER_CANDIDATE',registration['evidence'],['registration_executed','matching_protocol_instance_and_key'])
    # Parallel evidence edges remain distinct; exact duplicates are redundant.
    unique={json.dumps(e,sort_keys=True):e for e in edges}
    graph['nodes']=list(by_id.values());graph['edges']=list(unique.values())
    graph['snapshot']=graph['source_commit']+':p3-data-v5';graph['input_paths']=sorted(paths)
    coverage={c['path']:c for c in base['coverage']};coverage.update({c['path']:c for c in facts['coverage']})
    graph['coverage']=[coverage[p] for p in paths]
    graph['data']=data;graph['extractors']['cpp_data']='cpp_data/0.6.0';graph['extractors']['cpp_value_types']='cpp_value_types/0.1.0'
    graph['extractors']['cpp_field_flow']='cpp_field_flow/0.2.0'
    graph['extractors']['cpp_serialization']='cpp_serialization/0.1.0'
    graph['extractors']['cpp_response_routing']='cpp_response_routing/0.1.0'
    graph['provenance']['data_base_snapshot']=base['snapshot']
    graph['diagnostics']+=data['diagnostics']
    return graph
