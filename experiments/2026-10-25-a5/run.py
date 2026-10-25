"""Run the real loopback Insight backend and a scenario browser against copied public inputs."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import copy
import os
from pathlib import Path
import shutil
import pickle
import socket
import subprocess
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0,str(ROOT))
from adapters.snapshot_refresh import writer_lock
spec = importlib.util.spec_from_file_location('p5_boot', HERE.parent/'2026-10-24-p5/run_boot_probe.py')
boot = importlib.util.module_from_spec(spec); spec.loader.exec_module(boot)
spec = importlib.util.spec_from_file_location('a5_oracle', HERE/'oracle.py')
oracle = importlib.util.module_from_spec(spec); spec.loader.exec_module(oracle)
spec = importlib.util.spec_from_file_location('process_metrics', HERE.parent/'2026-10-24-a2/probe_full_build.py')
metrics = importlib.util.module_from_spec(spec); spec.loader.exec_module(metrics)


class Site(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
        super().end_headers()

    def log_message(self, *args):
        pass


def run(a):
    source, output = a.source.resolve(), a.output.resolve()
    if output.is_relative_to(ROOT) or output.is_relative_to(source): raise ValueError('Raw outputs must remain external')
    git = lambda *args: subprocess.check_output(['git', '-C', str(source), *args], text=True).strip()
    if not git('remote', 'get-url', '--push', 'origin').startswith('disabled://'): raise ValueError('Requires isolated source')
    if git('status', '--porcelain', '--untracked-files=no'): raise ValueError('Commit capture source before running')
    output.mkdir(parents=True, exist_ok=False)
    site = output/'site'; shutil.copytree(source/'modules/framework/build', site)
    for module, plugin in [('timeline', 'Timeline'), ('cluster', 'Cluster'), ('leaks', 'Leaks')]:
        shutil.copytree(source/'modules'/module/'build', site/'plugins'/plugin)
    data = output/'data'; data.mkdir()
    fixture_root = source/'server/src/test/test_data'
    if a.scenario.startswith('communication'):
        sample = data/'cluster-project'; sample.mkdir()
        shutil.copytree(fixture_root/'cluster_analysis_output', sample/'cluster_analysis_output', ignore=shutil.ignore_patterns('*.db', '*.db-*'))
    elif a.scenario.startswith('memscope'):
        sample = data/'leaks_dump_20250806.db'; shutil.copyfile(fixture_root/'full_db/leaks_dump_20250806.dat', sample)
    else:
        sample = data/'snapshot_expandable.pkl'; shutil.copyfile(fixture_root/'snapshot'/sample.name, sample)
        if a.scenario == 'snapshot-replacement':
            with sample.open('rb') as stream: fixture = oracle.primitive.PrimitiveSnapshot(stream).load()
            shift = 1 << 45
            fixture['device_traces'][1] = copy.deepcopy(fixture['device_traces'][0])
            for event in fixture['device_traces'][1]:
                if 'addr' in event: event['addr'] += shift
            additions = []
            for segment in fixture['segments']:
                if segment['device'] != 0: continue
                new = copy.deepcopy(segment); new['device'] = 1; new['address'] += shift
                for block in new['blocks']: block['address'] += shift
                additions.append(new)
            fixture['segments'].extend(additions)
            with sample.open('wb') as stream: pickle.dump(fixture, stream, protocol=4)
    expected = oracle.expectations(source, sample if a.scenario.startswith('snapshot') else None)
    (output/'expected.json').write_text(json.dumps(expected, indent=2)+'\n', encoding='utf-8')
    logs = output/'server-log'; logs.mkdir()
    port, limits = boot.available_backend_port(source)
    http = ThreadingHTTPServer(('127.0.0.1', 0), partial(Site, directory=str(site)))
    thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    executable = source/'server/output/win_mingw64/bin/profiler_server.exe'
    manifest = {'evidence_kind': 'real_Insight_runtime', 'source_commit': git('rev-parse', 'HEAD'),
        'scenario': a.scenario, 'page_size': a.page_size, 'fault_drop_block': a.fault_drop_block,
        'site_headers': {'COOP': 'same-origin', 'COEP': 'require-corp'}, 'ports': [port, http.server_port],
        'file_hash_verification': 'not_run_per_user_preference'}
    (output/'input.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    backend = None
    try:
        with (output/'backend.log').open('w', encoding='utf-8') as log:
            backend = subprocess.Popen([str(executable), '--logPath='+str(logs), '--wsHost=127.0.0.1', '--wsPort='+str(port)],
                cwd=output, stdout=log, stderr=subprocess.STDOUT, creationflags=flags,
                env=dict(os.environ, PATH=str(executable.parent)+os.pathsep+os.environ['PATH']))
            deadline = time.monotonic()+30
            while True:
                if backend.poll() is not None: raise RuntimeError('Backend exited; inspect backend.log')
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=.2): break
                except OSError:
                    if time.monotonic() > deadline: raise TimeoutError('Backend startup')
                    time.sleep(.1)
            with (output/'browser.log').open('w', encoding='utf-8') as browser_log:
                browser_process = subprocess.Popen(['node', str(HERE/'browser.cjs'), str(source), str(output),
                    f'http://127.0.0.1:{http.server_port}/?port={port}', str(sample), a.scenario,
                    str(a.page_size), 'fault' if a.fault_drop_block else 'normal'],
                    stdout=browser_log, stderr=subprocess.STDOUT, creationflags=flags)
                measurements=[]; deadline=time.monotonic()+300
                while browser_process.poll() is None:
                    measurements.append({'seconds':round(300-(deadline-time.monotonic()),3),
                        'backend_working_set':metrics.working_set(backend.pid),
                        'browser_process_tree_working_set':metrics.tree_working_set(browser_process.pid)})
                    if time.monotonic()>deadline:
                        subprocess.run(['taskkill','/PID',str(browser_process.pid),'/T','/F'],capture_output=True)
                        browser_process.wait(); raise TimeoutError('Browser scenario wall budget')
                    try:browser_process.wait(timeout=.5)
                    except subprocess.TimeoutExpired:pass
                (output/'process-metrics.json').write_text(json.dumps({'samples':measurements,
                    'method':'sampled Windows working sets; browser tree includes Node driver; shared pages can be counted more than once'},indent=2)+'\n',encoding='utf-8')
            if browser_process.returncode: raise RuntimeError('Browser scenario failed; inspect result.json and browser.log')
    finally:
        http.shutdown(); http.server_close(); thread.join(5)
        if backend and backend.poll() is None:
            backend.terminate()
            try: backend.wait(10)
            except subprocess.TimeoutExpired: backend.kill(); backend.wait(10)
        events = []
        for log in logs.rglob('*.log'):
            for line in log.read_text(encoding='utf-8', errors='replace').splitlines():
                if 'PROJECT_MAP_EVENT ' in line:
                    try: events.append(json.loads(line.split('PROJECT_MAP_EVENT ', 1)[1]))
                    except json.JSONDecodeError: pass
        (output/'native-events.json').write_text(json.dumps(events, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'scenario': a.scenario, 'source_commit': manifest['source_commit']}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--scenario', required=True); p.add_argument('--page-size', type=int, default=1000)
    p.add_argument('--fault-drop-block', action='store_true')
    a=p.parse_args()
    # The native server can select another port when a concurrent launch wins the bind.
    # Serialize launches from this driver so a browser cannot attach to another run.
    with writer_lock(a.source.resolve().parent/'a5-runtime-lock'):
        run(a)
