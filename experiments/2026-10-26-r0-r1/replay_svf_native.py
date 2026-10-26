"""Bounded SVF retry reusing native LLVM passes and the existing bitcode capture."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    import pysvf
    wpa=next(Path(pysvf.__file__).parent.rglob('wpa'))
    programs=[('probe',args.input/'probe.bc','fixture/release','native-probe',subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),str(ROOT)),
              ('profiler_server',args.input/'insight/profiler_server/program.bc','server/linux-Release','profiler_server',
               'd4e8d1cf9f90208bcbe5371c127088f6fd66c688','/home/runner/work/_temp/insight-native/cmake/source')]
    reports=[]
    for name,original,context,module,commit,source in programs:
        folder=args.output/name;folder.mkdir();bitcode=folder/'program.bc'
        passes='strip-nonlinetable-debuginfo'
        subprocess.run(['opt-16','-passes='+passes,str(original),'-o',str(bitcode)],check=True,timeout=180)
        with (folder/'analysis.log').open('w') as log:
            subprocess.run([str(wpa),'-ander','-svfg','-write-ander='+str(folder/'points-to.txt'),str(bitcode)],
                           stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)
        with (folder/'export.log').open('w') as log:
            subprocess.run([sys.executable,'-m','adapters.svf_export','--bitcode',str(bitcode),
                '--native-points',str(folder/'points-to.txt'),'--output',str(folder/'native.json'),
                '--source-root',source,'--source-commit',commit,'--context',context,'--module',module],
                stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
        if name=='probe':
            subprocess.run([sys.executable,str(Path(__file__).with_name('score_svf_admission.py')),
                '--native',str(folder/'native.json'),'--output',str(folder/'admission')],check=True,timeout=60)
        reports.append({'target':name,'source_commit':commit,'context':context,'llvm_passes':passes,
            'original_bitcode_bytes':original.stat().st_size,'analysis_bitcode_bytes':bitcode.stat().st_size})
        (args.output/'result.json').write_text(json.dumps(reports,indent=2))
        print(json.dumps(reports[-1]),flush=True)


if __name__=='__main__':main()
