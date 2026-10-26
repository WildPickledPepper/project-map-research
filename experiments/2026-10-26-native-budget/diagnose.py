"""Bounded native API, identity and stage probes; analysis stays in upstream SVF."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))


def worker(args):
    import pysvf
    def event(phase):
        import resource
        with (args.output/'events.jsonl').open('a') as stream:
            stream.write(json.dumps({'phase':phase,'elapsed':round(time.monotonic()-started,6),
                                    'self_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})+'\n')
    started=time.monotonic();event('import_complete')
    api={'schema':'svf-runtime-api/1','package_version':importlib.metadata.version('pysvf'),
         'module_interfaces':{k:callable(getattr(pysvf,k,None)) for k in
             ('buildSVFModule','get_svfir','run_pta','get_pta','getPAG','getSVFG')}}
    if args.mode=='api':
        api['module_symbols']=dir(pysvf)
        (args.output/'api.json').write_text(json.dumps(api,indent=2));return
    if args.mode=='pta':
        event('pag_start');pysvf.get_svfir(str(args.bitcode.resolve()));event('pag_complete')
        event('pta_start');pysvf.run_pta(pysvf.AndersenWaveDiff_WPA);event('pta_complete')
        api['pta_type']=type(pysvf.get_pta()).__name__
        api['pta_interfaces']=dir(pysvf.get_pta())
        api['pag_variables']=pysvf.getPAG().getSVFVarNum()
        (args.output/'api.json').write_text(json.dumps(api,indent=2));return
    if args.mode=='full':
        event('native_analysis_start')
        pysvf.buildSVFModule(['-stat','-svfg',str(args.bitcode.resolve())])
        event('native_analysis_complete')
        api['svfg_available']=pysvf.getSVFG() is not None
        (args.output/'api.json').write_text(json.dumps(api,indent=2));return
    from adapters.svf_export import export
    data=export(args.bitcode,single_process_points=True,progress=event)
    data.update(source_root=str(ROOT),source_commit=args.source_commit,context='fixture/release',module='native-probe')
    (args.output/'native.json').write_text(json.dumps(data,separators=(',',':')))
    event('output_complete')


def bounded(command,folder,*,seconds=600,memory_gib=13):
    """Sample the complete worker tree with psutil, and stop its process group."""
    import psutil
    folder.mkdir(parents=True,exist_ok=False)
    started=time.monotonic();peak=0;reason=None;counts=0;stages={};phase='startup'
    with (folder/'analysis.log').open('w') as log:
        proc=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=os.name!='nt')
        root=psutil.Process(proc.pid)
        while proc.poll() is None:
            rss=0
            try:processes=[root,*root.children(recursive=True)]
            except psutil.NoSuchProcess:processes=[]
            for process in processes:
                try:rss+=process.memory_info().rss
                except (psutil.NoSuchProcess,psutil.AccessDenied):pass
            peak=max(peak,rss);counts+=1
            events=folder/'events.jsonl'
            if events.exists():
                lines=events.read_text().splitlines()
                for line in reversed(lines):
                    try:phase=json.loads(line)['phase'];break
                    except json.JSONDecodeError:continue
            stages[phase]=max(stages.get(phase,0),rss)
            if rss>memory_gib*1024**3:reason='process_tree_memory_budget'
            elif time.monotonic()-started>seconds:reason='native_wall_time_budget'
            if reason:
                if os.name!='nt':os.killpg(proc.pid,signal.SIGTERM)
                else:
                    for child in processes[1:]:
                        try:child.terminate()
                        except psutil.NoSuchProcess:pass
                    proc.terminate()
                try:proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    if os.name!='nt':os.killpg(proc.pid,signal.SIGKILL)
                    else:proc.kill()
                    proc.wait()
                break
            time.sleep(.1)
        proc.wait()
    events=[json.loads(line) for line in (folder/'events.jsonl').read_text().splitlines()] if (folder/'events.jsonl').exists() else []
    receipt={'schema':'svf-bounded-diagnostic/1','command':command,'exit_code':proc.returncode,
             'stop_reason':reason,'seconds':round(time.monotonic()-started,3),'peak_tree_rss_bytes':peak,
             'sample_interval_seconds':.1,'samples':counts,'events':events,'phase_sample_peak_bytes':stages,
             'limits':{'seconds':seconds,'memory_gib':memory_gib},
             'phase_scope':'events bracket PAG and PTA; full native build combines PTA/MemorySSA/SVFG'}
    (folder/'resources.json').write_text(json.dumps(receipt,indent=2))
    return receipt


def identity(native):
    data=json.loads(native.read_text());variables={n['id']:n for n in data['variables']}
    pairs={(p['source'],p['target']) for p in data['points_to']}
    def targets(name):
        sources={n['id'] for n in variables.values() if n['name']==name and 'ObjVar' in n['kind']}
        return {variables[t]['name'] for s,t in pairs if s in sources}
    expected={'first_alias':{'first_object'},'second_alias':{'first_object'},'isolated_alias':{'second_object'}}
    checks=[{'name':name,'expected':sorted(value),'actual':sorted(targets(name)),
             'passed':targets(name)==value} for name,value in expected.items()]
    return {'schema':'svf-independent-identity/1','checks':checks,
            'all_endpoints_in_current_pag':data['same_process_endpoints_checked'],
            'passed':all(c['passed'] for c in checks) and data['same_process_endpoints_checked']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=['api','pta','full','export'],required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--bitcode',type=Path)
    p.add_argument('--source-commit',default='');p.add_argument('--worker',action='store_true')
    p.add_argument('--seconds',type=float,default=600);p.add_argument('--memory-gib',type=float,default=13)
    args=p.parse_args()
    if args.worker:worker(args);return
    if args.mode!='api' and (args.bitcode is None or not args.bitcode.is_file()):p.error('Existing bitcode required')
    if not 0<args.seconds<=600 or not 0<args.memory_gib<=13:p.error('Budget exceeds the fixed diagnostic ceiling')
    command=[sys.executable,str(Path(__file__).resolve()),'--worker','--mode',args.mode,'--output',str(args.output.resolve()),
             '--source-commit',args.source_commit]
    if args.bitcode:command+=['--bitcode',str(args.bitcode.resolve())]
    result=bounded(command,args.output,seconds=args.seconds,memory_gib=args.memory_gib)
    print(json.dumps(result),flush=True)
    if result['exit_code']:raise SystemExit(1)


if __name__=='__main__':main()
