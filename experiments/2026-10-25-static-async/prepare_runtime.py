"""Check an isolated runtime checkout and optionally build new frontend modules."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time


def command(args, cwd):
    return subprocess.check_output(args, cwd=cwd, text=True, encoding='utf-8').strip()


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--build',action='append',choices=['cluster','leaks'],default=[])
    a=p.parse_args();source=a.source.resolve();a.output.mkdir(parents=True,exist_ok=False)
    push=command(['git','remote','get-url','--push','origin'],source)
    if not push.startswith('disabled://'):raise ValueError('Runtime preparation requires a checkout with a disabled push URL')
    result={'evidence_kind':'executed_runtime_environment_preparation','source_commit':command(['git','rev-parse','HEAD'],source),
        'push_disabled':True,'source_dirty_before':bool(command(['git','status','--porcelain'],source)),
        'node_version':command(['node','--version'],source),'builds':{},'product_scenarios_executed':0,
        'file_hash_verification':'not_run_per_user_preference'}
    paths=['server/output/win_mingw64/bin/profiler_server.exe','modules/framework/build/index.html',
           'modules/timeline/build/index.html','e2e/node_modules/playwright/package.json',
           'server/src/test/test_data/cluster_analysis_output/cluster_communication.json',
           'server/src/test/test_data/full_db/leaks_dump_20250806.dat']
    result['inputs']={name:{'present':(source/name).is_file(),
                    'bytes':(source/name).stat().st_size if (source/name).is_file() else None} for name in paths}
    def save():
        result['source_dirty_after']=bool(command(['git','status','--porcelain'],source))
        (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    save()
    for module in a.build:
        env=dict(os.environ,NODE_OPTIONS='--max-old-space-size=3072 --openssl-legacy-provider',
                 GENERATE_SOURCEMAP='false',CI='false',NODE_ENV='production',DISABLE_ESLINT_PLUGIN='true')
        tool=source/'modules/node_modules/.bin'/('craco.CMD' if os.name=='nt' else 'craco')
        started=time.monotonic()
        with (a.output/(module+'-build.log')).open('w',encoding='utf-8') as log:
            try:
                completed=subprocess.run([str(tool),'build'],cwd=source/'modules'/module,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600)
                status='passed' if completed.returncode==0 else 'failed';code=completed.returncode
            except subprocess.TimeoutExpired:status='time_budget_exceeded';code=None
        result['builds'][module]={'status':status,'exit_code':code,'elapsed_seconds':round(time.monotonic()-started,3),
            'index_present':(source/'modules'/module/'build/index.html').is_file(),
            'node_heap_mib':3072,'wall_budget_seconds':600,'process_memory_measured':False}
        save();print(json.dumps({module:result['builds'][module]}),flush=True)
    print(json.dumps({'prepared':list(result['builds']),'source_dirty_after':result['source_dirty_after']}))
