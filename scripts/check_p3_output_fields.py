"""Check published response production evidence without completing D02."""
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


def check():
    base=ROOT/'experiments/2026-10-23-p3';raw=(base/'evidence/output-fields.json').read_text(encoding='utf-8')
    assert not re.search(r'[A-Za-z]:[\\/]+Users[\\/]',raw)
    r=json.loads(raw);m=json.loads((base/'output-manifest.json').read_text(encoding='utf-8'))
    assert r['source_commit']==m['source_commit'] and r['counts']['files']==len(m['files'])==141
    assert r['snapshot']==r['source_commit']+':p3-data-v3'
    assert r['phase_status']=='P3_in_progress' and r['gate_under_test']=='D02_incomplete'
    assert re.fullmatch('[0-9a-f]{40}',r['rules_revision'])
    p=r['production'];assert (p['db_write_sites'],p['text_write_sites'])==(5,2)
    assert len(p['selected_effects'])==len({e['write'] for e in p['selected_effects']})==7 and not p['truncated']
    for effect in p['selected_effects']:
        assert effect['root']==r['response_object']['id']
        assert effect['selectors']==['pointee','member:body','member:unitAllFlows']
        assert effect['evidence'] and effect['condition_scopes'] and effect['runtime_execution']=='unknown'
        first,last=effect['call_chain']
        assert first['caller']==r['entry']['id'] and last['callee']==effect['writer'] and first['callee']==last['caller']
        for call in effect['call_chain']:assert call['actual'] and call['evidence'] and call['runtime_target']=='unknown'
    assert r['unresolved_query_gaps'] and r['remaining']
    assert r['python_tests']['passed'] and r['python_tests']['count']>=126
    assert r['storage']['payload_roundtrip'] and r['storage']['stored_output_query_pass']
    assert r['storage']['native_rows_unchanged']==790
    assert (r['storage']['nodes'],r['storage']['edges'])==(r['counts']['nodes'],r['counts']['edges'])
    for module in ['cpp_field_flow','field_queries']:
        source=(ROOT/'adapters'/f'{module}.py').read_text(encoding='utf-8')
        assert not any(word in source for word in ['QueryUnitFlows','unitAllFlows','responsePtr','TextTraceDatabase','reference.json','output-manifest']),module
    assert r['file_hash_verification']=='not_run_per_user_preference'
    print('OK: P3 response production, scoped argument substitution and stored query; D02 remains incomplete; no file hash verification.')


if __name__=='__main__':check()
