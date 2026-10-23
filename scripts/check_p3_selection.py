"""Validate published P3 selection evidence, keeping remaining gates open."""
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


def check():
    base=ROOT/'experiments/2026-10-23-p3'
    raw=(base/'evidence/selection.json').read_text(encoding='utf-8')
    assert not re.search(r'[A-Za-z]:[\\/]+Users[\\/]',raw)
    r=json.loads(raw);manifest=json.loads((base/'selection-manifest.json').read_text(encoding='utf-8'))
    assert r['source_commit']==manifest['source_commit']
    assert r['snapshot']==r['source_commit']+':p3-data-v2'
    assert r['counts']['files']==len(manifest['files'])==140
    assert r['phase_status']=='P3_in_progress'
    assert r['gates']=={'D01':'pass','D02':'incomplete','D03':'incomplete','D04':'pass','D05':'incomplete'}
    assert re.fullmatch('[0-9a-f]{40}',r['rules_revision'])
    assert len(r['database_paths'])==4 and len(r['instance_paths'])==2
    for p in [*r['database_paths'].values(),*r['instance_paths'].values()]:
        assert p['found'] and len(p['nodes'])==len(p['edges'])+1
        for a,b,e in zip(p['nodes'],p['nodes'][1:],p['edges']):
            assert (e['source'],e['target'])==((b['id'],a['id']) if p['reverse'] else (a['id'],b['id']))
            assert e['evidence']
    resolution=r['iterator_call']['resolution']
    assert not resolution['gaps'] and resolution['runtime_instance']=='unknown'
    assert resolution['candidates'][0]['template_bindings']['T']['names']==['Dic::Module::Timeline::VirtualTraceDatabase']
    for suffix in ['DBConnectionPool<T>::GetConnection','DBConnectionPool<T>::CreatConnection']:
        assert any(f['name'].endswith(suffix) for f in r['receiver_functions'])
    for label,entries in [('db',['DataType::DB']),('text',['DataType::TEXT','default'])]:
        condition=next(c for c in r['factory_conditions'][label] if c['kind']=='switch_label')
        assert condition['entry_labels']==entries
    assert any(c['kind']=='early_exit_guard' and c['when'] is False for c in r['factory_conditions']['derived_db'])
    assert r['instance']['kind']=='static_local_object'
    assert r['instance']['identity_scope']=='process_and_link_image'
    assert r['accessor']['instance']==r['instance']['id'] and len(r['setter_call_contexts'])>=2
    for p in r['instance_paths'].values():
        assert {n['instance'] for n in p['nodes'] if 'instance' in n}=={r['instance']['id']}
        edge=next(e for e in p['edges'] if e['kind']=='INSTANCE_VALUE_READ_BY')
        assert {'process_and_link_image','matching_runtime_key','write_reaches_read_without_intervening_update'}<=set(edge['conditions'])
    assert 'unseen_callers_remain_unknown' in r['instance_limits']
    assert r['receiver_runtime_conditions'] and r['remaining']
    assert r['python_tests']['passed'] and r['python_tests']['count']>=114
    storage=r['storage']
    assert (storage['nodes'],storage['edges'])==(r['counts']['nodes'],r['counts']['edges'])
    assert all(storage[k] for k in ['payload_roundtrip','stored_queries_pass','replace_delete_restore'])
    assert storage['native_rows_unchanged']==790 and storage['buffer_pool_mb']>0
    assert re.fullmatch('[0-9a-f]{40}',storage['adapter_revision'])
    for name in ['cpp_data','cpp_value_types','cpp_control','cpp_instances','data_graph','data_queries']:
        source=(ROOT/'adapters'/f'{name}.py').read_text(encoding='utf-8')
        assert not any(s in source for s in ['QueryUnitFlows','getUnitFlows','DataBaseManager','unitAllFlows','reference.json','score_increment','selection-manifest']),name
    assert r['file_hash_verification']=='not_run_per_user_preference'
    print('OK: P3 D01/D04 selected-source evidence and Kuzu lifecycle; D02/D03/D05 remain incomplete; no file hash verification.')


if __name__=='__main__':check()
