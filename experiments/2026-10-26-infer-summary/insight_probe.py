"""Measure the admitted Infer route on an actual native compilation database."""
import argparse
import importlib.util
import json
from pathlib import Path
import shlex
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('bounded_native', ROOT / 'experiments/2026-10-26-native-budget/diagnose.py')
MONITOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MONITOR)


def database_counts(path):
    if not path.is_file():
        return {'status': 'not_emitted'}
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        result = {'status': 'native_sqlite_metadata_only'}
        for table in ('procedures', 'source_files', 'specs'):
            if table in tables:
                result[table] = db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
        if 'specs' in tables:
            fields = {row[1] for row in db.execute('PRAGMA table_info(specs)')}
            if 'pulse' in fields:
                result['specs_with_pulse_payload'] = db.execute('SELECT count(*) FROM specs WHERE pulse IS NOT NULL').fetchone()[0]
        return result
    finally:
        db.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--infer', type=Path, required=True)
    p.add_argument('--cmake-capture', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--match-native-gcc-headers', action='store_true')
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    metadata = json.loads((args.cmake_capture / 'result.json').read_text(encoding='utf-8'))
    if not metadata['attempts'][-1]['configured']:
        raise ValueError('Successful native CMake capture required')
    selection = json.loads((args.cmake_capture / 'selection.json').read_text(encoding='utf-8'))
    if selection['source_commit'] != metadata['source_commit']:
        raise ValueError('CMake/source revision mismatch')
    source = (args.cmake_capture / 'source').resolve()
    commands = json.loads((args.cmake_capture / metadata['attempts'][-1]['id'] / 'compile_commands.json').read_text(encoding='utf-8'))
    selected = {r['path'] for r in selection['files']}
    owned, owned_paths, gcc_selections = [], set(), {}
    for row in commands:
        file = Path(row['file'])
        if not file.is_absolute():
            file = Path(row['directory']) / file
        file = file.resolve()
        if file.is_relative_to(source) and file.relative_to(source).as_posix() in selected:
            if args.match_native_gcc_headers:
                arguments = list(row['arguments']) if 'arguments' in row else shlex.split(row['command'])
                compiler = arguments[0]
                if compiler not in gcc_selections:
                    library = subprocess.check_output([compiler, '-print-libgcc-file-name'], text=True, timeout=15).strip()
                    install = Path(library).resolve().parent
                    if not Path(library).is_file() or install.name == '':
                        raise ValueError('Native GCC installation could not be identified')
                    gcc_selections[compiler] = str(install)
                row = {key: value for key, value in row.items() if key != 'command'}
                row['arguments'] = [arguments[0], '--gcc-install-dir=' + gcc_selections[compiler], *arguments[1:]]
            owned.append(row)
            owned_paths.add(file.relative_to(source).as_posix())
    if not owned:
        raise ValueError('Native compilation database contains no selected source')
    compilation = (args.output / 'compile_commands.json').resolve()
    compilation.write_text(json.dumps(owned, indent=2), encoding='utf-8')
    native = (args.output / 'infer-out').resolve()
    infer = str(args.infer.resolve())
    result = {'schema': 'infer-insight-native-probe/1', 'source_commit': metadata['source_commit'],
              'infer_version': subprocess.check_output([infer, '--version'], text=True, timeout=15).strip(),
              'native_context': {'project': metadata['subdir'], 'configuration': metadata['configuration'],
                                 'cmake': metadata['cmake'], 'compiler': metadata['cxx']},
              'compilation_units': len(owned), 'original_compilation_units': len(commands),
              'capture_gcc_installations': gcc_selections,
              'capture_argument_adjustment': 'match_configured_gcc_headers' if args.match_native_gcc_headers else 'none',
              'stages': [], 'semantic_equivalence_accepted': False, 'whole_R0_R1_accepted': False}
    try:
        stages = [
            ('capture', [infer, 'capture', '--results-dir', str(native), '--compilation-database', str(compilation),
                         '--headers', '--jobs', '1']),
            ('analyze', [infer, 'analyze', '--results-dir', str(native), '--pulse-only', '--jobs', '1']),
            ('export', [infer, 'debug', '--results-dir', str(native), '--procedures',
                        '--procedures-summary-json', '--dump-json-summaries']),
        ]
        for name, command in stages:
            receipt = MONITOR.bounded(command, args.output / name, seconds=600, memory_gib=4)
            receipt['schema'] = 'infer-bounded-command/1'
            receipt['phase_scope'] = 'external_command_process_tree_no_internal_stage_markers'
            (args.output / name / 'resources.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
            result['stages'].append({'name': name, **{key: receipt[key] for key in
                ('exit_code', 'stop_reason', 'seconds', 'peak_tree_rss_bytes', 'limits')}})
            if receipt['exit_code'] != 0 or receipt['stop_reason']:
                result['status'] = name + '_failed_or_budget_exceeded'
                break
        else:
            result['status'] = 'native_commands_completed_semantics_not_yet_accepted'
    finally:
        result['native_databases'] = {name: database_counts(native / name) for name in ('capture.db', 'results.db')}
        summary = native / 'all_summaries.json'
        result['summary_json_bytes'] = summary.stat().st_size if summary.exists() else None
        result['summary_values_parsed'] = False
        result['input_source_units'] = sorted(owned_paths)
        (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({key: value for key, value in result.items() if key != 'input_source_units'}), flush=True)
    if result['status'] != 'native_commands_completed_semantics_not_yet_accepted':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
