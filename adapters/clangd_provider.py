"""Translate native clangd replies through multilspy; no C++ semantic solver."""
import asyncio
from collections import defaultdict
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import quote

from adapters.snapshot_inputs import validate_path

VERSION = 'clangd_multilspy_provider/0.1.0'
SYMBOL_KINDS = {5: 'type', 6: 'callable', 7: 'value', 8: 'value', 9: 'callable',
                10: 'type', 11: 'type', 12: 'callable', 13: 'value', 14: 'value',
                22: 'value', 23: 'type', 26: 'type', 3: 'namespace'}


def reference_owners(facts):
    """Connect native lexical ranges while retaining provider/context identities."""
    def position(value):
        return value['line'], value['character']
    def scope(node):
        return node['path'], node.get('provenance', {}).get('context', facts['components'].get('context'))
    declarations = defaultdict(list)
    for node in facts['nodes']:
        if node['kind'] == 'callable' and node.get('native_range'):
            declarations[scope(node)].append(node)
    existing = {(e['source'], e['target']) for e in facts['edges']
                if e['kind'] == 'CLANGD_LEXICALLY_CONTAINS_REFERENCE'}
    for reference in facts['nodes']:
        bounds = reference.get('native_range')
        if reference['kind'] != 'symbol_reference' or not bounds:
            continue
        candidates = [n for n in declarations[scope(reference)]
                      if position(n['native_range']['start']) <= position(bounds['start'])
                      and position(bounds['end']) <= position(n['native_range']['end'])]
        # An innermost native range must be contained by every enclosing range.
        owners = [n for n in candidates if all(
            position(other['native_range']['start']) <= position(n['native_range']['start'])
            and position(n['native_range']['end']) <= position(other['native_range']['end'])
            for other in candidates)]
        if len(owners) != 1:
            reference['native_owner_status'] = 'ambiguous' if owners or candidates else 'outside_callable_range'
            continue
        owner = owners[0]
        reference['enclosing_native_symbol'] = owner['id']
        reference['native_owner_status'] = 'native_lexical_range'
        if (owner['id'], reference['id']) not in existing:
            facts['edges'].append({'source': owner['id'], 'target': reference['id'],
                'kind': 'CLANGD_LEXICALLY_CONTAINS_REFERENCE', 'status': 'static_declaration',
                'evidence': [{'path': reference['path'], 'line': reference['line'],
                              'column': reference['column']}],
                'basis': 'native_symbol_range_contains_reference_range_not_execution_or_call_dispatch',
                'provenance': {'provider': 'clangd', 'adapter': 'clangd_reference_owner/0.1.0',
                               'context': scope(reference)[1]}, 'runtime_execution': 'not_observed'})
            existing.add((owner['id'], reference['id']))
    facts['components']['reference_owner_policy'] = 'native_lexical_ranges/1'
    return facts


def diagnostic_precision(facts):
    """Keep declaration lookups from error-bearing contexts as candidates."""
    reference_owners(facts)
    states = {r['path']: r['status'] for r in facts['coverage'] if r['status'] != 'parsed'}
    by_id = {n['id']: n for n in facts['nodes']}
    for item in facts['nodes']:
        if item['path'] in states:
            item['semantic_context_status'] = states[item['path']]
    for edge in facts['edges']:
        source = by_id.get(edge['source'])
        if source and source['path'] in states and edge['status'] == 'static_declaration':
            edge['status'] = 'candidate'
            edge['precision_reason'] = 'native_context_has_diagnostics_or_analysis_failure'
    facts['components']['precision_policy'] = 'diagnostic_context_candidates/1'
    return facts


