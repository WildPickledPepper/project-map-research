"""Score development replays and separately frozen, new protocol references."""
import argparse
import importlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
scoring = importlib.import_module('experiments.2026-10-24-a4.score_chains')
from adapters.return_bridge_queries import explain_return_bridge


def run(graph_path, output):
    output.mkdir(parents=True, exist_ok=False)
    old_ref = ROOT/'experiments/2026-10-24-a4/reference-reviewed.json'
    score = scoring.run(graph_path, old_ref, output/'development-replay')
    score.update(evidence_kind='executed_post_repair_development_regression',
                 extraction_rules_adapted_to_six_cases=True, independent_holdout=False,
                 scope='post-repair development replay; six cases used to locate mechanism gaps; not an independent holdout')
    (output/'development-replay/first-results.json').write_text(json.dumps(score, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    graph = json.loads(graph_path.read_text(encoding='utf-8'))
    nodes = {n['id']: n for n in graph['nodes']}
    reference = json.loads(old_ref.read_text(encoding='utf-8'))
    consumers = []
    for case, row in zip(reference['cases'], score['cases']):
        pairs = [p for p in row.get('actual_pairs', []) if p['correct']]
        found = []
        if pairs:
            result = explain_return_bridge(graph, pairs[0]['provider'], field_path=case['field'])
            for link in result['links']:
                for item in link.get('consumers', []):
                    consumer = item['consumer']; symbol = nodes[consumer['source_symbol']]
                    if symbol['path'] == case['consumer_path']:
                        found.append({'source': {k:symbol[k] for k in ('id','name','path','line')},
                            'mode': consumer['mode'], 'evidence': consumer['evidence'], 'conditions': consumer['conditions'],
                            'dependencies': [d['path'] for d in consumer['matching_dependencies']]})
        consumers.append({'id':case['id'], 'expected':case['consumer'], 'state':case['state'], 'found':found})
    new_ref = json.loads((Path(__file__).parent/'new-reference.json').read_text(encoding='utf-8'))
    providers = {p['id']:p for p in graph['protocol']['providers']}
    def protocols(reference):
        rows = []
        for case in reference['cases']:
            entries = [r for r in graph['protocol']['results'] if r['name'] == case['api'] and
                       nodes.get(r['consumer'].removeprefix('protocol:'),{}).get('path') == case['api_path']]
            pairs = []
            for entry in entries:
                for match in entry['matches']:
                    p = providers[match['provider']]
                    pairs.append({'provider':p['id'], 'correct':scoring.provider_correct(case,p,[nodes[t] for t in p['handler_methods']])})
            rows.append({'id':case['id'], 'api':case['api'], 'outcome':scoring.classify_outcome(entries,pairs),
                         'source_coordinate_matched':any(nodes.get(e['consumer'].removeprefix('protocol:'),{}).get('line')==case['source_call_line'] for e in entries),
                         'entries':entries, 'pairs':pairs})
        return rows
    rows = protocols(new_ref)
    final_ref = json.loads((Path(__file__).parent/'final-reference.json').read_text(encoding='utf-8'))
    final_rows = protocols(final_ref)
    result = {'source_commit':graph['source_commit'], 'build_version':graph['version']['build_version'],
        'development_counts':score['counts'], 'development_consumers':consumers,
        'new_reference':new_ref, 'new_protocol_cases':rows,
        'new_protocol_passed':all(r['outcome']=='correct_unique_conditional' for r in rows),
        'supplementary_cases_reused_for_development':True,
        'final_reference':final_ref, 'final_protocol_cases':final_rows,
        'final_protocol_passed':all(r['outcome']=='correct_unique_conditional' and r['source_coordinate_matched'] for r in final_rows),
        'runtime_reproduced':False, 'historical_validation_records_used_for_tuning':False}
    (output/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'development':score['counts'], 'new':[(r['id'],r['outcome']) for r in rows], 'final':[(r['id'],r['outcome']) for r in final_rows]}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--graph', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); run(a.graph.resolve(), a.output.resolve())
