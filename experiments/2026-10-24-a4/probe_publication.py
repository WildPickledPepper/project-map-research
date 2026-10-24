"""Measure the existing refresh controller's validation on a complete full graph."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--worker', action='store_true')
    a = p.parse_args()
    if a.worker:
        from adapters.snapshot_refresh import Refresher
        request = json.loads((a.build/'request.json').read_text(encoding='utf-8'))
        result = json.loads((a.build/'result.json').read_text(encoding='utf-8'))
        controller = Refresher(a.source, a.output/'unused-store', lambda: {}, lambda: {}, None)
        started = time.perf_counter()
        controller.validate(a.build, request, result)
        print(json.dumps({'status': 'validated', 'seconds': round(time.perf_counter()-started, 4)}))
    else:
        spec = importlib.util.spec_from_file_location('a3_cost', ROOT/'experiments/2026-10-24-a3/probe.py')
        probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)
        a.output.mkdir(parents=True, exist_ok=False)
        command = [sys.executable, '-X', 'utf8', str(Path(__file__).resolve()), '--worker',
            '--build', str(a.build.resolve()), '--source', str(a.source.resolve()), '--output', str(a.output.resolve())]
        measured = probe.execute(command, a.output/'worker.log', seconds=180, memory=6*1024**3)
        result = {'evidence_kind': 'executed_full_graph_controller_publication_validation',
            'navigation_or_runtime_claim': False, 'build_version': json.loads((a.build/'request.json').read_text(encoding='utf-8'))['build_version'],
            'measured': measured, 'scope': 'controller validation only; no new extraction or publication was performed',
            'file_hash_verification': 'not_run_per_user_preference'}
        (a.output/'result.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(result))
