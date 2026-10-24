"""Package partial, first repair observations without calling them a full score."""
import argparse
import json
from pathlib import Path

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); a.output.mkdir(parents=True, exist_ok=True)
    protocol = json.loads((a.run/'build/protocol-checkpoint.json').read_text(encoding='utf-8'))['protocol']
    raw = json.loads((a.run/'build/typescript_protocol_flow.cjs.json').read_text(encoding='utf-8'))
    nodes = {n['id']:n for n in raw['nodes']}
    providers = {p['id']:p for p in protocol['providers']}
    ref = json.loads((Path(__file__).parent/'new-reference.json').read_text(encoding='utf-8'))
    rows = []
    for case in ref['cases']:
        entries = [r for r in protocol['results'] if r['name']==case['api'] and nodes.get(r['consumer'].removeprefix('protocol:'),{}).get('path')==case['api_path']]
        pairs = []
        for entry in entries:
            for match in entry['matches']:
                provider = providers[match['provider']]
                evidence = [e for m in provider['dispatch_evidence'] for e in m['evidence']]
                pairs.append({'provider':provider['id'], 'correct':provider['command']==case['command'] and case['scope'] in provider['scope_values'] and
                    any(e.get('path')==case['handler_path'] and case['handler_suffix'] in e.get('expression','') for e in evidence)})
        rows.append({'id':case['id'], 'entry_count':len(entries), 'pairs':pairs,
            'outcome':'omission' if not entries else 'correct_unique_conditional' if len(pairs)==1 and pairs[0]['correct'] else 'unresolved_or_wrong'})
    cost = json.loads((a.run/'result.json').read_text(encoding='utf-8'))
    result = {'evidence_kind':'executed_partial_first_repair_protocol_phase', 'rules_commit':'2631af8',
        'reference_frozen_commit':'1cd0b0e','new_cases':rows,
        'scoring_basis':'compiler consumer source identity and C++ dispatch source header/path; complete graph was not published',
        'build':cost,'manual_stop':{'phase':'typescript_return_flow','reason':'return phase CPU/memory growth after expanding collection rules into transport interpretation',
            'automatic_budget_stop':False,'partial_graph_published':False},
        'scope':'supplementary first output; cases reused for later development repair, not a new independent score'}
    (a.output/'first-repair.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
