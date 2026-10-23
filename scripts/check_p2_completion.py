"""Validate published P2 evidence; do not rebuild sources or verify file hashes."""
import json
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]


def check():
    base=ROOT/'experiments/2026-10-23-p2'
    raw=(base/'evidence/completion.json').read_text(encoding='utf-8')
    assert not re.search(r'[A-Za-z]:[\\/]+Users[\\/]',raw)
    r=json.loads(raw);manifest=json.loads((base/'input-manifest.json').read_text(encoding='utf-8'))
    assert r['facts']['source_commit']==manifest['source_commit']
    assert r['checks']=={f'L{i:02d}':'pass' for i in range(1,7)}
    assert r['facts']['counts']['files']==len(manifest['files'])==133
    assert sum(r['facts']['counts']['statuses'].values())==r['facts']['counts']['results']
    assert len(r['facts']['cases'])==3 and len(r['facts']['cross_request_checks'])==6
    for case in r['facts']['cases'].values():
        assert case['status']=='matched_conditional'
        for key in ['forward','reverse']:
            p=case[key];assert p['found'] and len(p['nodes'])==len(p['edges'])+1
            for a,b,e in zip(p['nodes'],p['nodes'][1:],p['edges']):
                assert (e['source'],e['target'])==((b['id'],a['id']) if p['reverse'] else (a['id'],b['id']))
                assert e['status']=='conditional' and e['conditions'] and e['evidence']
    assert all(not x['forward_found'] and not x['reverse_found'] for x in r['facts']['cross_request_checks'])
    assert all(x['passed'] for x in r['tests'].values())
    assert r['tests']['python']['count']>=73 and r['tests']['typescript']['count']>=22
    assert all(r['lifecycle'][k] for k in ['payload_roundtrip','stored_forward_reverse_paths','replacement_removes_protocol_edges','deletion_removes_snapshot','restored'])
    assert r['reuse']['rules_frozen_before_final_run'] and r['reuse']['assessment_after_extraction']
    for module in r['reference_independence']['extraction_modules']:
        source=(ROOT/module).read_text(encoding='utf-8')
        assert not any(word in source for word in ['unit/flows','getUnitFlows','QueryFlowsBySliceInfoHandler','timeline/rankOffset','create/curve','reference.json','score_graph']),module
    assert not r['reference_independence']['builder_reads_reference']
    assert r['file_hash_verification']=='not_run_per_user_preference'
    print('OK: P2 L01-L06 evidence, source-derived identities, scoped paths, rename/negative fixtures and Kuzu lifecycle; no file hash verification.')


if __name__=='__main__':check()
