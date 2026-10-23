"""Validate the published serializer increment without completing D02."""
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


def check():
    base=ROOT/'experiments/2026-10-23-p3';raw=(base/'evidence/serialization.json').read_text(encoding='utf-8')
    assert not re.search(r'[A-Za-z]:[\\/]+Users[\\/]',raw)
    r=json.loads(raw);manifest=json.loads((base/'output-manifest.json').read_text(encoding='utf-8'))
    assert r['source_commit']==manifest['source_commit'] and r['counts']['files']==len(manifest['files'])==141
    assert r['snapshot']==r['source_commit']+':p3-data-v4'
    assert r['phase_status']=='P3_in_progress' and r['gate_under_test']=='D02_incomplete'
    assert re.fullmatch('[0-9a-f]{40}',r['rules_revision'])
    mappings=r['mappings'];paths={tuple(m['wire_path']) for m in mappings}
    assert len(paths)==r['counts']['callback_wire_paths']==34
    assert len(mappings)==r['counts']['callback_mapping_variants']==55
    assert len([p for p in paths if p[0]=='body'])==r['counts']['body_paths']==26
    for m in mappings:
        assert m['selectors']==['element' if p=='*' else 'member:'+p for p in m['wire_path']]
        assert m['evidence'] and not any(c.get('kind')=='unresolved_overload_requirement' for c in m['conditions'])
    assert r['callback']['registration']['key']=='unit/flows'
    assert r['callback_gaps'] and all(g['wire_path'][0]=='type' for g in r['callback_gaps'])
    assert r['previous_production_query']['write_sites']==7 and not r['previous_production_query']['truncated']
    assert r['producer_serializer_join']=='pending_protocol_and_response_instance_context' and r['remaining']
    assert r['python_tests']['passed'] and r['python_tests']['count']>=142
    assert r['storage']['payload_roundtrip'] and r['storage']['stored_serialization_query_pass']
    assert r['storage']['native_rows_unchanged']==790
    assert (r['storage']['nodes'],r['storage']['edges'])==(r['counts']['nodes'],r['counts']['edges'])
    for module in ['cpp_serialization','cpp_library_types','serialization_queries']:
        source=(ROOT/'adapters'/f'{module}.py').read_text(encoding='utf-8')
        assert not any(word in source for word in ['UnitFlowsResponse','unitAllFlows','ToUnitFlowsResponseJson','JsonUtil','reference.json','output-manifest']),module
    assert r['file_hash_verification']=='not_run_per_user_preference'
    print('OK: scoped serialization mappings, registration and persisted query; D02 remains incomplete; no file hash verification.')


if __name__=='__main__':check()
