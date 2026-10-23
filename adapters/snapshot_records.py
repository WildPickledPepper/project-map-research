"""Immutable records tied to published graphs, with explicit cross-version gaps.

This envelope preserves producer claims; it does not certify a run or contract.
Relocation yields candidates. Only the original snapshot supports direct overlay.
"""
import json
from pathlib import Path
import uuid

from adapters.snapshot_refresh import atomic_json, detached, now, read_snapshot


KINDS = {'trace', 'summary', 'verification', 'asset_anchor'}
BASIS_KEYS = ('id', 'snapshot', 'source_commit', 'config', 'build_version')
# Location and content hashes do not define identity. These fields are compared
# exactly, including parameter lists and interface scope. Matches remain candidates.
SELECTOR_KEYS = ('kind', 'path', 'name', 'parameters', 'signature', 'qualified_name',
                 'owner', 'scope', 'identity', 'command', 'command_fields',
                 'scope_values', 'scope_fields', 'service', 'module', 'transport', 'payload')


def basis_of(resolved):
    return detached({key: resolved['receipt'][key] for key in BASIS_KEYS})


def snapshot_basis(store, snapshot_id=None):
    """Capture this before producing a summary/run, then submit it unchanged."""
    return basis_of(read_snapshot(store, snapshot_id))


def _graph(resolved):
    graph = json.loads((Path(resolved['directory'])/'graph.json').read_text(encoding='utf-8'))
    expected = {k: resolved['receipt'][k] for k in BASIS_KEYS if k != 'id'}
    if graph.get('version') != expected:
        raise ValueError('Published graph does not match its receipt')
    return {n['id']: n for n in graph['nodes']}


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(field + ' must be a nonempty string')
    return value


def _uuid(value):
    if not isinstance(value, str) or uuid.UUID(hex=value).hex != value:
        raise ValueError('Expected a canonical record ID')
    return value


def _selector(node):
    return detached({key: node[key] for key in SELECTOR_KEYS if key in node})


def append_record(store, submission):
    """Append one producer-declared record; never infer its version from HEAD."""
    submission = detached(submission)
    if not isinstance(submission, dict) or set(submission) != {'kind', 'basis', 'provenance', 'payload', 'anchors'}:
        raise ValueError('Record requires kind, basis, provenance, payload and anchors')
    if submission['kind'] not in KINDS: raise ValueError('Unknown record kind')
    basis = submission['basis']
    if not isinstance(basis, dict) or set(basis) != set(BASIS_KEYS): raise ValueError('Complete producer basis is required')
    resolved = read_snapshot(store, _text(basis['id'], 'basis.id'))
    if basis != basis_of(resolved): raise ValueError('Producer basis differs from published snapshot')
    provenance = submission['provenance']
    if not isinstance(provenance, dict): raise ValueError('Provenance must be an object')
    for key in ('evidence_kind', 'source_ref'): _text(provenance.get(key), 'provenance.' + key)
    producer = provenance.get('producer')
    if not isinstance(producer, dict): raise ValueError('Producer name and version are required')
    for key in ('name', 'version'): _text(producer.get(key), 'producer.' + key)
    if not isinstance(submission['payload'], dict): raise ValueError('Payload must be an object')
    if not isinstance(submission['anchors'], list): raise ValueError('Anchors must be a list')
    nodes = _graph(resolved); anchors = []; labels = set()
    for anchor in submission['anchors']:
        if not isinstance(anchor, dict) or set(anchor) - {'label', 'node_id', 'reason'}:
            raise ValueError('Anchor accepts label, node_id and reason')
        label = _text(anchor.get('label'), 'anchor.label')
        if label in labels: raise ValueError('Duplicate anchor label: ' + label)
        labels.add(label)
        uid = anchor.get('node_id')
        if uid is not None: _text(uid, 'anchor.node_id')
        node = nodes.get(uid)
        if node is None:
            anchors.append({'label': label, 'node_id': uid, 'status': 'unmapped',
                            'reason': _text(anchor.get('reason'), 'unmapped anchor.reason')})
        else:
            anchors.append({'label': label, 'node_id': uid, 'status': 'mapped', 'selector': _selector(node),
                            'location': {k: node[k] for k in ('path', 'line', 'column') if k in node}})
    uid = uuid.uuid4().hex
    record = {**submission, 'schema_version': 1, 'id': uid, 'created_at': now(), 'anchors': anchors}
    # Private directories with no record.json are incomplete and never listed.
    directory = Path(store)/'records'/uid
    directory.mkdir(parents=True, exist_ok=False)
    atomic_json(directory/'record.json', record)
    return record


def _read(store, record_id):
    path = Path(store)/'records'/_uuid(record_id)/'record.json'
    record = json.loads(path.read_text(encoding='utf-8'))
    if record.get('schema_version') != 1 or record.get('id') != record_id:
        raise ValueError('Record schema or ID mismatch')
    origin = read_snapshot(store, record['basis']['id'])
    if record['basis'] != basis_of(origin): raise ValueError('Record basis differs from origin receipt')
    return record


def _project(record, resolved, nodes):
    requested = basis_of(resolved)
    differences = [k for k in BASIS_KEYS if record['basis'][k] != requested[k]]
    same = not differences
    anchors = []
    for original in record['anchors']:
        result = {'label': original['label'], 'original_node_id': original['node_id']}
        if original['status'] == 'unmapped':
            result.update(status='unmapped', reason=original['reason'], candidates=[])
        elif same:
            node = nodes.get(original['node_id'])
            if node is None or _selector(node) != original['selector']:
                raise ValueError('Original anchor no longer matches its immutable graph')
            result.update(status='mapped', candidates=[original['node_id']])
        else:
            candidates = [uid for uid, node in nodes.items() if _selector(node) == original['selector']]
            result.update(status=('candidate' if len(candidates) == 1 else 'ambiguous' if candidates else 'dangling'),
                          candidates=candidates, reason='cross_snapshot_exact_selector_only')
        anchors.append(result)
    return {'record': record, 'requested_basis': requested,
            'version_relation': 'same_snapshot' if same else 'different_snapshot',
            'version_differences': differences, 'eligible_for_direct_overlay': same,
            'requested_freshness': resolved['freshness'], 'observed_at': resolved['observed_at'],
            'anchors': anchors, 'applicability': 'not_evaluated',
            'verification_scope': 'original_recorded_snapshot_only',
            'verification_carried_forward': False}


def query_record(store, record_id, *, snapshot_id=None):
    """Compare with an explicit snapshot, or the last successful published graph."""
    record = _read(store, record_id)
    resolved = read_snapshot(store, snapshot_id)
    return _project(record, resolved, _graph(resolved))


def query_records(store, *, snapshot_id=None, kind=None, include_history=True):
    """One coherent target snapshot per query; records retain their original basis."""
    if kind is not None and kind not in KINDS: raise ValueError('Unknown record kind')
    resolved = read_snapshot(store, snapshot_id); nodes = _graph(resolved); items = []
    for path in sorted((Path(store)/'records').glob('*/record.json')):
        record = _read(store, path.parent.name)
        if kind is not None and record['kind'] != kind: continue
        if not include_history and record['basis']['id'] != resolved['receipt']['id']: continue
        items.append(_project(record, resolved, nodes))
    return {'requested_basis': basis_of(resolved), 'requested_freshness': resolved['freshness'],
            'observed_at': resolved['observed_at'], 'include_history': include_history,
            'kind': kind, 'count': len(items), 'truncated': False, 'items': items}
