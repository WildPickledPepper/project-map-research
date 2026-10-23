"""Reproduce original CodeGraph CLI measurements. No LLM or GUI commands.
Usage: python run_experiment.py --source-repo PATH --tool-repo PATH
  --reference PATH --binary PATH --output NEW_DIRECTORY [--phase all]
Third-party source and caches stay outside the research repository.
"""
import argparse, hashlib, json, os, pathlib, platform, shutil, subprocess, sys, time

ap=argparse.ArgumentParser()
ap.add_argument('--workspace',type=pathlib.Path,default=pathlib.Path.cwd())
ap.add_argument('--source-repo',type=pathlib.Path,required=True)
ap.add_argument('--tool-repo',type=pathlib.Path,required=True)
ap.add_argument('--reference',type=pathlib.Path,required=True)
ap.add_argument('--binary',type=pathlib.Path,required=True)
ap.add_argument('--output',type=pathlib.Path,required=True)
ap.add_argument('--phase',default='all')
args=ap.parse_args()
ws=args.workspace.resolve()
root=args.output.resolve()
source=args.source_repo.resolve()
tool=args.tool_repo.resolve()
exe=args.binary.resolve()
reference_path=args.reference.resolve()
research_repo=pathlib.Path(__file__).resolve().parents[3]
if any(root==p or root.is_relative_to(p) for p in (source,tool,research_repo)):
    raise SystemExit('Output must be outside the source, tool and research repositories.')
if args.phase=='all' and root.exists():
    raise SystemExit('Use a new output directory for a complete independent run.')
