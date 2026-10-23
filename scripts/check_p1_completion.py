"""Check published P1 completion evidence and extraction/assessment separation."""
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
BASE=ROOT/'experiments/2026-10-23-p1-completion'


def read(name):
    text=(BASE/'evidence'/name).read_text(encoding='utf-8')
    assert not re.search(r'[A-Za-z]:[\\/]+(?:Users|workspace)[\\/]',text),name
    return json.loads(text)


def check():
    report=read('completion.json');facts=report['facts']
    manifest=json.loads((ROOT/'experiments/2026-10-23-p1/evidence/input-manifest.json').read_text(encoding='utf-8'))
    assert facts['source_commit']==manifest['source_commit']
    assert report['checks']=={f'F{i:02d}':'pass' for i in range(1,6)}
    counts=facts['counts']
    assert sum(counts['node_kinds'].values())==counts['nodes']==9031
    assert sum(counts['edge_kinds'].values())==counts['edges']==8580
    assert sum(counts['call_resolutions'].values())==counts['node_kinds']['call_site']
    assert {r['path'] for r in facts['coverage']}=={r['path'] for r in manifest['files']}
    assert all(n['reason'] for n in facts['unresolved_examples'])
    for p in facts['paths'].values():
        assert p['found'] and len(p['edges'])+1==len(p['nodes'])
        for a,b,e in zip(p['nodes'],p['nodes'][1:],p['edges']):
            assert (e['source'],e['target'])==((b['id'],a['id']) if p['reverse'] else (a['id'],b['id']))
            assert e['kind'] and e['status'] and e['evidence']
    assert any(e['kind']=='PASSES_CALLBACK' for e in facts['paths']['frontend']['edges'])
    for label in ('db','text'):
        assert any(e['kind']=='OVERRIDE_CANDIDATE' and e['status']=='candidate' for e in facts['paths'][label]['edges'])
    for store in report['lifecycle'].values():
        assert store['nodes']==counts['nodes'] and store['edges']==counts['edges']
        for key in ('payload_roundtrip','stored_graph_case_paths_pass','replacement_removes_old_edges','deletion_removes_snapshot','other_snapshot_preserved','restored'):
            assert store[key]
    assert all(q['same_results'] and q['rows'] for q in report['direct_database_queries'].values())
    independence=report['reference_independence']
    assert independence['scorer_runs_after_extraction'] and not independence['manual_reference_read_by_builder']
    for module in independence['extraction_modules']:
        source=(ROOT/module).read_text(encoding='utf-8')
        assert not any(s in source for s in ('reference.json','score_graph','getUnitFlows','QueryUnitFlows','unit/flows')),module
    fixture=read('fixtures.json')
    assert fixture['checks']['cpp_query_occurrences']==7
    assert all(fixture['checks'].values())
    # Re-check published fixture edge endpoints and statuses through the same
    # portable storage validator; fixtures remain authored inputs, not case truth.
    from adapters.sqlite_fact_graph import _prepare
    for name,graph in fixture['graphs'].items():_prepare({'snapshot':'fixture/'+name,**graph})
    independent=read('codegraph-storage.json')
    assert independent
    assert report['file_hash_verification']=='not_run_per_user_preference'
    assert 'P2 protocol joins' in report['untested']
    print('OK: P1 F01-F05 evidence, typed paths, two-store lifecycle, fixtures and extraction independence; no file hash verification.')


if __name__=='__main__':check()
