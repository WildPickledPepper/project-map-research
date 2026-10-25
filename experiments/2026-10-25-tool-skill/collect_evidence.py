"""Publish compact executed results while keeping machine paths and raw artifacts outside Git."""
import argparse
import json
from pathlib import Path
import re
import zipfile


def read(path):return json.loads(path.read_text(encoding='utf-8'))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--artifacts',type=Path,required=True)
    p.add_argument('--previous',type=Path,required=True);p.add_argument('--typescript-log',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    fresh=read(a.artifacts/'fresh-smoke/result.json');fresh.pop('package_location')
    real=read(a.artifacts/'insight-smoke/result.json')
    pylog=(a.artifacts/'python-tests.txt').read_text(encoding='utf-8')
    tslog=a.typescript_log.read_text(encoding='utf-8')
    if not re.search(r'\nOK\s*$',pylog) or '# fail 0' not in tslog:raise ValueError('Full suite did not pass')
    with zipfile.ZipFile(a.artifacts/'wheels/project_map_tool-0.2.1-py3-none-any.whl') as z:
        package=json.loads(z.read('projectmap/_build_info.json'));package['wheel_entries']=len(z.namelist())
    if any(not row['passed'] for section in (fresh,real) for row in section['checks']):raise ValueError('A tool check failed')
    report={'date':'2026-10-25','evidence_kind':'executed_tool_delivery_checks','distribution':package,
        'full_python_suite':{'passed':int(re.search(r'Ran (\d+) tests',pylog)[1]),'failed':0},
        'typescript_suite':{'passed':int(re.search(r'# pass (\d+)',tslog)[1]),'failed':0,'typescript_sources_changed_after_run':False},
        'new_repository':fresh,'insight_existing_graph':real,
        'attached_graph_counts':read(a.previous/'insight-attach.json')['counts'],
        'retained_failures':[
            {'run':'initial_full_suite','tests':356,'errors':2,'causes':['test patch still targeted the promoted implementation old module','transient Windows sharing violation while reading state.json']},
            {'run':'insight-smoke','cause':'driver selected a type node from a substring search; function filter added'},
            {'run':'insight-smoke-02','cause':'unfiltered path search reached 200-node budget; protocol relationship filter used'},
            {'run':'insight-smoke-03','cause':'driver passed a relative context path after changing process directory; absolute path used'}],
        'accuracy_experiment':'not_run','historical_asset_integration':'deferred_by_user','new_historical_candidates':'7 still unassigned; registration reviewed only',
        'file_hash_reverification':'not_run_per_user_preference'}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'output':str(a.output),'new_repository_checks':len(fresh['checks']),'insight_checks':len(real['checks'])}))


if __name__=='__main__':main()