root.mkdir(parents=True,exist_ok=True)
raw=root/'raw'; raw.mkdir(exist_ok=True)
env=os.environ.copy(); env.update(CODEGRAPH_CACHE_DIR=str(root/'cache'),CODEGRAPH_AUTO_SCIP='0')
records=[]
if (root/'commands.json').exists(): records=json.loads((root/'commands.json').read_text())
def save(name,obj): (root/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def run(label,cmd,cwd=root,timeout=90):
    start=time.perf_counter()
    try:
        p=subprocess.run([str(x) for x in cmd],cwd=cwd,env=env,capture_output=True,timeout=timeout)
        stdout=p.stdout.decode('utf-8',errors='replace');stderr=p.stderr.decode('utf-8',errors='replace');code=p.returncode
    except subprocess.TimeoutExpired as e:
        stdout=(e.stdout or b'').decode('utf-8',errors='replace');stderr=(e.stderr or b'').decode('utf-8',errors='replace');code='timeout'
    elapsed=round(time.perf_counter()-start,4)
    (raw/(label+'.stdout.txt')).write_text(stdout,encoding='utf-8')
    (raw/(label+'.stderr.txt')).write_text(stderr,encoding='utf-8')
    def portable(x):
        x=str(x)
        for old,new in ((root,'<output>'),(source,'<source-repo>'),(tool,'<tool-repo>'),(exe,'<binary>'),(ws,'<workspace>')): x=x.replace(str(old),new)
        return x
    cmd_public=[portable(x) for x in cmd]
    records.append(dict(label=label,command=cmd_public,elapsed_seconds=elapsed,exit_code=code,stdout='raw/'+label+'.stdout.txt',stderr='raw/'+label+'.stderr.txt'))
    save('commands.json',records)
    print(label,code,elapsed,flush=True)
    return stdout
def cg(label,*cmd,path=None,timeout=90):
    cmd=list(cmd)
    if path is not None: cmd+=['--path',path]
    return run(label,[exe,*cmd],timeout=timeout)
def manifest(directory):
    return [dict(path=p.relative_to(directory).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(directory.rglob('*')) if p.is_file()]

slice_path=root/'unit-flows-slice'
if args.phase in ('prepare','all'):
    for checkout in (source,tool):
        if subprocess.check_output(['git','-C',str(checkout),'status','--porcelain','--untracked-files=no'],text=True).strip():
            raise SystemExit('Tracked source/tool changes found; refusing an original-version trial.')
    assert subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()=='d4e8d1cf9f90208bcbe5371c127088f6fd66c688'
    assert subprocess.check_output(['git','-C',str(tool),'rev-parse','HEAD'],text=True).strip()=='7bac941c1916d34fae0e93dd0ffeaef360d741fb'
    assert subprocess.check_output(['git','-C',str(tool),'rev-list','-n','1','v1.39.0'],text=True).strip()=='7bac941c1916d34fae0e93dd0ffeaef360d741fb'
    assert hashlib.sha256(exe.read_bytes()).hexdigest()=='54156dd1f6481b4d7658f1435b97939a606ff7447caca196bb4b89499773df22'
    save('environment.json',dict(os=platform.platform(),python=platform.python_version(),execution='original official x64 release binary; no GUI; no LLM; no SCIP/compiler oracle; process-local cache override',environment_overrides={k:('<output>/cache' if k=='CODEGRAPH_CACHE_DIR' else env[k]) for k in ('CODEGRAPH_CACHE_DIR','CODEGRAPH_AUTO_SCIP')}))
    reference=json.loads(reference_path.read_text(encoding='utf-8'))
    paths={a['path'] for a in reference['anchors']}
    paths.update('''modules/timeline/src/components/FilterLinkLine.tsx
modules/timeline/src/insight/units/AscendUnit.tsx
modules/timeline/src/api/interface.ts
modules/timeline/src/connection/index.ts
server/src/modules/timeline/TimelineModule.h
server/src/modules/ModuleManager.h
server/msinsight/include/base/BaseModule.h
server/msinsight/include/base/ModuleRequestHandler.h
server/src/modules/timeline/handler/QueryFlowsBySliceInfoHandler.h
server/src/modules/timeline/core/database/DataBaseManager.cpp
server/src/modules/timeline/core/database/VirtualTraceDatabase.cpp
server/src/modules/timeline/core/database/DbTraceDataBase.h
server/src/modules/timeline/core/database/DbTraceDataBase.cpp
server/src/modules/timeline/core/database/TextTraceDatabase.h'''.splitlines())
    # Include all real front-end direct callers (including tests), discovered from source.
    callers=subprocess.check_output(['rg','-l','getUnitFlows','modules'],cwd=source,text=True).splitlines()
    paths.update(x.replace('\\','/') for x in callers)
    # Request/response shapes and dispatch protocol support, without a synthetic graph.
    for base in ('server/src/modules/timeline/protocol','server/src/modules/protocol'):
        if (source/base).exists():
            paths.update(p.relative_to(source).as_posix() for p in (source/base).rglob('*') if p.suffix in ('.h','.cpp'))
    slice_path.mkdir(exist_ok=True)
    for rel in sorted(paths):
        p=slice_path/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/rel,p)
    rows=manifest(slice_path)
    for row in rows:
        anchors=[a['id'] for a in reference['anchors'] if a['path']==row['path']]
        row['reason']='reference_anchor' if anchors else ('frontend_direct_caller' if row['path'] in {x.replace('\\','/') for x in callers} else 'supporting_declaration_or_implementation')
        row['anchor_ids']=anchors
    save('slice-manifest.json',dict(source_commit=reference['repository']['commit'],files=rows,total_bytes=sum(x['bytes'] for x in rows),scope='selected real source slice; includes all reference anchors and all rg-discovered getUnitFlows callers; not a build closure'))
    cg('version','--version')
    run('tag-commit',['git','-C',tool,'rev-list','-n','1','v1.39.0'])
    save('binary-provenance.json',dict(source='https://github.com/sina-parsania/CodeGraph',source_commit='7bac941c1916d34fae0e93dd0ffeaef360d741fb',release='v1.39.0',release_tag_commit_matches_source=True,execution='official prebuilt Windows x64 release, not a local source build',url='https://github.com/sina-parsania/CodeGraph/releases/download/v1.39.0/codegraph-windows-x64.exe',sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),official_sha256='54156dd1f6481b4d7658f1435b97939a606ff7447caca196bb4b89499773df22',license='MIT OR Apache-2.0',source_modified=False))
