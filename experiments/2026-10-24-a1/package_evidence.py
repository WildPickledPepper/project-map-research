"""Publish compact A1 results; keep exported source and complete facts external."""
import argparse
from collections import Counter
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def read(path):return json.loads(path.read_text(encoding='utf-8'))


def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')


def package(results):
    raw=results/'a1-final-01';d=read(raw/'discovery.json');s=read(raw/'summary.json')
    evidence=HERE/'evidence';evidence.mkdir(exist_ok=True)
    s.update(evidence_kind='executed_committed_tree_discovery_and_local_ast_extraction',
        schema_version=d['schema_version'],build_version=d['build_version'],policy=d['policy'],attempts=d['attempts'],
        publication='file-local facts and full path status; no whole-repository cross-language graph claim',
        roles={name:{'tracked':sum(r['role']==name for r in d['files']),
                     'eligible_sources':sum(r['role']==name and r['eligible'] and r['task']=='source' for r in d['files'])}
               for name in sorted({r['role'] for r in d['files']})},
        cpp_compile_commands_missing=sum(r['eligible'] and r['language']=='cpp' and not r['build_context']['compile_commands'] for r in d['files']),
        ts_build_file_sets=dict(Counter(r['build_context']['build_membership'] for r in d['files'] if r['eligible'] and r['language'] in {'typescript','tsx'})),
        provenance=d['provenance'],module_group_origin='nearest tracked package/CMake/TOML manifest; fallback top-level',
        raw_output='results/a1-final-01 outside research Git; regenerate using README',
        definitions={'interfaces':'syntax interface/type members and virtual/declaration records; not a business API count',
                     'registrations':'AST calls with generic spelling hints; candidate only',
                     'resources':'member/top-level declaration candidates; not runtime allocation/occupancy',
                     'calls':'source call sites with unresolved targets',
                     'build_context_missing':'absence of nearby manifest; does not measure usable compiler context'})
    write(evidence/'summary.json',s)
    write(evidence/'auto-config.json',read(raw/'build-config.json'))
    write(evidence/'modules.json',{'source_commit':d['source_commit'],'modules':d['modules']})
    with (evidence/'file-status.jsonl').open('w',encoding='utf-8',newline='\n') as stream:
        for r in d['files']:
            row={k:r[k] for k in ('path','language','role','module','eligible','task','status','reason')}
            stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    diagnostics=[]
    for row in d['files']:
        if not row.get('facts'):continue
        f=read(raw/row['facts'])['facts']
        if f.get('diagnostics'):
            diagnostics.append({'path':row['path'],'status':row['status'],'count':len(f['diagnostics']),
                                'examples':f['diagnostics'][:3],'examples_truncated':len(f['diagnostics'])>3})
    write(evidence/'diagnostics.json',{'source_commit':d['source_commit'],'files':diagnostics,
        'interpretation':'parser/configuration diagnostics, not an issue root-cause audit'})
    write(evidence/'mutation.json',read(results/'a1-mutation-01/result.json'))
    regression=read(results/'a1-chain-acceptance-01/validation.json')
    regression['scope']='P7 historical 191-file regression only; normal A1 scope is automatic'
    regression['storage_note']='JSON output; prior P7 Kuzu persistence result unchanged, not rerun here'
    auto=read(raw/'input-manifest.json')
    old=read(HERE.parent/'2026-10-24-p7/upstream-graph-config.json')
    regression['old_baseline_inputs_present_in_automatic_scope']=set(old['scope']['include']) <= {r['path'] for r in auto['files']}
    write(evidence/'chain-regression.json',regression)
    text=(results/'a1-final-python-tests.txt').read_text(encoding='utf-8')
    ts=(results/'a1-typescript-tests.txt').read_text(encoding='utf-8')
    assert 'Ran 305 tests' in text and text.rstrip().endswith('OK')
    assert '# pass 80' in ts and '# fail 0' in ts
    write(evidence/'tests.json',{'evidence_kind':'executed_test_suites','python':305,'typescript':80,'passed':True,
        'new_test_module':'tests/test_repository_discovery.py',
        'refresh_test':'tests/test_snapshot_refresh.py:test_automatic_scope_replans_new_modules_without_configuration_edits',
        'real_extractor_refresh_test':'tests/test_snapshot_watch.py:test_watcher_tracks_cross_file_identity_registration_consumer_and_configuration_changes',
        'scope':'authored fixtures plus existing regression suites; no reserved historical sample execution',
        'checks':['fixed commit ignores dirty worktree','add/rename/delete','roles/size/symlink exclusions',
                  'interfaces and registration candidates','comment/string false positives',
                  'invalid UTF-8/binary/syntax errors','worker timeout/exit','budget/resume/version guard',
                  'automatic scope in existing refresh controller']})
    print('Packaged A1 summary, file statuses, module groups, diagnostics, mutation and regression evidence.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--results',type=Path,required=True)
    package(p.parse_args().results)
