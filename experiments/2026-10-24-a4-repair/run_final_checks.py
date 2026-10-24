"""Run measured, sequential verification after both complete builders finish."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('a3_probe',ROOT/'experiments/2026-10-24-a3/probe.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('results','typescript','source','runtime-store','old-index'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();a.results=a.results.resolve()
    root=a.results/'a4-repair-final-checks-01';root.mkdir(parents=True,exist_ok=False)
    started=time.monotonic()
    while True:
        outcomes=[a.results/name/'result.json' for name in ['a4-repair-full-06','a4-repair-full-07']]
        if all(f.exists() for f in outcomes):
            if not all(json.loads(f.read_text(encoding='utf-8'))['status']=='passed' for f in outcomes):raise RuntimeError('A complete builder failed')
            break
        if time.monotonic()-started>900:raise TimeoutError('Builders not ready after 900 seconds')
        time.sleep(2)
    build=a.results/'a4-repair-full-06/build';other=a.results/'a4-repair-full-07/build'
    steps=[
      ('chains', 'experiments/2026-10-24-a4-repair/retest.py', ['--graph',build/'graph.json','--output',a.results/'a4-repair-scoring-02'],300,6),
      ('updates', 'experiments/2026-10-24-a4-repair/run_direct_updates.py', ['--typescript',a.typescript.resolve(),'--output',a.results/'a4-repair-direct-updates-04'],300,6),
      ('navigation','experiments/2026-10-24-a4-repair/verify_navigation.py',['--graph',build/'graph.json','--source',a.source.resolve(),'--old-index',a.old_index.resolve(),'--output',a.results/'a4-repair-navigation-02'],300,6),
      ('rebuild','experiments/2026-10-24-a4/compare_graphs.py',['--first',build/'graph.json','--second',other/'graph.json','--output',a.results/'a4-repair-comparison-02/comparison.json'],180,10),
      ('publication','experiments/2026-10-24-a4/probe_publication.py',['--build',build,'--source',a.source.resolve(),'--output',a.results/'a4-repair-publication-02'],240,7),
      ('known','experiments/2026-10-24-a4/run_regression.py',['--source',a.source.resolve(),'--build',build,'--runtime-store',a.runtime_store.resolve(),'--output',a.results/'a4-repair-known-02'],300,10),
    ]
    results={}
    for name,script,args,seconds,gib in steps:
        command=[sys.executable,'-X','utf8',str(ROOT/script),*map(str,args)]
        measured=probe.execute(command,root/(name+'.log'),seconds=seconds,memory=gib*1024**3)
        results[name]=measured
        (root/'result.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'step':name,**measured}),flush=True)
        if measured['status']!='passed':raise RuntimeError('Verification failed: '+name)
