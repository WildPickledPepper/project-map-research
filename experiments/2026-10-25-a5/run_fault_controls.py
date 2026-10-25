"""Run same-build normal/fault/restored controls against the frozen input assertion."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from verify import verify,read

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--results',type=Path,required=True)
    a=p.parse_args();runs=[]
    for label,fault in [('control',False),('fault',True),('restored',False)]:
        output=a.results/('a5-small-page-'+label+'-01')
        command=[sys.executable,str(Path(__file__).with_name('run.py')),'--source',str(a.source),'--output',str(output),'--scenario','snapshot-normal','--page-size','128']
        if fault:command.append('--fault-drop-block')
        result=subprocess.run(command,timeout=330)
        assert (result.returncode!=0)==fault
        outcome=read(output/'result.json')
        verification=verify(output)
        (output/'verification.json').write_text(json.dumps(verification,indent=2)+'\n',encoding='utf-8')
        assert verification['independent_blocks_passed'] != fault
        assert outcome['passed'] != fault
        if fault:assert 'Independent allocation-lifetime multiset' in outcome['failure']
        runs.append({'label':label,'run':output.name,'source_commit':verification['source_commit'],
            'scenario_passed':outcome['passed'],'independent_blocks_passed':verification['independent_blocks_passed'],
            'blocks':verification['checks']['blocks'],'page_size':128})
        print(json.dumps(runs[-1]),flush=True)
    assert len({r['source_commit'] for r in runs})==1
    (a.results/'a5-fault-controls.json').write_text(json.dumps({'passed':True,'runs':runs},indent=2)+'\n',encoding='utf-8')
