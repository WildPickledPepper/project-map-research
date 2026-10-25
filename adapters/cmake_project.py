"""Discover CMake roots and configure independent copies for native build facts."""
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess

from adapters.cmake_file_api import analyze, link_source_symbols


def configuration(value=None):
    from adapters.snapshot_inputs import validate_path
    value = json.loads(json.dumps(value if value is not None else {'version': 1, 'cmake': {}}))
    if not isinstance(value, dict) or value.get('version') != 1 or set(value) - {'version', 'cmake'}:
        raise ValueError('Expected build configuration version 1')
    cmake = value.setdefault('cmake', {})
    if not isinstance(cmake, dict) or set(cmake) - {'enabled', 'generator', 'configurations', 'arguments', 'dependencies', 'timeout_seconds'}:
        raise ValueError('Unknown CMake build configuration field')
    if type(cmake.setdefault('enabled', True)) is not bool: raise ValueError('cmake.enabled must be boolean')
    if not isinstance(cmake.setdefault('generator', 'Ninja'), str) or not cmake['generator']:
        raise ValueError('CMake generator is required')
    configs = cmake.setdefault('configurations', ['Release'])
    if not isinstance(configs, list) or not configs or not all(isinstance(c, str) and c and '/' not in c and '\\' not in c for c in configs):
        raise ValueError('CMake configurations must be nonempty names')
    cmake['configurations'] = sorted(set(configs))
    arguments = cmake.setdefault('arguments', [])
    if not isinstance(arguments, list) or not all(isinstance(a, str) and a.startswith('-D') and '=' in a for a in arguments):
        raise ValueError('CMake context arguments must be -DNAME=VALUE entries')
    if any(a.split('=', 1)[0].split(':', 1)[0] in {'-DCMAKE_HOME_DIRECTORY', '-DCMAKE_BUILD_TYPE', '-DCMAKE_MAKE_PROGRAM'} for a in arguments):
        raise ValueError('Use dedicated generator/configuration fields for the native context')
    timeout = cmake.setdefault('timeout_seconds', 180)
    if type(timeout) is not int or not 1 <= timeout <= 1800: raise ValueError('Invalid CMake timeout')
    dependencies = cmake.setdefault('dependencies', []); seen = set()
    if not isinstance(dependencies, list): raise ValueError('CMake dependencies must be a list')
    for dependency in dependencies:
        if not isinstance(dependency, dict): raise ValueError('Invalid native dependency input')
        destination = validate_path(dependency.get('destination'))
        if destination in seen: raise ValueError('Duplicate native dependency destination')
        seen.add(destination)
        kind = dependency.get('kind')
        keys = {'kind', 'destination', 'repository', 'revision'} if kind == 'git' else {'kind', 'destination', 'path', 'version', 'origin'}
        if kind not in {'git', 'file'} or set(dependency) != keys or not all(isinstance(v, str) and v for v in dependency.values()):
            raise ValueError('Native dependencies require pinned Git revision or prepared-file version/origin')
        if kind == 'git' and (len(dependency['revision']) != 40 or any(c not in '0123456789abcdef' for c in dependency['revision'])):
            raise ValueError('Native dependency Git revision must be a fixed full commit')
    return value


def binary(name):
    return os.environ.get('PROJECT_MAP_' + name.upper()) or shutil.which(name)


def tool_versions():
    result = {}
    for name in ('cmake', 'ninja'):
        try:
            program = binary(name)
            result[name] = subprocess.check_output([program, '--version'], text=True, stderr=subprocess.STDOUT, timeout=10).splitlines()[0] if program else None
        except (OSError, subprocess.SubprocessError): result[name] = None
    return result


def roots(paths):
    directories = {PurePosixPath(p).parent for p in paths if PurePosixPath(p).name == 'CMakeLists.txt'}
    return sorted(p.as_posix() for p in directories if not any(a in directories for a in p.parents))


def _write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def _dependencies(source, rows):
    from adapters.snapshot_inputs import select_inputs, export_inputs
    records = []
    for row in rows:
        target = source / row['destination']
        if target.exists(): raise ValueError('Native dependency would replace selected source: ' + row['destination'])
        if row['kind'] == 'git':
            selection = select_inputs(Path(row['repository']), row['revision'],
                {'version': 1, 'scope': {'include': ['*']}, 'deployment': {}, 'storage': 'json'})
            if selection['source_commit'] != row['revision']: raise ValueError('Dependency revision must identify a commit directly')
            export_inputs(Path(row['repository']), selection, target)
            records.append({'destination': row['destination'], 'kind': 'git', 'revision': selection['source_commit']})
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(Path(row['path']).read_bytes())
            records.append({k: row[k] for k in ('kind', 'destination', 'version', 'origin')})
    return records