async def analyze(root, paths, *, binary, context, source_commit, output,
                  compile_commands=None, query_drivers=(), file_timeout=120,
                  reference_budget=10000, input_paths=None, emit=None):
    from multilspy.language_servers.clangd_language_server.clangd_language_server import ClangdLanguageServer
    from multilspy.multilspy_config import MultilspyConfig
    from multilspy.multilspy_logger import MultilspyLogger

    root, output = Path(root).resolve(), Path(output).resolve()
    analyzed = set(paths)
    selected = set(input_paths if input_paths is not None else paths)
    if not analyzed <= selected:
        raise ValueError('Analyzed files must belong to selected input')
    for path in selected:
        validate_path(path)
    output.mkdir(parents=True, exist_ok=False)
    prefix = 'clangd:' + quote(context, safe='') + ':'
    nodes, edges, diagnostics, coverage = {}, [], [], []
    published = {}
    class SymbolServer(ClangdLanguageServer):
        def _get_initialize_params(self, repository_absolute_path):
            params = super()._get_initialize_params(repository_absolute_path)
            params['capabilities']['textDocument'].setdefault('documentSymbol', {})[
                'hierarchicalDocumentSymbolSupport'] = True
            return params
    server = SymbolServer(MultilspyConfig.from_dict({
        'code_language': 'cpp', 'server_binary': str(binary)}), MultilspyLogger(), str(root))
    server.server.process_launch_info.cmd.extend(['--background-index=false', '--pch-storage=memory', '--log=error'])
    provenance = {'adapter': VERSION, 'provider': 'clangd', 'context': context,
                  'source_commit': source_commit, 'multilspy': importlib.metadata.version('multilspy'),
                  'version': subprocess.check_output([str(binary), '--version'], text=True, timeout=10).splitlines()[0]}
    if compile_commands:
        database = Path(compile_commands).resolve()
        if query_drivers:
            from adapters.compilation_database import with_builtin_headers
            major = re.search(r'version (\d+)', provenance['version'])
            if not major:
                raise ValueError('Cannot identify clangd builtin header version')
            headers = Path(binary).resolve().parent.parent / 'lib' / 'clang' / major[1] / 'include'
            provenance['compile_command_adjustment'] = with_builtin_headers(database, output / 'compile-database', headers)
            database = output / 'compile-database'
        server.server.process_launch_info.cmd.append('--compile-commands-dir=' + str(database))
    if query_drivers:
        server.server.process_launch_info.cmd.append('--query-driver=' + ','.join(map(str, query_drivers)))
    def uri_key(uri):
        return uri.casefold() if os.name == 'nt' else uri

    def identifier(path, position, category='declaration'):
        return prefix + quote(path, safe='/') + ':' + category + ':' + str(position['line']) + ':' + str(position['character'])

    def node(path, position, category, name, **extra):
        uid = identifier(path, position, 'module' if category == 'code_module' else
                         'reference' if category == 'symbol_reference' else 'declaration')
        if category == 'symbol_reference':
            end = extra['native_range']['end']
            uid += ':' + extra['native_kind'] + ':' + str(end['line']) + ':' + str(end['character'])
        record = {'id': uid, 'kind': category, 'path': path, 'line': position['line'] + 1,
                  'column': position['character'] + 1, 'name': name, 'language': 'cpp',
                  'evidence_kind': 'clangd_native_reply', 'provenance': provenance,
                  'runtime_execution': 'not_observed', **extra}
        previous = nodes.get(uid)
        if previous and category == 'declaration':
            return uid
        nodes[uid] = record
        return uid

    def relation(source, target, kind, path, position, **extra):
        edges.append({'source': source, 'target': target, 'kind': kind, 'status': 'static_declaration',
                      'evidence': [{'path': path, 'line': position['line'] + 1,
                                    'column': position['character'] + 1}],
                      'provenance': provenance, 'runtime_execution': 'not_observed', **extra})

    async def collect(path):
        uri = (root / path).as_uri()
        module = node(path, {'line': 0, 'character': 0}, 'code_module', path)
        with server.open_file(path):
            symbols = await server.server.send_request('textDocument/documentSymbol', {'textDocument': {'uri': uri}})
            ast = await server.server.send_request('textDocument/ast', {'textDocument': {'uri': uri}})
            if not ast or ast.get('kind') != 'TranslationUnit':
                raise ValueError('Native translation-unit AST unavailable')
            (output / (quote(path, safe='') + '.json')).write_text(
                json.dumps({'symbols': symbols, 'ast': ast}), encoding='utf-8')

            def declarations(items, parents=()):
                for item in items or []:
                    position = item.get('selectionRange', item.get('range', {})).get('start')
                    if position:
                        name = '::'.join((*parents, item['name']))
                        uid = node(path, position, SYMBOL_KINDS.get(item['kind'], 'declaration'), name,
                                   native_kind=item['kind'], detail=item.get('detail'),
                                   native_range=item.get('range'), native_selection_range=item.get('selectionRange'))
                        relation(module, uid, 'CLANGD_DECLARES', path, position)
                    declarations(item.get('children'), (*parents, item['name']))
            declarations(symbols)

            references = []
            def visit(item):
                if not item:
                    return
                if item.get('kind') in {'DeclRef', 'Member'} and item.get('range'):
                    references.append(item)
                for child in item.get('children', []):
                    visit(child)
            visit(ast)
            resolved = 0
            for ordinal, item in enumerate(references):
                start, end = item['range']['start'], item['range']['end']
                uid = node(path, start, 'symbol_reference', item.get('detail', item['kind']),
                           native_kind=item['kind'], native_range=item['range'],
                           resolution='unresolved', reason='native_definition_not_returned')
                relation(module, uid, 'CLANGD_CONTAINS_REFERENCE', path, start)
                if ordinal >= reference_budget:
                    nodes[uid]['reason'] = 'reference_query_budget'
                    continue
                targets = await server.request_definition(path, end['line'], max(0, end['character'] - 1))
                internal = [t for t in targets if t.get('relativePath', '').replace('\\', '/') in selected]
                if internal:
                    nodes[uid].update(resolution='native_declaration_target', reason=None)
                    resolved += 1
                elif targets:
                    nodes[uid]['reason'] = 'native_target_outside_selected_input'
                for target in internal:
                    target_path = target['relativePath'].replace('\\', '/')
                    position = target['range']['start']
                    target_uid = node(target_path, position, 'declaration', item.get('detail', ''),
                                      native_target_range=target['range'])
                    relation(uid, target_uid, 'CLANGD_REFERS_TO_DECLARATION', path, start,
                             target_selection='native_definition_at_reference_range_end')
            errors = [d for d in published.get(uri_key(uri), []) if d.get('severity') == 1]
            diagnostics.extend({'path': path, 'kind': 'clangd_diagnostic', 'native': d} for d in published.get(uri_key(uri), []))
            coverage.append({'path': path, 'status': 'parsed_with_diagnostics' if errors else 'parsed',
                             'provider': 'clangd', 'context': context, 'native_ast_kind': (ast or {}).get('kind'),
                             'references': len(references), 'resolved_input_references': resolved,
                             'reference_budget_exhausted': len(references) > reference_budget,
                             'compile_command': 'native_database_or_clangd_inference' if compile_commands else 'fallback'})

    async with server.start_server():
        async def on_diagnostics(params):
            published[uri_key(params['uri'])] = params.get('diagnostics', [])
        server.server.on_notification('textDocument/publishDiagnostics', on_diagnostics)
        for path in sorted(analyzed):
            try:
                await asyncio.wait_for(collect(path), timeout=file_timeout)
            except (asyncio.TimeoutError, OSError, ValueError, RuntimeError) as exc:
                diagnostics.append({'path': path, 'kind': 'clangd_file_failed', 'error': str(exc)})
                coverage.append({'path': path, 'status': 'provider_failed', 'provider': 'clangd', 'context': context})
            if emit:
                emit({'path': path, 'status': coverage[-1]['status'], 'nodes': len(nodes), 'edges': len(edges)})
    return diagnostic_precision({'nodes': list(nodes.values()), 'edges': edges, 'diagnostics': diagnostics,
            'coverage': coverage, 'components': provenance,
            'limits': ['compiler_declaration_identity_not_runtime_object_or_dispatch',
                       'native_inferred_header_commands_are_not_explicit_build_membership',
                       'reference_query_residuals_and_diagnostics_remain_visible']})


