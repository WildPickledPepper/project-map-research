"""Reproduce native CBM/CGC facts on identical files, without reference answers.

Run with the isolated CGC Python environment. Source manifests contain only
input paths/hashes; expected nodes and edges never enter the indexers.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time

RESEARCH = Path(__file__).resolve().parents[2]
SOURCE_SHA = 'd4e8d1cf9f90208bcbe5371c127088f6fd66c688'
CGC_SHA = '93c9685bff9151f50a3121e9913e5ba2d27c1191'
CBM_SHA256 = '39f6a789cd858d7428561ac5afaefb9a47b018dcba0ad6fa41ae71a45e0ed656'


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str)+'\n', encoding='utf-8', newline='\n')


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True, encoding='utf-8').strip()


def verify_checkout(root, sha):
    if git(root, 'rev-parse', 'HEAD') != sha or git(root, 'status', '--porcelain', '--untracked-files=no'):
        raise ValueError(f'Expected clean tracked checkout at {sha}')


def normalize(obj, roots):
    if isinstance(obj, dict):
        return {k: normalize(v, roots) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize(v, roots) for v in obj]
    if isinstance(obj, tuple):
        return [normalize(v, roots) for v in obj]
    if isinstance(obj, str):
        for root, token in roots:
            obj = obj.replace(str(root), token).replace(root.as_posix(), token)
        return obj.replace('\\', '/')
    return obj


def prepare(source, out):
    entries = {}
    old = RESEARCH/'experiments/2026-10-23-unit-flows'
    for manifest in (old/'codegraph/slice-manifest.json', old/'code-map/manifest.json'):
        for item in json.loads(manifest.read_text(encoding='utf-8'))['files']:
            entries[item['path']] = item
    rows = []
    for rel, item in sorted(entries.items()):
        data = (source/rel).read_bytes().replace(b'\r\n', b'\n')
        digest = hashlib.sha256(data).hexdigest()
        if digest != item['sha256_lf_utf8']:
            raise ValueError(f'Input hash mismatch: {rel}')
        target = out/'source'/rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        rows.append({'path': rel, 'bytes': len(data), 'sha256_lf_utf8': digest})
    (out/'fixtures').mkdir()
    for path in (Path(__file__).parent/'fixtures').iterdir():
        (out/'fixtures'/path.name).write_bytes(path.read_bytes().replace(b'\r\n', b'\n'))
    fixture_rows = [{'path': p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                    for p in sorted((out/'fixtures').iterdir())]
    write(out/'input-manifest.json', {'source_commit': SOURCE_SHA, 'files': rows,
          'fixture_origin': 'self_authored_synthetic', 'fixtures': fixture_rows,
          'scope': 'union of prior real-file slices; not a compilation closure'})
    return rows


def run_cbm(binary, out, roots):
    env = os.environ.copy()
    # Keep the Windows local IPC endpoint path short.
    (out/'c').mkdir()
    (out/'r').mkdir()
    env.update(CBM_CACHE_DIR=str(out/'c'), CBM_RUNTIME_DIR=str(out/'r'))
    results = {}
    def call(name, tool, args):
        args = dict(args, format='json')
        argfile = out/'raw'/(name+'.args.json')
        write(argfile, args)
        command = [str(binary), 'cli', tool, '--args-file', str(argfile)]
        started = time.monotonic()
        proc = subprocess.run(command, env=env, capture_output=True, timeout=240)
        (out/'raw'/(name+'.stdout.json')).write_bytes(proc.stdout)
        (out/'raw'/(name+'.stderr.log')).write_bytes(proc.stderr)
        try:
            payload = json.loads(proc.stdout)
        except ValueError:
            payload = {'non_json_stdout': proc.stdout.decode('utf-8', errors='replace')}
        results[name] = {'tool': tool, 'args': normalize(args, roots), 'exit_code': proc.returncode,
                         'seconds': round(time.monotonic()-started, 3), 'result': normalize(payload, roots)}
        write(out/'cbm-evidence.json', results)
        print(f'CBM {name}: exit={proc.returncode}', flush=True)
        if proc.returncode:
            raise RuntimeError(f'CBM {name} failed; see raw log')
        return payload
    for scope in ('source', 'fixtures'):
        project = 'p1_'+scope
        call(scope+'_index', 'index_repository', {'repo_path': str(out/scope), 'name': project, 'mode': 'moderate'})
        call(scope+'_schema', 'get_graph_schema', {'project': project})
        coverage = call(scope+'_coverage', 'check_index_coverage', {'project': project, 'diagnostics': 'full',
             'path_limit': 128,
             'paths': [p.relative_to(out/scope).as_posix() for p in sorted((out/scope).rglob('*')) if p.is_file()]})
        if coverage.get('path_has_more'):
            raise RuntimeError('Coverage is truncated; paginate before publishing evidence')
        call(scope+'_files', 'query_graph', {'project': project, 'query':
             "MATCH (n:File) RETURN n.file_path LIMIT 1000", 'max_output_tokens': 30000})
        if scope == 'fixtures':
            where = ''
        else:
            where = "WHERE n.name IN ['QueryUnitFlows','HandleRequest','send','fetch','getUnitFlows','createRequest','BaseConnector','ClientConnector','VirtualTraceDatabase','DbTraceDataBase','TextTraceDatabase'] "
        call(scope+'_symbols', 'query_graph', {'project': project, 'query':
             'MATCH (n) '+where+'RETURN n.name,n.label,n.qualified_name,n.file_path,n.start_line,n.end_line LIMIT 500', 'max_output_tokens': 30000})
        where_edge = '' if scope == 'fixtures' else "WHERE a.name IN ['HandleRequest','getUnitFlows','fetch','send'] "
        call(scope+'_calls', 'query_graph', {'project': project, 'query':
             'MATCH (a)-[r:CALLS]->(b) '+where_edge+
             'RETURN a.qualified_name,a.file_path,b.qualified_name,b.file_path,r.properties LIMIT 500', 'max_output_tokens': 30000})
    return results


def run_cgc(tool, cache, dll, out, roots):
    sys.path.insert(0, str(tool/'src'))
    handles = [os.add_dll_directory(str(dll))] if dll and os.name == 'nt' else []
    isolated_home = out/'cgc-home'
    isolated_home.mkdir()
    Path.home = classmethod(lambda cls: isolated_home)
    os.environ.update(LOG_FILE_PATH=str(out/'raw'/'cgc.log'), ENABLE_APP_LOGS='ERROR',
                      CGC_RUNTIME_DB_TYPE='kuzudb', CGC_RUNTIME_DB_PATH=str(out/'cgc.kuzu'),
                      CGC_EMBEDDED_BUFFER_POOL_MB='256', PARALLEL_WORKERS='4', SCIP_INDEXER='false')
    tmp = out/'tmp'
    tmp.mkdir()
    os.environ.update(TMP=str(tmp), TEMP=str(tmp))
    import tree_sitter_language_pack as pack
    pack.configure(pack.PackConfig(cache_dir=str(cache)))
    from codegraphcontext.tools.tree_sitter_parser import TreeSitterParser
    from codegraphcontext.cli.cli_helpers import _initialize_services
    db, builder, _, _ = _initialize_services()
    results = {'version': importlib.metadata.version('codegraphcontext'), 'commit': git(tool, 'rev-parse', 'HEAD'),
               'mode': 'unmodified Tree-sitter pipeline; no SCIP; no Query-cache shim', 'scopes': {}}
    for scope in ('source', 'fixtures'):
        started = time.monotonic()
        asyncio.run(builder.build_graph_from_path_async(out/scope))
        queries = {
            'database_counts_cumulative': 'MATCH (n) RETURN label(n) AS kind,count(*) AS count',
            'files': 'MATCH (n:File) WHERE n.path STARTS WITH $root RETURN n.path AS path',
            'symbols': "MATCH (n:Function) WHERE n.path STARTS WITH $root RETURN n.name AS name,n.path AS path,n.line_number AS line,n.class_context AS owner,n.args AS args,n.uid AS uid",
            'classes': "MATCH (n:Class) WHERE n.path STARTS WITH $root RETURN n.name AS name,n.path AS path,n.line_number AS line,n.uid AS uid",
            'calls': "MATCH (a:Function)-[r:CALLS|HEURISTIC_CALLS]->(b) WHERE a.path STARTS WITH $root RETURN a.name AS caller,a.path AS caller_path,a.line_number AS caller_line,b.name AS callee,b.path AS callee_path,b.line_number AS callee_line,label(r) AS kind,r.line_number AS call_line,r.resolution_tier AS tier,r.source AS source,r.resolution_method AS method",
        }
        record = {'index_seconds': round(time.monotonic()-started, 3), 'queries': {}}
        for key, query in queries.items():
            with db.get_driver().session() as session:
                rows = session.run(query, root=(out/scope).as_posix()).data()
            write(out/'raw'/(scope+'-cgc-'+key+'.json'), rows)
            if scope == 'source' and key == 'symbols':
                names = {'QueryUnitFlows','HandleRequest','send','fetch','getUnitFlows','createRequest'}
                rows = [r for r in rows if r['name'] in names]
            if scope == 'source' and key == 'calls':
                rows = [r for r in rows if r['caller'] in {'HandleRequest','getUnitFlows','fetch','send'}]
            record['queries'][key] = {'query': query, 'rows': normalize(rows, roots)}
        # Preserve native parser evidence: declaration omissions and unresolved raw calls.
        raw_parser = []
        paths = sorted((out/scope).rglob('*'))
        for path in paths:
            lang = {'.h':'cpp','.hpp':'cpp','.cpp':'cpp','.ts':'typescript','.tsx':'tsx'}.get(path.suffix)
            if not lang:
                continue
            data = TreeSitterParser(lang).parse(path)
            write(out/'raw'/'parsed'/scope/(path.relative_to(out/scope).as_posix()+'.json'), data)
            keep = {'QueryUnitFlows','HandleRequest','send','fetch','getUnitFlows','createRequest','query','consume','consumeOwned'}
            raw_parser.append({'path': path.relative_to(out/scope).as_posix(), 'language': lang,
                               'counts': {k:len(v) for k,v in data.items() if isinstance(v,list)},
                               'functions': [f for f in data.get('functions',[]) if f.get('name') in keep],
                               'calls': [f for f in data.get('function_calls',[]) if f.get('name') in keep],
                               'declarations': data.get('declarations',[])})
        record['parser'] = normalize(raw_parser, roots)
        results['scopes'][scope] = record
        write(out/'cgc-evidence.json', results)
        print(f'CGC {scope}: indexed and queried', flush=True)
    # Synthetic extension test: probe new tables through the same database API.
    probe = {'origin': 'synthetic_storage_roundtrip_not_extracted_product_edges'}
    try:
        with db.get_driver().session() as s:
            s.run('CREATE NODE TABLE P1Interface(id STRING, service STRING, command STRING, evidence STRING, PRIMARY KEY(id))')
            s.run('CREATE REL TABLE P1Consumes(FROM Function TO P1Interface, condition STRING, evidence STRING)')
            candidates = s.run("MATCH (f:Function) WHERE f.name='entry' AND f.path STARTS WITH $root RETURN f.uid AS uid", root=(out/'fixtures').as_posix()).data()
            uid = candidates[0]['uid']
            s.run('CREATE (i:P1Interface {id: $id, service: $service, command: $command, evidence: $evidence})',
                  id='service-a|fixture/query', service='service-a', command='fixture/query', evidence='synthetic:transport.ts')
            s.run('MATCH (f:Function {uid:$uid}),(i:P1Interface {id:$id}) CREATE (f)-[:P1Consumes {condition:$condition,evidence:$evidence}]->(i)',
                  uid=uid,id='service-a|fixture/query',condition='fixture=true',evidence='synthetic round-trip fixture')
            query='MATCH (f:Function)-[r:P1Consumes]->(i:P1Interface) RETURN f.name AS caller,i.service AS service,i.command AS command,r.condition AS condition,r.evidence AS evidence'
            probe['before_delete']=s.run(query).data()
            s.run('MATCH (i:P1Interface) DETACH DELETE i')
            probe['after_delete']=s.run(query).data()
            probe['passed']=(len(probe['before_delete'])==1 and not probe['after_delete'])
    except Exception as error:
        probe.update(passed=False,error=normalize(str(error),roots))
    results['extension_probe']=probe
    write(out/'cgc-evidence.json',results)
    db.close_driver()
    for handle in handles:
        handle.close()
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--cgc',type=Path,required=True)
    parser.add_argument('--cbm-binary',type=Path,required=True)
    parser.add_argument('--parser-cache',type=Path,required=True)
    parser.add_argument('--dll-dir',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    for key,value in vars(args).items():
        if isinstance(value,Path):setattr(args,key,value.resolve())
    for root in (args.source,args.cgc,RESEARCH):
        if args.output.is_relative_to(root):raise ValueError('Output must be external to checkouts')
    if args.output.exists():raise ValueError('Use a new output directory')
    verify_checkout(args.source,SOURCE_SHA)
    verify_checkout(args.cgc,CGC_SHA)
    if hashlib.sha256(args.cbm_binary.read_bytes()).hexdigest()!=CBM_SHA256:
        raise ValueError('CBM binary does not match verified v0.12.1')
    args.output.mkdir(parents=True)
    (args.output/'raw').mkdir()
    roots=[(args.output/'source','<source>'),(args.output/'fixtures','<fixtures>'),
           (args.output,'<output>'),(args.source,'<original-source>'),(args.cgc,'<cgc>')]
    rows=prepare(args.source,args.output)
    write(args.output/'environment.json', {'source_commit':SOURCE_SHA,'cgc_commit':CGC_SHA,'cbm_sha256':CBM_SHA256,
          'python':sys.version.split()[0], 'packages':{p:importlib.metadata.version(p) for p in ('codegraphcontext','tree-sitter','tree-sitter-language-pack','kuzu')},
          'files':len(rows),'input_count_by_suffix':dict(Counter(Path(r['path']).suffix for r in rows))})
    run_cbm(args.cbm_binary,args.output,roots)
    run_cgc(args.cgc,args.parser_cache,args.dll_dir,args.output,roots)
    verify_checkout(args.source,SOURCE_SHA)
    verify_checkout(args.cgc,CGC_SHA)
    print('Native trial completed; inspect evidence for capability outcomes.',flush=True)


if __name__=='__main__':main()
