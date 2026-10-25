"""Inspect source-specific consumers; used only for evaluation, never extraction."""
import argparse
import json
from pathlib import Path


def leaves(value):
    if value.get('kind') == 'alternatives':
        return [v for item in value['values'] for v in leaves(item)]
    if value.get('kind') == 'object':
        return [v for item in value['fields'].values() for v in leaves(item)]
    return [value]


def inspect(facts):
    nodes = {n['id']: n for n in facts['nodes']}
    if 'return_flow' in facts:
        flow = facts['return_flow']
        rows = []
        for name in ['queryIterations', 'queryStages']:
            symbols = {n['id'] for n in facts['nodes'] if n['name'] == name or
                       n['path'] == 'modules/cluster/src/utils/RequestUtils.ts' and n['line'] == 64 and n['kind'] == 'callable'} if name == 'queryStages' else {
                           n['id'] for n in facts['nodes'] if n['name'] == name}
            returned = [r for r in flow['returns'] if r['entry'] == r['source_symbol'] and r['source_symbol'] in symbols]
            rows.append({'name': name, 'values': [r['value'] for r in returned],
                         'boundary_projection': any(v.get('kind') == 'input_path' for r in returned for v in leaves(r['value'])),
                         'diagnostic_kinds': sorted({d['kind'] for d in flow['diagnostics'] if d['entry'] in symbols})})
        return rows
    flow = facts['data_flow']
    rows = []
    for consumer in flow['consumptions']:
        symbol = nodes[consumer['source_symbol']]
        if symbol['name'] in {'getiterationOptions', 'getStageOptions', 'fetchSnapshotViewBlocksPaginated'} or consumer.get('callee') == 'workerSetMemoryBlockData':
            rows.append({'source': {k: symbol[k] for k in ['id', 'name', 'path', 'line']}, 'mode': consumer['mode'],
                         'callee': consumer.get('callee'), 'evidence': consumer['evidence'],
                         'dependencies': [{'api': nodes[d['api']]['name'], 'path': d['path'],
                                           'excluded_paths': d.get('excluded_paths', []),
                                           'conditions': d.get('conditions', [])} for d in consumer['value_dependencies']]})
    return rows


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--facts', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = inspect(json.loads(a.facts.read_text(encoding='utf-8')))
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps([{'name': r.get('name', r.get('source', {}).get('name')), 'mode': r.get('mode'),
                       'projection': r.get('boundary_projection'),
                       'paths': [(d['api'], d['path']) for d in r.get('dependencies', [])]} for r in result], ensure_ascii=False))
