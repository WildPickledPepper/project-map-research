"""Check combined D01-D05 evidence and the registered cross-module case."""
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'experiments/2026-10-23-p3'))
from run_response_routing import expand


def check():
    base = ROOT/'experiments/2026-10-23-p3'
    raw = (base/'evidence/combined.json').read_text(encoding='utf-8')
    assert not re.search(r'[A-Za-z]:[\\/]+Users[\\/]', raw)
    report = expand(json.loads(raw)); chain = report['chain']
    manifest = json.loads((base/'server-channels-manifest.json').read_text(encoding='utf-8'))
    assert report['source_commit'] == manifest['source_commit']
    assert report['snapshot'] == report['source_commit'] + ':p3-data-v13'
    assert re.fullmatch('[0-9a-f]{40}', report['rules_revision'])
    assert report['phase_status'] == 'P3_complete_selected_source_scope'
    assert report['gates'] == {k: 'pass' for k in ['D01', 'D02', 'D03', 'D04', 'D05']}
    assert report['counts']['files'] == len(manifest['files']) == 154
    assert chain['status'] == 'conditional_source_chain' and not chain['truncated']
    summary = chain['summary']
    assert summary['response_exits'] == 4 and summary['transmission_paths'] == 16
    assert len(summary['states']) == 2 and set(summary['reverse_states'].values()) == {4}
    assert summary['database_reverse_paths'] == 2
    assert report['stages']['production'] == 7 and len(report['stages']) == 12
    paths = {f['path'] for f in manifest['files']}
    assert all(e['path'] in paths and e['line'] > 0 for e in chain['evidence'].values())
    assert all(r['source'] in chain['nodes'] and r['target'] in chain['nodes'] and r['evidence'] and
               all(e in chain['evidence'] for e in r['evidence']) for r in chain['relations'])
    controls = [r for r in chain['relations'] if r['stage'] == 'source_conditions']
    assert len(controls) == 3 and all(r['value'] is False for r in controls)
    assert all(report['negative_checks'].values()) and all(report['return_checks']['negative_checks'].values())
    assert report['selection']['instance']['kind'] == 'static_local_object'
    assert all(p['found'] for p in report['selection']['database_paths'].values())
    assert all(p['found'] for p in report['selection']['instance_paths'].values())
    assert chain['gaps'] and chain['unexpanded'] and not chain['coverage']['whole_repository']
    assert chain['runtime_observation'] == 'not_executed_in_P3'
    assert report['tests']['passed'] and report['tests']['python'] >= 237 and report['tests']['typescript'] >= 76
    s = report['storage']; assert s['payload_roundtrip'] and s['combined_gates_pass'] and s['native_rows_unchanged'] == 790
    assert (s['nodes'], s['edges']) == (report['counts']['nodes'], report['counts']['edges'])
    assert report['file_hash_verification'] == 'not_run_per_user_preference'
    case = (ROOT/'cases/memory-usage/README.md').read_text(encoding='utf-8')
    assert '待 P7 冻结规则后执行' in case and 'Memory/view/memoryUsage' in case
    for name in ['chain_queries.py', 'cpp_encoding.py', 'cpp_source_conditions.py']:
        text = (ROOT/'adapters'/name).read_text(encoding='utf-8')
        assert not any(s in text for s in ['unit/flows', 'unitAllFlows', 'useResponseQueue', 'GbkToUtf8', 'QueryUnitFlows', 'Memory/view'])
    print('OK: P3 D01-D05 pass together on the selected 154-file source graph; P4-P7 remain.')


if __name__ == '__main__': check()
