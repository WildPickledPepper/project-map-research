"""Measure fresh query processes and index building; raw output stays outside Git."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('a2_probe', ROOT / 'experiments/2026-10-24-a2/probe_full_build.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def execute(command, output, seconds=120, memory=4 * 1024**3):
    started, peak, reason = time.perf_counter(), 0, None
    with output.open('w', encoding='utf-8') as stream:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        while process.poll() is None:
            peak = max(peak, probe.tree_working_set(process.pid) or 0)
            if time.perf_counter() - started > seconds: reason = 'wall_time_budget'
            if peak > memory: reason = 'process_tree_working_set_budget'
            if reason:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                else:
                    process.kill()
                process.wait()
                break
            try: process.wait(timeout=0.01)
            except subprocess.TimeoutExpired: pass
    return {'elapsed_seconds': round(time.perf_counter() - started, 4), 'exit_code': process.returncode,
        'status': 'budget_stopped' if reason else 'passed' if process.returncode == 0 else 'failed',
        'stop_reason': reason, 'peak_tree_working_set_bytes_observed': peak,
        'output_bytes': output.stat().st_size, 'process_budgets': {'seconds': seconds, 'working_set_bytes': memory}}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('graph', 'source', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    index = a.output / 'map.sqlite'
    base = [sys.executable, '-X', 'utf8', str(ROOT / 'scripts/project_map.py')]
    build = execute(base + ['build', '--graph', str(a.graph.resolve()), '--source', str(a.source.resolve()),
        '--output', str(index.resolve())], a.output / 'build.json')
    results = {}
    if build['status'] == 'passed':
        for name, args in [('overview', ['overview', '--limit', '10']),
            ('entries', ['entries', '--name', 'getUnitFlows']),
            ('search', ['search', '--text', 'CurveContainer', '--kind', 'storage_member', '--limit', '10']),
            ('trace', ['trace', '--start', 'getUnitFlows', '--depth', '4']),
            ('reverse', ['impact', '--start', 'getUnitFlows', '--depth', '4']),
            ('source', ['source', '--source', str(a.source.resolve()), '--start', 'getUnitFlows', '--context', '3']),
            ('diagnostics', ['diagnostics', '--limit', '10'])]:
            results[name] = execute(base + ['query', '--index', str(index.resolve()), *args], a.output / (name + '.json'),
                seconds=10, memory=256 * 1024**2)
    result = {'evidence_kind': 'executed_fresh_navigation_processes', 'build': build, 'queries': results,
        'index_bytes': index.stat().st_size if index.exists() else None,
        'memory_measurement': 'sampled sum of Windows process-tree working sets including Python redirector; shared pages may count twice',
        'cold_definition': 'new Python process for every query; operating-system file cache not flushed',
        'file_hash_verification': 'not_run_per_user_preference'}
    (a.output / 'cost.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))
