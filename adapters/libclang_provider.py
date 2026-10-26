"""Import Clang's translation-unit cursors, references and compilation contexts.

The compiler resolves names/types/targets. This adapter selects native compilation
units and translates cursors; it implements no C++ parser or alias analysis.
"""
from collections import defaultdict
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import quote

from adapters.compilation_database import command_arguments
from adapters.snapshot_inputs import validate_path

VERSION = 'libclang_translation_units/2'
_DLL_HANDLES = []


def compiler_environment(driver, *, builtin_headers=None):
    """Ask the configured compiler for its native target and include directories."""
    def run(args, text=None):
        return subprocess.run([str(driver), *args], input=text, capture_output=True,
                              text=True, encoding='utf-8', errors='replace',
                              check=True, timeout=20)
    result = run(['-E', '-x', 'c++', '-', '-v'], '')
    body = result.stderr.partition('#include <...> search starts here:')[2]
    if not body or 'End of search list.' not in body:
        raise ValueError('Configured compiler did not return native include paths')
    includes = [str(Path(p.strip()).resolve()) for p in body.split('End of search list.')[0].splitlines()
                if p.strip() and not p.strip().startswith('ignoring ')]
    arguments = ['--target=' + run(['-dumpmachine']).stdout.strip()]
    if builtin_headers:
        if not Path(builtin_headers).is_dir():
            raise ValueError('Matching Clang builtin headers are unavailable')
        arguments += ['-isystem', str(Path(builtin_headers).resolve())]
    for path in includes:
        arguments += ['-isystem', path]
    return {'arguments': arguments, 'native_include_paths': includes,
            'compiler_version': run(['--version']).stdout.splitlines()[0]}


def parse_arguments(row):
    """Retain semantic flags; omit output/dependency actions and one GCC codegen flag."""
    raw = row.get('arguments') or command_arguments(row['command'])
    args, omitted, skip = [], [], False
    source = Path(row['file']).resolve()
    for value in raw[1:]:
        if skip:
            omitted.append(value); skip = False; continue
        if value in {'-o', '-MF', '-MT', '-MQ'}:
            omitted.append(value); skip = True; continue
        if value in {'-c', '-MD', '-MMD', '-MP', '-MG', '-fno-keep-inline-dllexport'}:
            omitted.append(value); continue
        if not value.startswith('-') and Path(value).resolve() == source:
            continue
        args.append(value)
    return raw[0], ['-working-directory=' + row['directory'], *args], omitted


def select_units(rows, root, required, import_pairs=()):
    """Prioritize existing import candidates; actual Clang inclusions decide coverage."""
    root = Path(root).resolve(); required = set(required)
    commands = {}
    for row in rows:
        path = Path(row['file'])
        if not path.is_absolute(): path = Path(row['directory']) / path
        try: relative = path.resolve().relative_to(root).as_posix()
        except ValueError: continue
        if path.suffix.lower() in {'.cpp', '.cc', '.cxx'}:
            commands.setdefault(relative, row)
    imports = defaultdict(set)
    for source, target in import_pairs: imports[source].add(target)
    reachable = {}
    for source in commands:
        pending = [source]; seen = set()
        while pending:
            path = pending.pop()
            if path in seen: continue
            seen.add(path); pending.extend(imports[path] - seen)
        reachable[source] = seen & required
    remaining = set(required); priority = []
    while remaining:
        source = max(sorted(commands), key=lambda p: len(reachable[p] & remaining), default=None)
        if source is None or not reachable[source] & remaining: break
        priority.append(source); remaining -= reachable[source]
    return [(p, commands[p]) for p in [*priority, *sorted(set(commands) - set(priority))]]


