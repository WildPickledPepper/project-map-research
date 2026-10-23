"""Refresh encoding paths and attach source constant guards to the P3 graph."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.cpp_data import DataExtractor
from adapters.cpp_transmission import Transmission
from adapters.cpp_source_conditions import extract_conditions
from adapters.transmission_graph import augment_transmission
from adapters.sqlite_fact_graph import _prepare


def augment(base, data, transmission, conditions):
    graph = deepcopy(base)
    old = graph.pop('cpp_transmission')
    owned = {r['id'] for group in ['sources', 'transmissions'] for r in old[group]}
    graph['nodes'] = [n for n in graph['nodes'] if n['id'] not in owned]
    graph['edges'] = [e for e in graph['edges'] if e['source'] not in owned and e['target'] not in owned]
    graph['diagnostics'] = [g for g in graph['diagnostics'] if g not in old['diagnostics']]
    graph = augment_transmission(graph, data.facts, transmission, base['input_paths'])
    graph['source_conditions'] = conditions
    for group, kind in [('constants', 'source_constant_member'), ('guards', 'source_constant_guard')]:
        for record in conditions[group]:
            e = record['evidence'][0]
            graph['nodes'].append({**record, 'kind': kind, 'name': kind, 'path': e['path'], 'line': e['line']})
    for guard in conditions['guards']:
        graph['edges'].append({'source': guard['constant'], 'target': guard['id'], 'kind': 'SOURCE_CONSTANT_CONTROLS_GUARD',
                               'status': 'source_fact', 'evidence': guard['evidence']})
    graph['snapshot'] = graph['source_commit'] + ':p3-data-v13'
    graph['provenance']['chain_closure_base_snapshot'] = base['snapshot']
    graph['extractors']['cpp_source_conditions'] = 'cpp_source_conditions/' + conditions['version']
    _prepare(graph)
    return graph


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ['source', 'base', 'output']: ap.add_argument('--' + name, type=Path, required=True)
    a = ap.parse_args(); source = a.source.resolve()
    if a.output.resolve().is_relative_to(ROOT): raise ValueError('Keep generated graphs outside Git')
    graph = json.loads(a.base.read_text(encoding='utf-8')); paths = graph['input_paths']
    if subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() != graph['source_commit']: raise ValueError('Source version mismatch')
    if any(PurePosixPath(p).is_absolute() or '\\' in p or not (source/p).resolve().is_relative_to(source) for p in paths): raise ValueError('Input escapes source')
    import tree_sitter_language_pack as pack
    if os.environ.get('PROJECT_MAP_PARSER_CACHE'): pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))
    data = DataExtractor({p: (source/p).read_bytes() for p in paths if PurePosixPath(p).suffix in {'.h', '.hpp', '.cpp', '.cc', '.cxx'}}, pack.get_parser('cpp'))
    flow = Transmission(data).build(); constants = extract_conditions(data)
    result = augment(graph, data, flow, constants)
    a.output.mkdir(parents=True, exist_ok=False)
    (a.output/'graph.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'nodes': len(result['nodes']), 'edges': len(result['edges']), 'constant_guards': len(constants['guards']),
                      'transmission_paths': sum(len(t['traces']) for t in flow['transmissions'])}))
