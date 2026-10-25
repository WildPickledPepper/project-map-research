"""Probe unmodified CMake File API before implementing artifact graph ingestion.

All sources and build trees are independent fixtures in a new caller-owned output
directory. This does not configure or build the analyzed product repository.
"""
import argparse
import json
from pathlib import Path
import subprocess


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def request(build):
    query = build / '.cmake/api/v1/query/client-project-map'
    query.mkdir(parents=True)
    for name in ('codemodel-v2', 'cache-v2', 'cmakeFiles-v1', 'toolchains-v1'):
        (query / name).touch()


def read_reply(build):
    reply = build / '.cmake/api/v1/reply'
    indexes = list(reply.glob('index-*.json'))
    if len(indexes) != 1:
        raise ValueError('Expected one index from a new build directory')
    index = json.loads(indexes[0].read_text(encoding='utf-8'))
    objects = {r['kind']: json.loads((reply / r['jsonFile']).read_text(encoding='utf-8'))
               for r in index['objects']}
    model = objects['codemodel']
    configurations = []
    for configuration in model['configurations']:
        targets = []
        for ref in configuration['targets']:
            target = json.loads((reply / ref['jsonFile']).read_text(encoding='utf-8'))
            targets.append(target)
        configurations.append({'name': configuration['name'], 'targets': targets})
    return index, objects, configurations


