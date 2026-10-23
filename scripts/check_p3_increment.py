"""Validate P3 incremental evidence without marking unfinished gates complete."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def check():
    base=ROOT/'experiments/2026-10-23-p3';r=json.loads((base/'evidence/increment.json').read_text(encoding='utf-8'))
    m=json.loads((base/'input-manifest.json').read_text(encoding='utf-8'))
    assert r['source_commit']==m['source_commit'] and r['counts']['files']==len(m['files'])==134
    assert r['phase_status']=='P3_in_progress' and set(r['gates'].values())=={'incomplete'}
    assert all(r['assertions'].values()) and r['remaining']
    for p in r['paths'].values():
        assert p['found'] and len(p['nodes'])==len(p['edges'])+1
        for a,b,e in zip(p['nodes'],p['nodes'][1:],p['edges']):
            assert (e['source'],e['target'])==((b['id'],a['id']) if p['reverse'] else (a['id'],b['id']))
            assert e['evidence']
    assert r['receiver']['runtime_selection']=='unknown'
    assert len(r['receiver']['factory_candidates'])==3 and not r['receiver']['truncated']
    for name in ['adapters/cpp_data.py','adapters/data_graph.py','adapters/data_queries.py','scripts/build_data_graph.py']:
        source=(ROOT/name).read_text(encoding='utf-8')
        assert not any(s in source for s in ['QueryUnitFlows','getUnitFlows','DataBaseManager','unitAllFlows','reference.json','score_increment']),name
    assert r['file_hash_verification']=='not_run_per_user_preference'
    print('OK: P3 incremental source/query evidence; D01-D05 remain incomplete; no file hash verification.')


if __name__=='__main__':check()
