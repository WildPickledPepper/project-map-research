"""Discover committed inputs and build/module context, without a business file list."""
from collections import Counter, defaultdict
from fnmatch import fnmatchcase
import json
from pathlib import PurePosixPath

from adapters.snapshot_inputs import commit, git, validate_path

VERSION = 'repository-discovery/3'
LANGUAGES = {'.ts': 'typescript', '.mts': 'typescript', '.cts': 'typescript', '.tsx': 'tsx', '.cpp': 'cpp', '.cc': 'cpp', '.cxx': 'cpp',
    '.h': 'cpp', '.hpp': 'cpp', '.hh': 'cpp', '.hxx': 'cpp', '.c': 'c',
    '.js': 'javascript', '.jsx': 'javascript', '.mjs': 'javascript', '.cjs': 'javascript',
    '.py': 'python', '.pyi':'python', '.rs': 'rust', '.sh': 'shell', '.ps1': 'powershell', '.cmake': 'cmake'}
SUPPORTED = {'cpp', 'typescript', 'tsx', 'javascript', 'python'}
DEFAULT_POLICY = {'version': 1, 'roles': ['product', 'test', 'build_tool'],
                  'exclude': [], 'max_file_bytes': 2 * 1024 * 1024}


def policy(value=None):
    result = {**DEFAULT_POLICY, **(value or {})}
    if set(result) != set(DEFAULT_POLICY) or result['version'] != 1:
        raise ValueError('Unknown discovery policy field/version')
    if not isinstance(result['roles'], list) or not set(result['roles']) <= {'product', 'test', 'build_tool', 'third_party', 'generated'}:
        raise ValueError('Invalid roles')
    if not isinstance(result['exclude'], list) or not all(isinstance(p, str) and p for p in result['exclude']):
        raise ValueError('Invalid exclude patterns')
    if type(result['max_file_bytes']) is not int or result['max_file_bytes'] < 1:
        raise ValueError('max_file_bytes must be positive')
    result['roles'] = sorted(set(result['roles'])); result['exclude'] = sorted(set(result['exclude']))
    return result


def manifest_kind(path):
    name = PurePosixPath(path).name
    if name == 'package.json': return 'package'
    if name.startswith('tsconfig') and name.endswith('.json'): return 'tsconfig'
    if name == 'CMakeLists.txt' or name.endswith('.cmake'): return 'cmake'
    if name == 'compile_commands.json': return 'compile_commands'
    if name in {'Cargo.toml', 'pyproject.toml'}: return 'toml'
    if name.startswith('requirements') and name.endswith('.txt'): return 'requirements'
    return None


def role(path):
    parts = {p.lower() for p in PurePosixPath(path).parts[:-1]}; name = PurePosixPath(path).name.lower()
    rules = [('third_party', {'third_party', 'third-party', 'node_modules', 'vendor', 'vendors', 'external'}),
             ('generated', {'generated', '__generated__', 'dist', 'output', 'out'}),
             ('test', {'test', 'tests', '__tests__', 'e2e', 'testing', 'fuzz', 'fixtures', 'mocks', '__mocks__'}),
             ('build_tool', {'scripts', 'build', 'docker', 'ci', '.github', '.gitcode', 'pre-commit'})]
    for label, tokens in rules:
        if parts & tokens: return label, 'directory:' + sorted(parts & tokens)[0]
    if any(token in name for token in ('.generated.', '.gen.')): return 'generated', 'generated_filename'
    if any(token in name for token in ('.test.', '.spec.')) or name.startswith('test_') or name.endswith('_test.cpp'):
        return 'test', 'test_filename'
    return 'product', 'default_first_party'


