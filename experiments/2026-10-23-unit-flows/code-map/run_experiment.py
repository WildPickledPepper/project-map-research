"""Independent code-map experiment. Requires pinned external checkouts; no target build or LLM.
Usage: python run_experiment.py --source <msinsight-full> --tool <code-map-new> --reference <reference.json> --output-dir <external-results>
All generated inputs, graphs and logs stay in --output-dir. Do not publish fixtures/raw graphs.
"""
import argparse, collections, hashlib, json, pathlib, platform, shutil, subprocess, time

HERE = pathlib.Path(__file__).resolve().parent
TOOL_COMMIT = 'd57c92bda4c3b1f62be8d2e75c9a45dddd430bb4'
SOURCE_COMMIT = 'd4e8d1cf9f90208bcbe5371c127088f6fd66c688'

def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

def execute(name, cmd, cwd, expected_exit=0):
    started = time.perf_counter()
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
    elapsed = round(time.perf_counter()-started, 3)
    (HERE/'raw').mkdir(exist_ok=True)
    (HERE/'raw'/f'{name}.log').write_text(p.stdout+'\nSTDERR\n'+p.stderr, encoding='utf-8')
    if p.returncode != expected_exit:
        raise RuntimeError(f'{name}: exit {p.returncode}; see raw log')
    return {'name':name,'exit_code':p.returncode,'seconds':elapsed}

