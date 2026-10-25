"""Execute the frozen A5 scope serially on a single committed instrumented build."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from verify import verify,read

CASES=[('communication','communication-scheduling',1000,False),
       ('cache','snapshot-cache',1000,False),
       ('replacement','snapshot-replacement',1000,False),
       ('failure','snapshot-failure',1000,False),
       ('memscope','memscope-normal',1000,False),
       ('small-control','snapshot-normal',128,False),
       ('small-fault','snapshot-normal',128,True),
       ('small-restored','snapshot-normal',128,False)]

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--results',type=Path,required=True)
    p.add_argument('--prefix',default='a5-final');a=p.parse_args();runs=[]
    for label,scenario,page,fault in CASES:
        output=a.results/(a.prefix+'-'+label+'-01')
        command=[sys.executable,str(Path(__file__).with_name('run.py')),'--source',str(a.source),'--output',str(output),'--scenario',scenario,'--page-size',str(page)]
        if fault:command.append('--fault-drop-block')
        result=subprocess.run(command,timeout=330)
        item={'label':label,'run':output.name,'fault':fault,'exit_code':result.returncode,'accepted':False}
        try:
            outcome=read(output/'result.json');verification=verify(output)
            (output/'verification.json').write_text(json.dumps(verification,indent=2)+'\n',encoding='utf-8')
            item.update(source_commit=verification['source_commit'],scenario_passed=outcome['passed'],
                capture_complete=verification['capture_complete'],requests=len(verification['chains']),
                independent_blocks_passed=verification['independent_blocks_passed'],blocks=verification['checks']['blocks'])
            assert (result.returncode!=0)==fault
            assert outcome['passed'] != fault and verification['independent_blocks_passed'] != fault
            if fault:assert 'Independent allocation-lifetime multiset' in outcome['failure']
            item['accepted']=True
        except Exception as error:item['error']=str(error)
        runs.append(item);print(json.dumps(item),flush=True)
        (a.results/(a.prefix+'-suite.json')).write_text(json.dumps({'passed':all(r['accepted'] for r in runs),'runs':runs},indent=2)+'\n',encoding='utf-8')
    if not all(r['accepted'] for r in runs):raise SystemExit(1)
