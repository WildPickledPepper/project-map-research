"""Compile native CMake inputs to LLVM IR and run existing SVF per executable."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.compilation_database import command_arguments
from adapters.libclang_provider import parse_arguments
from adapters.repository_discovery import discover


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ('repository','cmake-capture','output','clang','llvm-link'):ap.add_argument('--'+key,type=Path,required=True)
    args=ap.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    receipt=json.loads((args.cmake_capture/'result.json').read_text())
    if not receipt['attempts'][-1]['configured']:raise ValueError('Successful native CMake export required')
    source=(args.cmake_capture/'source').resolve()
    discovery=discover(args.repository,receipt['source_commit'])
    selected={r['path'] for r in discovery['files'] if r['eligible'] and r['language']=='cpp' and r['role']!='test'}
    rows=json.loads((args.cmake_capture/'prepared-dependencies/compile_commands.json').read_text())
    targets={t['id']:t for t in receipt['attempts'][-1]['targets']}
    names={t['name']:t['id'] for t in targets.values()};groups={k:[] for k in targets};jobs=[]
    for row in rows:
        path=Path(row['file']).resolve()
        try:relative=path.relative_to(source).as_posix()
        except ValueError:continue
        if relative not in selected:continue
        raw=row.get('arguments') or command_arguments(row['command'])
        output=row.get('output') or (raw[raw.index('-o')+1] if '-o' in raw else '')
        object_parts=output.replace('\\','/').split('/')
        owner=next((part[:-4] for part in object_parts if part.endswith('.dir') and part[:-4] in names),None)
        if not owner:raise ValueError('Cannot map native object to CMake target: '+relative)
        ordinal=len(jobs);jobs.append((ordinal,relative,row));groups[names[owner]].append(ordinal)
    def compile_unit(item):
        ordinal,relative,row=item;_,arguments,omitted=parse_arguments(row)
        command=[str(args.clang),*arguments,'-Wno-error','-O0','-g','-fno-discard-value-names',
                 '-Xclang','-disable-O0-optnone','-emit-llvm','-c',str(source/relative),
                 '-o',str(args.output/f'unit-{ordinal}.bc')]
        r=subprocess.run(command,cwd=row['directory'],capture_output=True,text=True,timeout=180)
        (args.output/f'unit-{ordinal}.log').write_text(r.stdout+r.stderr)
        return {'unit':ordinal,'path':relative,'exit_code':r.returncode,'omitted_actions':omitted}
    started=time.monotonic()
    if not jobs:raise ValueError('Native CMake database did not select any first-party C++ inputs')
    with ThreadPoolExecutor(max_workers=3) as pool:compilations=list(pool.map(compile_unit,jobs))
    (args.output/'compilations.json').write_text(json.dumps(compilations,indent=2))
    failures=[r for r in compilations if r['exit_code']]
    if failures:print(json.dumps({'compiler_failures':failures}));raise SystemExit(1)
    reports=[]
    for target in targets.values():
        if target['type']!='EXECUTABLE':continue
        pending=[target['id']];seen=set();units=set()
        while pending:
            uid=pending.pop()
            if uid in seen:continue
            seen.add(uid);units.update(groups.get(uid,[]));pending.extend(targets.get(uid,{}).get('dependencies',[]))
        if not units:continue
        folder=args.output/target['name'];folder.mkdir()
        merged=folder/'program.bc'
        subprocess.run([str(args.llvm_link),*[str(args.output/f'unit-{i}.bc') for i in sorted(units)],'-o',str(merged)],check=True,timeout=180)
        context=receipt['subdir']+'/linux-'+receipt['configuration']
        with (folder/'export.log').open('w') as log:
            subprocess.run([sys.executable,'-m','adapters.svf_export','--bitcode',str(merged),
                '--single-process-points','--output',str(folder/'native.json'),
                '--source-root',str(source),'--source-commit',receipt['source_commit'],
                '--context',context,'--module',target['id']],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
        reports.append({'target':target['name'],'native_target_id':target['id'],'translation_units':len(units),
                        'context':context,'native_analysis_runs':1,'points_to_identity_status':'same_process_native_ids'})
        print(json.dumps(reports[-1]),flush=True)
    if not reports:raise ValueError('No native executable target was analyzed')
    result={'schema':'svf-cmake-native-run/1','source_commit':receipt['source_commit'],
        'compilation_units':len(compilations),'compiler_failures':failures,'targets':reports,
        'seconds':round(time.monotonic()-started,3),'input_scope':'first_party_native_CMake_units_and_native_target_dependencies',
        'analysis_overrides':['LLVM_IR','O0','debug_locations','compiler_warnings_not_promoted'],
        'clang_version':subprocess.check_output([str(args.clang),'--version'],text=True).splitlines()[0],
        'whole_R0_R1_accepted':False}
    (args.output/'result.json').write_text(json.dumps(result,indent=2))


if __name__=='__main__':main()
