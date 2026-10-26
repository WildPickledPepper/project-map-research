"""Use Cargo/rustc LLVM output and the installed SVF to supplement MIR facts."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('manifest','source-root','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--source-commit',required=True);p.add_argument('--context',required=True)
    p.add_argument('--toolchain',default='1.94.0');p.add_argument('--target')
    p.add_argument('--release',action='store_true');p.add_argument('--no-default-features',action='store_true')
    p.add_argument('--features');args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
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
    command+=['--','-Zno-link','--emit=llvm-bc','-Cdebuginfo=2','-Cembed-bitcode=yes','-Ccodegen-units=1','-Copt-level=0']
    with (output/'compile.log').open('w') as log:
        subprocess.run(command,cwd=manifest.parent,env=environment,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)
    crate=package['name'].replace('-','_')
    bitcodes=list((output/'cargo').rglob(crate+'*.bc'))
    if len(bitcodes)!=1:raise ValueError('Expected one native crate bitcode: '+str(bitcodes))
    import pysvf
    wpa=next((Path(pysvf.__file__).parent).rglob('wpa'))
    with (output/'analysis.log').open('w') as log:
        subprocess.run([str(wpa),'-ander','-svfg','-write-ander='+str(output/'points-to.txt'),str(bitcodes[0])],
                       stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
    relative=manifest.parent.relative_to(source).as_posix()
    with (output/'export.log').open('w') as log:
        subprocess.run([sys.executable,'-m','adapters.svf_export','--bitcode',str(bitcodes[0]),
            '--native-points',str(output/'points-to.txt'),'--output',str(output/'native.json'),
            '--source-root',str(source),'--source-directory',relative,'--source-commit',args.source_commit,
            '--context',args.context,'--module','cargo:'+package['name'],'--language','rust'],
            stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
    receipt={'schema':'cargo-svf-capture/1','source_commit':args.source_commit,'context':args.context,
        'compiler':subprocess.check_output(['rustc','-vV'],env=environment,text=True),
        'target':args.target,'release':args.release,'no_default_features':args.no_default_features,
        'features':args.features,'native_link_executed':False,'product_executed':False}
    (output/'receipt.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt))


if __name__=='__main__':main()