if args.phase in ('slice','all'):
    cg('slice-index','index',slice_path,'--full')
    cg('slice-routes','routes',path=slice_path)
    for name in ('getUnitFlows','REQ_RES_UNIT_FLOWS','QueryFlowsBySliceInfoHandler','QueryUnitFlows','RegisterRequestHandlers','OnRequest','HandleRequest'):
        cg('slice-search-'+name,'search',name,'--limit','50',path=slice_path)
    for name in ('getUnitFlows','QueryUnitFlows'):
        cg('slice-callers-'+name,'callers',name,path=slice_path)
        cg('slice-callees-'+name,'callees',name,path=slice_path)
    cg('slice-implementers','implementers','VirtualTraceDatabase',path=slice_path)
    cg('slice-trace-handler','trace','getUnitFlows','QueryFlowsBySliceInfoHandler',path=slice_path)
    cg('slice-trace-database','trace','getUnitFlows','QueryUnitFlows',path=slice_path)
    cg('slice-impact','impact','QueryUnitFlows',path=slice_path)
    cg('slice-schema','query',"SELECT name,sql FROM sqlite_master WHERE type='table'",'--limit','100',path=slice_path)
    cg('slice-counts','query',"SELECT label,count(*) AS n FROM nodes GROUP BY label",path=slice_path)
    cg('slice-relation-counts','query',"SELECT relation,count(*) AS n FROM edges GROUP BY relation",path=slice_path)
    cg('slice-named-nodes','query',"SELECT id,name,label,file_path,line_start,data FROM nodes WHERE name LIKE '%UnitFlows%' OR name LIKE '%FlowsBySlice%' OR name='VirtualTraceDatabase' OR name='DbTraceDataBase' OR name='TextTraceDatabase'",'--limit','100',path=slice_path)
    cg('slice-named-edges','query',"SELECT a.name AS source,a.file_path AS source_file,b.name AS target,b.file_path AS target_file,e.relation,e.data FROM edges e JOIN nodes a ON a.id=e.src JOIN nodes b ON b.id=e.dst WHERE a.name LIKE '%UnitFlows%' OR b.name LIKE '%UnitFlows%' OR a.file_path LIKE '%QueryFlowsBySliceInfoHandler%' OR b.file_path LIKE '%QueryFlowsBySliceInfoHandler%'",'--limit','300',path=slice_path)
    cg('slice-raw-calls','query',"SELECT n.name,c.callee_name,c.file_path,c.line,c.receiver FROM calls c LEFT JOIN nodes n ON n.id=c.caller_id WHERE c.callee_name LIKE '%UnitFlows%' OR c.callee_name LIKE '%REQ_RES_UNIT_FLOWS%' OR n.name='getUnitFlows'",'--limit','100',path=slice_path)

