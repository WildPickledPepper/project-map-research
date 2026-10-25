"""Replay a TypeScript phase against an existing immutable source export."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('a3_probe', ROOT/'experiments/2026-10-24-a3/probe.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--phase', choices=['return', 'frontend'], required=True)
    for name in ['build', 'typescript', 'output']:
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    checkpoint = a.output/'input.json'
    previous = json.loads((a.build/'phase-input.json').read_text(encoding='utf-8'))
    if a.phase == 'frontend':
        protocol = json.loads((a.build/'protocol-checkpoint.json').read_text(encoding='utf-8'))
        previous = {'project_map_phase': 'frontend', 'api_symbols': sorted({e['source'] for e in protocol['edges'] if e['kind'] == 'EMITS_MESSAGE'})}
    checkpoint.write_text(json.dumps(previous)+'\n', encoding='utf-8')
    name = 'typescript_return_flow.cjs' if a.phase == 'return' else 'typescript_data_flow.cjs'
    command = ['node', str(ROOT/'adapters'/name), str((a.build/'source').resolve()),
               str((a.build/'input-manifest.json').resolve()), str(checkpoint.resolve()),
               str(a.typescript.resolve()), str((a.output/'facts.json').resolve())]
    result = probe.execute(command, a.output/'process.log', seconds=480, memory=4*1024**3)
    result.update(phase=a.phase, evidence_kind='executed_component_replay_not_full_rebuild',
                  research_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  working_tree_rules=bool(subprocess.check_output(['git', 'status', '--porcelain', '--', 'adapters'], cwd=ROOT)),
                  file_hash_verification='not_run_per_user_preference')
    (a.output/'result.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result), flush=True)
    raise SystemExit(0 if result['status'] == 'passed' else 1)
