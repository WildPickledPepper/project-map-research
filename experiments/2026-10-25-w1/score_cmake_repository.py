"""Score native product CMake output against a post-hoc source audit reference."""
import argparse
from collections import Counter
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--trial', type=Path, required=True); ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    if args.output.exists(): ap.error('Choose a new output path')
    raw = json.loads((args.trial / 'result.json').read_text(encoding='utf-8'))
    checks = []
    def check(name, value): checks.append({'id': name, 'passed': bool(value)})
    # This reference only reaches this scorer; the exporter/configurer above has
    # no product target, artifact or entry names in its extraction rules.
    reference = {'source_commit': 'd4e8d1cf9f90208bcbe5371c127088f6fd66c688',
        'target': 'profiler_server', 'entry': 'server/src/entry/server/bin/main.cpp',
        'artifact': 'server/output/win_mingw64/bin/profiler_server.exe',
        'declaration': 'server/src/entry/server/bin/CMakeLists.txt', 'line': 13,
        'dependencies': {'uv_a', 'sqlite', 'msinsight'}}
    absent, prepared = raw['attempts']
    targets = prepared['targets']; by_name = {t['name']: t for t in targets}; target = by_name[reference['target']]
    entry = [r for r in target['sources'] if r.get('path') == reference['entry'] and r['root'] == 'source']
    dependency_names = {t['name'] for t in targets if t['id'] in target['dependencies']}
    check('pinned_source', raw['source_commit'] == reference['source_commit'])
    check('complete_server_committed_subtree_exported', raw['subdir'] == 'server' and raw['source_export_files'] == 1417)
    check('native_cmake_version', raw['cmake'] == 'cmake version 3.31.6' and prepared['native_version'] == '3.31.6')
    check('native_context_release_ninja', raw['configuration'] == 'Release' and raw['generator'] == 'Ninja' and target['configuration'] == 'Release')
    check('missing_dependencies_fail_configuration', not absent['configured'] and absent['returncode'] != 0)
    check('failed_configuration_has_no_success_index', not absent['successful_reply_available'] and not absent['targets'])
    check('required_dependency_diagnostic_retained', any('third_party/CMakeLists.txt:9' in r for r in absent['diagnostics']))
    check('prepared_configuration_succeeds', prepared['configured'] and prepared['returncode'] == 0 and prepared['successful_reply_available'])
    check('four_native_objects', set(prepared['native_objects']) == {'cache', 'cmakeFiles', 'codemodel', 'toolchains'})
    check('compile_commands_emitted', prepared['compile_commands_available'])
    check('native_target_ids_unique', len({t['id'] for t in targets}) == len(targets) == 33)
    check('product_target_is_executable', target['type'] == 'EXECUTABLE')
    check('complete_artifact_path', {'root': 'source', 'path': reference['artifact']} in target['artifacts'])
    check('target_declaration_source', any(r['path'] == {'root': 'source', 'path': reference['declaration']}
        and r.get('line') == reference['line'] and r.get('command') == 'add_executable' for r in target['declaration']))
    check('entry_is_owned_source', len(entry) == 1 and not entry[0]['generated'])
    check('entry_source_has_native_backtrace', len(entry) == 1 and any(r.get('command') == 'add_executable' and
        r['path'] == {'root': 'source', 'path': reference['declaration']} for r in entry[0]['backtrace']))
    check('linked_target_identity', dependency_names == reference['dependencies'])
    check('sources_retained', len(target['sources']) == 408)
    definitions = {r for group in target['compile_groups'] for r in group['definitions']}
    check('native_compile_configuration', {'LIBUS_NO_SSL', 'LIBUS_USE_LIBUV', 'UWS_NO_ZLIB'} <= definitions and
        any(r.startswith('DATABASE_VERSION=') for r in definitions))
    check('native_compile_languages', {group['language'] for group in target['compile_groups']} == {'C', 'CXX'})
    dependencies = {r['destination']: r for r in raw['dependencies'] if r['kind'] == 'git_committed_blob_export'}
    check('pinned_libuv_dependency', dependencies['server/third_party/libuv']['revision'] == '0c1fa696aa502eb749c2c4735005f41ba00a27b8')
    check('pinned_usockets_dependency', dependencies['server/third_party/uSockets']['revision'] == '8cd4cb66eb061b2594ca114b9ea1ead64613ad4b')
    check('no_product_execution_or_build_claim', not raw['product_source_compiled'] and not raw['product_executed'] and
          raw['compiler_probe_executed'] and raw['project_cmake_configuration_executed'])
    check('original_checkout_and_hash_preference', not raw['original_checkout_modified'] and raw['file_hash_verification'] == 'not_run_per_user_preference')
    output = {'schema': 'cmake-repository-native-score/1', 'origin': 'executed_native_configuration_separate_source_audit',
        'source_commit': raw['source_commit'], 'source_export_files': raw['source_export_files'],
        'tools': {key: raw[key] for key in ('cmake', 'make', 'cxx')},
        'configuration': raw['configuration'], 'generator': raw['generator'], 'dependencies': raw['dependencies'],
        'target_type_counts': dict(Counter(t['type'] for t in targets)),
        'selected_target': {key: target[key] for key in ('id', 'name', 'type', 'configuration', 'artifacts', 'dependencies', 'declaration')},
        'selected_target_source_count': len(target['sources']), 'entry': entry,
        'linked_targets': sorted(dependency_names), 'compile_definitions': sorted(definitions),
        'first_failure': {k: absent[k] for k in ('id', 'returncode', 'configured', 'diagnostics', 'successful_reply_available')},
        'checks': checks, 'passed': all(r['passed'] for r in checks),
        'product_source_compiled': False, 'product_executed': False,
        'production_graph_generated': False, 'process_counterpart_connected': False,
        'whole_G02_accepted': False, 'whole_G03_accepted': False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'checks': len(checks), 'passed': output['passed'], 'failed': [r['id'] for r in checks if not r['passed']]}))
    if not output['passed']: raise SystemExit(1)


if __name__ == '__main__': main()
