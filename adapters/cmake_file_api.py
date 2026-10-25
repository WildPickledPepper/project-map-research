"""Normalize native CMake File API replies; never interpret project CMake code.

A context is bound by its caller to an immutable source export and revision.
Configured sources/outputs are build facts, not evidence of compilation or use.
"""
from collections import defaultdict
import json
from pathlib import Path
import re
from urllib.parse import quote


class NativeContextError(ValueError):
    pass


def _read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def target_system(build,version):
    """Read literal fields from CMake's generated system record; execute none."""
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+){1,3}(?:-[A-Za-z0-9.+-]+)?',version):
        raise NativeContextError('Invalid native CMake version for system record')
    build=Path(build).resolve();relative='CMakeFiles/'+version+'/CMakeSystem.cmake';path=(build/relative).resolve()
    if not path.is_relative_to(build) or not path.is_file():raise NativeContextError('Generated CMake system record missing or outside build')
    with path.open('r',encoding='utf-8-sig') as stream:
        text=stream.read(65537)
    if len(text)>65536:raise NativeContextError('Generated CMake system record exceeds limit')
    values={}
    for field in ('CMAKE_SYSTEM_NAME','CMAKE_SYSTEM_PROCESSOR','CMAKE_HOST_SYSTEM_NAME','CMAKE_HOST_SYSTEM_PROCESSOR','CMAKE_CROSSCOMPILING'):
        rows=re.findall(r'^\s*set\(\s*'+field+r'\s+(?:"([^"\r\n]*)"|([^()\s]+))\s*\)\s*$',text,re.M)
        if len(rows)!=1:raise NativeContextError('Missing or ambiguous generated system field: '+field)
        value=rows[0][0] or rows[0][1]
        if any(c in value for c in ('$','\\',';')):raise NativeContextError('Nonliteral generated system field: '+field)
        values[field]=value
    if values['CMAKE_CROSSCOMPILING'] not in {'TRUE','FALSE'}:raise NativeContextError('Unknown CMake cross-compiling state')
    def path_style(name):
        return 'windows' if name in {'Windows','WindowsStore','WindowsPhone','WindowsCE'} else 'posix' if name in {
            'Linux','Darwin','Android','FreeBSD','OpenBSD','NetBSD','DragonFly','AIX','SunOS','GNU','CYGWIN','MSYS','iOS','tvOS','watchOS','visionOS'} else None
    name=values['CMAKE_SYSTEM_NAME'];host=values['CMAKE_HOST_SYSTEM_NAME']
    return {'status':'available','name':name,'declared_processor':values['CMAKE_SYSTEM_PROCESSOR'],
        'host_name':values['CMAKE_HOST_SYSTEM_NAME'],'host_processor':values['CMAKE_HOST_SYSTEM_PROCESSOR'],
        'cross_compiling':values['CMAKE_CROSSCOMPILING']=='TRUE','target_path_style':path_style(name),'host_path_style':path_style(host),
        'processor_interpretation':'cmake_system_processor_not_verified_compiler_architecture',
        'basis':'cmake_generated_system_literals','file':relative}


def _reply_file(reply, name):
    path = (reply / name).resolve()
    if not path.is_relative_to(reply) or not path.is_file():
        raise NativeContextError('Missing or unsafe native reply file')
    return _read(path)


def _load(build, index_name=None,recorded_build=None):
    reply = (build / '.cmake/api/v1/reply').resolve()
    indexes = sorted(reply.glob('index-*.json'))
    if index_name is None:
        if not indexes: raise NativeContextError('No successful native File API index')
        index_name = indexes[-1].name
    index = _reply_file(reply, index_name)
    objects = {}
    for row in index.get('objects', []):
        if row.get('kind') in {'codemodel', 'cache', 'toolchains', 'cmakeFiles'}:
            objects[row['kind']] = _reply_file(reply, row['jsonFile'])
    model = objects.get('codemodel')
    if not model or model.get('version', {}).get('major') != 2:
        raise NativeContextError('Native codemodel version 2 required')
    if Path(model['paths']['build']).resolve() != (recorded_build or build):
        raise NativeContextError('Native build directory differs from context')
    configurations = []
    for configuration in model['configurations']:
        targets = [_reply_file(reply, r['jsonFile']) for r in configuration['targets']]
        if len({r['id'] for r in targets}) != len(targets):
            raise NativeContextError('Duplicate native target ID within configuration')
        configurations.append((configuration['name'], targets))
    return index_name, index, objects, configurations


