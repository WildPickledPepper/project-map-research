"""Run sequential full-graph checks after the measured build completes."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('a3_probe',ROOT/'experiments/2026-10-24-a3/probe.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['results','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--full',default='static-async-full-01')
    a=p.parse_args();a.results=a.results.resolve();a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=False)
    started=time.monotonic();full=a.results/a.full;build=full/'build'
    while not (full/'result.json').is_file():
        if time.monotonic()-started>1800:raise TimeoutError('Full build not ready')
        time.sleep(2)
    if json.loads((full/'result.json').read_text(encoding='utf-8'))['status']!='passed':raise RuntimeError('Full build failed; retain the failed evidence')
    steps=[
        ('chains','experiments/2026-10-25-static-async/evaluate.py',['--graph',build/'graph.json','--output',a.output/'chains.json'],300,6),
        ('a4-replay','experiments/2026-10-24-a4-repair/retest.py',['--graph',build/'graph.json','--output',a.output/'a4-replay'],300,8),
        ('known','experiments/2026-10-24-a4/run_regression.py',['--source',a.results/'a4-product-02/source','--build',build,'--runtime-store',a.results/'p5-r06-01/store','--output',a.output/'known'],300,10),
        ('navigation','experiments/2026-10-24-a4-repair/verify_navigation.py',['--graph',build/'graph.json','--source',a.results/'a4-product-02/source','--old-index',a.results/'a4-repair-navigation-02/map.sqlite','--output',a.output/'navigation'],300,6),
        ('frontend-repeat','experiments/2026-10-25-static-async/compare_frontend.py',['--first',a.results/'static-async-frontend-03/facts.json','--second',build/'typescript_data_flow.cjs.json','--output',a.output/'frontend-repeat.json'],180,6),
    ]
    result={}
    for name,script,args,seconds,gib in steps:
        print(json.dumps({'starting':name}),flush=True)
        result[name]=probe.execute([sys.executable,'-X','utf8',str(ROOT/script),*map(str,args)],a.output/(name+'.log'),seconds=seconds,memory=gib*1024**3)
        (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({name:result[name]}),flush=True)
