"""Validate published contextual response routes and explicit remaining scope."""
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


def check():
    base=ROOT/'experiments/2026-10-23-p3';raw=(base/'evidence/response-routing.json').read_text(encoding='utf-8')
    assert not re.search(r'[A-Za-z]:[\\/]+Users[\\/]',raw)
    r=json.loads(raw);manifest=json.loads((base/'response-manifest.json').read_text(encoding='utf-8'))
    assert r['source_commit']==manifest['source_commit'] and r['snapshot']==r['source_commit']+':p3-data-v5'
    assert r['counts']['files']==len(manifest['files'])==148
    assert r['phase_status']=='P3_in_progress' and r['gate_under_test']=='D02_incomplete'
    assert re.fullmatch('[0-9a-f]{40}',r['rules_revision'])
    assert len(r['routes'])==r['counts']['routes']==4 and not r['query']['truncated']
    assert len({route['object_root'] for route in r['routes']})==1
    def value(record,key):return record[key] if key in record else r['shared_records'][record[key+'_ref']]
    for route in r['routes']:
        assert len(route['steps'])==6 and route['protocol_owner']=='Dic::Protocol::TimelineProtocol'
        assert route['steps'][-1]['key']=='unit/flows'
        assert route['body_write_sites']==(7 if route['send_line'] in {61,65} else 0)
        assert route['body_links']==(182 if route['body_write_sites'] else 0)
        assert len({tuple(m['wire_path']) for m in value(route,'field_mappings')})==34
        assert all(a['callee']==b['caller'] for a,b in zip(route['steps'],route['steps'][1:]))
        assert all(s['evidence_refs'] for s in route['steps'])
    def references(value):
        if isinstance(value,dict):
            if 'evidence_refs' in value:assert set(value['evidence_refs'])<=set(r['source_evidence'])
            for key,item in value.items():
                if key.endswith('_ref'):assert item in r['shared_records']
            for item in value.values():references(item)
        elif isinstance(value,list):
            for item in value:references(item)
    references(r)
    paths={f['path'] for f in manifest['files']}
    assert all(e['path'] in paths and e['line']>0 for e in r['source_evidence'].values())
    assert any(g['kind']=='operator_transfer_not_expanded' for g in r['gaps']) and r['remaining']
    assert r['python_tests']['passed'] and r['python_tests']['count']>=154
    assert r['storage']['payload_roundtrip'] and r['storage']['stored_response_query_pass']
    assert r['storage']['native_rows_unchanged']==790
    assert (r['storage']['nodes'],r['storage']['edges'])==(r['counts']['nodes'],r['counts']['edges'])
    for module in ['cpp_response_routing','response_queries']:
        source=(ROOT/'adapters'/f'{module}.py').read_text(encoding='utf-8')
        assert not any(word in source for word in ['UnitFlowsResponse','unitAllFlows','ToUnitFlowsResponseJson','WsSession','SendResponse','reference.json','response-manifest']),module
    assert r['file_hash_verification']=='not_run_per_user_preference'
    print('OK: four scoped response routes, field-write ordering, isolation and persisted query; D02 remains incomplete.')


if __name__=='__main__':check()