def extract(source, paths, *, source_commit, output, config=None, source_facts=None, emit=None):
    source = Path(source).resolve(); output = Path(output).resolve(); options = configuration(config)['cmake']
    result = {'nodes': [], 'edges': [], 'diagnostics': [], 'coverage': [], 'limits': [], 'contexts': [],
              'components': {'adapter': 'native_cmake_file_api/0.1.0', 'tools': tool_versions()}}
    discovered = roots(paths); result['projects'] = discovered
    if not discovered: return result
    output.mkdir(parents=True, exist_ok=False)
    def gap(project, reason):
        result['diagnostics'].append({'kind': 'cmake_project_context_unavailable',
            'path': (PurePosixPath(project) / 'CMakeLists.txt').as_posix(), 'reason': reason, 'required': True})
    if not options['enabled'] or not result['components']['tools']['cmake']:
        reason = 'native_CMake_disabled' if not options['enabled'] else 'native_CMake_tool_missing'
        for project in discovered:
            gap(project, reason)
            for name in options['configurations']:
                result['contexts'].append({'key': project + '/' + name, 'source_commit': source_commit,
                    'status': 'unavailable', 'project': project, 'configuration': name, 'reason': reason})
        return result
    for ordinal, project in enumerate(discovered):
        for config_ordinal, name in enumerate(options['configurations']):
            context_key = (project if project != '.' else '@repository') + '/' + name
            directory = output / str(ordinal) / str(config_ordinal); directory.mkdir(parents=True)
            copied = directory / 'source'; build = directory / 'build'
            receipt = {'source_commit': source_commit, 'context_key': context_key, 'project': project,
                       'configuration': name, 'status': 'preparing', 'dependencies': []}
            try:
                # Copy only fixed selected inputs; configure never writes the graph's immutable export.
                copied.mkdir()
                for path in paths:
                    target = copied / path; target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes((source / path).read_bytes())
                receipt['dependencies'] = _dependencies(copied, options['dependencies'])
                query = build / '.cmake/api/v1/query/client-project-map'; query.mkdir(parents=True)
                for kind in ('codemodel-v2', 'cache-v2', 'toolchains-v1', 'cmakeFiles-v1'): (query / kind).touch()
                command = [binary('cmake'), '-S', str(copied / project), '-B', str(build), '-G', options['generator'],
                    '-DCMAKE_BUILD_TYPE=' + name, '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON', *options['arguments']]
                if options['generator'] in {'Ninja Multi-Config', 'Xcode'} or options['generator'].startswith('Visual Studio '):
                    command.append('-DCMAKE_CONFIGURATION_TYPES=' + name)
                if options['generator'].startswith('Ninja') and binary('ninja'):
                    command.append('-DCMAKE_MAKE_PROGRAM=' + str(binary('ninja')))
                receipt['command'] = command
                with (directory / 'configure.log').open('w', encoding='utf-8') as log:
                    completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                               timeout=options['timeout_seconds'], check=False)
                receipt['returncode'] = completed.returncode
                replies = sorted((build / '.cmake/api/v1/reply').glob('index-*.json'))
                receipt['reply_index'] = replies[-1].name if completed.returncode == 0 and replies else None
                facts = analyze(build, copied, context_key=context_key, source_commit=source_commit,
                    expected_commit=source_commit, selected_paths=paths, configure_returncode=completed.returncode,
                    index_name=receipt['reply_index'], dependency_prefixes=[r['destination'] for r in receipt['dependencies']])
                receipt['status'] = facts['native_context']['status']
                for key in ('nodes', 'edges', 'diagnostics', 'limits'): result[key].extend(facts[key])
                if source_facts: result['edges'].extend(link_source_symbols(facts, source_facts))
                result['contexts'].append({**facts['native_context'], 'project': project,
                    'configuration': name, 'dependencies': receipt['dependencies'],
                    'configure_returncode': completed.returncode,
                    'compile_commands_available': (build / 'compile_commands.json').is_file(),
                    'configure_log': str((directory / 'configure.log').relative_to(output)).replace('\\', '/')})
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                receipt.update(status='unavailable', error=str(error)); gap(project, str(error))
                result['contexts'].append({'key': context_key, 'source_commit': source_commit,
                                           'status': 'unavailable', 'project': project, 'configuration': name})
            _write(directory / 'receipt.json', receipt)
            if emit: emit({'context': context_key, 'status': receipt['status'], 'nodes': len(result['nodes']), 'edges': len(result['edges'])})
    result['limits'] = sorted(set(result['limits']))
    return result