if args.phase == 'diagnostic':
    cg('slice-exact-symbols','query',"SELECT name,label,file_path,line_start FROM nodes WHERE name IN ('QueryUnitFlows','HandleRequest','OnRequest','RegisterRequestHandlers','REQ_RES_UNIT_FLOWS','DbTraceDataBase','TextTraceDatabase','VirtualTraceDatabase') ORDER BY name,file_path",'--limit','100',path=slice_path)
    cg('slice-handler-definitions','query',"SELECT name,label,file_path,line_start FROM nodes WHERE file_path LIKE '%QueryFlowsBySliceInfoHandler%'",path=slice_path)
    cg('slice-db-file-definitions','query',"SELECT name,label,file_path,line_start FROM nodes WHERE file_path IN ('server/src/modules/timeline/core/database/DbTraceDataBase2.cpp','server/src/modules/timeline/core/database/TextTraceDatabase.cpp')",'--limit','300',path=slice_path)
    cg('slice-protocol-value-nodes','query',"SELECT name,label,file_path,line_start FROM nodes WHERE file_path='server/src/modules/defs/ProtocolDefs.h'",'--limit','100',path=slice_path)
    cg('slice-cpp-vs-c','query',"SELECT language,label,count(*) AS n FROM nodes GROUP BY language,label",path=slice_path)
    fixture=root/'http-fixture'
    cg('http-trace-hub','trace','loadPositive','GET /renamed',path=fixture)
    cg('http-impact-shared-hub','impact','GET /shared',path=fixture)
    cg('http-absolute-callees','callees','loadAbsolute',path=fixture)
    cpp=root/'cpp-fixture';cpp.mkdir(exist_ok=True)
    inputs={'sample.cpp':'class InlineDatabase { public: bool QueryInline() { return true; } };\nclass ExternalDatabase { public: bool QueryExternal(); };\nbool ExternalDatabase::QueryExternal() { return true; }\nbool QueryFree() { return true; }\n', 'sample.h':'class HeaderDatabase { public: virtual bool QueryHeader() = 0; };\n', 'sample.hpp':'class HppDatabase { public: virtual bool QueryHpp() = 0; };\n'}
    for rel,content in inputs.items(): (cpp/rel).write_text(content,encoding='utf-8')
    save('cpp-fixture-manifest.json',manifest(cpp))
    cg('cpp-index','index',cpp,'--full')
    cg('cpp-nodes','query',"SELECT name,label,language,file_path,line_start FROM nodes ORDER BY file_path,line_start",'--limit','100',path=cpp)

if args.phase in ('fixture','all'):
    fixture=root/'http-fixture';fixture.mkdir(exist_ok=True)
    inputs={
        'frontend/client.ts':'''import axios from 'axios';\nconst api = axios.create({baseURL: 'https://service-a.example'});\nconst apiB = axios.create({baseURL: 'https://service-b.example'});\nexport function loadPositive() { return api.get('/positive'); }\nexport function loadSamePathA() { return api.get('/shared'); }\nexport function loadSamePathB() { return apiB.get('/shared'); }\nexport function loadAbsolute() { return api.get('https://service-a.example/shared'); }\nexport function loadPostNegative() { return api.post('/shared'); }\n''',
        'service-a/routes.py':'''from flask import Flask\napp = Flask(__name__)\ndef db_positive():\n    return 'positive'\ndef db_a():\n    return 'a'\n@app.get('/positive')\ndef positive_handler():\n    return db_positive()\n@app.get('/shared')\ndef handler_a():\n    return db_a()\n''',
        'service-b/routes.py':'''from flask import Flask\napp = Flask(__name__)\ndef db_b():\n    return 'b'\n@app.get('/shared')\ndef handler_b():\n    return db_b()\n'''
    }
    for rel,content in inputs.items():
        p=fixture/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content,encoding='utf-8')
    save('fixture-manifest-before.json',manifest(fixture))
    cg('http-index','index',fixture,'--full')
    cg('http-routes','routes',path=fixture)
    cg('http-all-edges','query',"SELECT a.name AS source,a.file_path AS source_file,b.name AS target,b.file_path AS target_file,e.relation,e.data FROM edges e JOIN nodes a ON a.id=e.src JOIN nodes b ON b.id=e.dst",'--limit','300',path=fixture)
    cg('http-route-nodes','query',"SELECT id,name,file_path,data FROM nodes WHERE label='Route'",path=fixture)
    cg('http-hub-impact-before','impact','GET /shared',path=fixture)
    for label,a,b in [('positive','loadPositive','positive_handler'),('positive-db','loadPositive','db_positive'),('same-a','loadSamePathA','handler_a'),('same-b','loadSamePathA','handler_b'),('method-negative','loadPostNegative','handler_a')]:
        cg('http-trace-'+label,'trace',a,b,path=fixture)
    cg('http-impact-positive','impact','positive_handler',path=fixture)
    cg('http-impact-a','impact','handler_a',path=fixture)
    # A consumer deletion plus route change; snapshot read establishes no background CLI watcher.
    p=fixture/'frontend/client.ts';p.write_text(inputs['frontend/client.ts'].replace("api.get('/positive')","api.get('/renamed')").replace("export function loadSamePathA() { return api.get('/shared'); }\n",''),encoding='utf-8')
    save('fixture-manifest-after.json',manifest(fixture))
    cg('http-update-no-autoheal','--no-autoheal','search','loadSamePathA',path=fixture)
    cg('http-update-query-autoheal','search','loadSamePathA',path=fixture)
    cg('http-update-routes','routes',path=fixture)
    cg('http-update-edges','query',"SELECT src,dst,relation,data FROM edges ORDER BY src,dst,relation",'--limit','300',path=fixture)
    cg('http-update-nodes','query',"SELECT id,name,label,file_path,line_start,line_end FROM nodes ORDER BY id",'--limit','300',path=fixture)
    cg('http-update-full','index',fixture,'--full')
    cg('http-rebuild-edges','query',"SELECT src,dst,relation,data FROM edges ORDER BY src,dst,relation",'--limit','300',path=fixture)
    cg('http-rebuild-nodes','query',"SELECT id,name,label,file_path,line_start,line_end FROM nodes ORDER BY id",'--limit','300',path=fixture)
    save('update-comparison.json',dict(edges_identical=(raw/'http-update-edges.stdout.txt').read_bytes()==(raw/'http-rebuild-edges.stdout.txt').read_bytes(),nodes_identical=(raw/'http-update-nodes.stdout.txt').read_bytes()==(raw/'http-rebuild-nodes.stdout.txt').read_bytes(),comparison='CLI SQL rows ordered by ids; semantic nodes and edges, excludes metrics/meta/cache bytes'))