def manifest(root):
    return [{'path': p.relative_to(root).as_posix(), 'bytes': p.stat().st_size,
             'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in sorted(root.rglob('*')) if p.is_file() and '.code-map' not in p.parts and not p.name.endswith('.project-map.json')]

def summary(g):
    return {'nodes':len(g['nodes']), 'edges':len(g['edges']),
            'node_types':dict(collections.Counter(n['type'] for n in g['nodes'])),
            'edge_types':dict(collections.Counter(e['type'] for e in g['edges'])),
            'file_paths':sorted({n['path'] for n in g['nodes'] if n.get('path')}),
            'endpoints':[{'id':n['id'],'backend':n.get('meta',{}).get('backend')} for n in g['nodes'] if n['type']=='endpoint'],
            'http_edges':[{k:e[k] for k in ('from','to','type')} for e in g['edges'] if e['type'] in ('calls-api','matches-endpoint','resolved-controller','handled-by')],
            'warnings':g.get('warnings',[])}

def config(name, front, back):
    return {'schemaVersion':1,'project':{'name':name, 'graphOutput':'.code-map/graph.json'},
            'sourceRoots':{'frontend':front, 'backend':back},
            'imports':{'aliases':[{'prefix':'@insight/lib','path':'modules/lib'},
                                  {'prefix':'@/','path':'modules/framework/src'}]}}

def main():
    global HERE
    ap=argparse.ArgumentParser(); ap.add_argument('--source',required=True,type=pathlib.Path); ap.add_argument('--tool',required=True,type=pathlib.Path)
    ap.add_argument('--reference',required=True,type=pathlib.Path); ap.add_argument('--output-dir',required=True,type=pathlib.Path)
    args=ap.parse_args(); HERE=args.output_dir.resolve()
    source=args.source.resolve(); tool=args.tool.resolve(); cli=str(tool/'cli.mjs')
    research_repo=pathlib.Path(__file__).resolve().parents[3]
    if HERE.exists() or any(HERE==p or HERE.is_relative_to(p) for p in (source,tool,research_repo)):
        raise SystemExit('Use a new output directory outside the source, tool and research repositories.')
    HERE.mkdir(parents=True)
    for root, expected in [(source,SOURCE_COMMIT),(tool,TOOL_COMMIT)]:
        actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
        if actual!=expected: raise RuntimeError('Commit mismatch')
        if subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=root,text=True).strip():
            raise RuntimeError('Tracked checkout changes found')
    reference=json.loads(args.reference.read_text(encoding='utf-8'))
    selected={a['path'] for a in reference['anchors']}
    selected.update(['package.json','modules/timeline/package.json','modules/package.json','modules/tsconfig.json',
        'modules/timeline/tsconfig.json','modules/lib/package.json','modules/lib/tsconfig.json','modules/framework/package.json',
        'modules/timeline/src/components/FilterLinkLine.tsx','modules/timeline/src/insight/units/AscendUnit.tsx',
        'modules/timeline/src/api/interface.ts','modules/timeline/src/connection/index.ts','modules/timeline/src/connection/messageSender.ts',
        'modules/timeline/src/connection/handler.ts','modules/timeline/src/connection/defs.ts','modules/timeline/src/connection/baseline.ts',
        'modules/lib/index.ts','modules/lib/src/utils/index.ts','modules/lib/src/utils/Console.ts',
        'modules/framework/src/connection/index.ts','modules/framework/src/connection/defs.ts',
        'modules/framework/src/connection/interceptor.ts','modules/framework/src/connection/interceptorHandler.ts',
        'modules/framework/src/connection/notification.ts','modules/framework/src/connection/notificationHandler.ts',
        'modules/framework/src/connection/sendNotification.ts','modules/framework/src/centralServer/websocket/defs.ts',
        'server/src/modules/timeline/core/database/DataBaseManager.cpp',
        'server/src/modules/timeline/core/database/DbTraceDataBase.h',
        'server/src/modules/timeline/core/database/TextTraceDatabase.h',
        'server/src/modules/timeline/handler/QueryFlowsBySliceInfoHandler.h'])
    fixtures=HERE/'fixtures'; fixtures.mkdir(exist_ok=True)
    # Fail if existing files would contaminate discovery. Re-run into the same directory is not supported.
    slice_root=fixtures/'insight'; slice_root.mkdir()
    missing=[]
    for rel in sorted(selected):
        src=source/rel
        if not src.is_file(): missing.append(rel); continue
        dst=slice_root/rel; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(src,dst)
    write_json(HERE/'manifest.json',{'source_commit':SOURCE_COMMIT,'files':manifest(slice_root),'requested_but_absent':missing})
    runs=[]; graphs={}
    def scan(name,root,cfg=None):
        cmd=['node',cli,'--scan']+(['--config',cfg] if cfg else [])
        run=execute(name,cmd,root); run['command']='node <code-map>/cli.mjs --scan'+(' --config '+cfg if cfg else '')
        run['cwd']='fixtures/'+root.name; runs.append(run)
        graph=json.loads((root/'.code-map/graph.json').read_text(encoding='utf-8'))
        write_json(HERE/'raw'/f'{name}.graph.json',graph); graphs[name]=graph
        return graph
    auto=scan('insight-auto',slice_root)
    write_json(HERE/'raw'/'insight-detected-config.json',auto.get('projectMap',{}))
    cfg=config('Insight real slice explicit React roots','modules','server')
    write_json(slice_root/'explicit.project-map.json',cfg)
    explicit=scan('insight-explicit',slice_root,'explicit.project-map.json')
    runs.append(execute('insight-query-export',['node',cli,'submap','create','unit-flows-imports','--graph','.code-map/graph.json',
        '--node','file:modules/timeline/src/api/request.ts','--direction','both','--depth','3','--output','.code-map/unit-flows.submap.json','--non-interactive'],slice_root))
    runs.append(execute('insight-submap-inspect',['node',cli,'submap','inspect','.code-map/unit-flows.submap.json','--json'],slice_root))
    submap=json.loads((slice_root/'.code-map/unit-flows.submap.json').read_text(encoding='utf-8'))
    write_json(HERE/'raw/insight-query-export.submap.json',submap)
    runs.append(execute('insight-missing-handler-query',['node',cli,'submap','create','missing-handler','--graph','.code-map/graph.json',
        '--node','file:server/src/modules/timeline/handler/QueryFlowsBySliceInfoHandler.cpp','--stdout','--json-errors','--non-interactive'],slice_root,expected_exit=3))
    diagnostic_log=(HERE/'raw/insight-missing-handler-query.log').read_text(encoding='utf-8')
    diagnostic=next(json.loads(line) for line in diagnostic_log.splitlines() if line.startswith('{"error":'))
    # Mutate only copied C++ protocol and provider; no target checkout modification.
    proto=slice_root/'server/src/modules/defs/ProtocolDefs.h'
    before=proto.read_text(encoding='utf-8')
    after=before.replace('REQ_RES_UNIT_FLOWS = "unit/flows"','REQ_RES_UNIT_FLOWS = "unit/flows/v2"')
    assert after!=before
    proto.write_text(after,encoding='utf-8')
    (slice_root/'server/src/modules/timeline/handler/QueryFlowsBySliceInfoHandler.cpp').unlink()
    changed=scan('insight-mutated',slice_root,'explicit.project-map.json')
    write_json(HERE/'mutated-manifest.json',{'files':manifest(slice_root)})
    # Supported React + .NET control: separate concrete method/path negatives and duplicate service positive.
    http=fixtures/'http-controls'; http.mkdir()
    files={
      'src/App.tsx':"import React from 'react'; import { load } from './api'; export const App = () => <button onClick={load}>Load</button>;\n",
      'src/api.ts':"export async function load() { return fetch('/api/items', {method:'GET'}); }\nexport const wrongMethod = () => fetch('/api/onlyget', {method:'POST'});\nexport const wrongPath = () => fetch('/api/absent', {method:'GET'});\nexport const sameServicePath = () => fetch('/api/shared', {method:'GET'});\nexport const foreignOrigin = () => fetch('https://other.invalid/api/items', {method:'GET'});\n",
      'backend/ServiceA/Controllers/ItemsController.cs':'''using Microsoft.AspNetCore.Mvc;
namespace ServiceA;
[ApiController]
[Route("api")]
public class ItemsController : ControllerBase {
 [HttpGet("items")] public string Items() => "ok";
 [HttpGet("onlyget")] public string OnlyGet() => "ok";
 [HttpGet("shared")] public string Shared() => "A";
}
''',
      'backend/ServiceB/Controllers/SharedController.cs':'''using Microsoft.AspNetCore.Mvc;
namespace ServiceB;
[ApiController]
[Route("api")]
public class SharedController : ControllerBase {
 [HttpGet("shared")] public string Shared() => "B";
}
''',
      'package.json':json.dumps({'name':'http-controls','dependencies':{'react':'18.3.1'}}),
      'backend/ServiceA/ServiceA.csproj':'<Project Sdk="Microsoft.NET.Sdk.Web"><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>',
      'backend/ServiceB/ServiceB.csproj':'<Project Sdk="Microsoft.NET.Sdk.Web"><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>'
    }
    for rel,txt in files.items():
        p=http/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(txt,encoding='utf-8')
    write_json(http/'explicit.project-map.json',config('HTTP matching controls','src','backend'))
    write_json(HERE/'http-manifest.json',{'files':manifest(http)})
    http_base=scan('http-baseline',http,'explicit.project-map.json')
    (http/'backend/ServiceB/Controllers/SharedController.cs').unlink()
    http_deleted=scan('http-provider-deleted',http,'explicit.project-map.json')
    api=http/'src/api.ts'; api.write_text(api.read_text(encoding='utf-8').replace("fetch('/api/items'", "fetch('/api/renamed'"),encoding='utf-8')
    http_changed=scan('http-path-changed',http,'explicit.project-map.json')
    # Clean final-state rebuild proves the explicit full scan has no stale output dependency.
    clean=fixtures/'http-final-clean'; clean.mkdir()
    for p in http.rglob('*'):
        if p.is_file() and '.code-map' not in p.parts:
            q=clean/p.relative_to(http); q.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(p,q)
    final_clean=scan('http-final-clean',clean,'explicit.project-map.json')
    canonical=lambda g: {'nodes':sorted(g['nodes'],key=lambda x:x['id']), 'edges':sorted(g['edges'],key=lambda x:x['id'])}
    exact_cpp_paths=[x['path'] for x in json.loads((HERE/'manifest.json').read_text(encoding='utf-8'))['files'] if pathlib.Path(x['path']).suffix in ('.h','.cpp')]
    initial_paths={row['path'] for row in json.loads((HERE/'manifest.json').read_text(encoding='utf-8'))['files']}
    evidence={'schema_version':1,'tool':{'url':'https://github.com/abbaing/code-map','commit':TOOL_COMMIT,'version':'0.1.0','license':'AGPL-3.0-only'},
      'source':{'url':'https://gitcode.com/Ascend/msinsight','commit':SOURCE_COMMIT},
      'environment':{'os':platform.system(),'os_release':platform.release(),'python':platform.python_version(),'node':subprocess.check_output(['node','--version'],text=True).strip()},
      'execution':{'llm_calls':False,'gui_or_server_started':False,'runtime_links_used':False,'upstream_modified':False,'source_checkout_modified':False,'mode':'scan-only; explicit full rescans'},
      'runs':runs,'results':{k:summary(v) for k,v in graphs.items()},
      'query_diagnostic':diagnostic,
      'query_export':{'selector':'file:modules/timeline/src/api/request.ts','direction':'both','depth':3,
                      'node_ids':[n['id'] for n in submap['nodes']],
                      'edges':[{k:e[k] for k in ('from','to','type')} for e in submap['edges']]},
      'checks':{'insight_semantic_graph_unchanged_after_cpp_mutation':canonical(explicit)==canonical(changed),
                'http_final_graph_matches_clean_rebuild':canonical(http_changed)==canonical(final_clean),
                'cpp_paths_in_slice_after_mutation':exact_cpp_paths,
                'cpp_nodes_in_explicit_graph':[n for n in explicit['nodes'] if pathlib.Path(n.get('path','')).suffix in ('.cpp','.h')],
                'insight_business_token_in_graph':'unit/flows' in json.dumps(explicit),
                'anchor_file_presence':[{'id':a['id'],'path':a['path'],'in_slice':a['path'] in initial_paths,
                                        'in_explicit_graph':any(n.get('path')==a['path'] for n in explicit['nodes'])} for a in reference['anchors']]},
      'unverified':['GUI trace rendering','watch/continuous updates','runtime behavior/scenarios','full target repository','custom C++ plugin','target implementation selection and dataflow','rapid commits/failure retry/cross-version snapshots']}
    write_json(HERE/'evidence.json',evidence)
    compact={k:evidence[k] for k in ('schema_version','tool','source','environment','execution','runs','checks','unverified','query_diagnostic')}
    compact['scans']={k:{a:s[a] for a in ('nodes','edges','node_types','edge_types','warnings')} for k,s in evidence['results'].items()}
    compact['auto_detected_roots']=auto.get('projectMap',{}).get('sourceRoots')
    compact['explicit_roots']=cfg['sourceRoots']
    compact['query_export']={k:v for k,v in evidence['query_export'].items() if k!='edges'}
    compact['http_baseline']={'endpoints':evidence['results']['http-baseline']['endpoints'],'edges':evidence['results']['http-baseline']['http_edges']}
    compact['http_deletion_removed']={'node_ids':sorted({n['id'] for n in http_base['nodes']}-{n['id'] for n in http_deleted['nodes']}),
        'edge_ids':sorted({e['id'] for e in http_base['edges']}-{e['id'] for e in http_deleted['edges']})}
    write_json(HERE/'evidence.compact.json',compact)
    print(json.dumps({'complete':True,'runs':len(runs),'slice_files':len(manifest(slice_root)),'missing':missing,'summaries':{k:{'nodes':len(v['nodes']),'edges':len(v['edges'])} for k,v in graphs.items()}},indent=2))

if __name__=='__main__': main()