def analyze(build, repository, *, context_key, source_commit, expected_commit,
            selected_paths, configure_returncode, index_name=None, dependency_prefixes=(),
            recorded_build_root=None,recorded_repository_root=None):
    """Return native build facts; unusable contexts yield an explicit required gap.

    ``selected_paths`` comes from committed discovery, not a target whitelist.
    Sources outside that set remain visible without claiming symbol coverage.
    """
    build = Path(build).resolve(); repository = Path(repository).resolve()
    logical_build=Path(recorded_build_root).resolve() if recorded_build_root else build
    logical_repository=Path(recorded_repository_root).resolve() if recorded_repository_root else repository
    selected = set(selected_paths); nodes = {}; edges = []; diagnostics = []
    result = {'nodes': [], 'edges': edges, 'diagnostics': diagnostics, 'coverage': [],
              'limits': ['configured_native_context_not_a_compiled_or_executed_product'],
              'native_context': {'key': context_key, 'source_commit': source_commit, 'status': 'unavailable'}}
    def fail(reason):
        diagnostics.append({'kind': 'cmake_context_unavailable', 'context_key': context_key,
                            'reason': reason, 'required': True})
        return result
    if not isinstance(context_key, str) or not context_key:
        return fail('Context key is required')
    if not source_commit or source_commit != expected_commit:
        return fail('Native context source revision does not match graph source revision')
    if type(configure_returncode) is not int or configure_returncode != 0:
        return fail('Native configuration did not succeed; previous replies are not applicable')
    if bool(recorded_build_root)!=bool(recorded_repository_root):return fail('Recorded build and source roots must be supplied together')
    try:
        index_name, index, objects, configurations = _load(build,index_name,logical_build)
        source_root = Path(objects['codemodel']['paths']['source']).resolve()
        if not source_root.is_relative_to(logical_repository):
            return fail('Native project source directory is outside the committed export')
        for _, targets in configurations:
            ids = {t['id'] for t in targets}
            if any(d['id'] not in ids for t in targets for d in t.get('dependencies', [])):
                return fail('Native target dependency is missing from its configuration')
    except (OSError, ValueError, KeyError, TypeError) as error:
        return fail(str(error))

    location_cache={};trace_cache={}
    def location(path):
        key=str(path)
        if key in location_cache:return dict(location_cache[key])
        path = Path(path).resolve()
        # Build paths may be inside the export; their identity stays a build path.
        for root, base in [('build',logical_build),('source',logical_repository)]:
            if path.is_relative_to(base):
                result={'root':root,'path':path.relative_to(base).as_posix()};location_cache[key]=result;return dict(result)
        result={'root':'external','path':str(path)};location_cache[key]=result;return dict(result)

    def identity(*parts): return 'cmake:' + ':'.join(quote(str(p), safe='') for p in parts)
    def node(uid, kind, name, loc, **extra):
        if uid not in nodes:
            nodes[uid] = {'id': uid, 'kind': kind, 'name': name,
                'path': loc['path'] if loc['root'] == 'source' else '@' + loc['root'] + '/' +
                    (loc['path'] if loc['root'] == 'build' else Path(loc['path']).name),
                'line': 0, 'language': 'cmake', 'location': loc, 'source_commit': source_commit,
                'runtime_execution': 'not_observed', **extra}
        return uid
    def edge(source, target, kind, evidence, **extra):
        edges.append({'source': source, 'target': target, 'kind': kind, 'status': 'static',
                      'evidence': evidence, 'basis': 'native_cmake_codemodel', **extra})

    try:
        system=target_system(build,index['cmake']['version']['string'])
        if system['target_path_style'] is None:
            diagnostics.append({'kind':'cmake_target_path_style_unavailable','context_key':context_key,
                'system_name':system['name'],'required':True})
        if system['host_path_style'] is None:
            diagnostics.append({'kind':'cmake_host_path_style_unavailable','context_key':context_key,
                'system_name':system['host_name'],'required':True})
    except (OSError,ValueError,KeyError) as error:
        system={'status':'unavailable','reason':str(error),'target_path_style':None,'host_path_style':None}
        diagnostics.append({'kind':'cmake_target_system_unavailable','context_key':context_key,'reason':str(error),'required':True})
    def trace(target, offset):
        key=(id(target),offset)
        if key in trace_cache:return [{**r,'location':dict(r['location'])} for r in trace_cache[key]]
        graph = target.get('backtraceGraph', {}); records = []; seen = set()
        while offset is not None:
            if offset in seen: raise NativeContextError('Cyclic native backtrace')
            seen.add(offset); row = graph['nodes'][offset]
            loc = location(source_root / graph['files'][row['file']])
            records.append({'location': loc, 'path': loc['path'] if loc['root'] == 'source' else '',
                            'line': row.get('line', 0),
                            **({'command': graph['commands'][row['command']]} if 'command' in row else {})})
            offset = row.get('parent')
        trace_cache[key]=records
        return [{**r,'location':dict(r['location'])} for r in records]

    try:
        for configuration, targets in configurations:
            context = identity(context_key, configuration)
            root_loc = location(source_root / 'CMakeLists.txt')
            node(context, 'build_configuration', configuration or 'default', root_loc,
                context_key=context_key, configuration=configuration, reply_index=index_name,
                cmake_version=index['cmake']['version']['string'], generator=index['cmake']['generator'],
                target_system=system,
                project_source=location(source_root), native_codemodel_version=objects['codemodel']['version'],
                cache_options=[{k: r[k] for k in ('name', 'type', 'value')}
                               for r in objects.get('cache', {}).get('entries', []) if r['type'] == 'BOOL'],
                state='configured_not_built')
            target_ids = {t['id']: identity(context_key, configuration, 'target', t['id']) for t in targets}
            for target in targets:
                declaration = trace(target, target.get('backtrace'))
                loc = declaration[0]['location'] if declaration else location(source_root / target['paths']['source'] / 'CMakeLists.txt')
                uid = node(target_ids[target['id']], 'build_target', target['name'], loc,
                    line=declaration[0]['line'] if declaration else 0, native_id=target['id'],
                    target_type=target['type'], build_context=context, configuration=configuration,
                    declaration=declaration, name_on_disk=target.get('nameOnDisk'),
                    link_fragments=target.get('link', {}).get('commandFragments', []))
                edge(context, uid, 'CONFIGURES_BUILD_TARGET', declaration, build_context=context)
                for dependency in target.get('dependencies', []):
                    edge(uid, target_ids[dependency['id']], 'LINKS_BUILD_TARGET',
                         trace(target, dependency.get('backtrace')), build_context=context)
                for artifact in target.get('artifacts', []):
                    artifact_loc = location(logical_build / artifact['path'])
                    primary = bool(target.get('nameOnDisk') and Path(artifact_loc['path']).name == target['nameOnDisk'])
                    artifact_id = node(identity(context_key, configuration, 'artifact', artifact_loc['root'], artifact_loc['path']),
                        'build_artifact', Path(artifact_loc['path']).name, artifact_loc,
                        build_context=context, configuration=configuration, materialization='not_verified')
                    edge(uid, artifact_id, 'PRODUCES_ARTIFACT', declaration,
                         build_context=context, artifact_role='primary' if primary else 'auxiliary_or_unclassified')
                for ordinal, source in enumerate(target.get('sources', [])):
                    source_loc = location(source_root / source['path'])
                    evidence = trace(target, source.get('backtrace'))
                    group_index = source.get('compileGroupIndex')
                    group = target.get('compileGroups', [])[group_index] if group_index is not None else None
                    tracked = source_loc['root'] == 'source' and source_loc['path'] in selected
                    dependency = source_loc['root'] == 'source' and any(
                        source_loc['path'] == prefix or source_loc['path'].startswith(prefix.rstrip('/') + '/')
                        for prefix in dependency_prefixes)
                    source_id = node(identity(context_key, configuration, 'source', target['id'], ordinal),
                        'build_source', Path(source_loc['path']).name, source_loc,
                        native_source_ordinal=ordinal, build_context=context, target=uid,
                        generated=source.get('isGenerated', False), selected_source=tracked, dependency_source=dependency,
                        symbol_coverage='eligible_for_selected_source_join' if tracked else
                            'versioned_dependency_source' if dependency else 'outside_selected_source_or_generated',
                        compile_group={'language': group.get('language'),
                            'definitions': [{'define': r['define'], 'declaration': trace(target, r.get('backtrace'))}
                                            for r in group.get('defines', [])],
                            'includes': [{'location': location(r['path']), 'system': r.get('isSystem', False),
                                          'declaration': trace(target, r.get('backtrace'))} for r in group.get('includes', [])],
                            'command_fragments': group.get('compileCommandFragments', [])} if group else None,
                        declaration=evidence)
                    edge(uid, source_id, 'COMPILES_SOURCE' if group else 'HAS_BUILD_INPUT', evidence, build_context=context)
                    if not tracked and target['type'] != 'UTILITY':
                        diagnostics.append({'kind': 'cmake_source_outside_semantic_inputs', 'path': nodes[source_id]['path'],
                            'build_context': context, 'generated': source.get('isGenerated', False),
                            'reason': 'versioned_dependency_internals_not_expanded' if dependency else
                                'native_source_kept_without_claiming_selected_symbol_coverage', 'required': not dependency})
    except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
        # A malformed reply must never publish a partial target/dependency graph.
        edges.clear(); diagnostics.clear()
        return fail('Invalid native codemodel: ' + str(error))
    result['nodes'] = list(nodes.values())
    result['native_context'].update(status='configured', reply_index=index_name,
        cmake_version=index['cmake']['version']['string'], configurations=[c for c, _ in configurations],target_system=system)
    if recorded_build_root:
        result['native_context']['relocation']={'build_root_relocated':logical_build!=build,'source_root_relocated':logical_repository!=repository,
            'basis':'caller_recorded_configure_roots_native_reply_checked'}
    return result


