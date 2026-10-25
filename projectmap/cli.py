"""One command for setup, versioned builds and read-only project understanding."""
import argparse
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

from adapters.project_map import encoded
from adapters.snapshot_refresh import RefreshBusy
from projectmap import __version__
from projectmap.workspace import VIEWS, Workspace, read


def parser():
    p=argparse.ArgumentParser(prog='project-map',description=__doc__)
    p.add_argument('--version',action='version',version=__version__)
    p.add_argument('--workspace',type=Path,required=True,help='State directory outside the source repository')
    p.add_argument('--pretty',action='store_true')
    sub=p.add_subparsers(dest='command',required=True)
    init=sub.add_parser('init',help='Register a source checkout without modifying it')
    init.add_argument('--source',type=Path,required=True);init.add_argument('--revision',default='HEAD')
    for key in ('typescript','analysis','parser-cache','dll-dir'):init.add_argument('--'+key,type=Path)
    sub.add_parser('setup',help='Install pinned TypeScript into this workspace')
    doctor=sub.add_parser('doctor');doctor.add_argument('--probe-parser',action='store_true')
    sub.add_parser('status',help='Check selected commit, dirty worktree and active snapshot')
    for name in ('build','update'):
        build=sub.add_parser(name);build.add_argument('--watch',action='store_true');build.add_argument('--interval',type=float,default=2)
    attach=sub.add_parser('attach',help='Index an existing immutable extraction')
    attach.add_argument('--graph',type=Path,required=True);attach.add_argument('--runtime-store',type=Path)
    query=sub.add_parser('query',help='Bounded navigation; results carry source and snapshot identities')
    query.add_argument('view',choices=sorted(VIEWS))
    for key in ('text','kind','module','name','start','target','path','entity','id','snapshot','cursor'):query.add_argument('--'+key)
    query.add_argument('--pointer',default='');query.add_argument('--direction',choices=['out','in'],default='out')
    query.add_argument('--kinds',help='Comma-separated exact relationship types')
    for name,default in [('depth',4),('limit',30),('nodes',200),('edges',500),('output-bytes',131072),('context',8)]:query.add_argument('--'+name,type=int,default=default)
    query.add_argument('--line',type=int);query.add_argument('--seconds',type=float,default=3)
    query.add_argument('--allow-stale',action='store_true')
    explain=sub.add_parser('explain',help='Composed request/field/response evidence, in a bounded worker process')
    explain.add_argument('start');explain.add_argument('--field',action='append',required=True)
    explain.add_argument('--depth',type=int,default=16);explain.add_argument('--limit',type=int,default=20)
    explain.add_argument('--offset',type=int,default=0);explain.add_argument('--snapshot')
    explain.add_argument('--seconds',type=float,default=30);explain.add_argument('--allow-stale',action='store_true')
    runtime=sub.add_parser('runtime',help='List runtime evidence or validate one explicit execution context')
    runtime.add_argument('--id',dest='record_id');runtime.add_argument('--context',type=Path);runtime.add_argument('--scenario')
    runtime.add_argument('--limit',type=int,default=20);runtime.add_argument('--offset',type=int,default=0)
    runtime.add_argument('--allow-stale',action='store_true')
    sub.add_parser('serve',help='Expose read-only queries over MCP stdio')
    return p


def main(argv=None):
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')
    args=parser().parse_args(argv)
    def emit(value,stream=sys.stdout):
        print(json.dumps(value,ensure_ascii=False,indent=2 if args.pretty else None,allow_nan=False),file=stream,flush=True)
    try:
        if args.command=='init':
            w=Workspace.create(args.workspace,args.source,revision=args.revision,typescript=args.typescript,
                analysis=read(args.analysis) if args.analysis else None,parser_cache=args.parser_cache,dll_dir=args.dll_dir)
            result=w.status()
        else:
            w=Workspace(args.workspace)
            if args.command=='setup':result=w.setup()
            elif args.command=='doctor':result=w.doctor(args.probe_parser)
            elif args.command=='status':result=w.status()
            elif args.command=='attach':result=w.attach(args.graph,runtime_store=args.runtime_store)
            elif args.command=='query':
                values={k:v for k,v in vars(args).items() if k not in {'workspace','command','pretty','view'}}
                if values.get('kinds'):values['kinds']=values['kinds'].split(',')
                result=w.query(args.view,**values)
            elif args.command=='explain':result=w.explain(args.start,args.field,allow_stale=args.allow_stale,seconds=args.seconds,limit=args.limit,offset=args.offset,snapshot=args.snapshot,depth=args.depth)
            elif args.command=='runtime':result=w.runtime(record_id=args.record_id,context=read(args.context) if args.context else None,
                scenario=args.scenario,limit=args.limit,offset=args.offset,allow_stale=args.allow_stale)
            elif args.command=='serve':
                from projectmap.mcp_server import create_server
                create_server(w).run(transport='stdio');return 0
            else:
                if not .1<=args.interval<=60:raise ValueError('Watch interval must be between 0.1 and 60 seconds')
                while True:
                    result=w.update(emit=lambda e:emit(e,sys.stderr));emit(result)
                    if not args.watch:return 0 if result['status'] in {'ready','unchanged'} else 2
                    # Retry after input/config changes or a watcher restart, not in a failed tight loop.
                    signature=(w.status()['target_commit'],encoded(read(w.file)['analysis']))
                    while True:
                        time.sleep(args.interval)
                        current=(w.status()['target_commit'],encoded(read(w.file)['analysis']))
                        if current!=signature:break
        emit(result)
        if args.command=='doctor' and not result['ready_for_build']:return 2
        return 0
    except KeyboardInterrupt:return 130
    except (ValueError,OSError,sqlite3.Error,subprocess.SubprocessError,RefreshBusy,ImportError) as error:
        emit({'error':str(error),'command':args.command,'historical_assets_enabled':False},sys.stderr)
        return 2


if __name__=='__main__':raise SystemExit(main())
