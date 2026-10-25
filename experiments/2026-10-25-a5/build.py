"""Rebuild instrumented frontend modules, preserving per-module build records."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--module', action='append', choices=['cluster','leaks','framework','timeline'])
    a = p.parse_args(); source = a.source.resolve(); a.output.mkdir(exist_ok=False, parents=True)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    results = {'source_commit': revision, 'modules': {}, 'node_heap_mib': 3072}
    for module in (a.module or ('cluster', 'leaks', 'framework', 'timeline')):
        env = dict(os.environ, NODE_OPTIONS='--max-old-space-size=3072 --openssl-legacy-provider',
                   GENERATE_SOURCEMAP='false', CI='false', NODE_ENV='production', DISABLE_ESLINT_PLUGIN='true')
        started = time.monotonic()
        with (a.output/(module+'.log')).open('w', encoding='utf-8') as log:
            r = subprocess.run([str(source/'modules/node_modules/.bin/craco.CMD'), 'build'],
                               cwd=source/'modules'/module, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=600)
        results['modules'][module] = {'exit_code': r.returncode, 'seconds': round(time.monotonic()-started, 3)}
        (a.output/'result.json').write_text(json.dumps(results, indent=2)+'\n', encoding='utf-8')
        print(json.dumps({module: results['modules'][module]}), flush=True)
        if r.returncode: raise SystemExit(r.returncode)
