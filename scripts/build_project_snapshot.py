"""Build a complete source graph from one immutable, committed input export."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import platform
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def write_json(path, value):
    with path.open('w', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, separators=(',', ':'))
        stream.write('\n')


def build(source, request, output, log, *, typescript):
    from adapters.snapshot_inputs import normalize_config, validate_path
    source = Path(source).resolve(); output = Path(output).resolve()
    paths = request['input_paths']
    if not paths or len(paths) != len(set(paths)): raise ValueError('Input paths must be nonempty and unique')
    for path in paths:
        validate_path(path)
        target = (source/path).resolve()
        if not target.is_relative_to(source) or not target.is_file(): raise ValueError('Missing or unsafe input: ' + path)
    if request['config'] != normalize_config(request['config']): raise ValueError('Request configuration must be normalized')
    if not request['snapshot'] or not request['source_commit'] or not request['build_version']:
        raise ValueError('Snapshot, source revision and builder version are required')
    from adapters.cpp_data import DataExtractor
    from adapters.cpp_protocol import ProtocolExtractor
    from adapters.protocol_graph import augment as protocol
    from adapters.data_graph import augment as data_graph
    from adapters.frontend_graph import augment_frontend
    from adapters.callback_graph import augment_callbacks
    from adapters.cpp_transmission import Transmission
    from adapters.transmission_graph import augment_transmission
    from adapters.socket_graph import augment_sockets
    from adapters.cpp_socket_origin import SocketOrigins
    from adapters.server_channel_graph import augment_server_channels
    from adapters.return_bridge_graph import augment_returns
    from adapters.cpp_source_conditions import extract_conditions
    from scripts.build_chain_closure_graph import augment as closure
    from scripts.build_fact_graph import remaining_coverage
    from adapters.sqlite_fact_graph import validate_graph
    import tree_sitter_language_pack as pack

    if os.environ.get('PROJECT_MAP_PARSER_CACHE'): pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))
    paths = request['input_paths']; revision = request['source_commit']
    manifest = output/'input-manifest.json'; checkpoint = output/'phase-input.json'
    write_json(manifest, {'source_commit': revision, 'files': [{'path': p} for p in paths]})

    def ts_phase(name, *args):
        print('Extract ' + name, file=log, flush=True)
        target = output/(name + '.json')
        subprocess.run(['node', str(ROOT/'adapters'/name), str(source), str(manifest), *map(str, args),
                        str(typescript), str(target)], check=True, stdout=log, stderr=subprocess.STDOUT)
        return json.loads(target.read_text(encoding='utf-8'))

    print('Extract C++ declarations and protocol', file=log, flush=True)
    inputs = {p: (source/p).read_bytes() for p in paths if Path(p).suffix in {'.h', '.hpp', '.cpp', '.cc', '.cxx'}}
    extractor = DataExtractor(inputs, pack.get_parser('cpp'))
    cpp = ProtocolExtractor({}, None, extractor=extractor.x, facts=extractor.facts, value_types=extractor.types).build()
    ts = ts_phase('typescript_protocol_flow.cjs'); facts = cpp['facts']
    python={'nodes':[],'edges':[],'diagnostics':[],'coverage':[],'limits':[]}
    python_paths=[p for p in paths if Path(p).suffix in {'.py','.pyi'}]
    if python_paths:
        print('Extract Python declarations, values and Jedi references', file=log, flush=True)
        from adapters.python_facts import analyze as python_facts
        from adapters.python_boundaries import augment as python_boundaries
        from adapters.python_path_values import augment as python_path_values,ADAPTER_VERSION as python_path_version
        python=python_facts(source,paths,emit=lambda row:print('Python '+json.dumps(row),file=log,flush=True))
        python=python_boundaries(python)
        python=python_path_values(source,python)
        write_json(output/'python-facts.json',python)
    rust={'nodes':[],'edges':[],'diagnostics':[],'coverage':[],'limits':[]}
    rust_paths=[p for p in paths if Path(p).suffix=='.rs']
    if rust_paths:
        print('Extract Rust declarations, values and native Cargo references',file=log,flush=True)
        from adapters.rust_semantics import analyze as rust_facts
        from adapters.rust_boundaries import augment as rust_boundaries
        from adapters.rust_path_values import augment as rust_path_values
        rust=rust_boundaries(rust_facts(source,paths,pack.get_parser('rust'),output=output/'rust-native',
            emit=lambda row:print('Rust '+json.dumps(row),file=log,flush=True)))
        rust=rust_path_values(source,rust,pack.get_parser('rust'))
        write_json(output/'rust-facts.json',rust)
    covered = {r['path'] for g in (facts, ts, python,rust) for r in g['coverage']}
    graph = {'schema_version': 1, 'snapshot': revision + ':protocol', 'source_commit': revision,
        'extractors': {'cpp': 'cpp_protocol/0.2.0', 'typescript': 'typescript_protocol_flow/0.2.0',
            'typescript_compiler': ts['compiler_version'], 'tree_sitter': importlib.metadata.version('tree-sitter'),
            'tree_sitter_language_pack': importlib.metadata.version('tree-sitter-language-pack')},
        'input_paths': paths, 'coverage': facts['coverage'] + ts['coverage'] + python['coverage'] + rust['coverage'] + remaining_coverage(paths, covered),
        'nodes': facts['nodes'] + ts['nodes'] + python['nodes'] + rust['nodes'], 'edges': facts['edges'] + ts['edges'] + python['edges'] + rust['edges'],
        'diagnostics': facts['diagnostics'] + ts['diagnostics'] + python['diagnostics'] + rust['diagnostics'], 'limits': facts['limits'] + ts['limits'] + python['limits'] + rust['limits'],
        'provenance': {'reference_used_for_extraction': False, 'file_hash_verification': 'not_run_per_user_preference',
            'deployment_scope': 'configured', 'update_mode': 'full_rebuild'}, 'path_configs': ts['path_configs'],
        'analysis_units': ts.get('analysis_units', []), 'typescript_compiler_options_origin': ts['compiler_options_origin']}
    if python_paths:graph['extractors']['python']={'adapter':'python_ast_jedi/0.1.0','components':python['components'],
        'path_values':python_path_version}
    if rust_paths:graph['extractors']['rust']={'adapter':'rust_tree_sitter_rust_analyzer/0.1.0','components':rust['components'],
        'path_values':'native_bound_positioned_paths/0.1.0'}
    from adapters.cmake_project import extract as cmake_facts, roots as cmake_roots
    if cmake_roots(paths):
        print('Extract native CMake targets, artifacts and selected-source membership', file=log, flush=True)
        native=cmake_facts(source,paths,source_commit=revision,output=output/'cmake-native',
            config={k:v for k,v in request['config']['build'].items() if k!='cargo'} if request['config'].get('build') else None,source_facts=facts,
            emit=lambda row:print('CMake '+json.dumps(row),file=log,flush=True))
        for key in ('nodes','edges','diagnostics','limits'):graph[key].extend(native[key])
        graph['native_build']={'projects':native['projects'],'contexts':native['contexts'],'source_coverage':'native_compilation_input_not_execution'}
        graph['extractors']['cmake']=native['components']
    cargo_captures=request['config'].get('build',{}).get('cargo',{}).get('captures',[])
    if cargo_captures:
        print('Import revision-bound Cargo compiler artifacts',file=log,flush=True)
        from adapters.cargo_artifact_graph import augment as cargo_artifacts
        graph=cargo_artifacts(graph,root=source,captures=cargo_captures,parser=pack.get_parser('rust'))
    from adapters.artifact_copy_graph import augment as artifact_copies
    graph=artifact_copies(graph)
    graph['extractors']['artifact_copy_flow']=graph['artifact_copy_flow']['adapter']
    graph = protocol(graph, ts['protocol'], cpp['protocol'], request['config']['deployment'])
    write_json(output/'protocol-checkpoint.json', {'stage': 'protocol_only_not_complete_graph',
        'source_commit': revision, 'build_version': request['build_version'],
        'protocol': graph['protocol'], 'nodes': [n for n in graph['nodes'] if n['kind'] == 'protocol_message'],
        'edges': [e for e in graph['edges'] if e['kind'] == 'EMITS_MESSAGE']})
    from collections import Counter
    print('Protocol joins ' + json.dumps(dict(Counter(r['status'] for r in graph['protocol']['results']))), file=log, flush=True)
    print('Extract C++ data, objects and fields', file=log, flush=True)
    graph = data_graph(graph, extractor.build(), paths)
    # Node phases consume boundary identities, never the multi-hundred-MB graph.
    write_json(checkpoint, {'project_map_phase': 'frontend', 'api_symbols': sorted({
        e['source'] for e in graph['edges'] if e['kind'] == 'EMITS_MESSAGE'})})
    graph = augment_frontend(graph, ts_phase('typescript_data_flow.cjs', checkpoint))
    graph = augment_callbacks(graph, ts_phase('typescript_response_flow.cjs'))
    transmission = Transmission(extractor).build()
    graph = augment_transmission(graph, extractor.facts, transmission, paths)
    graph = augment_sockets(graph, ts_phase('typescript_socket_flow.cjs'))
    print('Extract source server connections', file=log, flush=True)
    graph = augment_server_channels(graph, extractor.facts, SocketOrigins(extractor).build(), paths)
    write_json(checkpoint, {'project_map_phase': 'return',
        'boundarySymbols': sorted({r['entry'] for r in graph['response_callbacks']['registrations']}),
        'apiEntries': graph['frontend']['api_symbols'],
        'handoffSymbols': sorted({r['entry'] for r in graph['response_callbacks']['settlements'] if r.get('registry_context')})})
    graph = augment_returns(graph, ts_phase('typescript_return_flow.cjs', checkpoint))
    print('Checkpoint extracted relations before closure validation', file=log, flush=True)
    write_json(output/'return-checkpoint.json', {'stage': 'pre_closure_unvalidated_not_published', 'request': request, 'graph': graph})
    print('Finalize and validate source graph', file=log, flush=True)
    graph = closure(graph, extractor, transmission, extract_conditions(extractor))
    graph['snapshot'] = request['snapshot']
    graph['version'] = {k: request[k] for k in ['source_commit', 'snapshot', 'config', 'build_version']}
    graph['provenance']['input_kind'] = 'git_committed_blob_export'
    graph['provenance']['working_tree_included'] = False
    graph['provenance']['update_mode'] = 'full_rebuild'
    graph['provenance']['trigger'] = request.get('trigger', 'caller')
    validate_graph(graph)
    write_json(output/'graph.json', graph)
    if request['config'].get('storage', 'kuzu') == 'kuzu':
        print('Persist and verify Kuzu snapshot', file=log, flush=True)
        from adapters import kuzu_fact_graph as store
        dll = os.add_dll_directory(os.environ['PROJECT_MAP_DLL_DIR']) if os.name == 'nt' and os.environ.get('PROJECT_MAP_DLL_DIR') else None
        import kuzu
        db = kuzu.Database(str(output/'graph.kuzu'), buffer_pool_size=1024*1024*1024); conn = kuzu.Connection(db)
        try:
            store.replace_snapshot(conn, graph)
            if store.read_snapshot(conn, graph['snapshot']) != graph: raise ValueError('Stored graph differs from built graph')
        finally:
            conn.close(); db.close()
            if dll: dll.close()
    return {'nodes': len(graph['nodes']), 'edges': len(graph['edges']), 'files': len(paths),
            'storage': request['config'].get('storage', 'kuzu'), 'coverage_records': len(graph['coverage']),
            'storage_roundtrip': request['config'].get('storage', 'kuzu') == 'kuzu'}


def build_version(typescript):
    from projectmap.version import rules_version
    ts = subprocess.check_output(['node', '-e', 'process.stdout.write(require(process.argv[1]).version)', str(typescript)], text=True)
    rules = rules_version(require_clean=True)
    from adapters.rust_project import available,binary,tool_output
    rust_tools={name:tool_output([binary(name),'--version'],ROOT).strip() if available(name) else None for name in ('cargo','rustc','rust-analyzer')}
    from adapters.cmake_project import tool_versions as cmake_tools
    return {'rules_commit': rules, 'python': platform.python_version(),'rust_tools':rust_tools,'native_build_tools':cmake_tools(),
            'node': subprocess.check_output(['node', '--version'], text=True).strip(), 'typescript': ts,
            'packages': {name: importlib.metadata.version(name) for name in ['tree-sitter', 'tree-sitter-language-pack', 'kuzu', 'jedi', 'parso']}}


if __name__ == '__main__':
    from adapters.snapshot_inputs import export_inputs, select_inputs
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ['source', 'config', 'output', 'typescript']: ap.add_argument('--' + name, type=Path, required=True)
    ap.add_argument('--revision', default='HEAD', help='Committed revision; worktree edits are excluded')
    a = ap.parse_args(); a.output = a.output.resolve(); a.source = a.source.resolve()
    if a.output.is_relative_to(ROOT) or a.output.is_relative_to(a.source): raise ValueError('Keep outputs outside both repositories')
    version = build_version(a.typescript.resolve())
    selection = select_inputs(a.source, a.revision, json.loads(a.config.read_text(encoding='utf-8')))
    a.output.mkdir(parents=True, exist_ok=False)
    write_json(a.output/'selection.json', selection)
    export_inputs(a.source, selection, a.output/'source')
    request = {'source_commit': selection['source_commit'], 'snapshot': selection['source_commit'] + ':full:' + uuid.uuid4().hex,
               'input_paths': [f['path'] for f in selection['files']], 'config': selection['config'], 'build_version': version,
               'trigger': 'explicit_cli'}
    write_json(a.output/'request.json', request)
    with (a.output/'build.log').open('w', encoding='utf-8') as log:
        result = build(a.output/'source', request, a.output, log, typescript=a.typescript.resolve())
    write_json(a.output/'result.json', result)
    print(json.dumps(result))
