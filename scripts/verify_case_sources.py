"""Verify pinned-checkout source anchors; this is not an automatic graph extractor."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repo', type=Path, required=True, help='Local MindStudio Insight checkout')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
case = json.loads((root/'cases/unit-flows/reference.json').read_text(encoding='utf-8'))
repo = args.repo.resolve()
proc = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'],
                      capture_output=True, text=True)
if proc.returncode or proc.stdout.strip() != case['repository']['commit']:
    raise SystemExit('Checkout HEAD differs from the fixed case commit or is not a Git checkout.')
status = subprocess.run(['git', '-C', str(repo), 'status', '--porcelain', '--untracked-files=no'],
                        capture_output=True, text=True)
if status.returncode or status.stdout.strip():
    raise SystemExit('Tracked checkout changes found; refusing to label these as pinned source evidence.')
errors = []
for anchor in case['anchors']:
    path = (repo/anchor['path']).resolve()
    if not path.is_relative_to(repo) or not path.is_file():
        errors.append(f'{anchor["id"]}: missing or invalid path')
        continue
    lines = path.read_text(encoding='utf-8').splitlines()
    line = anchor['line']
    if line > len(lines) or anchor['marker'] not in lines[line-1]:
        errors.append(f'{anchor["id"]}: marker absent at declared line {line}')
        continue
    print(f'OK {anchor["id"]}: {anchor["path"]}:{line}')
if errors:
    print('\n'.join(errors), file=sys.stderr)
    raise SystemExit(1)
print(f'Verified {len(case["anchors"])} anchors at {case["repository"]["commit"]}. '
      'This checks source locations, not semantic completeness or runtime behavior.')
