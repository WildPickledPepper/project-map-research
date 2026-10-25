"""Configure a committed CMake subtree in an independent exported source copy.

Dependency locations/revisions are explicit experiment inputs, not production
business-name rules. Raw commands, native replies and logs stay outside Git.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from adapters.snapshot_inputs import export_inputs, select_inputs, validate_path
from run_cmake_probe import backtrace, read_reply, request, write


def selection(source, revision, include):
    return select_inputs(source, revision, {'version': 1, 'scope': {'include': include, 'exclude': []},
                                           'deployment': {}, 'storage': 'json'})


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'cmake', 'make', 'cc', 'cxx', 'output'): ap.add_argument('--' + name, type=Path, required=True)
    ap.add_argument('--revision', required=True); ap.add_argument('--subdir', required=True)
    ap.add_argument('--generator', default='Ninja'); ap.add_argument('--configuration', default='Release')
    ap.add_argument('--dependency-git', nargs=3, action='append', default=[], metavar=('DESTINATION', 'REPOSITORY', 'REVISION'))
    ap.add_argument('--dependency-file', nargs=2, action='append', default=[], metavar=('DESTINATION', 'FILE'))
    args = ap.parse_args()
    output = args.output.resolve(); source = args.source.resolve()
    if output.exists(): ap.error('Choose a new output directory')
    if output.is_relative_to(source) or output.is_relative_to(ROOT): ap.error('Keep output outside both repositories')
    subdir = validate_path(args.subdir); output.mkdir(parents=True)
    exported = output / 'source'; chosen = selection(source, args.revision, [subdir + '/*'])
    export_inputs(source, chosen, exported)
    write(output / 'selection.json', json.dumps(chosen, indent=2) + '\n')
    dependencies = []; attempts = []

    def portable(path, build):
        path = Path(path).resolve()
        for root_name, base in [('source', exported), ('build', build)]:
            if path.is_relative_to(base): return {'root': root_name, 'path': path.relative_to(base).as_posix()}
        return {'root': 'external', 'basename': path.name, 'location': 'retained_in_raw_reply'}

    def configure(label):
        build = output / label; request(build)
        command = [str(args.cmake), '-S', str(exported / subdir), '-B', str(build), '-G', args.generator,
            '-DCMAKE_BUILD_TYPE=' + args.configuration, '-DCMAKE_MAKE_PROGRAM=' + args.make.as_posix(),
            '-DCMAKE_C_COMPILER=' + args.cc.as_posix(), '-DCMAKE_CXX_COMPILER=' + args.cxx.as_posix(),
            '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON', '-DCMAKE_POLICY_VERSION_MINIMUM=3.5']
        write(build / 'command.json', json.dumps(command, indent=2) + '\n')
        result = subprocess.run(command, text=True, encoding='utf-8', errors='replace',
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
        write(build / 'configure.log', result.stdout)
        record = {'id': label, 'returncode': result.returncode, 'configured': result.returncode == 0,
                  'targets': [], 'compile_commands_available': (build / 'compile_commands.json').exists(),
                  'successful_reply_available': bool(list((build / '.cmake/api/v1/reply').glob('index-*.json')))}
        if result.returncode:
            record['diagnostics'] = [line.strip() for line in result.stdout.splitlines()
                                     if 'Error' in line or 'does not' in line or 'No SOURCES' in line]
        else:
            index, objects, configurations = read_reply(build)
            model = objects['codemodel']; record['native_version'] = index['cmake']['version']['string']
            record['codemodel_version'] = model['version']
            record['native_objects'] = sorted(objects)
            source_root = Path(model['paths']['source']); build_root = Path(model['paths']['build'])
            def trace(target, offset):
                return [{**row, 'path': portable(source_root / row['path'], build)} for row in backtrace(target, offset)]
            for configuration in configurations:
                for target in configuration['targets']:
                    record['targets'].append({'id': target['id'], 'name': target['name'], 'type': target['type'],
                        'configuration': configuration['name'],
                        'artifacts': [portable(build_root / a['path'], build) for a in target.get('artifacts', [])],
                        'sources': [{**portable(source_root / s['path'], build), 'generated': s.get('isGenerated', False),
                                     'backtrace': trace(target, s['backtrace']) if 'backtrace' in s else []}
                                    for s in target.get('sources', [])],
                        'dependencies': [r['id'] for r in target.get('dependencies', [])],
                        'declaration': trace(target, target['backtrace']) if 'backtrace' in target else [],
                        'compile_groups': [{'language': group['language'],
                            'definitions': [r['define'] for r in group.get('defines', [])],
                            'includes': [portable(r['path'], build) for r in group.get('includes', [])]}
                            for group in target.get('compileGroups', [])]})
        attempts.append(record)
        print(json.dumps({'attempt': label, 'configured': record['configured'], 'targets': len(record['targets'])}), flush=True)

    configure('without-dependencies')
    for destination, repository, revision in args.dependency_git:
        destination = validate_path(destination)
        chosen_dep = selection(Path(repository), revision, ['*'])
        export_inputs(Path(repository), chosen_dep, exported / destination)
        dependencies.append({'destination': destination, 'kind': 'git_committed_blob_export',
                             'revision': chosen_dep['source_commit'], 'files': len(chosen_dep['files'])})
    for destination, filename in args.dependency_file:
        destination = validate_path(destination); target = exported / destination
        if target.exists(): raise ValueError('Dependency file would replace existing source: ' + destination)
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(Path(filename).read_bytes())
        dependencies.append({'destination': destination, 'kind': 'prepared_source_file',
                             'origin': 'caller_provided_source_cache_not_rehashed'})
    configure('prepared-dependencies')
    receipt = {'schema': 'cmake-repository-native-trial/1', 'source_commit': chosen['source_commit'],
        'subdir': subdir, 'source_export_files': len(chosen['files']),
        'cmake': subprocess.check_output([str(args.cmake), '--version'], text=True).splitlines()[0],
        'make': subprocess.check_output([str(args.make), '--version'], text=True).splitlines()[0],
        'cxx': subprocess.check_output([str(args.cxx), '--version'], text=True).splitlines()[0],
        'configuration': args.configuration, 'generator': args.generator, 'dependencies': dependencies,
        'attempts': attempts, 'product_source_compiled': False, 'product_executed': False,
        'compiler_probe_executed': True, 'project_cmake_configuration_executed': True,
        'original_checkout_modified': False, 'file_hash_verification': 'not_run_per_user_preference',
        'production_graph_generated': False, 'process_counterpart_connected': False,
        'whole_G02_accepted': False, 'whole_G03_accepted': False}
    write(output / 'result.json', json.dumps(receipt, indent=2) + '\n')
    if not attempts[-1]['configured']: raise SystemExit(1)


if __name__ == '__main__': main()
