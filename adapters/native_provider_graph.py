"""Connect native provider outputs to the existing graph and coverage model."""
from collections import Counter
import json
import os
from pathlib import Path
import shutil

from adapters.snapshot_inputs import validate_path

PROVIDERS = {'cbm', 'clangd'}


def configuration(value):
    data = json.loads(json.dumps(value))
    if not isinstance(data, dict) or set(data) - {'cbm', 'clangd', 'captures'}:
        raise ValueError('Unknown native provider configuration')
    for provider in PROVIDERS:
        options = data.setdefault(provider, {'enabled': True})
        if not isinstance(options, dict) or set(options) != {'enabled'} or type(options['enabled']) is not bool:
            raise ValueError('Native providers require an enabled boolean')
    captures = data.setdefault('captures', [])
    if not isinstance(captures, list):
        raise ValueError('Native captures must be an array')
    seen = set()
    for capture in captures:
        if not isinstance(capture, dict) or set(capture) != {'provider', 'directory', 'source_commit', 'context_key'}:
            raise ValueError('Native captures require provider, directory, source_commit and context_key')
        if capture['provider'] not in PROVIDERS or not all(isinstance(v, str) and v for v in capture.values()):
            raise ValueError('Invalid native capture provider or fields')
        revision = capture['source_commit']
        if len(revision) != 40 or any(c not in '0123456789abcdef' for c in revision):
            raise ValueError('Native capture must bind a fixed Git revision')
        if not Path(capture['directory']).is_absolute():
            raise ValueError('Native capture directory must be absolute')
        key = capture['provider'], capture['context_key']
        if key in seen:
            raise ValueError('Duplicate native provider/context capture')
        seen.add(key)
    return data


def read_capture(capture, *, paths, source_commit):
    if capture['source_commit'] != source_commit:
        raise ValueError('Native provider capture belongs to another source revision')
    root = Path(capture['directory']).resolve()
    if capture['provider'] == 'cbm':
        from adapters.cbm_provider import read_native
        receipt = json.loads((root / 'receipt.json').read_text(encoding='utf-8'))
        if receipt['source_commit'] != source_commit or receipt['status'] != 'ready':
            raise ValueError('CBM capture is stale or unsuccessful')
        return read_native(root / 'native.db', project=receipt['project'], paths=paths,
                           source_commit=source_commit, provider_version=receipt['version'])
    facts = json.loads((root / 'facts.json').read_text(encoding='utf-8'))
    components = facts.get('components', {})
    if components.get('source_commit') != source_commit or components.get('provider') != 'clangd':
        raise ValueError('Clangd capture is stale or has the wrong provider')
    if components.get('context') != capture['context_key']:
        raise ValueError('Clangd capture belongs to another compile context')
    selected = set(paths)
    nodes = [n for n in facts['nodes'] if not n['path'] or n['path'] in selected]
    ids = {n['id'] for n in nodes}
    from adapters.clangd_provider import diagnostic_precision
    return diagnostic_precision({**facts, 'nodes': nodes,
            'edges': [e for e in facts['edges'] if e['source'] in ids and e['target'] in ids],
            'coverage': [r for r in facts['coverage'] if r['path'] in selected],
            'diagnostics': [r for r in facts['diagnostics'] if not r.get('path') or r['path'] in selected]})


def merge(graph, facts, *, provider, context):
    selected = set(graph['input_paths'])
    existing = {n['id'] for n in graph['nodes']}
    for node in facts['nodes']:
        if node['path']:
            validate_path(node['path'])
            if node['path'] not in selected:
                raise ValueError('Provider facts escaped selected repository input')
        if node['id'] in existing:
            raise ValueError('Native provider node identity collision')
        existing.add(node['id'])
    graph['nodes'].extend(facts['nodes']); graph['edges'].extend(facts['edges'])
    graph['diagnostics'].extend(facts['diagnostics']); graph['limits'].extend(facts['limits'])
    by_path = {r['path']: r for r in graph['coverage']}
    for row in facts['coverage']:
        if row['path'] not in selected:
            raise ValueError('Provider coverage escaped selected input')
        current = by_path.get(row['path'])
        if current is None:
            current = {'path': row['path'], 'status': 'provider_required'}
            graph['coverage'].append(current); by_path[row['path']] = current
        current.setdefault('providers', []).append(row)
        if provider == 'clangd':
            current.setdefault('source_parser_status', current['status'])
            current['native_semantic_status'] = row['status']
            current['status'] = row['status']
        elif current['status'] in {'unsupported_extension', 'provider_required'}:
            current['status'] = 'parsed' if row['status'] == 'provider_facts_available' else row['status']
    graph.setdefault('native_providers', []).append({'provider': provider, 'context': context,
        'components': facts['components'], 'nodes': len(facts['nodes']), 'edges': len(facts['edges']),
        'coverage_statuses': dict(Counter(r['status'] for r in facts['coverage']))})


def augment(graph, *, root, output, config=None, emit=None):
    options = configuration(config or {})
    root, output = Path(root), Path(output)
    paths = graph['input_paths']; source_commit = graph['source_commit']
    captures = options['captures']
    for capture in captures:
        if not options[capture['provider']]['enabled']:
            raise ValueError('Capture supplied for disabled provider')
        facts = read_capture(capture, paths=paths, source_commit=source_commit)
        merge(graph, facts, provider=capture['provider'], context=capture['context_key'])
    already = {r['provider'] for r in captures}
    cbm = os.environ.get('PROJECT_MAP_CBM') or shutil.which('codebase-memory-mcp')
    if options['cbm']['enabled'] and 'cbm' not in already:
        if cbm:
            from adapters.cbm_provider import index
            facts = index(root, output / 'cbm-native', paths=paths,
                          source_commit=source_commit, binary=cbm)
            merge(graph, facts, provider='cbm', context='selected_repository')
        else:
            graph['diagnostics'].append({'kind': 'native_provider_unavailable', 'provider': 'cbm',
                                         'required_for': 'shell_container_and_native_auxiliary_facts'})
    clangd = os.environ.get('PROJECT_MAP_CLANGD') or shutil.which('clangd')
    cpp = [p for p in paths if Path(p).suffix in {'.h', '.hpp', '.hh', '.hxx', '.cpp', '.cc', '.cxx'}]
    if options['clangd']['enabled'] and 'clangd' not in already and cpp:
        contexts = []
        if clangd:
            from adapters.clangd_provider import analyze_batch
            for receipt_file in sorted((output / 'cmake-native').glob('*/*/receipt.json')):
                receipt = json.loads(receipt_file.read_text(encoding='utf-8'))
                directory = receipt_file.parent
                if receipt.get('source_commit') != source_commit or receipt.get('status') != 'configured':
                    continue
                context = receipt['context_key']
                drivers = [v for v in (os.environ.get('CC'), os.environ.get('CXX')) if v]
                source_root=Path(receipt.get('native_source_root', directory / 'source'))
                build_root=Path(receipt.get('native_build_root', directory / 'build'))
                facts = analyze_batch(source_root, cpp, binary=clangd, context=context,
                    source_commit=source_commit, output=directory / 'clangd-native',
                    compile_commands=build_root, query_drivers=drivers, emit=emit)
                merge(graph, facts, provider='clangd', context=context); contexts.append(context)
        if not contexts:
            graph['diagnostics'].append({'kind': 'native_provider_context_unavailable', 'provider': 'clangd',
                                         'required_for': 'compiler_bound_cpp_semantics'})
    return graph
