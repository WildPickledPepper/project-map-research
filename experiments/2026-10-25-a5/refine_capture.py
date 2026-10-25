"""Add explicit result identities and labeled direct-driver controls to the A5 clone."""
import argparse
import json
from pathlib import Path
import subprocess


def refine(source):
    source=Path(source).resolve()
    git=lambda *args:subprocess.check_output(['git','-C',str(source),*args],text=True).strip()
    if not git('remote','get-url','--push','origin').startswith('disabled://'):raise ValueError('Requires isolated source')
    if git('status','--porcelain','--untracked-files=no'):raise ValueError('Requires clean capture source')
    changes={}
    def replace(path,old,new):
        value=changes.get(path,(source/path).read_text(encoding='utf-8'))
        if value.count(old)!=1:raise ValueError('Expected one anchor: '+path+': '+old[:60])
        changes[path]=value.replace(old,new)
    p='modules/cluster/src/components/communication/Filter.tsx'
    replace(p,"{ compareOptions, baselineOptions });","{ compareOptions, baselineOptions, trace_id: (globalThis as any).__a5?.trace(res) });")
    replace(p,"'consumer.groups', { options });","'consumer.groups', { options, trace_id: (globalThis as any).__a5?.trace(res) });")
    p='modules/cluster/src/utils/RequestUtils.ts'
    changes[p]=(source/p).read_text(encoding='utf-8')+'\n(globalThis as any).__a5Queries = { queryIterations, queryStages };\n'
    p='modules/leaks/src/components/dataHandler.ts'
    replace(p,"'pagination.page', { baseParam, currentPage, pageSize, blocks: res.blocks, total: res.total }", "'pagination.page', { baseParam, currentPage, pageSize, blocks: res.blocks, total: res.total, trace_id: (globalThis as any).__a5?.trace(res) }")
    replace(p,"        if (cacheStatus === 'hit') {", "        if (cacheStatus === 'hit') {\n            (globalThis as any).__a5?.event('cache.adopted', { requestSeq, blockContextKey });")
    for path,value in changes.items():(source/path).write_text(value,encoding='utf-8',newline='\n')
    return {'files':list(changes),'result_identity':'WeakMap tags do not enter product data','driver_controls':'explicitly labeled; normal scenario starts through UI'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True)
    print(json.dumps(refine(p.parse_args().source),indent=2))
