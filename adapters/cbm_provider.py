"""Invoke CBM's native indexer and import its SQLite facts without re-parsing code."""
from collections import Counter
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time
from urllib.parse import quote

from adapters.snapshot_inputs import validate_path

VERSION = 'native_cbm_provider/0.1.0'
LABELS = {'Module': 'code_module', 'Function': 'callable', 'Method': 'callable',
          'Class': 'type', 'Interface': 'type', 'Enum': 'type', 'Type': 'type', 'Struct': 'type',
          'Macro': 'macro', 'Variable': 'value',
          'Constant': 'value', 'Parameter': 'parameter', 'Field': 'value',
          'Process': 'process', 'EnvVar': 'environment_variable', 'Image': 'container_image',
          'Resource': 'deployment_resource', 'Route': 'interface_endpoint', 'File': 'source_file'}


def read_native(database, *, project, paths, source_commit, provider_version):
    """Preserve native identities/properties; inferred relations remain candidates."""
    selected = set(paths)
    for path in selected:
        validate_path(path)
    nodes, edges, diagnostics, identities = [], [], [], {}
    database = Path(database).resolve()
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        native_nodes = list(db.execute('SELECT * FROM nodes WHERE project=? ORDER BY id', (project,)))
        native_edges = list(db.execute('SELECT * FROM edges WHERE project=? ORDER BY id', (project,)))
        coverage_table = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='index_coverage'").fetchone()
        native_coverage = [dict(r) for r in db.execute('SELECT rel_path,kind,detail FROM index_coverage WHERE project=?',
                                                     (project,))] if coverage_table else []
    provenance = {'provider': 'codebase-memory-mcp', 'version': provider_version,
                  'source_commit': source_commit, 'adapter': VERSION}
    prefix = 'cbm:' + quote(project, safe='') + ':'
    for native in native_nodes:
        label, path = native['label'], native['file_path'] or ''
        if label in {'Project', 'Branch'}:
            continue
        if path and path not in selected:
            if not path.startswith('<'):
                diagnostics.append({'kind': 'cbm_node_outside_selected_input',
                                    'native_id': native['id'], 'native_label': label})
            continue
        uid = prefix + str(native['id'])
        identities[native['id']] = uid
        properties = json.loads(native['properties'] or '{}')
        nodes.append({'id': uid, 'kind': LABELS.get(label, 'provider_symbol'),
                      'path': path, 'line': max(native['start_line'] or 0, 0),
                      'name': native['qualified_name'] or native['name'],
                      'display_name': native['name'], 'native_label': label,
                      'native_id': native['id'], 'native_properties': properties,
                      'evidence_kind': 'native_provider_output', 'provenance': provenance,
                      'runtime_execution': 'not_observed'})
    by_id = {n['id']: n for n in nodes}
    for native in native_edges:
        source, target = identities.get(native['source_id']), identities.get(native['target_id'])
        if not source or not target:
            continue
        properties = json.loads(native['properties'] or '{}')
        evidence = [{'path': by_id[uid]['path'], 'line': by_id[uid]['line']}
                    for uid in (source, target) if by_id[uid]['path']]
        if evidence and type(properties.get('line')) is int:
            evidence[0] = {**evidence[0], 'line': properties['line']}
        structural = native['type'] in {'DEFINES', 'CONTAINS_FILE', 'HAS_BRANCH'}
        edges.append({'source': source, 'target': target, 'kind': 'CBM_' + native['type'],
                      'status': 'source_relation' if structural else 'candidate',
                      'evidence': evidence, 'native_id': native['id'],
                      'native_properties': properties, 'provenance': provenance,
                      'basis': 'native_cbm_relation_not_runtime_or_compiler_identity',
                      'runtime_execution': 'not_observed'})
    covered = {n['path'] for n in nodes if n['kind'] == 'code_module'}
    coverage = []
    for path in sorted(selected):
        problems = [r for r in native_coverage if r['rel_path'] == path or
                    (r['kind'] == 'not_indexed_dir' and path.startswith(r['rel_path'].rstrip('/') + '/'))]
        kinds = {r['kind'] for r in problems}
        status = ('provider_unusable' if 'parse_unusable' in kinds else 'provider_partial' if 'parse_partial' in kinds
                  else 'provider_excluded' if kinds else 'provider_facts_available' if path in covered else 'provider_not_emitted')
        coverage.append({'path': path, 'status': status, 'provider': 'codebase-memory-mcp',
                         'version': provider_version, 'native_coverage': problems})
    return {'nodes': nodes, 'edges': edges, 'diagnostics': diagnostics,
            'coverage': coverage,
            'components': provenance,
            'limits': ['native_provider_relations_retain_candidate_precision',
                       'native_module_presence_is_not_independent_semantic_acceptance',
                       'external_targets_without_input_source_are_not_source_definitions']}


