"""A persistent tool workspace over the existing extractor, refresher and navigation index."""
from collections import Counter
from contextlib import contextmanager
from functools import partial
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import uuid

from adapters.project_map import Budget, ProjectMap, build_index, encoded
from adapters.repository_discovery import discover
from adapters.snapshot_inputs import commit, normalize_config, git
from adapters.snapshot_refresh import Refresher, atomic_json, read_json, read_snapshot, read_state, writer_lock
from projectmap import __version__
from projectmap.version import ROOT, rules_version

VIEWS={'overview','links','files','search','entries','providers','status','neighbors','trace','impact','path','detail','diagnostics','source'}


def read(path):return read_json(path)


def default_analysis():
    return normalize_config({'version':1,'scope':{'discovery':{}},'deployment':{'version':1,'services':[]},'storage':'json'})


def node_typescript(explicit=None, paths=()):
    if explicit:
        path=Path(explicit).expanduser().resolve()
        if not path.is_file():raise ValueError('TypeScript module not found: '+str(path))
        return path
    script='process.stdout.write(require.resolve("typescript",{paths:JSON.parse(process.argv[1])}))'
    result=subprocess.run(['node','-e',script,json.dumps([str(p) for p in paths])],capture_output=True,text=True,encoding='utf-8')
    if result.returncode:raise ValueError('TypeScript 5.9.3 is missing; run project-map setup or init with --typescript PATH')
    return Path(result.stdout).resolve()


