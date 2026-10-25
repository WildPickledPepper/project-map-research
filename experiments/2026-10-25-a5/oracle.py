"""Compute fixture expectations without invoking the product parser or querying its database."""
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import re
import sqlite3

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('primitive_fixture', HERE.parent/'2026-10-25-static-async/inspect_fixture.py')
primitive = importlib.util.module_from_spec(spec); spec.loader.exec_module(primitive)


def expectations(source, snapshot_path=None):
    fixtures = Path(source)/'server/src/test/test_data'
    communication = json.loads((fixtures/'cluster_analysis_output/cluster_communication.json').read_text(encoding='utf-8'))
    steps = sorted({re.fullmatch(r'step(\d+)', step).group(1) for category in communication.values()
                    for step in category if re.fullmatch(r'step(\d+)', step)}, key=int)
    with (snapshot_path or fixtures/'snapshot/snapshot_expandable.pkl').open('rb') as f:
        snapshot = primitive.PrimitiveSnapshot(f).load()
    devices = {}
    for device, traces in enumerate(snapshot['device_traces']):
        active = {}; lifetimes = []; initial = []
        for index, item in enumerate(traces):
            action = item['action']; address = item.get('addr')
            if action == 'alloc':
                if address in active: raise ValueError('Fixture allocates an already active address')
                block = {'alloc': index, 'free': -1, 'address': address, 'requested_size': item['size']}
                active[address] = block; lifetimes.append(block)
            elif action in ('free_completed', 'free'):
                block = active.pop(address, None)
                if block is None:
                    block = {'alloc': -1, 'free': index, 'address': address, 'requested_size': item['size']}
                    initial.append(block)
                else: block['free'] = index
        for segment in snapshot['segments']:
            if segment['device'] != device: continue
            for item in segment['blocks']:
                if item['state'] == 'inactive': continue
                if item['address'] not in active:
                    initial.append({'alloc': -1, 'free': -1, 'address': item['address'], 'requested_size':item['requested_size']})
        devices[str(device)] = {'events': len(traces), 'positive_lifetimes':lifetimes, 'initial_lifetimes':initial,
            'expected_blocks':len(lifetimes)+len(initial), 'actions':dict(Counter(t['action'] for t in traces))}
    raw = fixtures/'full_db/leaks_dump_20250806.dat'
    connection=sqlite3.connect(raw.resolve().as_uri()+'?mode=ro',uri=True)
    live={}; memscope={}
    for event,kind,device,ptr,attr in connection.execute('SELECT Event,"Event Type","Device Id",Ptr,Attr FROM leaks_dump WHERE Event IN (\'MALLOC\',\'FREE\') ORDER BY "Timestamp(ns)", ID'):
        fields=json.loads(attr);size=int(fields.get('size',0));key=(device,kind,ptr)
        if not size:continue
        if event=='MALLOC' and key not in live:live[key]=(ptr,abs(size))
        elif event=='FREE' and key in live:memscope.setdefault(device+':'+kind,[]).append(live.pop(key))
    for (device,kind,_),block in live.items():memscope.setdefault(device+':'+kind,[]).append(block)
    connection.close()
    return {'evidence_kind':'independent_public_input_oracle', 'communication_steps':steps, 'devices':devices,'memscope':memscope,
            'method':'forward allocation/free ledger plus final active segments; no product parser imports or product database reads',
            'file_hash_verification':'not_run_per_user_preference'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--source',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); result=expectations(a.source); a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'steps':result['communication_steps'],'devices':{k:{'expected_blocks':v['expected_blocks'],'actions':v['actions']} for k,v in result['devices'].items()}}))