def analyze_batch(root, paths, *, output, workers=4, input_paths=None, emit=None, **options):
    """Run independent native clients while retaining project-wide target scope."""
    from concurrent.futures import ThreadPoolExecutor
    import threading
    if type(workers) is not int or workers < 1 or workers > 8:
        raise ValueError('Use between one and eight native clients')
    paths = sorted(set(paths))
    selected = sorted(set(input_paths if input_paths is not None else paths))
    if not paths:
        raise ValueError('C++ input is empty')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    workers = min(workers, len(paths)); lock = threading.Lock()
    def report(row):
        if emit:
            with lock:
                emit(row)
    def collect(ordinal):
        facts = asyncio.run(analyze(root, paths[ordinal::workers], output=output / str(ordinal),
                                   input_paths=selected, emit=report, **options))
        (output / (str(ordinal) + '-facts.json')).write_text(json.dumps(facts), encoding='utf-8')
        return facts
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(collect, range(workers)))
    nodes = {}
    for result in results:
        for item in result['nodes']:
            if item['id'] not in nodes or item['kind'] != 'declaration':
                nodes[item['id']] = item
    combined = {key: [v for result in results for v in result[key]]
                for key in ('edges', 'coverage', 'diagnostics')}
    combined.update(nodes=list(nodes.values()), components=results[0]['components'],
                    limits=sorted({v for result in results for v in result['limits']}))
    return combined
