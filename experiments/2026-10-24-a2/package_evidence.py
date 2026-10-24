"""Package compact executed results; raw graphs, sources and logs stay external."""
import argparse
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent/'evidence'


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def save(name,value):
    body=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
    if re.search(r'[A-Za-z]:[\\/]+(?:Users|workspace)[\\/]',body):raise ValueError('Nonportable evidence: '+name)
    (HERE/name).write_text(body,encoding='utf-8')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('first','second','audit','comparison','controls','regression','python-log','typescript-log'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();HERE.mkdir(exist_ok=True)
    summary=read(a.audit);controls=read(a.controls);regression=read(a.regression);comparison=read(a.comparison)
    if not all(r['passed'] for r in (summary,controls,regression,comparison)):raise ValueError('Acceptance is incomplete')
    version=summary['build_version']
    runs=[]
    for directory in (a.first,a.second):
        run=read(directory/'result.json');request=read(directory/'build/request.json')
        if request['build_version']!=version or run['status']!='passed':raise ValueError('Build version or completion differs')
        runs.append({**run,'build_version':request['build_version']})
    python=a.python_log.read_text(encoding='utf-8');typescript=a.typescript_log.read_text(encoding='utf-8')
    count=re.search(r'Ran (\d+) tests in ([0-9.]+)s\s+OK\s*$',python)
    ts_count=re.search(r'# tests (\d+)',typescript)
    if not count or not ts_count or not re.search(r'# fail 0\b',typescript):raise ValueError('Test logs do not show success')
    tests={'evidence_kind':'executed_full_test_suites','build_version':version,'python':int(count[1]),
        'python_seconds':float(count[2]),'typescript':int(ts_count[1]),'passed':True,
        'commands':['python -m unittest discover -s tests -v','npm test'],
        'file_hash_verification':'not_run_per_user_preference'}
    for name,value in [('graph-summary.json',summary),('controls-final.json',controls),('chain-regression.json',regression),
                       ('rebuild.json',comparison),('build-runs.json',runs),('tests.json',tests)]:save(name,value)
    print('Packaged successful full graph, fresh rebuild, controls, case queries and test logs.')


if __name__=='__main__':main()
