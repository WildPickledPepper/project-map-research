"""Isolated evaluation helper. Copy to a bundle root; all reads are logged."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output';OUT.mkdir(exist_ok=True)
STATE=OUT/'active.json'


def log(row):
    row['time']=datetime.now(timezone.utc).isoformat()
    with (OUT/'usage.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--select',help='JSON key path, separated by dots')
    sub=ap.add_subparsers(dest='mode',required=True)
    for action in ('begin','end'):
        p=sub.add_parser(action);p.add_argument('task')
    p=sub.add_parser('read');p.add_argument('path');p.add_argument('--start',type=int,default=1);p.add_argument('--count',type=int,default=100)
    p=sub.add_parser('query');p.add_argument('args',nargs=argparse.REMAINDER)
    a=ap.parse_args();begin=time.perf_counter();state=json.loads(STATE.read_text()) if STATE.exists() else {}
    if a.mode=='begin':
        state={'task':a.task,'started':time.time()};STATE.write_text(json.dumps(state));log({'action':'begin',**state});print(a.task);return
    if a.mode=='end':
        if state.get('task')!=a.task:raise ValueError('Task mismatch')
        log({'action':'end','task':a.task,'elapsed_seconds':time.time()-state['started'],'tokens':'not_exposed','context_tokens':'not_exposed'});STATE.unlink();print(a.task);return
    if not state:raise ValueError('Begin a task before reading/querying')
    if a.mode=='read':
        p=(ROOT/a.path).resolve()
        if not p.is_relative_to(ROOT) or not p.is_file():raise ValueError('Only own bundle files may be read')
        text=p.read_text(encoding='utf-8');value=json.loads(text) if a.select else None
        if not a.select:
            lines=text.splitlines();text='\n'.join(f'{i+1}: {lines[i]}' for i in range(max(0,a.start-1),min(len(lines),a.start-1+min(a.count,200))))
    else:
        result=subprocess.run([sys.executable,str(ROOT/'experiments/2026-10-24-p7/query.py'),
            '--graph',str(ROOT/'graph.json'),'--inventory',str(ROOT/'inventory.json'),*a.args],capture_output=True,text=True,encoding='utf-8')
        if result.returncode:raise RuntimeError(result.stderr)
        text=result.stdout;value=json.loads(text) if a.select else None
    raw_bytes=len(text.encode('utf-8'))
    if a.select:
        for key in a.select.split('.'):value=value[int(key)] if isinstance(value,list) else value[key]
        text=json.dumps(value,ensure_ascii=False,indent=2)
    log({'action':a.mode,'task':state['task'],'arguments':vars(a),'elapsed_seconds':time.perf_counter()-begin,
         'result_bytes':raw_bytes,'displayed_bytes':len(text.encode('utf-8'))})
    print(text)


if __name__=='__main__':main()
