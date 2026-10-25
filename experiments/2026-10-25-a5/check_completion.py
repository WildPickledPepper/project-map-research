"""Check the committed A5 evidence contract without starting product services."""
from pathlib import Path
import json
import re

HERE=Path(__file__).resolve().parent
read=lambda name:json.loads((HERE/'evidence'/name).read_text(encoding='utf-8'))
validation=read('validation.json');runtime=read('runtime.json');mapping=read('mapping.json');resources=read('resources.json')
assert validation['passed'] and all(validation['gates'].values())
assert runtime['accepted_scenarios']==8 and runtime['selected_requests']==45
assert runtime['normal_or_restored_passes']==7 and runtime['controlled_product_failures']==1
assert runtime['capture_corruption_controls']==runtime['capture_corruption_rejected']==24
assert len({r['source_commit'] for r in runtime['runs']})==1
assert mapping['graph']['source_commit']==runtime['source_commit']
assert mapping['graph']['nodes']>280000 and mapping['graph']['inputs']>2300
assert read('build-receipt-audit.json')['passed']
assert len(mapping['runs'])==8 and all(r['same_context_overlay'] for r in mapping['runs'])
assert mapping['compatibility_controls']['changed_source_admission_rejected']
assert not mapping['compatibility_controls']['changed_fault_overlay']
for run in runtime['runs']:
    assert run['accepted'] and run['capture_complete']
    assert run['independent_blocks_passed'] != run['fault']
    assert all(c['rejected'] for c in run['capture_negative_controls'])
    assert all(g['completed'] for g in run['worker_generations'])
    assert run['page_errors']==0
    ids=[(r['connection'],r['request_id']) for r in run['requests']]
    assert len(ids)==len(set(ids))
    for request in run['requests']:
        assert request['trace_id']
        assert all(request['native_stages'][stage]==1 for stage in ('request.decoded','handler.invoke','database.call','database.return','handler.complete'))
scheduling=next(r for r in runtime['runs'] if r['label']=='communication')['scheduling']
assert [t['status'] for t in scheduling['iterations']]==['pending','pending','resolved']
assert scheduling['cancelledTrailingSent']==0
assert len([t for t in scheduling['tasks'] if t['name'].startswith('cancel-leading') and t['status']=='rejected'])==2
fault=next(r for r in runtime['runs'] if r['fault'])
assert fault['blocks'][0]['missing']==1 and fault['blocks'][0]['extra']==0
cache=next(r for r in resources['runs'] if r['run']=='a5-final-cache-01')['phases']
assert cache[0]['file_bytes']>0 and cache[1]['file_bytes']==cache[0]['file_bytes']
assert cache[2]['entry_count']==cache[2]['file_bytes']==0 and cache[3]['file_bytes']>0
for path in (HERE/'evidence').glob('*.json'):
    assert not re.search(r'[A-Za-z]:[\\/]|/home/|/Users/',path.read_text(encoding='utf-8')),path
print(f"OK: A5 {len(validation['gates'])} gates; 8 scenarios, 45 requests, 24 capture controls; expected fault retained.")