def discover(source, revision='HEAD', configuration=None):
    config = policy(configuration); revision = commit(source, revision); files = []
    for record in git(source, 'ls-tree', '-r', '-l', '-z', '--full-tree', revision).split(b'\0'):
        if not record: continue
        header, raw_path = record.split(b'\t', 1)
        mode, kind, oid, size = header.decode('ascii').split()
        path = raw_path.decode('utf-8'); suffix = PurePosixPath(path).suffix.lower()
        category, rule = role(path); manifest = manifest_kind(path)
        language = 'cmake' if PurePosixPath(path).name == 'CMakeLists.txt' else LANGUAGES.get(suffix)
        row = {'path': path, 'object': oid, 'mode': mode, 'bytes': int(size) if size != '-' else None,
               'language': language, 'role': category, 'classification_rule': rule, 'manifest_kind': manifest}
        reason = None
        try: validate_path(path)
        except ValueError: reason = 'unsafe_path'
        if not reason and (kind != 'blob' or mode not in {'100644', '100755'}): reason = 'unsupported_git_mode'
        if not reason and category not in config['roles']: reason = 'excluded_role:' + category
        if not reason and any(fnmatchcase(path, p) for p in config['exclude']): reason = 'excluded_by_policy'
        if not reason and row['bytes'] > config['max_file_bytes']: reason = 'file_size_budget'
        if not reason and language not in SUPPORTED and not manifest:
            reason = 'unsupported_language' if language else 'not_source_or_build_manifest'
        row.update(status='excluded' if reason else 'pending', reason=reason,
                   task='manifest' if manifest else 'source', eligible=not bool(reason))
        files.append(row)
    # Record both colliding paths before any portable export; never overwrite.
    collisions = defaultdict(list)
    for row in files:
        if row['eligible']: collisions[row['path'].casefold()].append(row)
    for group in collisions.values():
        if len(group) > 1:
            for row in group: row.update(eligible=False, status='excluded', reason='case_collision')
    files.sort(key=lambda r: r['path'])
    manifests = [r['path'] for r in files if r['manifest_kind']]
    module_roots = {str(PurePosixPath(p).parent) for p in manifests if PurePosixPath(p).name in
                    {'package.json', 'CMakeLists.txt', 'Cargo.toml', 'pyproject.toml'}}
    groups = defaultdict(list)
    for index, row in enumerate(files):
        row['index'] = index
        ancestors = [str(p) for p in PurePosixPath(row['path']).parents]
        module = next((p for p in ancestors if p in module_roots), row['path'].split('/')[0] if '/' in row['path'] else '.')
        row['module'] = module; groups[module].append(row)
        if row['language'] in SUPPORTED:
            nearest = []
            for ancestor in ancestors:
                nearest = [p for p in manifests if str(PurePosixPath(p).parent) == ancestor and
                           (PurePosixPath(p).name=='pyproject.toml' if row['language']=='python' else
                            PurePosixPath(p).name == 'CMakeLists.txt' if row['language']=='cpp' else manifest_kind(p)=='tsconfig')]
                if nearest: break
            row['build_context'] = {'manifests': nearest, 'status': 'recorded_not_applied' if nearest else 'missing',
                'analysis_mode': 'source_syntax', 'build_membership': 'not_proven',
                'compile_commands': [p for p in manifests if manifest_kind(p) == 'compile_commands'] if row['language'] == 'cpp' else []}
    return {'schema_version': VERSION, 'source_commit': revision, 'policy': config, 'files': files,
        'modules': [{'path': key, 'files': len(rows), 'selected_sources': sum(r['eligible'] and r['task'] == 'source' for r in rows),
            'manifests': [r['path'] for r in rows if r['manifest_kind']], 'origin': 'nearest_tracked_manifest_or_top_level'}
            for key, rows in sorted(groups.items())],
        'provenance': {'input_kind': 'git_committed_blobs', 'working_tree_included': False,
                       'file_hash_verification': 'not_run_per_user_preference'},
        'limits': ['module_ownership_is_structural', 'all_tracked_supported_source_is_a_conservative_scope',
                   'build_conditions_not_executed', 'unsupported_languages_have_no_semantic_facts']}


def generated_config(discovery, deployment=None):
    return {'version': 1, 'scope': {'include': ['*'], 'exclude': [], 'discovery': discovery['policy']},
            'deployment': deployment or {'services': []}, 'storage': 'json'}


def summary(discovery):
    files = discovery['files']; counts = Counter(r['status'] for r in files)
    return {'source_commit': discovery['source_commit'], 'tracked_files': len(files), 'module_groups': len(discovery['modules']),
        'eligible_sources': sum(r['eligible'] and r['task'] == 'source' for r in files),
        'eligible_manifests': sum(r['eligible'] and r['task'] == 'manifest' for r in files),
        'statuses': dict(sorted(counts.items())), 'reasons': dict(sorted(Counter(r['reason'] for r in files if r.get('reason')).items())),
        'languages': {lang: {'tracked': sum(r['language'] == lang for r in files),
            'eligible_sources': sum(r['language'] == lang and r['eligible'] and r['task'] == 'source' for r in files),
            'statuses': dict(Counter(r['status'] for r in files if r['language'] == lang))}
            for lang in sorted({r['language'] for r in files if r['language']})},
        'fact_counts': dict(sum((Counter(r.get('fact_counts', {})) for r in files), Counter())),
        'build_context_missing': sum(r.get('build_context', {}).get('status') == 'missing' for r in files if r['eligible']),
        'cpp_compile_context': 'not_applied', 'complete_semantic_graph': False}