if args.phase == 'all':
    subprocess.run([sys.executable,str(pathlib.Path(__file__).resolve()),'--workspace',str(ws),'--source-repo',str(source),'--tool-repo',str(tool),'--binary',str(exe),'--reference',str(reference_path),'--output',str(root),'--phase','diagnostic'],check=True)

if args.phase in ('all','evidence'):
    def stdout(label): return (raw/(label+'.stdout.txt')).read_text(encoding='utf-8').strip()
    def table(label):
        lines=stdout(label).splitlines()
        if not lines or ' | ' not in lines[0]: return []
        keys=lines[0].split(' | ')
        rows=[]
        for line in lines[1:]:
            vals=line.split(' | ',len(keys)-1)
            if len(vals)!=len(keys): continue
            row=dict(zip(keys,vals))
            if 'data' in row:
                try: row['data']=json.loads(row['data'])
                except json.JSONDecodeError: pass
            rows.append(row)
        return rows
    recent={x['label']:x for x in json.loads((root/'commands.json').read_text(encoding='utf-8'))}
    slice_manifest=json.loads((root/'slice-manifest.json').read_text(encoding='utf-8'))
    inc_edges=table('http-update-edges');full_edges=table('http-rebuild-edges')
    inc_nodes=table('http-update-nodes');full_nodes=table('http-rebuild-nodes')
    def canonical(row): return json.dumps(row,sort_keys=True)
    inc_edge_keys={canonical(r) for r in inc_edges};full_edge_keys={canonical(r) for r in full_edges}
    inc_node_map={r['id']:r for r in inc_nodes};full_node_map={r['id']:r for r in full_nodes}
    delta=dict(
        comparison='incremental query-healed final fixture versus forced-full index of identical final source',
        only_in_incremental_edges=[json.loads(x) for x in sorted(inc_edge_keys-full_edge_keys)],
        only_in_full_edges=[json.loads(x) for x in sorted(full_edge_keys-inc_edge_keys)],
        changed_node_rows=[dict(id=k,incremental=inc_node_map.get(k),full=full_node_map.get(k)) for k in sorted(set(inc_node_map)|set(full_node_map)) if inc_node_map.get(k)!=full_node_map.get(k)],
        Calls_and_HttpCalls_rows_identical={canonical(r) for r in inc_edges if r['relation'] in ('Calls','HttpCalls')}=={canonical(r) for r in full_edges if r['relation'] in ('Calls','HttpCalls')},
        interpretation='In this fixture the surviving shared hub changes file ownership and its Defines relation endpoint; call/HTTP-call rows remain equal. This is a structural and source-location difference, not solely a metrics/metadata difference.'
    )
    save('update-delta.json',delta)
    save('compact-evidence.json',dict(
        schema_version=1,evidence_type='executed_original_release_cli_and_read_only_native_SQL_queries',
        provenance=json.loads((root/'binary-provenance.json').read_text(encoding='utf-8')),
        input=dict(commit=slice_manifest['source_commit'],files=len(slice_manifest['files']),bytes=slice_manifest['total_bytes'],manifest='slice-manifest.json'),
        counts=dict(nodes_by_label=table('slice-counts'),edges_by_relation=table('slice-relation-counts')),
        slice=dict(exact_symbols=table('slice-exact-symbols'),handler_file_definitions=table('slice-handler-definitions'),database_file_definitions=table('slice-db-file-definitions'),protocol_file_definitions=table('slice-protocol-value-nodes'),raw_calls=table('slice-raw-calls'),getUnitFlows_incoming_edges=[r['data'] for r in table('slice-named-edges') if isinstance(r.get('data'),dict) and r['data']['relation']=='Calls'],getUnitFlows_callers_stdout=stdout('slice-callers-getUnitFlows'),getUnitFlows_callees_stdout=stdout('slice-callees-getUnitFlows'),QueryUnitFlows_callers_stdout=stdout('slice-callers-QueryUnitFlows'),trace_handler_stdout=stdout('slice-trace-handler'),trace_database_stdout=stdout('slice-trace-database'),implementers_stdout=stdout('slice-implementers'),routes_stdout=stdout('slice-routes')),
        http=dict(initial_routes=[r['data'] for r in table('http-route-nodes')],initial_call_edges=[r['data'] for r in table('http-all-edges') if isinstance(r.get('data'),dict) and r['data']['relation'] in ('HttpCalls','Calls')],traces={x:stdout('http-trace-'+x) for x in ('positive','positive-db','same-a','same-b','method-negative')},shared_route_impact_stdout=stdout('http-hub-impact-before'),absolute_client_callees_stdout=stdout('http-absolute-callees'),updated_consumer_to_hub_trace_stdout=stdout('http-trace-hub')),
        cpp_fixture=table('cpp-nodes'),
        update=dict(stale_search_stdout=stdout('http-update-no-autoheal'),autoheal_search_stdout=stdout('http-update-query-autoheal'),comparison=json.loads((root/'update-comparison.json').read_text(encoding='utf-8')),delta=delta,scope='one removed TS consumer and changed relative HTTP path, another shared-path consumer survives; query-triggered healing; MCP watch not run'),
        timings={k:recent[k]['elapsed_seconds'] for k in ('slice-index','slice-callers-getUnitFlows','slice-callers-QueryUnitFlows','http-index','http-trace-positive','http-update-query-autoheal','http-update-full')},
        untested=['full repository','SCIP/compiler oracle','MCP server watcher','MindStudio dynamic runtime scenarios','unit/flows source-change updates','provider removal','handler rename','custom module-command collision update matrix','fast successive commits','failed reindex retry','cross-version snapshots'],
    ))