def backtrace(target, index):
    graph = target['backtraceGraph']; result = []; visited = set()
    while index is not None:
        if index in visited:
            raise ValueError('Cyclic native backtrace')
        visited.add(index); node = graph['nodes'][index]
        row = {'path': graph['files'][node['file']]}
        if 'line' in node: row['line'] = node['line']
        if 'command' in node: row['command'] = graph['commands'][node['command']]
        result.append(row); index = node.get('parent')
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cmake', type=Path, required=True)
    ap.add_argument('--make', type=Path, required=True)
    ap.add_argument('--cxx', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    if args.output.exists(): ap.error('Choose a new output directory')
    args.output.mkdir(parents=True)
    version = subprocess.check_output([str(args.cmake), '--version'], text=True).splitlines()[0]
    checks = []; records = []
    def check(name, value): checks.append({'id': name, 'passed': bool(value)})
    for layout, directory, target_name, library_name in (
        ('nested', 'products/agent', 'launch_unit', 'utility_core'),
        ('renamed', 'other/deep/runtime', 'backend_alpha', 'helper_beta'),
    ):
        source = args.output / layout / 'source'
        write(source / 'CMakeLists.txt', '\n'.join([
            'cmake_minimum_required(VERSION 3.16)',
            'project(IndependentArtifactProbe LANGUAGES CXX)',
            'option(ENABLE_EXTRA "Extra source" OFF)',
            f'add_subdirectory({directory})', '',
        ]))
        write(source / directory / 'CMakeLists.txt', '\n'.join([
            f'add_library({library_name} STATIC shared.cpp)',
            'function(register_program target source output_directory)',
            '  add_executable(${target} ${source})',
            '  set_target_properties(${target} PROPERTIES OUTPUT_NAME worker RUNTIME_OUTPUT_DIRECTORY "${output_directory}")',
            'endfunction()',
            f'register_program({target_name} startup.cpp "${{CMAKE_BINARY_DIR}}/artifacts/service")',
            'register_program(unrelated_target unrelated.cpp "${CMAKE_BINARY_DIR}/artifacts/decoy")',
            f'target_link_libraries({target_name} PRIVATE {library_name})',
            'if(ENABLE_EXTRA)',
            f'  target_sources({target_name} PRIVATE extra.cpp)',
            f'  target_compile_definitions({target_name} PRIVATE EXTRA_ENABLED=1)',
            'endif()',
            f'install(TARGETS {target_name} RUNTIME DESTINATION package/bin)', '',
        ]))
        for name, text in [('startup.cpp', 'int main(){return 0;}\n'),
                           ('unrelated.cpp', 'int main(){return 1;}\n'),
                           ('shared.cpp', 'int helper(){return 7;}\n'),
                           ('extra.cpp', 'int extra(){return 9;}\n')]:
            write(source / directory / name, text)
        for enabled in (False, True):
            label = layout + ('.extra' if enabled else '.base')
            build = args.output / layout / ('build-extra' if enabled else 'build-base')
            request(build)
            command = [str(args.cmake), '-S', str(source), '-B', str(build), '-G', 'MinGW Makefiles',
                       '-DCMAKE_BUILD_TYPE=Release', '-DENABLE_EXTRA=' + ('ON' if enabled else 'OFF'),
                       '-DCMAKE_MAKE_PROGRAM=' + args.make.as_posix(),
                       '-DCMAKE_CXX_COMPILER=' + args.cxx.as_posix()]
            result = subprocess.run(command, text=True, encoding='utf-8', errors='replace',
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
            write(build / 'configure.log', result.stdout)
            if result.returncode:
                raise RuntimeError(f'{label}: native configure failed; inspect configure.log')
            index, objects, configurations = read_reply(build)
            check(label + '.native_objects', set(objects) == {'codemodel', 'cache', 'cmakeFiles', 'toolchains'})
            check(label + '.codemodel_v2', objects['codemodel']['version']['major'] == 2)
            check(label + '.release_context', len(configurations) == 1 and configurations[0]['name'] == 'Release')
            targets = {t['name']: t for t in configurations[0]['targets']}
            app = targets[target_name]; decoy = targets['unrelated_target']; lib = targets[library_name]
            check(label + '.targets_distinct', len({t['id'] for t in targets.values()}) == len(targets) == 3)
            check(label + '.executable_type', app['type'] == decoy['type'] == 'EXECUTABLE' and lib['type'] == 'STATIC_LIBRARY')
            artifacts = [r['path'] for r in app['artifacts']]; other = [r['path'] for r in decoy['artifacts']]
            check(label + '.same_basename_separate_paths', Path(artifacts[0]).name == Path(other[0]).name and
                  not set(artifacts) & set(other) and '/service/' in artifacts[0] and '/decoy/' in other[0])
            check(label + '.artifact_not_target_name', target_name not in Path(artifacts[0]).name)
            source_paths = [r['path'] for r in app['sources']]
            check(label + '.own_entry_source', directory + '/startup.cpp' in source_paths and
                  directory + '/unrelated.cpp' not in source_paths)
            check(label + '.conditional_source', (directory + '/extra.cpp' in source_paths) == enabled)
            definitions = [r['define'] for group in app.get('compileGroups', []) for r in group.get('defines', [])]
            check(label + '.conditional_define', ('EXTRA_ENABLED=1' in definitions) == enabled)
            dependencies = [r['id'] for r in app.get('dependencies', [])]
            check(label + '.dependency_identity', lib['id'] in dependencies and decoy['id'] not in dependencies)
            trace = backtrace(app, app['backtrace'])
            check(label + '.declaration_and_function_backtrace',
                  {'add_executable', 'register_program'} <= {r.get('command') for r in trace} and
                  all('line' in r for r in trace if 'command' in r))
            source_trace = backtrace(app, next(r for r in app['sources'] if r['path'].endswith('/startup.cpp'))['backtrace'])
            check(label + '.source_backtrace', any(r.get('command') == 'add_executable' for r in source_trace))
            check(label + '.install_destination', any(r['path'] == 'package/bin' for r in app.get('install', {}).get('destinations', [])))
            cache = {r['name']: r['value'] for r in objects['cache']['entries']}
            check(label + '.cache_configuration', cache['ENABLE_EXTRA'] == ('ON' if enabled else 'OFF') and cache['CMAKE_BUILD_TYPE'] == 'Release')
            records.append({'id': label, 'configuration': configurations[0]['name'], 'feature': enabled,
                'native_target_id': app['id'], 'target_name': app['name'], 'artifacts': artifacts,
                'sources': source_paths, 'dependencies': dependencies, 'declaration': trace,
                'native_version': index['cmake']['version']['string'],
                'codemodel_version': objects['codemodel']['version']})
    failed_source = args.output / 'missing-dependency/source'; failed_build = args.output / 'missing-dependency/build'
    write(failed_source / 'CMakeLists.txt', 'cmake_minimum_required(VERSION 3.16)\nproject(MissingContext NONE)\nadd_subdirectory(required_dependency)\n')
    request(failed_build)
    result = subprocess.run([str(args.cmake), '-S', str(failed_source), '-B', str(failed_build), '-G', 'MinGW Makefiles',
        '-DCMAKE_MAKE_PROGRAM=' + args.make.as_posix()], text=True, encoding='utf-8', errors='replace',
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    write(failed_build / 'configure.log', result.stdout)
    check('missing_dependency.configure_failed', result.returncode != 0)
    check('missing_dependency.no_success_reply', not list((failed_build / '.cmake/api/v1/reply').glob('index-*.json')))
    evidence = {'schema': 'cmake-native-component-probe/1', 'cmake': version,
        'official_documentation': 'https://cmake.org/cmake/help/v3.31/manual/cmake-file-api.7.html',
        'origin': 'executed_independent_fixtures_unmodified_native_cmake',
        'records': records, 'checks': checks, 'passed': all(r['passed'] for r in checks),
        'product_repository_configured': False, 'product_built': False,
        'production_graph_generated': False, 'process_counterpart_connected': False,
        'whole_G02_accepted': False, 'whole_G03_accepted': False}
    write(args.output / 'result.json', json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({'checks': len(checks), 'passed': evidence['passed'], 'failed': [r['id'] for r in checks if not r['passed']]}))
    if not evidence['passed']: raise SystemExit(1)


if __name__ == '__main__': main()
