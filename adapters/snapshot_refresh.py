"""Detect committed input changes, build privately, and publish complete snapshots.

The state file is the publication authority. A directory rename alone does not
publish a snapshot. Only this controller writes that state, under an OS lock;
builders write to a unique attempt directory and cannot replace the live graph.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import time
import traceback
import uuid

from adapters.snapshot_inputs import commit, export_inputs, normalize_config, select_inputs
from adapters.sqlite_fact_graph import validate_graph
from adapters.graph_document import read_graph


def now():
    return datetime.now(timezone.utc).isoformat()


def detached(value):
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def atomic_json(path, value):
    """Readers see either the complete old document or the complete new one."""
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.' + path.name + '-', suffix='.tmp', delete=False) as stream:
            name = stream.name
            json.dump(value, stream, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        # Windows readers can briefly deny delete sharing. Keep the old file
        # intact while retrying the same atomic replacement for at most 0.95 s.
        for attempt in range(10):
            try:
                os.replace(name, path)
                break
            except PermissionError as error:
                if getattr(error, 'winerror', None) not in {5, 32, 33} or attempt == 9:
                    raise
                time.sleep(0.01 * 2**min(attempt, 4))
        if os.name != 'nt':
            fd = os.open(path.parent, os.O_RDONLY)
            try: os.fsync(fd)
            finally: os.close(fd)
    finally:
        if name and os.path.exists(name): os.unlink(name)


class RefreshBusy(RuntimeError):
    pass


@contextmanager
def writer_lock(store):
    """Process death releases the lock; the lock file may remain forever."""
    store = Path(store); store.mkdir(parents=True, exist_ok=True)
    with (store/'.refresh.lock').open('a+b') as stream:
        stream.seek(0, os.SEEK_END)
        if not stream.tell(): stream.write(b'0'); stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RefreshBusy('Another refresh owns this store') from error
        try: yield
        finally:
            stream.seek(0)
            if os.name == 'nt': msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else: fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def read_json(path):
    """Allow short Windows delete-sharing conflicts during atomic publication."""
    for attempt in range(10):
        try:return json.loads(Path(path).read_text(encoding='utf-8'))
        except PermissionError as error:
            if getattr(error,'winerror',None) not in {5,32,33} or attempt==9:raise
            time.sleep(0.01 * 2**min(attempt,4))


def read_state(store):
    try: return read_json(Path(store)/'state.json')
    except FileNotFoundError: return None


def identity(record):
    return {key: record[key] for key in ['source_commit', 'config', 'build_version']}


def read_snapshot(store, snapshot_id=None):
    """Resolve a published version without following an unfinished directory."""
    store = Path(store).resolve(); state = read_state(store)
    if not state or not state['last_success']: raise LookupError('No successfully published snapshot')
    snapshot_id = snapshot_id or state['last_success']['id']
    if snapshot_id not in state['published']: raise LookupError('Snapshot was not published: ' + snapshot_id)
    if uuid.UUID(hex=snapshot_id).hex != snapshot_id: raise ValueError('Invalid snapshot directory ID')
    directory = store/'snapshots'/snapshot_id
    receipt = json.loads((directory/'receipt.json').read_text(encoding='utf-8'))
    if not (directory/'graph.json').is_file(): raise ValueError('Published graph is missing')
    if receipt['result']['storage'] == 'kuzu' and not (directory/'graph.kuzu').is_file():
        raise ValueError('Published Kuzu database is missing')
    current = snapshot_id == state['last_success']['id']
    return {'directory': str(directory), 'receipt': receipt, 'is_last_success': current,
            'freshness': ('current_at_observation' if current and state['status'] == 'up_to_date'
                          and identity(receipt) == state['target'] else 'historical_or_pending'),
            'observed_at': state.get('observed_at'), 'refresh_status': state['status'],
            'working_tree_included': False}


class Refresher:
    def __init__(self, source, store, config, version, builder, *, revision='HEAD', on_event=None):
        self.source = Path(source).resolve(); self.store = Path(store).resolve()
        if self.store.is_relative_to(self.source) or self.source.is_relative_to(self.store):
            raise ValueError('Snapshot store and source repository must be separate directories')
        self.config = config; self.version = version; self.builder = builder
        self.revision = revision; self.on_event = on_event or (lambda event: None)

    def observe(self):
        version = detached(self.version())
        if not isinstance(version, dict) or not version: raise ValueError('A builder version is required')
        return {'source_commit': commit(self.source, self.revision),
                'config': normalize_config(self.config()), 'build_version': version}

    def save(self, state):
        state['updated_at'] = now()
        atomic_json(self.store/'state.json', state)

    def event(self, kind, **fields):
        self.on_event({'event': kind, **fields})

    def failure(self, state, error, *, interrupted=False):
        attempt = state.get('current_attempt')
        info = {'type': type(error).__name__, 'message': str(error), 'at': now()}
        if attempt:
            atomic_json(self.store/'attempts'/(attempt['id']+'.json'),
                        {**attempt, 'outcome': 'interrupted' if interrupted else 'failed', 'error': info})
        state.update(status='interrupted' if interrupted else 'failed', current_attempt=None, last_error=info)
        self.save(state)
        self.event(state['status'], attempt_id=attempt['id'] if attempt else None, error=info)

    def validate(self, directory, request, result):
        graph = read_graph(directory/'graph.json')
        validate_graph(graph)
        expected = {key: request[key] for key in ['snapshot', 'source_commit', 'config', 'build_version']}
        if graph.get('version') != expected or graph['snapshot'] != request['snapshot']:
            raise ValueError('Graph version does not match build request')
        if graph.get('source_commit') != request['source_commit'] or graph.get('input_paths') != request['input_paths']:
            raise ValueError('Graph source or input scope does not match build request')
        if graph.get('provenance', {}).get('working_tree_included') is not False:
            raise ValueError('Only committed input exports can be published')
        for name, expected_count in [('nodes', len(graph['nodes'])), ('edges', len(graph['edges'])), ('files', len(request['input_paths']))]:
            if result.get(name) != expected_count: raise ValueError('Build result count mismatch: ' + name)
        if result.get('storage') != request['config']['storage']: raise ValueError('Storage mode mismatch')
        if request['config']['storage'] == 'kuzu':
            if not result.get('storage_roundtrip') or not (directory/'graph.kuzu').is_file():
                raise ValueError('Kuzu build has not completed its storage roundtrip')

    def run(self, *, max_builds=4):
        """Catch up to observed HEAD/config. Bound a busy repository's lock tenure."""
        if type(max_builds) is not int or max_builds < 1: raise ValueError('max_builds must be positive')
        with writer_lock(self.store):
            state = read_state(self.store) or {'schema_version': 1, 'source': str(self.source),
                'status': 'empty', 'target': None, 'last_success': None, 'current_attempt': None, 'published': []}
            if state['schema_version'] != 1 or state['source'] != str(self.source):
                raise ValueError('Store belongs to a different source or state schema')
            if state.get('current_attempt'):
                # Owning the OS lock proves that no previous controller still owns it.
                self.failure(state, RuntimeError('Previous controller stopped before publication'), interrupted=True)
            for _ in range(max_builds):
                try:
                    target = self.observe(); state['target'] = target; state['observed_at'] = now()
                    last = state['last_success']
                    if last and identity(last) == target:
                        # A missing artifact is an error, not an unchanged successful build.
                        directory = self.store/'snapshots'/last['id']
                        if not (directory/'receipt.json').is_file() or not (directory/'graph.json').is_file():
                            raise ValueError('Published snapshot artifacts are missing')
                        read_snapshot(self.store, last['id'])
                        state.update(status='up_to_date', last_error=None)
                        self.save(state); self.event('unchanged', snapshot_id=last['id'])
                        return state
                    uid = uuid.uuid4().hex
                    attempt = {'id': uid, 'snapshot': target['source_commit'] + ':full:' + uid,
                               **target, 'started_at': now(), 'phase': 'building'}
                    state.update(status='building', current_attempt=attempt, last_error=None)
                    self.save(state)
                    directory = self.store/'staging'/uid; directory.mkdir(parents=True, exist_ok=False)
                    self.event('building', attempt_id=uid, source_commit=target['source_commit'])
                    selection = select_inputs(self.source, target['source_commit'], target['config'])
                    atomic_json(directory/'selection.json', selection)
                    export_inputs(self.source, selection, directory/'source')
                    request = {**detached(target), 'snapshot': attempt['snapshot'],
                               'input_paths': [f['path'] for f in selection['files']], 'trigger': 'version_change_detection'}
                    atomic_json(directory/'request.json', request)
                    with (directory/'build.log').open('w', encoding='utf-8') as log:
                        try:
                            result = self.builder(directory/'source', request, directory, log)
                            self.validate(directory, request, result)
                        except BaseException:
                            traceback.print_exc(file=log); raise
                    # Config/HEAD can advance; changing executing rules invalidates this attempt.
                    if detached(self.version()) != target['build_version']:
                        raise ValueError('Builder version changed during extraction')
                    latest = self.observe(); observed = now()
                    if latest['build_version'] != target['build_version']:
                        raise ValueError('Builder version changed before publication')
                    receipt = {'id': uid, **target, 'snapshot': request['snapshot'], 'built_at': now(), 'result': result}
                    atomic_json(directory/'result.json', result); atomic_json(directory/'receipt.json', receipt)
                    attempt['phase'] = 'validated'; self.save(state)
                    destination = self.store/'snapshots'/uid; destination.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(directory, destination)
                    # Build the next state separately: a failed state write keeps the old pointer.
                    published = detached(state)
                    published.update(last_success=receipt, current_attempt=None, target=latest, observed_at=observed,
                                     status='up_to_date' if latest == target else 'pending', last_error=None)
                    published['published'].append(uid)
                    self.save(published); state = published
                except Exception as error:
                    self.failure(state, error)
                    return state
                except BaseException as error:
                    self.failure(state, error, interrupted=True)
                    raise
                self.event('published', snapshot_id=uid, source_commit=target['source_commit'], status=state['status'])
                if state['status'] == 'up_to_date': return state
            return state