class Workspace:
    def __init__(self,directory):
        self.directory=Path(directory).expanduser().resolve()
        self.file=self.directory/'project-map.json'
        self.config=read(self.file)
        if self.config.get('schema')!=1 or self.config.get('historical_assets')!={'enabled':False}:
            raise ValueError('Unsupported workspace configuration; historical assets are disabled in this tool version')
        self.source=Path(self.config['source']).resolve()
        self._check_location(self.source,self.directory)

    @staticmethod
    def _check_location(source,directory):
        if source.is_relative_to(directory) or directory.is_relative_to(source):
            raise ValueError('Choose a workspace outside the source repository')
        if directory.is_relative_to(ROOT) or ROOT.is_relative_to(directory):
            raise ValueError('Choose a workspace outside the installed tool/research directory')

    @classmethod
    def create(cls,directory,source,*,revision='HEAD',typescript=None,analysis=None,parser_cache=None,dll_dir=None):
        directory=Path(directory).expanduser().resolve();source=Path(source).expanduser().resolve()
        cls._check_location(source,directory);commit(source,revision)
        if (directory/'project-map.json').exists():raise ValueError('Workspace already exists; use status or update')
        directory.mkdir(parents=True,exist_ok=True)
        config={'schema':1,'source':str(source),'revision':revision,'analysis':normalize_config(analysis or default_analysis()),
            'typescript':str(Path(typescript).resolve()) if typescript else None,
            'parser_cache':str(Path(parser_cache).resolve()) if parser_cache else os.environ.get('PROJECT_MAP_PARSER_CACHE'),
            'dll_dir':str(Path(dll_dir).resolve()) if dll_dir else os.environ.get('PROJECT_MAP_DLL_DIR'),
            'historical_assets':{'enabled':False},'active':None}
        atomic_json(directory/'project-map.json',config)
        return cls(directory)

    def reload(self):self.config=read(self.file);return self.config

    @contextmanager
    def engine_environment(self):
        changes={k:v for k,v in [('PROJECT_MAP_PARSER_CACHE',self.config.get('parser_cache')),
                                ('PROJECT_MAP_DLL_DIR',self.config.get('dll_dir'))] if v}
        previous={k:os.environ.get(k) for k in changes};os.environ.update(changes);handle=None
        if os.name=='nt' and self.config.get('dll_dir'):handle=os.add_dll_directory(self.config['dll_dir'])
        try:yield
        finally:
            if handle:handle.close()
            for key,value in previous.items():
                if value is None:os.environ.pop(key,None)
                else:os.environ[key]=value

    def typescript(self):
        return node_typescript(self.config.get('typescript'),[self.directory/'dependencies',Path.cwd(),ROOT])

    def setup(self):
        npm=shutil.which('npm.cmd' if os.name=='nt' else 'npm')
        if not npm:raise ValueError('Install Node.js 22 and npm before setup')
        target=self.directory/'dependencies';target.mkdir(exist_ok=True)
        with (self.directory/'setup.log').open('w',encoding='utf-8') as log:
            subprocess.run([npm,'install','--prefix',str(target),'--ignore-scripts','--no-audit','--no-fund','typescript@5.9.3'],
                           cwd=target,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
        config=self.reload();config['typescript']=str(node_typescript(paths=[target]));atomic_json(self.file,config)
        return {'status':'ready','typescript':config['typescript'],'log':str(self.directory/'setup.log')}

    def doctor(self,probe_parser=False):
        checks=[]
        def check(name,callback,required=True):
            try:value=callback();checks.append({'name':name,'ok':True,'value':value,'required_for_build':required})
            except Exception as error:checks.append({'name':name,'ok':False,'error':str(error),'required_for_build':required})
        check('git_source',lambda:commit(self.source,self.config['revision']))
        check('node',lambda:subprocess.check_output(['node','--version'],text=True).strip())
        check('typescript',lambda:subprocess.check_output(['node','-e','process.stdout.write(require(process.argv[1]).version)',str(self.typescript())],text=True).strip())
        for name in ('tree-sitter','tree-sitter-language-pack','kuzu','jedi','parso','mcp'):
            check(name,lambda name=name:importlib.metadata.version(name),name!='mcp')
        check('engine_revision',lambda:rules_version())
        from adapters.rust_project import binary as rust_binary,available as rust_available,tool_output
        for name in ('cargo','rustc','rust-analyzer'):
            def rust_tool(name=name):
                if not rust_available(name):raise ValueError('Install the native Rust analysis tool and expose its executable: '+name)
                return tool_output([rust_binary(name),'--version'],ROOT).strip()
            check('rust_'+name,rust_tool,False)
        if probe_parser:
            def parser():
                with self.engine_environment():
                    import tree_sitter_language_pack as pack
                    if self.config.get('parser_cache'):pack.configure(pack.PackConfig(cache_dir=self.config['parser_cache']))
                    tree=pack.get_parser('cpp').parse(b'int main(){return 0;}')
                    if tree.root_node.has_error:raise ValueError('C++ parser probe failed')
                    return 'parsed'
            check('cpp_parser',parser)
        return {'tool_version':__version__,'ready_for_build':all(c['ok'] for c in checks if c['required_for_build']),
            'checks':checks,'historical_assets':{'enabled':False},
            'deployment_binding':'configured' if self.config['analysis']['deployment'].get('services') else 'unconfigured_candidates_retain_scope_gaps'}

    def status(self):
        config=self.reload();active=config.get('active');head=commit(self.source);target=commit(self.source,config['revision'])
        dirty=bool(git(self.source,'status','--porcelain','--untracked-files=normal').strip())
        state=read_state(self.directory/'store')
        current=bool(active and active['source_commit']==target and active['analysis']==config['analysis'])
        return {'tool_version':__version__,'source':str(self.source),'selected_revision':config['revision'],'target_commit':target,
            'installed_rules_commit':rules_version(),'graph_rules_commit':active['build_version'].get('rules_commit') if active else None,
            'repository_head':head,'worktree_has_changes':dirty,'worktree_included':False,'active':active,
            'freshness':'current_for_selected_commit' if current else 'outdated' if active else 'not_built',
            'graph_refresh_status':state.get('status') if state else 'not_started',
            'navigation_pending':bool(state and state.get('last_success') and (not active or active['snapshot']!=state['last_success']['snapshot'])),
            'historical_assets':{'enabled':False},'missing_relation_meaning':'unknown'}

    def _publish_index(self,graph_path,*,store=None,snapshot_id=None):
        initial=read(self.file);graph=read(graph_path)
        if commit(self.source,graph['source_commit'])!=graph['source_commit']:raise ValueError('Graph source commit is unavailable')
        if graph.get('version',{}).get('source_commit')!=graph['source_commit']:raise ValueError('Graph version/source mismatch')
        if graph.get('provenance',{}).get('working_tree_included') is not False:raise ValueError('Require an immutable committed-source extraction')
        uid=uuid.uuid4().hex;relative='navigation/'+uid+'.sqlite';index=self.directory/relative
        descriptor=build_index(graph,discover(self.source,graph['source_commit']),index,
            navigation_version={'schema':'project-map/1','tool_version':__version__,'rules_commit':rules_version()})
        # Re-read before publishing so a long build cannot overwrite concurrent configuration changes.
        if read(self.file)!=initial:raise ValueError('Workspace changed while indexing; active version was preserved')
        initial['analysis']=graph['version']['config']
        initial['active']={'snapshot':graph['snapshot'],'source_commit':graph['source_commit'],'index':relative,
            'graph':str(Path(graph_path).resolve()),'analysis':graph['version']['config'],'build_version':graph['version']['build_version'],
            'runtime_store':str(Path(store).resolve()) if store else None,'snapshot_id':snapshot_id}
        atomic_json(self.file,initial);self.config=initial
        return {'status':'ready','snapshot':graph['snapshot'],'source_commit':graph['source_commit'],'counts':descriptor['counts']}

    def attach(self,graph_path,*,runtime_store=None):
        with writer_lock(self.directory):
            snapshot_id=None
            if runtime_store:
                resolved=read_snapshot(runtime_store);receipt=resolved['receipt'];graph=read(graph_path)
                if any(graph['version'].get(k)!=receipt[k] for k in ('source_commit','snapshot','config','build_version')):
                    raise ValueError('Runtime store and graph must identify the same snapshot')
                snapshot_id=receipt['id'];del graph
            return self._publish_index(graph_path,store=runtime_store,snapshot_id=snapshot_id)

    def update(self,emit=None,builder=None,version=None):
        from scripts.build_project_snapshot import build,build_version
        with writer_lock(self.directory):
            ts=self.typescript() if builder is None else None
            initial=self.reload();frozen=version or build_version(ts)
            def config():return read(self.file)['analysis']
            def current_version():return version or build_version(ts)
            with self.engine_environment():
                state=Refresher(self.source,self.directory/'store',config,current_version,
                    builder or partial(build,typescript=ts),revision=initial['revision'],on_event=emit).run(max_builds=1)
            if state['status']!='up_to_date':return {'status':state['status'],'error':state.get('last_error'),'active_preserved':True}
            resolved=read_snapshot(self.directory/'store');receipt=resolved['receipt']
            if self.config.get('active',{} ) and self.config['active']['snapshot']==receipt['snapshot'] and (self.directory/self.config['active']['index']).is_file():
                return {'status':'unchanged','snapshot':receipt['snapshot'],'source_commit':receipt['source_commit']}
            if current_version()!=frozen:raise ValueError('Tool version changed during update')
            return self._publish_index(Path(resolved['directory'])/'graph.json',store=self.directory/'store',snapshot_id=receipt['id'])

    def _active(self,allow_stale=False):
        status=self.status();active=status['active']
        if not active:raise ValueError('No project map; run build or attach first')
        if status['freshness']=='outdated' and not allow_stale:raise ValueError('Project map is outdated; run update, pin a revision, or explicitly use --allow-stale')
        return active,status

    def query(self,view,*,allow_stale=False,**args):
        if view not in VIEWS:raise ValueError('Unsupported map view: '+view)
        active,status=self._active(allow_stale)
        budget=Budget(args.pop('seconds',3),args.pop('nodes',200),args.pop('edges',500),args.pop('output_bytes',131072))
        q=ProjectMap(self.directory/active['index'],budget=budget,expected_snapshot=args.pop('snapshot',None) or active['snapshot'])
        page={'limit':args.pop('limit',30),'cursor':args.pop('cursor',None)}
        try:
            if view=='overview':result=q.overview(**page)
            elif view=='links':result=q.links(args.get('module'),**page)
            elif view=='files':result=q.files(args.get('module'),**page)
            elif view=='search':result=q.search(args.get('text',''),args.get('kind'),args.get('module'),**page)
            elif view=='entries':result=q.entries(args.get('name') or args.get('start'),**page)
            elif view=='providers':result=q.providers(args.get('text',''),**page)
            elif view=='diagnostics':result=q.diagnostics(args.get('path'),**page)
            elif view=='status':result=q.status(args.get('start'))
            elif view=='neighbors':result=q.neighbors(args.get('start'),args.get('direction','out'),args.get('kinds'),**page)
            elif view in {'trace','impact','path'}:
                if view=='path' and not args.get('target'):raise ValueError('Path requires a target')
                result=q.walk(args.get('start'),direction='in' if view=='impact' else args.get('direction','out'),
                    depth=args.get('depth',4),target=args.get('target'),kinds=args.get('kinds'))
            elif view=='detail':result=q.detail(args.get('entity'),args.get('id'),args.get('pointer',''),**page)
            else:result=q.source(self.source,selector=args.get('start'),path=args.get('path'),line=args.get('line'),context=args.get('context',8))
        finally:q.close()
        result['workspace']={'freshness':status['freshness'],'worktree_has_changes':status['worktree_has_changes'],'worktree_included':False,'historical_assets_enabled':False}
        return result

    def explain(self,start,field,*,allow_stale=False,seconds=30,limit=20,offset=0,snapshot=None,depth=16):
        if not 1<=seconds<=120 or not 1<=limit<=200 or offset<0 or not 0<=depth<=64:raise ValueError('Use seconds 1..120, limit 1..200, offset >= 0 and depth 0..64')
        field=field if isinstance(field,list) else [field]
        if not field or any(not isinstance(part,str) or not part for part in field):raise ValueError('A nonempty field path is required')
        active,status=self._active(allow_stale)
        if snapshot is not None and snapshot!=active['snapshot']:raise ValueError('Field query snapshot differs from active workspace')
        request={'graph':active['graph'],'source_commit':active['source_commit'],'snapshot':active['snapshot'],
            'start':start,'field':field,'limit':limit,'offset':offset,'depth':depth}
        jobs=self.directory/'queries';jobs.mkdir(exist_ok=True)
        request_path=jobs/(uuid.uuid4().hex+'.json');atomic_json(request_path,request)
        try:
            result=subprocess.run([sys.executable,'-I','-X','utf8',str(Path(__file__).with_name('worker.py')),str(request_path)],capture_output=True,text=True,encoding='utf-8',timeout=seconds)
            if result.returncode:raise ValueError('Field query failed: '+result.stderr[-1000:])
            if len(result.stdout.encode('utf-8'))>1048576:raise ValueError('Field query exceeds 1 MiB; narrow the field or limit')
            data=json.loads(result.stdout);data['workspace']={'freshness':status['freshness'],'historical_assets_enabled':False}
            return data
        except subprocess.TimeoutExpired:
            return {'query':'explain','snapshot':active['snapshot'],'source_commit':active['source_commit'],'items':[],
                'stop_reason':'wall_time_budget','extraction_truncated':True,'missing_relation_meaning':'unknown'}
        finally:request_path.unlink(missing_ok=True)

    def runtime(self,*,record_id=None,context=None,scenario=None,limit=20,offset=0,allow_stale=False):
        active,status=self._active(allow_stale);store=active.get('runtime_store')
        if not 1<=limit<=200 or offset<0:raise ValueError('Use limit 1..200 and offset >= 0')
        if not store:return {'query':'runtime','items':[],'status':'not_attached','runtime_execution':'unknown','snapshot':active['snapshot']}
        if record_id:
            if uuid.UUID(hex=record_id).hex!=record_id:raise ValueError('Invalid runtime record ID')
            if context is None:raise ValueError('An explicit execution context is required for runtime overlay')
            from adapters.runtime_records import query_runtime
            result=query_runtime(store,record_id,snapshot_id=active['snapshot_id'],context=context)
            payload=result['record']['payload']
            return {'query':'runtime_record','id':record_id,'snapshot':active['snapshot'],'source_commit':active['source_commit'],
                'eligible_for_direct_overlay':result['eligible_for_direct_overlay'],
                'runtime_context_differences':result['runtime_context_differences'],'version_differences':result['version_differences'],
                'outcome':payload.get('outcome'),'diagnostics':payload.get('diagnostics'),
                'items':payload.get('mappings',[])[offset:offset+limit],'total':len(payload.get('mappings',[])),
                'next_offset':offset+limit if offset+limit<len(payload.get('mappings',[])) else None}
        rows=[]
        for path in sorted((Path(store)/'records').glob('*/record.json')):
            record=read(path)
            if record['kind']!='trace':continue
            payload=record['payload'];execution=payload.get('execution_context',{});case=execution.get('scenario',{})
            if scenario and scenario not in (case.get('name'),case.get('run_id')):continue
            rows.append({'id':record['id'],'source_commit':record['basis']['source_commit'],'snapshot':record['basis']['snapshot'],
                'scenario':case,'outcome':payload.get('outcome'),'stage_counts':dict(Counter(e['stage'] for e in payload.get('events',[]))),
                'same_snapshot':record['basis']['snapshot']==active['snapshot'],'eligible_for_direct_overlay':False,
                'reason':'explicit_execution_context_required'})
        return {'query':'runtime','snapshot':active['snapshot'],'source_commit':active['source_commit'],'items':rows[offset:offset+limit],
                'total':len(rows),'next_offset':offset+limit if offset+limit<len(rows) else None}
