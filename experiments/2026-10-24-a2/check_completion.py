"""Check portable A2 evidence; never read product source or recompute hashes."""
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent/'evidence'


def read(name):return json.loads((HERE/name).read_text(encoding='utf-8'))


def main():
    summary=read('graph-summary.json');controls=read('controls-final.json');first=read('controls-first.json')
    regression=read('chain-regression.json');rebuild=read('rebuild.json');tests=read('tests.json');runs=read('build-runs.json')
    assert summary['source_commit']==regression['source_commit']=='d4e8d1cf9f90208bcbe5371c127088f6fd66c688'
    assert summary['snapshot']==regression['snapshot']==rebuild['snapshots'][0]
    assert summary['build_version']==controls['build_version']==regression['build_version']==tests['build_version']
    assert summary['passed'] and all(summary['checks'].values())
    assert summary['counts']['input_files']==regression['counts']['input_files']==2310
    assert sum(len(u['root_files']) for u in summary['analysis_units'])==933
    assert summary['counts']['nodes']==regression['counts']['nodes'] and summary['counts']['edges']==regression['counts']['edges']
    assert summary['counts']['protocol_provider_candidates']==len(summary['interfaces'])
    assert sum(summary['counts']['protocol_consumer_status'].values())==len(summary['consumers'])
    for kind in ('STATIC_CALL_TARGET','DECLARES_DEFINITION','SOURCE_CALL_CANDIDATE','MATCHES_REGISTERED_PROTOCOL','VALUE_SERIALIZED_AS','POTENTIALLY_READ_BY'):
        assert summary['counts']['edge_kinds'][kind]>0,kind
    assert not first['passed'] and sum(first['checks'].values())==13 and len(first['checks'])==14
    assert controls['passed'] and len(controls['checks'])==14 and all(controls['checks'].values())
    assert first['checks']['renamed_symbols_fields_command_reconnect'] is False
    assert regression['passed'] and len(regression['checks'])==19 and all(regression['checks'].values())
    assert rebuild['passed'] and rebuild['differing_top_level_keys']==[] and rebuild['snapshots'][0]!=rebuild['snapshots'][1]
    assert tests['passed'] and tests['python']==314 and tests['typescript']==88
    assert len(runs)==2
    for run in runs:
        assert run['status']=='passed' and run['exit_code']==0
        assert run['build_version']==summary['build_version'] and run['source_commit']==summary['source_commit']
        assert run['peak_tree_working_set_bytes_observed']<=run['budgets']['process_tree_working_set_bytes']
    assert summary['kuzu_full_scope_roundtrip']=='not_executed'
    assert summary['historical_sample_use']=='none; validation candidates untouched'
    for file in HERE.glob('*.json'):
        assert not re.search(r'[A-Za-z]:[\\/]+(?:Users|workspace)[\\/]',file.read_text(encoding='utf-8')),file.name
    assert summary['file_hash_verification']==rebuild['file_hash_verification']=='not_run_per_user_preference'
    print('OK: A2 full automatic scope, source relations, 14 mutation controls, three-chain regression, fresh rebuild and tests.')


if __name__=='__main__':main()
