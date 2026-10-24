"""Validate portable A1 evidence without reading source or verifying hashes."""
from collections import Counter
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent/'evidence'


def read(name):return json.loads((HERE/name).read_text(encoding='utf-8'))


def main():
    summary=read('summary.json'); config=read('auto-config.json'); mutation=read('mutation.json')
    regression=read('chain-regression.json'); tests=read('tests.json'); modules=read('modules.json')
    rows=[json.loads(line) for line in (HERE/'file-status.jsonl').read_text(encoding='utf-8').splitlines()]
    assert summary['source_commit']==regression['source_commit']==modules['source_commit']=='d4e8d1cf9f90208bcbe5371c127088f6fd66c688'
    assert len(rows)==summary['tracked_files']==4855 and len({r['path'] for r in rows})==4855
    assert Counter(r['status'] for r in rows)==summary['statuses']
    assert sum(r['eligible'] and r['task']=='source' for r in rows)==summary['eligible_sources']==2256
    assert sum(r['eligible'] and r['task']=='manifest' for r in rows)==summary['eligible_manifests']==54
    assert summary['statuses']['parsed']==2237 and summary['statuses']['syntax_errors']==19
    assert summary['statuses']['metadata_with_diagnostics']==2
    assert all(r['status']!='pending' and (r['eligible'] or r['reason']) for r in rows)
    assert summary['cpp_compile_commands_missing']==1323 and not summary['complete_semantic_graph']
    assert summary['module_groups']==len(modules['modules'])==29
    assert config['scope']['include']==['*'] and config['scope']['discovery']==summary['policy']
    assert config['scope']['exclude']==[] and config['storage']=='json'
    for language in ('python','rust','javascript','shell'):
        assert summary['languages'][language]['eligible_sources']==0
    assert mutation['passed'] and len(mutation['checks'])==12 and all(mutation['checks'].values())
    assert mutation['base_source_commit']==summary['source_commit']
    assert mutation['added_source_commit']!=mutation['changed_source_commit']
    assert mutation['build_version']==summary['build_version']==regression['build_version']
    assert regression['passed'] and len(regression['checks'])==19 and all(regression['checks'].values())
    assert regression['old_baseline_inputs_present_in_automatic_scope']
    assert regression['counts']['nodes']==31298 and regression['counts']['edges']==45196
    assert tests['passed'] and tests['python']==305 and tests['typescript']==80
    assert summary['provenance']['file_hash_verification']=='not_run_per_user_preference'
    for file in HERE.iterdir():
        if file.suffix in {'.json','.jsonl'}:
            assert not re.search(r'[A-Za-z]:[\\/]+(?:Users|workspace)[\\/]',file.read_text(encoding='utf-8')),file.name
    print('OK: A1 automatic full-tree input, 4855 path states, 2256 source facts, mutation/resume and three-chain regression; A2-A5 pending.')


if __name__=='__main__':main()
