"""Reconstruct a pinned real-source slice from a published manifest, without running it."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repo', required=True, type=Path)
parser.add_argument('--manifest', required=True, type=Path)
parser.add_argument('--out', required=True, type=Path)
args = parser.parse_args()
repo = args.repo.resolve()
out = args.out.resolve()
manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
expected_commit = manifest['repository']['commit']
head = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'],
                      text=True, capture_output=True, check=True).stdout.strip()
if head != expected_commit:
    raise SystemExit('Source HEAD differs from the manifest commit.')
status = subprocess.run(['git', '-C', str(repo), 'status', '--porcelain', '--untracked-files=no'],
                        text=True, capture_output=True, check=True)
if status.stdout.strip():
    raise SystemExit('Source has tracked changes; refusing to reproduce pinned input.')
if out.exists() or out.is_relative_to(repo) or repo.is_relative_to(out):
    raise SystemExit('Output must be a new directory outside the source checkout and its ancestors.')
files = []
seen = set()
for entry in manifest['files']:
    relative = PurePosixPath(entry['path'])
    if relative.is_absolute() or '..' in relative.parts or '\\' in entry['path'] or not relative.parts:
        raise SystemExit('Manifest contains a non-portable source path.')
    if entry['path'] in seen:
        raise SystemExit('Manifest contains duplicate paths.')
    seen.add(entry['path'])
    source = (repo / entry['path']).resolve()
    if not source.is_relative_to(repo) or not source.is_file():
        raise SystemExit('Manifest source is absent or leaves the checkout.')
    content = source.read_bytes()
    canonical = content.decode('utf-8').replace('\r\n', '\n').encode('utf-8')
    if hashlib.sha256(canonical).hexdigest() != entry['sha256_lf_utf8']:
        raise SystemExit(f'Content hash mismatch: {entry["path"]}')
    files.append((relative, content))
# Check all input before creating output. Keep original bytes on this machine;
# LF-normalized hashes make identity verification portable across Git CRLF settings.
out.mkdir(parents=True)
for relative, content in files:
    target = out / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
print(f'Prepared {len(files)} source files at commit {head}; no application code executed.')
