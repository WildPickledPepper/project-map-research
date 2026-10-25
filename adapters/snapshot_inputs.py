"""Select committed Git blobs and export an immutable input for a full rebuild.

Selection patterns use fnmatch on whole, case-sensitive POSIX paths; '*' may
cross directories. No worktree files, Git filters or archive substitutions are
used. Git object IDs locate existing content; file hashes are not recomputed.
"""
from fnmatch import fnmatchcase
import json
from pathlib import Path, PurePosixPath
import subprocess


def git(source, *args):
    return subprocess.check_output(['git', '-C', str(source), *args], stderr=subprocess.PIPE)


def commit(source, revision='HEAD'):
    return git(source, 'rev-parse', '--verify', '--end-of-options', revision + '^{commit}').decode().strip()


def validate_path(path):
    parts = path.split('/') if isinstance(path, str) else []
    if not parts or any(p in ('', '.', '..') for p in parts) or '\\' in path or ':' in path or '\0' in path:
        raise ValueError('Expected a portable repository-relative path: ' + repr(path))
    if PurePosixPath(path).is_absolute() or any(p.lower() == '.git' for p in parts):
        raise ValueError('Unsafe input path: ' + repr(path))
    return path


def normalize_config(config):
    # A detached JSON copy keeps later caller mutations out of a build request.
    config = json.loads(json.dumps(config, allow_nan=False))
    if not isinstance(config, dict) or config.get('version') != 1:
        raise ValueError('Expected configuration version 1')
    if set(config) - {'version', 'scope', 'deployment', 'storage', 'build'}:
        raise ValueError('Unknown configuration field')
    scope = config.get('scope')
    if not isinstance(scope, dict) or set(scope) - {'include', 'exclude', 'discovery'}:
        raise ValueError('Expected scope.include / scope.exclude')
    if 'discovery' in scope:
        from adapters.repository_discovery import policy
        scope['discovery'] = policy(scope['discovery'])
    for key, default in [('include', ['*']), ('exclude', [])]:
        values = scope.setdefault(key, default)
        if not isinstance(values, list) or not all(isinstance(p, str) and p for p in values):
            raise ValueError('Scope patterns must be nonempty strings')
        scope[key] = sorted(set(values))
    if not scope['include']: raise ValueError('At least one include pattern is required')
    if not isinstance(config.get('deployment'), dict): raise ValueError('Expected deployment configuration')
    if 'build' in config:
        from adapters.build_configuration import configuration as build_configuration
        config['build'] = build_configuration(config['build'])
    if config.setdefault('storage', 'kuzu') not in {'json', 'kuzu'}: raise ValueError('Unknown storage')
    return config


def select_inputs(source, revision, config):
    config = normalize_config(config)
    revision = commit(source, revision)
    discovery = None
    if 'discovery' in config['scope']:
        from adapters.repository_discovery import discover
        discovery = {r['path']: r for r in discover(source, revision, config['scope']['discovery'])['files']}
    selected, omitted, seen = [], [], set()
    raw = git(source, 'ls-tree', '-r', '-z', '--full-tree', revision)
    for record in raw.split(b'\0'):
        if not record: continue
        header, path = record.split(b'\t', 1)
        mode, kind, oid = header.decode('ascii').split()
        path = path.decode('utf-8')
        scope = config['scope']
        if (not any(fnmatchcase(path, p) for p in scope['include'])
                or any(fnmatchcase(path, p) for p in scope['exclude'])):
            omitted.append({'path': path, 'reason': 'outside_configured_scope'})
            continue
        if discovery is not None and not discovery[path]['eligible']:
            omitted.append({'path': path, 'reason': discovery[path]['reason']})
            continue
        if kind != 'blob' or mode not in {'100644', '100755'}:
            omitted.append({'path': path, 'reason': 'unsupported_git_mode', 'mode': mode})
            continue
        validate_path(path)
        # Reject collisions even on Linux, so exported snapshots are portable.
        folded = path.casefold()
        if folded in seen: raise ValueError('Case-colliding input paths: ' + path)
        seen.add(folded)
        selected.append({'path': path, 'object': oid, 'mode': mode})
    if not selected: raise ValueError('No regular committed files matched the scope')
    return {'source_commit': revision, 'files': sorted(selected, key=lambda f: f['path']),
            'omitted': omitted, 'config': config, 'input_kind': 'git_committed_blob_export',
            'working_tree_included': False, 'file_hash_verification': 'not_run_per_user_preference'}


def export_inputs(source, selection, destination):
    """Export once to a new directory. Failures retain partial inputs for diagnosis."""
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    proc = subprocess.Popen(['git', '-C', str(source), 'cat-file', '--batch'],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for item in selection['files']:
            path = validate_path(item['path'])
            target = (destination / path).resolve()
            if not target.is_relative_to(destination): raise ValueError('Input escapes export root')
            proc.stdin.write((item['object'] + '\n').encode('ascii')); proc.stdin.flush()
            fields = proc.stdout.readline().split()
            if len(fields) != 3 or fields[1] != b'blob': raise ValueError('Cannot read committed blob: ' + path)
            size = int(fields[2]); content = proc.stdout.read(size)
            if len(content) != size or proc.stdout.read(1) != b'\n': raise ValueError('Incomplete Git blob: ' + path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        proc.stdin.close()
        stderr = proc.stderr.read()
        if proc.wait(): raise RuntimeError('Git export failed: ' + stderr.decode('utf-8', errors='replace'))
    finally:
        if proc.poll() is None: proc.kill(); proc.wait()
        for pipe in [proc.stdin, proc.stdout, proc.stderr]:
            if pipe and not pipe.closed: pipe.close()