def analyze(root, paths, *, compile_commands, required_headers, context, source_commit,
            output, query_drivers=(), builtin_headers=None, import_pairs=(), emit=None):
    if os.name == 'nt' and os.environ.get('PROJECT_MAP_DLL_DIR'):
        _DLL_HANDLES.append(os.add_dll_directory(os.environ['PROJECT_MAP_DLL_DIR']))
    from clang import cindex
    root, output = Path(root).resolve(), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    selected = set(paths); required = set(required_headers)
    if not required <= selected: raise ValueError('Required headers escaped selected input')
    for path in selected: validate_path(path)
    database = Path(compile_commands)
    if database.is_dir(): database /= 'compile_commands.json'
    rows = json.loads(database.read_text(encoding='utf-8-sig'))
    units = select_units(rows, root, required, import_pairs)
    allowed = {str(Path(p).resolve()).casefold() for p in query_drivers}
    environments = {}; nodes = {}; edges = []; diagnostics = []; observed = defaultdict(list)
    provenance = {'provider':'libclang', 'adapter':VERSION, 'source_commit':source_commit,
                  'context':context, 'libclang_package':importlib.metadata.version('libclang')}
    index = cindex.Index.create()
    callable_kinds = {'FUNCTION_DECL','CXX_METHOD','CONSTRUCTOR','DESTRUCTOR',
                      'CONVERSION_FUNCTION','FUNCTION_TEMPLATE'}
    type_kinds = {'STRUCT_DECL','CLASS_DECL','UNION_DECL','ENUM_DECL','TYPEDEF_DECL',
                  'TYPE_ALIAS_DECL','CLASS_TEMPLATE','CLASS_TEMPLATE_PARTIAL_SPECIALIZATION'}

    def relative(file):
        if not file: return None
        try: path = Path(str(file)).resolve().relative_to(root).as_posix()
        except ValueError: return None
        return path if path in selected else None

    for ordinal, (unit, row) in enumerate(units):
        if required and all(any(s['status']=='parsed' for s in observed[p]) for p in required): break
        driver, arguments, omitted = parse_arguments(row)
        if str(Path(driver).resolve()).casefold() not in allowed:
            raise ValueError('Compilation driver is not one of the configured query drivers')
        if driver not in environments:
            environments[driver] = compiler_environment(driver, builtin_headers=builtin_headers)
        arguments += environments[driver]['arguments']
        tu = index.parse(str(root/unit), args=arguments)
        tu.save(str(output/f'{ordinal}.ast'))
        errors = [d for d in tu.diagnostics if d.severity>=3]
        includes = {relative(i.include) for i in tu.get_includes()} & required
        includes.discard(None)
        state = 'parsed_with_diagnostics' if errors else 'parsed'
        native = {**provenance,'translation_unit':unit,'compiler_version':environments[driver]['compiler_version']}
        prefix = 'libclang:' + quote(context,safe='') + ':' + quote(unit,safe='/') + ':'
        for diagnostic in tu.diagnostics:
            diagnostics.append({'path':relative(diagnostic.location.file) or unit,
                'kind':'libclang_diagnostic','translation_unit':unit,
                'severity':diagnostic.severity,'message':diagnostic.spelling,
                'line':diagnostic.location.line,'column':diagnostic.location.column})
        for path in sorted(includes):
            observed[path].append({'translation_unit':unit,'status':state,'errors':len(errors)})
        status = 'candidate' if errors else 'static_declaration'

        def declaration(cursor):
            path = relative(cursor.location.file)
            external = not path
            if external and not cursor.get_usr(): return None
            kind = cursor.kind.name
            category = ('callable' if kind in callable_kinds else 'type' if kind in type_kinds else
                        'parameter' if kind=='PARM_DECL' else 'binding' if kind in {'VAR_DECL','FIELD_DECL'} else
                        'namespace' if kind=='NAMESPACE' else 'value')
            usr = cursor.get_usr()
            identity = usr or f'{path}:{cursor.location.offset}:{kind}'
            uid = prefix + 'declaration:' + quote(identity,safe='')
            if uid not in nodes:
                nodes[uid] = {'id':uid,'kind':category,'path':path or '', 'line':cursor.location.line,
                    'column':cursor.location.column,'name':cursor.displayname or cursor.spelling,
                    'language':'cpp','native_usr':usr,'native_kind':kind,
                    'native_definition':cursor.is_definition(),'native_type':cursor.type.spelling,
                    'evidence_kind':'libclang_native_cursor','provenance':native,
                    'semantic_context_status':state,'runtime_execution':'not_observed'}
                if external:
                    nodes[uid]['external_declaration'] = True
                    nodes[uid]['external_header'] = Path(str(cursor.location.file)).name if cursor.location.file else None
            return uid

        def relation(source,target,kind,cursor):
            edges.append({'source':source,'target':target,'kind':kind,'status':status,
                'evidence':[{'path':relative(cursor.location.file),'line':cursor.location.line,
                             'column':cursor.location.column}], 'provenance':native,
                'runtime_execution':'not_observed'})

        def visit(cursor, owner=None):
            path = relative(cursor.location.file)
            if cursor.location.file and not path: return
            active_owner = owner
            if path in required and cursor.kind.is_declaration():
                uid = declaration(cursor)
                if cursor.kind.name in callable_kinds: active_owner = uid
            reference = cursor.kind.is_reference() or cursor.kind.name in {'DECL_REF_EXPR','MEMBER_REF_EXPR','CALL_EXPR'}
            if path in required and reference:
                uid = prefix + 'reference:' + quote(path,safe='/') + ':' + str(cursor.location.offset) + ':' + cursor.kind.name
                target = declaration(cursor.referenced) if cursor.referenced else None
                nodes[uid] = {'id':uid,'kind':'call_site' if cursor.kind.name=='CALL_EXPR' else 'symbol_reference',
                    'path':path,'line':cursor.location.line,'column':cursor.location.column,
                    'name':cursor.displayname or cursor.spelling,'language':'cpp',
                    'native_kind':cursor.kind.name,'native_type':cursor.type.spelling,
                    'resolution':('native_external_declaration_target' if nodes[target].get('external_declaration') else
                                  'native_declaration_target') if target else 'unresolved',
                    'evidence_kind':'libclang_native_cursor','provenance':native,
                    'semantic_context_status':state,'runtime_execution':'not_observed'}
                if target: relation(uid,target,'CLANG_TU_REFERS_TO_DECLARATION',cursor)
                if active_owner: relation(active_owner,uid,'CLANG_TU_CONTAINS_REFERENCE',cursor)
            for child in cursor.get_children(): visit(child,active_owner)
        visit(tu.cursor)
        report = {'translation_unit':unit,'status':state,'headers':sorted(includes),
                  'errors':len(errors),'omitted_nonsemantic_arguments':omitted,
                  'native_inclusions':len(list(tu.get_includes())),'nodes_so_far':len(nodes)}
        (output/f'{ordinal}.json').write_text(json.dumps(report),encoding='utf-8')
        if emit: emit(report)
        del tu
    coverage = [{'path':path,'provider':'libclang','context':context,
        'status':('parsed' if any(s['status']=='parsed' for s in observed[path]) else
                  'parsed_with_diagnostics' if observed[path] else 'native_context_unavailable'),
        'translation_units':observed[path],'standalone_diagnostics_superseded_only_in_observed_TU':True}
        for path in sorted(required)]
    return {'nodes':list(nodes.values()),'edges':edges,'diagnostics':diagnostics,'coverage':coverage,
        'components':provenance,'limits':['active_native_compilation_contexts_only',
            'native_static_targets_not_runtime_dispatch','no_pointer_or_alias_solver']}
