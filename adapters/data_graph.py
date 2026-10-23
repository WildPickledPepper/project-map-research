"""Attach data evidence to the portable graph without merging instance identities."""
from copy import deepcopy
import json

from adapters.protocol_graph import PROTOCOL_KINDS

IMPLEMENTATION_KINDS={'OBSERVES_CALL','MEMBER_TARGET_CANDIDATE','OVERRIDE_CANDIDATE','DECLARES_DEFINITION'}
END_TO_END_KINDS=PROTOCOL_KINDS|IMPLEMENTATION_KINDS
RESOURCE_IMPACT_KINDS={'OBSERVES_STORAGE_WRITE','POTENTIALLY_READ_BY','AFFECTS_READER'}


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
    for writer in data['accesses']:
        if writer['role']!='write' and not writer.get('implicit_write'):continue
        for reader in data['accesses']:
            if reader['role']!='read' or writer['storage']!=reader['storage'] or not keys_compatible(writer,reader):continue
            edge(writer['id'],reader['id'],'POTENTIALLY_READ_BY',writer['evidence']+reader['evidence'],
                 ['same_runtime_instance','matching_runtime_key','write_reaches_read_without_intervening_update'])
    for access in data['accesses']:
        if access['role']!='write' or not access['value']:continue
        for expr in set(expression_ids(access['value'])):
            if expr in allocation_exprs:
                edge(access['id'],allocation_exprs[expr],'STORED_ALLOCATION_CANDIDATE',access['evidence'],
                     [*access['conditions'],'reaching_definition_and_successful_insertion_required'])
    for summary in data['summaries']:
        for call in summary['calls']:
            if call['call_site'] not in by_id:continue
            for target in call['targets']:
                edge(call['call_site'],target,'SOURCE_CALL_CANDIDATE',[{k:call[k] for k in ['path','line','expression']}],call['conditions'])
    # Parallel evidence edges remain distinct; exact duplicates are redundant.
    unique={json.dumps(e,sort_keys=True):e for e in edges}
    graph['nodes']=list(by_id.values());graph['edges']=list(unique.values())
    graph['snapshot']=graph['source_commit']+':p3-data-v1';graph['input_paths']=sorted(paths)
    coverage={c['path']:c for c in base['coverage']};coverage.update({c['path']:c for c in facts['coverage']})
    graph['coverage']=[coverage[p] for p in paths]
    graph['data']=data;graph['extractors']['cpp_data']='cpp_data/0.3.0'
    graph['provenance']['data_base_snapshot']=base['snapshot']
    graph['diagnostics']+=data['diagnostics']
    return graph
