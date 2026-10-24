"""Generate and extract an automatic, resumable whole-repository input plan."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.repository_discovery import discover, generated_config, summary
from adapters.snapshot_inputs import commit, export_inputs
from adapters.snapshot_refresh import atomic_json, writer_lock

FACT_KEYS = ('symbols', 'types', 'interfaces', 'calls', 'imports', 'registrations', 'resources', 'entries')
RETRYABLE = {'read_error', 'invalid_encoding', 'binary_input', 'extractor_error', 'worker_timeout', 'worker_exit'}


class Worker:
    def __init__(self, command, stderr):
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr,
                                        text=True, encoding='utf-8', bufsize=1)
        self.pool = ThreadPoolExecutor(max_workers=1)

    def request(self, request, timeout):
        try:
            self.process.stdin.write(json.dumps(request)+'\n'); self.process.stdin.flush()
        except (OSError, ValueError) as error:
            raise ChildProcessError('Worker input closed') from error
        future = self.pool.submit(self.process.stdout.readline)
        try: line = future.result(timeout=timeout)
        except FutureTimeout as error:
            self.close(); raise TimeoutError('Per-file worker time budget reached') from error
        if not line: raise ChildProcessError('Worker exited without a result')
        return json.loads(line)

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait()
        for pipe in (self.process.stdin, self.process.stdout):
            if pipe: pipe.close()
        self.pool.shutdown(wait=True)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def simple_manifest(path, kind, source):
    result = {'path': path, 'kind': kind, 'status': 'metadata_parsed'}
    if kind == 'toml':
        data = tomllib.loads(source)
        result['metadata'] = {k: data[k] for k in ('package', 'project', 'workspace', 'build-system', 'dependencies') if k in data}
    elif kind == 'requirements':
        result['requirements'] = [{'line': i, 'expression': s.strip()} for i, s in enumerate(source.splitlines(), 1)
                                  if s.strip() and not s.lstrip().startswith('#')]
    elif kind == 'cmake':
        result['commands'] = [{'line': source[:m.start()].count('\n')+1, 'command': m[1].lower(),
            'expression': m[2].strip(), 'resolution': 'source_expression_not_evaluated'}
            for m in re.finditer(r'^\s*(project|add_subdirectory|add_library|add_executable|file|set|option|find_package|target_link_libraries|target_include_directories)\s*\((.*?)\)', source, re.M|re.S|re.I)]
        result['limits'] = ['cmake_expression_fragments_not_executed', 'variables_globs_conditions_not_resolved',
                            'no_compile_context_generated']
    elif kind == 'compile_commands':
        rows = json.loads(source)
        if not isinstance(rows, list): raise ValueError('Expected compile_commands array')
        result['entries'] = len(rows); result['applied'] = False
        result['limits'] = ['commands_recorded_not_executed_or_applied']
    else: raise ValueError('Unknown manifest kind')
    return result


def enrich_context(report, metadata):
    for row in report['files']:
        context = row.get('build_context')
        if not context: continue
        if row['language'] != 'cpp':
            parsed = [metadata[p] for p in context['manifests'] if p in metadata]
            context['build_membership'] = ('included_in_config_file_set' if any(row['path'] in p.get('matched_source_files', []) for p in parsed)
                else 'outside_or_unresolved_config_file_sets')
            context['metadata_statuses'] = {p: metadata[p]['status'] for p in context['manifests'] if p in metadata}
        else:
            context['compile_commands_status'] = 'recorded_not_applied' if context['compile_commands'] else 'missing'


def run(source, revision, output, typescript, *, configuration=None, deployment=None,
        resume=False, max_files=None, seconds=900, file_timeout=30, version=None, retry_errors=False,
        worker_factory=Worker):
    for value in (seconds, file_timeout):
        if not math.isfinite(value) or value <= 0: raise ValueError('Budgets must be finite and positive')
    if max_files is not None and (type(max_files) is not int or max_files < 0): raise ValueError('Invalid max_files')
    source = Path(source).resolve(); output = Path(output).resolve(); typescript = Path(typescript).resolve()
    if (output.is_relative_to(ROOT) or ROOT.is_relative_to(output) or
        output.is_relative_to(source) or source.is_relative_to(output)):
        raise ValueError('Keep output separate from source and research repositories')
    version = version or {'kind': 'unversioned_programmatic_call'}
    if output.exists() and not resume: raise FileExistsError('Use a new output or --resume')
    if resume and not output.is_dir(): raise ValueError('Resume directory does not exist')
    output.mkdir(parents=True, exist_ok=True)
    with writer_lock(output):
        report_path = output/'discovery.json'; started = time.monotonic()
        if resume:
            report = read(report_path)
            if report['source_commit'] != commit(source, revision) or report['build_version'] != version:
                raise ValueError('Source/rules version changed; use a new output')
            from adapters.repository_discovery import policy
            if report['policy'] != policy(configuration) or report['deployment'] != (deployment or {'services': []}):
                raise ValueError('Policy/deployment changed; use a new output')
        else:
            report = discover(source, revision, configuration)
            report.update(build_version=version, deployment=deployment or {'services': []}, status='discovered')
            atomic_json(report_path, report)
            atomic_json(output/'input-manifest.json', {'source_commit': report['source_commit'],
                'files': [{k:r[k] for k in ('path','object','mode')} for r in report['files'] if r['eligible']],
                'provenance': report['provenance']})
            atomic_json(output/'build-config.json', generated_config(report, deployment))
        if not (output/'source/.export-complete').exists():
            if (output/'source').exists(): raise ValueError('Incomplete export retained; use a new output')
            export_inputs(source, read(output/'input-manifest.json'), output/'source')
            (output/'source/.export-complete').write_text(report['source_commit'], encoding='utf-8')
        (output/'facts').mkdir(exist_ok=True)
        workers = {}; metadata = {}; processed = 0
        attempt = {'source_commit': report['source_commit'], 'max_files': max_files, 'seconds': seconds,
                   'file_timeout': file_timeout, 'processed': 0, 'resume': resume, 'retry_errors': retry_errors}
        stderr = (output/'workers.log').open('a', encoding='utf-8')
        deadline = started + seconds

        def checkpoint():
            enrich_context(report, metadata)
            atomic_json(report_path, report); atomic_json(output/'summary.json', summary(report))

        def get_worker(kind):
            if kind not in workers:
                command = ([sys.executable, '-X', 'utf8', str(ROOT/'scripts/discovery_cpp_worker.py'), str(output/'source')]
                    if kind == 'cpp' else ['node', '--max-old-space-size=256', str(ROOT/'adapters/discovery_ts.cjs'), str(output/'source'), str(typescript)])
                workers[kind] = worker_factory(command, stderr)
            return workers[kind]

        try:
            # Build manifests first so compiler file sets can be related to source inputs.
            rows = sorted((r for r in report['files'] if r['eligible']), key=lambda r:(r['task'] != 'manifest', r['path']))
            for row in rows:
                fact_path = output/'facts'/f"{row['index']:06}.json"
                if fact_path.exists():
                    existing = read(fact_path)
                    if (existing['source_commit'] != report['source_commit'] or existing['build_version'] != version
                            or existing['facts']['path'] != row['path']):
                        raise ValueError('Fact does not match frozen input')
                    row.update(status=existing['facts']['status'], fact_counts={k: len(existing['facts'].get(k, [])) for k in FACT_KEYS},
                               facts=fact_path.relative_to(output).as_posix(), reason=None)
                    if row['task'] == 'manifest': metadata[row['path']] = existing['facts']
                    continue
                if row['status'] in RETRYABLE and not retry_errors: continue
                if (max_files is not None and processed >= max_files) or time.monotonic() >= deadline:
                    if row['status'] in {'pending', 'pending_budget'}:
                        row.update(status='pending_budget', reason='run_budget')
                    continue
                try:
                    raw = (output/'source'/row['path']).read_bytes()
                    if b'\0' in raw:
                        row.update(status='binary_input', reason='nul_byte_in_source'); processed += 1; continue
                    body = raw.decode('utf-8-sig')
                    if row['task'] == 'manifest' and row['manifest_kind'] not in {'package', 'tsconfig'}:
                        try: facts = simple_manifest(row['path'], row['manifest_kind'], body)
                        except (ValueError, tomllib.TOMLDecodeError) as error:
                            facts = {'path': row['path'], 'status': 'manifest_error', 'diagnostics': [{'kind': 'manifest_parse_error', 'message': str(error)}]}
                    else:
                        kind = 'cpp' if row['language'] == 'cpp' and row['task'] == 'source' else 'ts'
                        result = get_worker(kind).request({'path': row['path'], 'task': row['task']},
                            max(0.001, min(file_timeout, deadline-time.monotonic())))
                        if not result['ok']: raise RuntimeError(result['error'])
                        facts = result['facts']
                    facts.update(path=row['path'])
                    atomic_json(fact_path, {'source_commit': report['source_commit'], 'build_version': version, 'facts': facts})
                    row.update(status=facts['status'], reason=None, fact_counts={k: len(facts.get(k, [])) for k in FACT_KEYS},
                               facts=fact_path.relative_to(output).as_posix())
                    if row['task'] == 'manifest': metadata[row['path']] = facts
                except UnicodeDecodeError:
                    row.update(status='invalid_encoding', reason='input_is_not_utf8')
                except TimeoutError:
                    row.update(status='worker_timeout', reason='per_file_time_budget')
                    if 'kind' in locals() and kind in workers: workers.pop(kind).close()
                except ChildProcessError:
                    row.update(status='worker_exit', reason='worker_terminated_without_result')
                    if 'kind' in locals() and kind in workers: workers.pop(kind).close()
                except OSError as error:
                    row.update(status='read_error', reason=type(error).__name__)
                except (RuntimeError, ValueError) as error:
                    row.update(status='extractor_error', reason=str(error).replace(str(output), '<output>').replace(str(ROOT), '<research>')[:500])
                processed += 1
                if processed % 25 == 0: checkpoint()
            report['status'] = 'partial' if any(r['eligible'] and r['status'] in {'pending', 'pending_budget', *RETRYABLE} for r in report['files']) else 'complete_with_diagnostics'
        finally:
            for worker in workers.values(): worker.close()
            stderr.close()
            attempt.update(processed=processed, elapsed_seconds=round(time.monotonic()-started, 3))
            report.setdefault('attempts', []).append(attempt)
            checkpoint()
        result = summary(report); result['status'] = report['status']; return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'output', 'typescript'): parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--revision', default='HEAD'); parser.add_argument('--policy', type=Path)
    parser.add_argument('--deployment', type=Path, help='Optional existing graph config containing deployment')
    parser.add_argument('--resume', action='store_true'); parser.add_argument('--retry-errors', action='store_true')
    parser.add_argument('--max-files', type=int); parser.add_argument('--seconds', type=float, default=900)
    parser.add_argument('--file-timeout', type=float, default=30)
    args = parser.parse_args()
    from scripts.build_project_snapshot import build_version
    result = run(args.source, args.revision, args.output, args.typescript,
        configuration=read(args.policy) if args.policy else None,
        deployment=read(args.deployment)['deployment'] if args.deployment else None,
        resume=args.resume, max_files=args.max_files, seconds=args.seconds, file_timeout=args.file_timeout,
        version=build_version(args.typescript.resolve()), retry_errors=args.retry_errors)
    print(json.dumps(result, ensure_ascii=False)); return 2 if result['status'] == 'partial' else 0


if __name__ == '__main__':
    raise SystemExit(main())
