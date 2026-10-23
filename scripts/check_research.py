"""Validate portable research links and case records. No external dependencies."""
import json
from pathlib import Path, PurePosixPath
import re
import sys
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
errors = []
for path in ROOT.rglob('*.md'):
    if set(path.parts) & {'.git','node_modules','.venv','venv','artifacts','downloads'}:
        continue
    text = path.read_text(encoding='utf-8')
    for target in re.findall(r'(?<!!)\[[^\]]*\]\(([^)\s]+)\)', text):
        if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', target) or target.startswith('#'):
            continue
        target = unquote(target.split('#', 1)[0])
        resolved = (path.parent / target).resolve()
        if not resolved.is_relative_to(ROOT) or not resolved.exists():
            errors.append(f'{path.relative_to(ROOT)}: invalid local link {target}')
    if re.search(r'[A-Za-z]:[\\/](?:Users|workspace)[\\/]', text):
        errors.append(f'{path.relative_to(ROOT)}: machine-specific workspace path')

case = json.loads((ROOT/'cases/unit-flows/reference.json').read_text(encoding='utf-8'))
if not re.fullmatch(r'[0-9a-f]{40}', case['repository']['commit']):
    errors.append('case commit must be a full Git SHA')
if case.get('origin') != 'manual_source_audit_reference':
    errors.append('case must explicitly identify its manual source-audit origin')
anchors = case['anchors']
anchor_ids = [a['id'] for a in anchors]
if len(anchor_ids) != len(set(anchor_ids)):
    errors.append('duplicate anchor ids')
for a in anchors:
    path = PurePosixPath(a['path'])
    if path.is_absolute() or '..' in path.parts or '\\' in a['path']:
        errors.append(f'invalid repository-relative anchor path: {a["id"]}')
    if not isinstance(a['line'], int) or a['line'] < 1 or not a['marker'].strip():
        errors.append(f'invalid source anchor: {a["id"]}')
nodes = {n['id'] for n in case['nodes']}
if len(nodes) != len(case['nodes']):
    errors.append('duplicate node ids')
edge_ids = set()
for edge in case['reference_relations']:
    if edge['id'] in edge_ids:
        errors.append('duplicate relation ids')
    edge_ids.add(edge['id'])
    if edge['source'] not in nodes or edge['target'] not in nodes:
        errors.append(f'unknown endpoint: {edge["id"]}')
    if not edge['evidence'] or not set(edge['evidence']).issubset(anchor_ids):
        errors.append(f'missing source evidence: {edge["id"]}')
    if edge.get('status') != 'source_audited_reference':
        errors.append(f'relation is not labelled as a source-audited reference: {edge["id"]}')
if not case.get('unverified'):
    errors.append('case must expose unverified scope')
if errors:
    print('\n'.join(errors), file=sys.stderr)
    raise SystemExit(1)
print(f'OK: local Markdown links; {len(anchors)} source anchors; '
      f'{len(nodes)} reference nodes; {len(edge_ids)} reference relations.')