def index(source, output, *, paths, source_commit, binary=None, cache_dir=None,
          runtime_dir=None, timeout=600, project=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    binary = binary or os.environ.get('PROJECT_MAP_CBM') or shutil.which('codebase-memory-mcp')
    cache_dir = cache_dir or os.environ.get('CBM_CACHE_DIR')
    runtime_dir = runtime_dir or os.environ.get('CBM_RUNTIME_DIR')
    if not binary or not cache_dir or not runtime_dir:
        raise ValueError('CBM executable, private cache and runtime parent must be explicit')
    if output.exists() or output.is_relative_to(source):
        raise ValueError('Use a new output outside the immutable source export')
    cache_dir, runtime_dir = Path(cache_dir).resolve(), Path(runtime_dir).resolve()
    if cache_dir.is_relative_to(source) or runtime_dir.is_relative_to(source):
        raise ValueError('Keep CBM cache/runtime outside the immutable source export')
    for directory in (cache_dir, runtime_dir):
        directory.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True)
    # Only the provider's private copy receives discovery controls. The caller's
    # immutable Git export and original tracked ignore files remain untouched.
    provider_source = output / 'source'
    provider_source.mkdir()
    directories = set()
    for path in paths:
        validate_path(path)
        original = (source / path).resolve()
        if not original.is_relative_to(source) or not original.is_file():
            raise ValueError('Input must be a regular file inside the source export')
        target = provider_source / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(original.read_bytes())
        directories.update(p.as_posix() for p in Path(path).parents if p.as_posix() != '.')
    control = provider_source / '.cbmignore'
    previous_control = control.read_text(encoding='utf-8') if control.exists() else ''
    rules = [*(f'!{path}/' for path in sorted(directories)), *(f'!{path}' for path in sorted(paths))]
    control.write_text(previous_control + '\n# Explicit project-map selected input scope\n' + '\n'.join(rules) + '\n', encoding='utf-8')
    project = project or 'project-map-' + source_commit[:12]
    if not project or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in project):
        raise ValueError('Use an alphanumeric CBM project identifier')
    version = subprocess.check_output([str(binary), '--version'], text=True, timeout=10).strip()
    env = {**os.environ, 'CBM_CACHE_DIR': str(cache_dir), 'CBM_RUNTIME_DIR': str(runtime_dir)}
    command = [str(binary), 'cli', '--json', 'index_repository', '--repo-path', str(provider_source),
               '--name', project, '--mode', 'full', '--persistence', 'false', '--doc-candidates', 'false']
    started = time.monotonic()
    try:
        process = subprocess.run(command, cwd=provider_source, env=env, capture_output=True,
                                 text=True, encoding='utf-8', errors='replace', timeout=timeout)
        (output / 'stdout.json').write_text(process.stdout, encoding='utf-8')
        (output / 'stderr.log').write_text(process.stderr, encoding='utf-8')
        payload = json.loads(process.stdout) if process.stdout.strip() else {}
        details = payload.get('structuredContent', {})
        if process.returncode or payload.get('isError') or details.get('status') != 'indexed':
            raise RuntimeError('CBM indexing failed; see native stdout/stderr')
        databases = [p for p in cache_dir.rglob(project + '.db') if p.is_file()]
        if len(databases) != 1:
            raise ValueError('Expected one native project database')
        target = output / 'native.db'
        with closing(sqlite3.connect(databases[0].as_uri() + '?mode=ro', uri=True)) as native:
            with closing(sqlite3.connect(target)) as frozen:
                native.backup(frozen)
        facts = read_native(target, project=project, paths=paths, source_commit=source_commit,
                            provider_version=version)
        receipt = {'adapter': VERSION, 'version': version, 'project': project,
                   'source_commit': source_commit, 'input_paths': sorted(paths),
                   'status': 'ready', 'seconds': round(time.monotonic() - started, 3),
                   'native_result': details, 'nodes': len(facts['nodes']), 'edges': len(facts['edges']),
                   'scope_policy': 'explicit_selected_paths_via_native_cbmignore_negations',
                   'labels': dict(Counter(n['native_label'] for n in facts['nodes'])),
                   'hash_verification': 'not_run_per_user_preference'}
        (output / 'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        return facts
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        (output / 'failure.json').write_text(json.dumps({'adapter': VERSION, 'status': 'failed',
            'source_commit': source_commit, 'error': str(exc),
            'seconds': round(time.monotonic() - started, 3)}, indent=2), encoding='utf-8')
        raise
