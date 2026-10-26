"""Verify diagnosed headers inside native compilation units selected by CBM imports.

The compiler's include trace and exit status are the evidence; the CBM candidate
import graph only selects work. This does not change header facts or source files.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.compilation_database import command_arguments


def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('capture','plan','output'):ap.add_argument('--'+name,type=Path,required=True)
    args=ap.parse_args()
    receipt=load(args.capture/'result.json')
    assert receipt['attempts'][-1]['configured']
    args.output.mkdir(parents=True,exist_ok=False)
    source=(args.capture/'source').resolve()
    rows=load(args.capture/'prepared-dependencies'/'compile_commands.json')
    commands={}
    for row in rows:
        try:path=Path(row['file']).resolve().relative_to(source).as_posix()
        except ValueError:continue
        commands[path]=row
    plan=load(args.plan)
    plan=plan.get('selection_plan',plan)
    headers={p for _,paths in plan['selected'] for p in paths}|set(plan['unmapped'])
    started=time.monotonic()
    def run(item):
        ordinal,(path,expected)=item
        row=commands[path]
        raw=row.get('arguments') or command_arguments(row['command'])
        cleaned=[];skip=False
        for argument in raw:
            if skip:skip=False;continue
            if argument in {'-o','-MF','-MT','-MQ'}:skip=True;continue
            if argument in {'-c','-MD','-MMD','-MP','-MG'}:continue
            cleaned.append(argument)
        if Path(cleaned[0]).name.lower() not in {'g++.exe','gcc.exe','clang++.exe','g++','gcc','clang++'}:
            raise ValueError('Expected an already configured GNU-style compiler')
        command=[*cleaned,'-fsyntax-only','-H','-fdiagnostics-color=never']
        folder=args.output/str(ordinal);folder.mkdir()
        (folder/'command.json').write_text(json.dumps({'arguments':command,'cwd':row['directory']}),encoding='utf-8')
        begin=time.monotonic()
        try:
            result=subprocess.run(command,cwd=row['directory'],capture_output=True,text=True,
                                  encoding='utf-8',errors='replace',timeout=180)
            (folder/'stdout.log').write_text(result.stdout,encoding='utf-8')
            (folder/'stderr.log').write_text(result.stderr,encoding='utf-8')
            included=set()
            for line in result.stderr.splitlines():
                match=re.match(r'^\.+\s+(.+)$',line)
                if not match:continue
                target=Path(match[1])
                if not target.is_absolute():target=Path(row['directory'])/target
                try:included.add(target.resolve().relative_to(source).as_posix())
                except ValueError:pass
            return {'translation_unit':path,'exit_code':result.returncode,'seconds':round(time.monotonic()-begin,3),
                'candidate_headers':expected,'observed_required_headers':sorted(included&headers),
                'native_project_includes':len(included),'status':'syntax_checked' if result.returncode==0 else 'compiler_failed'}
        except subprocess.TimeoutExpired:
            return {'translation_unit':path,'status':'compiler_timeout','observed_required_headers':[],
                    'candidate_headers':expected,'seconds':180}
    with ThreadPoolExecutor(max_workers=2) as pool:
        checks=list(pool.map(run,enumerate(plan['selected'])))
    covered={p for r in checks if r['status']=='syntax_checked' for p in r['observed_required_headers']}
    report={'schema':'native-header-context-review/1','source_commit':receipt['source_commit'],
        'configuration':receipt['configuration'],'context':receipt['subdir']+'/'+receipt['configuration'],
        'origin':'actual_configured_compiler_syntax_check_and_include_trace','seconds':round(time.monotonic()-started,3),
        'compiler':subprocess.check_output([raw_compiler(rows[0]),'--version'],text=True,encoding='utf-8').splitlines()[0],
        'required_header_count':len(headers),'selection_plan':plan,'checks':checks,'context_validated_headers':sorted(covered),
        'remaining_headers':sorted(headers-covered),'standalone_clangd_diagnostics_preserved':True,
        'interpretation':'header_compiles_in_observed_TU_context; not_complete_header_reference_recovery',
        'runtime_execution':False,'whole_G02_accepted':False}
    (args.output/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'translation_units':len(checks),'context_validated_headers':len(covered),
                      'remaining_headers':len(headers-covered),'seconds':report['seconds']}))


def raw_compiler(row):return (row.get('arguments') or command_arguments(row['command']))[0]


if __name__=='__main__':main()
