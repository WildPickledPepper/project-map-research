"""Launch an isolated real Insight server and browser; retain raw evidence outside Git."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = 'test/data/pytorch/text/level0/rank0_ascend_pt/ASCEND_PROFILER_OUTPUT/trace_view.json'


def available_backend_port(source):
    # The native argument parser restricts the server to its declared port range.
    parser = (source/'server/msinsight/src/base/ParamsParser.h').read_text(encoding='utf-8')
    limits = [int(re.search(r'\b' + name + r'\s*=\s*(\d+)\s*;', parser).group(1))
              for name in ('minPortNum', 'maxPortNum')]
    for port in range(limits[0], limits[1] + 1):
        with socket.socket() as sock:
            if os.name == 'nt': sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try: sock.bind(('127.0.0.1', port))
            except OSError: continue
            return port, limits
    raise RuntimeError('No available backend port in product range: ' + str(limits))


def run(source, output, scenario='boot', allow_stale_response=False):
    source = Path(source).resolve(); output = Path(output).resolve()
    if allow_stale_response:
        if scenario != 'late': raise ValueError('The controlled stale-response fault requires the late scenario')
        guard = (source/'modules/framework/src/centralServer/websocket/connection.ts').read_text(encoding='utf-8')
        if '__projectMapAllowStaleResponse' not in guard: raise ValueError('Prepare and rebuild the controlled fault source first')
    if output.is_relative_to(ROOT) or output.is_relative_to(source): raise ValueError('Keep probe outputs outside both repositories')
    executable = source/'server/output/win_mingw64/bin/profiler_server.exe'
    if not executable.is_file(): raise ValueError('Compile the Windows backend before the probe')
    for directory in ('modules/framework/build', 'modules/timeline/build'):
        if not (source/directory/'index.html').is_file(): raise ValueError('Build frontend: ' + directory)
    changes = subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain', '--untracked-files=no'], text=True)
    if changes: raise ValueError('Commit local source changes before recording a runtime input: ' + changes)
    revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    output.mkdir(parents=True, exist_ok=False)
    site = output/'site'; shutil.copytree(source/'modules/framework/build', site)
    shutil.copytree(source/'modules/timeline/build', site/'plugins/Timeline')
    data = output/'data/project-A/trace_view.json'; data.parent.mkdir(parents=True); shutil.copyfile(source/SAMPLE, data)
    if scenario == 'late':
        data_b = output/'data/project-B/trace_view.json'; data_b.parent.mkdir(parents=True); shutil.copyfile(source/SAMPLE, data_b)
    logs = output/'server-log'; logs.mkdir()
    backend_port, port_range = available_backend_port(source)
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    handler = partial(SimpleHTTPRequestHandler, directory=str(site))
    http = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
    command = [str(executable), '--logPath=' + str(logs), '--wsHost=127.0.0.1', '--wsPort=' + str(backend_port)]
    url = 'http://127.0.0.1:' + str(http.server_port) + '/?port=' + str(backend_port)
    source_changes = subprocess.check_output(['git', '-C', str(source), 'diff', '--name-only',
        'd4e8d1cf9f90208bcbe5371c127088f6fd66c688', 'HEAD'], text=True).splitlines()
    manifest = {'evidence_kind': 'executed_runtime_preparation', 'source_commit': revision, 'scenario': scenario,
                'fault_injection': {'allow_stale_response': allow_stale_response},
                'sample': SAMPLE, 'sample_bytes': data.stat().st_size,
                'product_source_changes': source_changes, 'listen_host': '127.0.0.1', 'frontend_port': http.server_port,
                'backend_port': backend_port, 'backend_port_range': port_range, 'strict_mode': True, 'browser': 'headless',
                'dataset_copy': 'data/project-A/trace_view.json',
                'additional_dataset_copies': ['data/project-B/trace_view.json'] if scenario == 'late' else [],
                'file_hash_verification': 'not_run_per_user_preference'}
    (output/'input.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    backend = None
    try:
        with (output/'server-stdout.log').open('w', encoding='utf-8') as server_log:
            backend = subprocess.Popen(command, cwd=executable.parent, stdout=server_log, stderr=subprocess.STDOUT, creationflags=flags)
            deadline = time.monotonic() + 30
            while True:
                if backend.poll() is not None:
                    raise RuntimeError(f'Backend stopped with exit code {backend.returncode}; inspect server-stdout.log')
                try:
                    with socket.create_connection(('127.0.0.1', backend_port), timeout=0.2): break
                except OSError:
                    if time.monotonic() >= deadline: raise TimeoutError('Backend did not start')
                    time.sleep(0.1)
            with (output/'browser.log').open('w', encoding='utf-8') as browser_log:
                browser = subprocess.Popen(['node', str(Path(__file__).with_name('boot_probe.cjs')), str(source), str(output), url, str(data), scenario,
                                            'allow-stale' if allow_stale_response else 'guard-active'],
                                           stdout=browser_log, stderr=subprocess.STDOUT, creationflags=flags)
                try: code = browser.wait(timeout=240)
                except subprocess.TimeoutExpired:
                    subprocess.run(['taskkill', '/PID', str(browser.pid), '/T', '/F'], stdout=subprocess.DEVNULL, creationflags=flags)
                    browser.wait(); raise
            if code: raise RuntimeError('Browser probe failed; inspect browser.log and boot-result.json')
    finally:
        http.shutdown(); http.server_close(); thread.join(timeout=5)
        if backend and backend.poll() is None:
            backend.terminate()
            try: backend.wait(timeout=10)
            except subprocess.TimeoutExpired: backend.kill(); backend.wait(timeout=10)
    print(json.dumps({'passed': True, 'source_commit': revision, 'scenario': scenario}))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'output'): ap.add_argument('--' + name, type=Path, required=True)
    ap.add_argument('--scenario', choices=('boot', 'normal', 'late'), default='boot')
    ap.add_argument('--allow-stale-response', action='store_true', help='Enable the controlled guard fault in a rebuilt experimental source')
    a = ap.parse_args(); run(a.source, a.output, a.scenario, a.allow_stale_response)
