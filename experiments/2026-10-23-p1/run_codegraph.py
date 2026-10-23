"""Run original CodeGraph on the same P1 files and fixtures as CBM/CGC."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from run_native import RESEARCH, SOURCE_SHA, normalize, prepare, verify_checkout, write

TOOL_SHA = '7bac941c1916d34fae0e93dd0ffeaef360d741fb'
BINARY_SHA = '54156dd1f6481b4d7658f1435b97939a606ff7447caca196bb4b89499773df22'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for option in ('source', 'tool', 'binary', 'output'):
        ap.add_argument('--'+option, type=Path, required=True)
    args = ap.parse_args()
    source, tool, binary, out = (getattr(args, key).resolve() for key in ('source', 'tool', 'binary', 'output'))
    if out.exists() or any(out.is_relative_to(p) for p in (source, tool, RESEARCH)):
        raise ValueError('Use a new output directory outside the checkouts')
    verify_checkout(source, SOURCE_SHA)
    verify_checkout(tool, TOOL_SHA)
    if hashlib.sha256(binary.read_bytes()).hexdigest() != BINARY_SHA:
        raise ValueError('Expected verified CodeGraph v1.39.0 Windows release')
    out.mkdir(parents=True)
    (out/'raw').mkdir()
    prepare(source, out)
    env = dict(os.environ, CODEGRAPH_CACHE_DIR=str(out/'cache'), CODEGRAPH_AUTO_SCIP='0')
    roots = [(out/'source','<source>'),(out/'fixtures','<fixtures>'),(out,'<output>'),(binary,'<binary>')]
    report = {'source_commit': SOURCE_SHA, 'tool_commit': TOOL_SHA, 'binary_sha256': BINARY_SHA,
              'mode': 'original release; automatic SCIP disabled; isolated cache',
              'manifest_sha256': hashlib.sha256((out/'input-manifest.json').read_bytes()).hexdigest(),
              'scopes': {}}

    def run(label, command):
        started = time.monotonic()
        proc = subprocess.run([str(binary), *map(str,command)], env=env, cwd=out,
                              capture_output=True, timeout=180)
        (out/'raw'/(label+'.stdout.txt')).write_bytes(proc.stdout)
        (out/'raw'/(label+'.stderr.txt')).write_bytes(proc.stderr)
        if proc.returncode:
            raise RuntimeError(f'{label}: exit {proc.returncode}; see raw log')
        return proc.stdout.decode('utf-8'), round(time.monotonic()-started,3)

    for scope in ('source','fixtures'):
        _, seconds = run(scope+'-index', ['index',out/scope,'--full'])
        record = {'index_seconds':seconds, 'queries':{}}
        queries = {
            'counts': "SELECT json_object('label',label,'count',count(*)) AS row FROM nodes GROUP BY label",
            'files': "SELECT json_object('path',file_path) AS row FROM nodes WHERE label='File' ORDER BY file_path",
            'symbols': "SELECT json_object('name',name,'label',label,'language',language,'path',file_path,'line',line_start,'data',json(data)) AS row FROM nodes " + ("WHERE name IN ('getUnitFlows','HandleRequest','QueryUnitFlows','VirtualTraceDatabase','DbTraceDataBase','TextTraceDatabase','send','fetch','createRequest') " if scope=='source' else '') + 'ORDER BY file_path,line_start,id',
            'calls': "SELECT json_object('caller',a.name,'caller_path',a.file_path,'caller_line',a.line_start,'callee',b.name,'callee_path',b.file_path,'callee_line',b.line_start,'relation',e.relation,'data',json(e.data)) AS row FROM edges e JOIN nodes a ON a.id=e.src JOIN nodes b ON b.id=e.dst WHERE e.relation='Calls' " + ("AND a.name IN ('getUnitFlows','HandleRequest','send','fetch') " if scope=='source' else '') + 'ORDER BY e.src,e.dst,e.relation',
            'raw_calls': "SELECT json_object('caller',n.name,'caller_label',n.label,'callee',c.callee_name,'path',c.file_path,'line',c.line,'receiver',c.receiver) AS row FROM calls c LEFT JOIN nodes n ON n.id=c.caller_id " + ("WHERE c.callee_name IN ('QueryUnitFlows','requestData','send','get') " if scope=='source' else '') + 'ORDER BY c.file_path,c.line',
        }
        for key, query in queries.items():
            stdout, _ = run(scope+'-'+key, ['--no-autoheal','query',query,'--path',out/scope,'--limit','10000'])
            # One JSON column avoids ambiguity from SQL's plain-text table separator.
            rows = [json.loads(line) for line in stdout.splitlines() if line.startswith('{')]
            record['queries'][key] = {'query':query,'rows':normalize(rows,roots)}
        report['scopes'][scope] = record
        write(out/'codegraph-evidence.json',report)
        print(f'CodeGraph {scope}: indexed and queried', flush=True)
    verify_checkout(source,SOURCE_SHA)
    verify_checkout(tool,TOOL_SHA)


if __name__ == '__main__':
    main()
