"""Bounded SVF retry reusing native LLVM passes and the existing bitcode capture."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))


def bounded_native(command,folder,name,timeout):
    started=time.monotonic();peak=0;reason=None
    with (folder/(name+'.log')).open('w') as log:
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
        while process.poll() is None:
            status=Path('/proc')/str(process.pid)/'status'
            if status.exists():
                values=dict(line.split(':',1) for line in status.read_text().splitlines() if ':' in line)
                peak=max(peak,int(values.get('VmRSS','0 kB').split()[0]))
            if peak>13*1024*1024 or time.monotonic()-started>timeout:
                reason='13_GiB_native_process_budget' if peak>13*1024*1024 else 'native_wall_time_budget'
                process.terminate()
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait()
                break
            time.sleep(.25)
        receipt={'exit_code':process.returncode,'stop_reason':reason,'peak_rss_kib':peak,
                 'seconds':round(time.monotonic()-started,3)}
        (folder/(name+'-resources.json')).write_text(json.dumps(receipt,indent=2))
        if process.returncode:raise RuntimeError(name+' failed: '+json.dumps(receipt))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    programs=[('probe',args.input/'probe.bc','fixture/release','native-probe',subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),str(ROOT)),
              ('profiler_server',args.input/'insight/profiler_server/program.bc','server/linux-Release','profiler_server',
               'd4e8d1cf9f90208bcbe5371c127088f6fd66c688','/home/runner/work/_temp/insight-native/cmake/source')]
    reports=[]
    for name,original,context,module,commit,source in programs:
        folder=args.output/name;folder.mkdir();bitcode=folder/'program.bc'
        passes='strip-nonlinetable-debuginfo,default<O1>'
        subprocess.run(['opt-16','-passes='+passes,str(original),'-o',str(bitcode)],check=True,timeout=180)
        bounded_native([sys.executable,'-m','adapters.svf_export','--bitcode',str(bitcode),
                '--single-process-points','--output',str(folder/'native.json'),
                '--source-root',source,'--source-commit',commit,'--context',context,'--module',module],
                folder,'export',600)
        if name=='probe':
            subprocess.run([sys.executable,str(Path(__file__).with_name('score_svf_admission.py')),
                '--native',str(folder/'native.json'),'--output',str(folder/'admission')],check=True,timeout=60)
        reports.append({'target':name,'source_commit':commit,'context':context,'llvm_passes':passes,
            'native_analysis_runs':1,'points_to_identity_status':'same_process_native_ids',
            'original_bitcode_bytes':original.stat().st_size,'analysis_bitcode_bytes':bitcode.stat().st_size})
        (args.output/'result.json').write_text(json.dumps(reports,indent=2))
        print(json.dumps(reports[-1]),flush=True)


if __name__=='__main__':main()
