"""Use Cargo/rustc LLVM output and the installed SVF to supplement MIR facts."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import shutil


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('manifest','source-root','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--source-commit',required=True);p.add_argument('--context',required=True)
    p.add_argument('--toolchain',default='1.94.0');p.add_argument('--target')
    p.add_argument('--analysis-optimization',choices=['0','1','2','3'])
    p.add_argument('--release',action='store_true');p.add_argument('--no-default-features',action='store_true')
    p.add_argument('--features');p.add_argument('--compile-only',action='store_true')
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    manifest=args.manifest.resolve();source=args.source_root.resolve();output=args.output.resolve()
    environment={**os.environ,'RUSTUP_TOOLCHAIN':args.toolchain,'RUSTC_BOOTSTRAP':'1'}
    environment.pop('RUSTC_WRAPPER',None)
    metadata=json.loads(subprocess.check_output(['cargo','metadata','--format-version','1','--no-deps',
        '--manifest-path',str(manifest)],cwd=manifest.parent,env=environment,text=True))
    package=next(p for p in metadata['packages'] if Path(p['manifest_path']).resolve()==manifest)
    command=['cargo','rustc','--manifest-path',str(manifest),'--target-dir',str(output/'cargo')]
    if args.target:command+=['--target',args.target]
    if args.release:command+=['--release']
    if args.no_default_features:command+=['--no-default-features']
    if args.features:command+=['--features',args.features]
    native_cfg=subprocess.check_output([*command,'--','--print=cfg'],cwd=manifest.parent,
        env=environment,text=True,stderr=subprocess.PIPE,timeout=900)
    (output/'native-cfg.txt').write_text(native_cfg)
    debug_assertions='debug_assertions' in native_cfg.splitlines()
    optimization=args.analysis_optimization or ('1' if args.release else '0')
    command+=['--','-Zno-link','--emit=llvm-bc','-Cdebuginfo=2','-Cembed-bitcode=yes','-Ccodegen-units=1',
              '-Copt-level='+optimization,'-Cdebug-assertions='+('yes' if debug_assertions else 'no')]
    with (output/'compile.log').open('w') as log:
        subprocess.run(command,cwd=manifest.parent,env=environment,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)
    crate=package['name'].replace('-','_')
    bitcodes=list((output/'cargo').rglob(crate+'*.bc'))
    if len(bitcodes)!=1:raise ValueError('Expected one native crate bitcode: '+str(bitcodes))
    relative=manifest.parent.relative_to(source).as_posix()
    shutil.copyfile(bitcodes[0],output/'program.bc')
    receipt={'schema':'cargo-svf-capture/1','source_commit':args.source_commit,'context':args.context,
        'compiler':subprocess.check_output(['rustc','-vV'],env=environment,text=True),
        'target':args.target,'release':args.release,'no_default_features':args.no_default_features,
        'features':args.features,'native_link_executed':False,'product_executed':False,
        'source_root':str(source),'source_directory':relative,'module':'cargo:'+package['name'],
        'native_cfg':native_cfg.splitlines(),'debug_assertions':debug_assertions,'analysis_optimization':optimization,
        'language':'rust','bitcode':'program.bc','compile_command':command,'analysis_executed':False}
    (output/'receipt.json').write_text(json.dumps(receipt,indent=2))
    if not args.compile_only:
        from analyze_svf_captures import analyze
        analyze(output/'receipt.json')
    print(json.dumps(receipt))


if __name__=='__main__':main()
