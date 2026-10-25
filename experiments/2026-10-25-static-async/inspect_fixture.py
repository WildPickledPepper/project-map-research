"""Summarize the public snapshot fixture without importing pickle classes."""
import argparse
import json
import pickle
from pathlib import Path


class PrimitiveSnapshot(pickle.Unpickler):
    def find_class(self, module, name):
        raise ValueError('Fixture requires a nonprimitive pickle class: '+module+'.'+name)

    def persistent_load(self, identifier):
        raise ValueError('Persistent pickle objects are outside this fixture inspection')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();relative='server/src/test/test_data/snapshot/snapshot_expandable.pkl';path=a.source/relative
    with path.open('rb') as stream:value=PrimitiveSnapshot(stream).load()
    segments=value.get('segments',[]);traces=value.get('device_traces',[])
    result={'evidence_kind':'executed_public_fixture_input_inspection','path':relative,'bytes':path.stat().st_size,
        'root_keys':sorted(value),'segments':len(segments),'block_records':sum(len(s.get('blocks',[])) for s in segments),
        'device_trace_events':sum(len(items) for items in traces),'pickle_class_loading':'disabled',
        'scope':'input inventory; query filters and expected results will be frozen with the runtime scenario',
        'product_scenarios_executed':0,'file_hash_verification':'not_run_per_user_preference'}
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