def link_source_symbols(build_facts, source_facts):
    """Join only declarations in native target inputs; entry edges remain candidates."""
    by_path = defaultdict(list)
    for symbol in source_facts['nodes']:
        if symbol['kind'] in {'callable', 'type'}: by_path[symbol['path']].append(symbol)
    nodes = {n['id']: n for n in build_facts['nodes']}; edges = []
    for unit in nodes.values():
        if unit['kind'] != 'build_source' or not unit['selected_source'] or unit['compile_group'] is None: continue
        target = nodes[unit['target']]
        for symbol in by_path[unit['path']]:
            if not (symbol.get('language') in {'c', 'cpp'} or symbol['id'].startswith('cpp:')): continue
            evidence = unit['declaration'] + [{'path': symbol['path'], 'line': symbol['line']}]
            extra = {'status': 'candidate', 'build_context': unit['build_context'], 'evidence': evidence,
                     'basis': 'native_compilation_input_and_source_declaration',
                     'condition': 'source_preprocessor_and_link_selection_not_proven', 'runtime_execution': 'not_observed'}
            edges.append({'source': unit['id'], 'target': symbol['id'], 'kind': 'INCLUDES_SOURCE_DECLARATION', **extra})
            if (target['target_type'] == 'EXECUTABLE' and symbol['kind'] == 'callable' and symbol.get('definition')
                    and symbol['name'] == 'main' and symbol.get('return_type_spelling', '').replace(' ', '') == 'int'):
                edges.append({'source': target['id'], 'target': symbol['id'], 'kind': 'EXECUTABLE_ENTRY_CANDIDATE', **extra})
    return edges
