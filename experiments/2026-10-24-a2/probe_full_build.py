"""Run a committed whole-graph builder with visible time and process-tree budgets."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]


def working_set(pid):
    if os.name!='nt':return None
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in
            ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
             'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);psapi=ctypes.WinDLL('psapi',use_last_error=True)
    kernel.OpenProcess.restype=wintypes.HANDLE;kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    handle=kernel.OpenProcess(0x1010,False,pid)
    if not handle:return None
    try:
        counters=Counters();counters.cb=ctypes.sizeof(counters)
        return counters.WorkingSetSize if psapi.GetProcessMemoryInfo(handle,ctypes.byref(counters),counters.cb) else None
    finally:kernel.CloseHandle(handle)


def tree_working_set(pid):
    """Count the venv redirector, actual interpreter and Node descendants."""
    if os.name!='nt':return None
    from ctypes import wintypes
    class Entry(ctypes.Structure):
        _fields_=[('dwSize',wintypes.DWORD),('cntUsage',wintypes.DWORD),('th32ProcessID',wintypes.DWORD),
            ('th32DefaultHeapID',ctypes.c_size_t),('th32ModuleID',wintypes.DWORD),('cntThreads',wintypes.DWORD),
            ('th32ParentProcessID',wintypes.DWORD),('pcPriClassBase',wintypes.LONG),('dwFlags',wintypes.DWORD),
            ('szExeFile',wintypes.WCHAR*260)]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
    kernel.CreateToolhelp32Snapshot.argtypes=[wintypes.DWORD,wintypes.DWORD]
    kernel.Process32FirstW.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)]
    kernel.Process32NextW.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.CreateToolhelp32Snapshot(2,0)
    if handle in (None,ctypes.c_void_p(-1).value):return None
    parents={};entry=Entry();entry.dwSize=ctypes.sizeof(entry)
    try:
        ok=kernel.Process32FirstW(handle,ctypes.byref(entry))
        while ok:
            parents[entry.th32ProcessID]=entry.th32ParentProcessID
            ok=kernel.Process32NextW(handle,ctypes.byref(entry))
    finally:kernel.CloseHandle(handle)
    family={pid}
    while True:
        added={child for child,parent in parents.items() if parent in family}-family
        if not added:break
        family.update(added)
    return sum(working_set(child) or 0 for child in family)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','config','typescript','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--revision',required=True);p.add_argument('--seconds',type=float,default=300)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    command=[sys.executable,'-X','utf8',str(ROOT/'scripts/build_project_snapshot.py'),
        '--source',str(a.source.resolve()),'--revision',a.revision,'--config',str(a.config.resolve()),
        '--typescript',str(a.typescript.resolve()),'--output',str(out/'build')]
    env=dict(os.environ);env['NODE_OPTIONS']='--max-old-space-size=3072'
    started=time.monotonic();peak=0;reason=None
    with (out/'process.log').open('w',encoding='utf-8') as log:
        process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        while process.poll() is None:
            rss=tree_working_set(process.pid)
            if rss:peak=max(peak,rss)
            if time.monotonic()-started>a.seconds:reason='wall_time_budget'
            if rss and rss>6*1024**3:reason='process_tree_working_set_budget'
            if reason:
                if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
                else:process.kill()
                process.wait();break
            try:process.wait(timeout=2)
            except subprocess.TimeoutExpired:pass
    result={'evidence_kind':'executed_full_scope_versioned_builder','source_commit':a.revision,
        'exit_code':process.returncode,'status':'budget_stopped' if reason else 'passed' if process.returncode==0 else 'failed',
        'stop_reason':reason,'elapsed_seconds':round(time.monotonic()-started,3),
        'budgets':{'wall_seconds':a.seconds,'process_tree_working_set_bytes':6*1024**3,'node_heap_mib':3072},
        'peak_tree_working_set_bytes_observed':peak,'memory_measurement':'sum of sampled Windows working sets for root, redirectors and descendants; shared pages may be counted more than once',
        'raw_artifacts':'process.log and build/ retained outside research Git','file_hash_verification':'not_run_per_user_preference'}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))


if __name__=='__main__':main()
