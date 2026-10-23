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
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')


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
    from adapters.sqlite_fact_graph import _prepare
    import tree_sitter_language_pack as pack

    if os.environ.get('PROJECT_MAP_PARSER_CACHE'): pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))
    paths = request['input_paths']; revision = request['source_commit']
    manifest = output/'input-manifest.json'; checkpoint = output/'working-graph.json'
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
    cpp = ProtocolExtractor({}, None, extractor=extractor.x, facts=extractor.facts).build()
    ts = ts_phase('typescript_protocol_flow.cjs'); facts = cpp['facts']
    covered = {r['path'] for g in (facts, ts) for r in g['coverage']}
    graph = {'schema_version': 1, 'snapshot': revision + ':protocol', 'source_commit': revision,
        'extractors': {'cpp': 'cpp_protocol/0.2.0', 'typescript': 'typescript_protocol_flow/0.2.0',
            'typescript_compiler': ts['compiler_version'], 'tree_sitter': importlib.metadata.version('tree-sitter'),
            'tree_sitter_language_pack': importlib.metadata.version('tree-sitter-language-pack')},
        'input_paths': paths, 'coverage': facts['coverage'] + ts['coverage'] + remaining_coverage(paths, covered),
        'nodes': facts['nodes'] + ts['nodes'], 'edges': facts['edges'] + ts['edges'],
        'diagnostics': facts['diagnostics'] + ts['diagnostics'], 'limits': facts['limits'] + ts['limits'],
        'provenance': {'reference_used_for_extraction': False, 'file_hash_verification': 'not_run_per_user_preference',
            'deployment_scope': 'configured', 'update_mode': 'automatic_full_rebuild'}, 'path_configs': ts['path_configs']}
    graph = protocol(graph, ts['protocol'], cpp['protocol'], request['config']['deployment'])
    print('Extract C++ data, objects and fields', file=log, flush=True)
    graph = data_graph(graph, extractor.build(), paths)
    write_json(checkpoint, graph)
    graph = augment_frontend(graph, ts_phase('typescript_data_flow.cjs', checkpoint))
    graph = augment_callbacks(graph, ts_phase('typescript_response_flow.cjs'))
    transmission = Transmission(extractor).build()
    graph = augment_transmission(graph, extractor.facts, transmission, paths)
    graph = augment_sockets(graph, ts_phase('typescript_socket_flow.cjs'))
    print('Extract source server connections', file=log, flush=True)
    graph = augment_server_channels(graph, extractor.facts, SocketOrigins(extractor).build(), paths)
    write_json(checkpoint, graph)
    graph = augment_returns(graph, ts_phase('typescript_return_flow.cjs', checkpoint))
    graph = closure(graph, extractor, transmission, extract_conditions(extractor))
    graph['snapshot'] = request['snapshot']
    graph['version'] = {k: request[k] for k in ['source_commit', 'snapshot', 'config', 'build_version']}
    graph['provenance']['input_kind'] = 'git_committed_blob_export'
    graph['provenance']['working_tree_included'] = False
    graph['provenance']['update_mode'] = 'automatic_full_rebuild'
    _prepare(graph)
    write_json(output/'graph.json', graph)
    if request['config'].get('storage', 'kuzu') == 'kuzu':
        print('Persist and verify Kuzu snapshot', file=log, flush=True)
        from adapters import kuzu_fact_graph as store
        dll = os.add_dll_directory(os.environ['PROJECT_MAP_DLL_DIR']) if os.name == 'nt' and os.environ.get('PROJECT_MAP_DLL_DIR') else None
        import kuzu
        db = kuzu.Database(str(output/'graph.kuzu'), buffer_pool_size=512*1024*1024); conn = kuzu.Connection(db)
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
    from adapters.snapshot_inputs import git, commit
    inputs = ['adapters', 'scripts', 'requirements-*.txt', 'package.json', 'package-lock.json']
    if git(ROOT, 'status', '--porcelain', '--untracked-files=all', '--', *inputs).strip():
        raise ValueError('Commit builder changes before recording a reproducible builder version')
    ts = subprocess.check_output(['node', '-e', 'process.stdout.write(require(process.argv[1]).version)', str(typescript)], text=True)
    return {'rules_commit': commit(ROOT), 'python': platform.python_version(),
            'node': subprocess.check_output(['node', '--version'], text=True).strip(), 'typescript': ts,
            'packages': {name: importlib.metadata.version(name) for name in ['tree-sitter', 'tree-sitter-language-pack', 'kuzu']}}


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
               'input_paths': [f['path'] for f in selection['files']], 'config': selection['config'], 'build_version': version}
    write_json(a.output/'request.json', request)
    with (a.output/'build.log').open('w', encoding='utf-8') as log:
        result = build(a.output/'source', request, a.output, log, typescript=a.typescript.resolve())
    write_json(a.output/'result.json', result)
    print(json.dumps(result))
