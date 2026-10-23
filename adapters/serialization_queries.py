"""Query serialization mappings within one source callback's parameter scope."""
from copy import deepcopy


def explain_serialization(graph,source_symbol,max_mappings=5000):
    if max_mappings<0:raise ValueError('max_mappings must be nonnegative')
    data=graph.get('data',{}).get('serialization',{})
    functions=[f for f in data.get('functions',[]) if f['source_symbol']==source_symbol]
    if not functions:
        return {'snapshot':graph['snapshot'],'source_symbol':source_symbol,'status':'not_extracted',
                'field_mappings':[],'registrations':[],'gaps':[{'kind':'no_serialization_summary'}],
                'truncated':False,'runtime_delivery':'unknown'}
    result=deepcopy(functions[0]);count=len(result['field_mappings'])
    result['field_mappings']=result['field_mappings'][:max_mappings]
    result.update({'snapshot':graph['snapshot'],'source_commit':graph['source_commit'],
        'registrations':deepcopy([r for r in data.get('registrations',[]) if source_symbol in r['functions']]),
        'total_mappings':count,'truncated':count>max_mappings,'max_mappings':max_mappings,
        'runtime_delivery':'unknown','limits':deepcopy(data.get('limits',[]))})
    return result
