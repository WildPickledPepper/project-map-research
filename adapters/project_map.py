"""A bounded, read-only navigation index over an existing source-fact snapshot.

The pm_fact node/edge schema is shared with the lossless SQLite fact store.
This derived index retains complete node/edge payloads; snapshot metadata is a
small navigation descriptor. The original JSON remains the extraction artifact.
"""
from collections import Counter, deque
from dataclasses import asdict, dataclass
import base64
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
import uuid
from functools import wraps
import sys

from adapters.sqlite_fact_graph import _SCHEMA, validate_graph
from adapters.snapshot_inputs import validate_path

SCHEMA = 'project-map/1'


def bounded_query(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        self._begin()
        try:
            return method(self, *args, **kwargs)
        except sqlite3.OperationalError as exc:
            if 'interrupted' not in str(exc):
                raise
            return self._finish(method.__name__, [], stop_reason='wall_time_budget', page_complete=False)
        finally:
            self.db.set_progress_handler(None, 0)
            self.deadline = None
    return call


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def build_index(graph, discovery, destination, *, navigation_version=None):
    """Build privately and atomically publish; source and graph must agree."""
    destination = Path(destination)
    if graph['source_commit'] != discovery['source_commit']:
        raise ValueError('Discovery and graph source versions differ')
    validate_graph(graph)
    files = discovery['files']
    paths = {r['path']: r for r in files}
    if len(paths) != len(files) or not set(graph['input_paths']) <= paths.keys():
        raise ValueError('Graph paths must belong to the discovered repository')
    if len(graph['input_paths']) != len(set(graph['input_paths'])):
        raise ValueError('Duplicate graph input')
    modules = discovery['modules']
    if set(r['module'] for r in files) != {m['path'] for m in modules}:
        raise ValueError('Discovery module ownership is inconsistent')
    destination.parent.mkdir(parents=True, exist_ok=True)
    private = destination.with_name(destination.name + '.' + uuid.uuid4().hex + '.building')
    started = time.monotonic()
    connection = sqlite3.connect(private)
    snapshot = graph['snapshot']
    coverage = {c['path']: c for c in graph['coverage']}
    try:
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA cache_size=-8192')
        connection.execute('PRAGMA temp_store=FILE')
        for sql in _SCHEMA:
            connection.execute(sql)
        connection.executescript('''
            CREATE TABLE pm_map_info (payload TEXT NOT NULL);
            CREATE TABLE pm_map_files (path TEXT PRIMARY KEY, module TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE INDEX pm_map_files_module ON pm_map_files(module,path);
            CREATE TABLE pm_map_modules (path TEXT UNIQUE, payload TEXT NOT NULL);
            CREATE TABLE pm_map_entries (node TEXT, name TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE INDEX pm_map_entries_name ON pm_map_entries(name);
            CREATE TABLE pm_map_providers (id TEXT UNIQUE, command TEXT, path TEXT, status TEXT, payload TEXT NOT NULL);
            CREATE TABLE pm_map_diagnostics (path TEXT, kind TEXT, scope TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE INDEX pm_map_diagnostics_path ON pm_map_diagnostics(path);
            CREATE INDEX pm_map_node_name ON pm_fact_nodes(snapshot,name,kind);
            CREATE INDEX pm_map_node_path ON pm_fact_nodes(snapshot,path,kind);
            CREATE INDEX pm_map_node_kind ON pm_fact_nodes(snapshot,kind);
            CREATE INDEX pm_map_edges_outgoing ON pm_fact_edges(snapshot,source,ordinal);
            CREATE INDEX pm_map_edges_incoming ON pm_fact_edges(snapshot,target,ordinal);
            CREATE TABLE pm_map_links (source TEXT,target TEXT,kind TEXT,status TEXT,edges INTEGER);
        ''')
        descriptor = {'schema': SCHEMA, 'source_commit': graph['source_commit'], 'snapshot': snapshot,
            'navigation_version': navigation_version or {'schema': SCHEMA},
            'navigation_runtime': {'python': sys.version.split()[0], 'sqlite': sqlite3.sqlite_version},
            'graph_version': graph.get('version'), 'counts': {'tracked_files': len(files),
                'input_files': len(graph['input_paths']), 'modules': len(modules),
                'nodes': len(graph['nodes']), 'edges': len(graph['edges'])},
            'coverage': dict(Counter(c['status'] for c in graph['coverage'])),
            'provenance': discovery.get('provenance'),
            'interpretation': 'source_relations_and_conditional_candidates',
            'runtime_execution': 'unknown_unless_linked_run',
            'assets': {'status': 'not_connected', 'dependency': 'P6'},
            'metadata_projection': 'navigation_descriptor_not_full_extraction_metadata'}
        connection.execute('INSERT INTO pm_fact_snapshots VALUES (?,?)', (snapshot, encoded(descriptor)))
        connection.executemany('INSERT INTO pm_fact_nodes VALUES (?,?,?,?,?,?,?)',
            ((snapshot, n['id'], n['kind'], n['path'], n['line'], n['name'], encoded(n)) for n in graph['nodes']))
        connection.executemany('INSERT INTO pm_fact_edges VALUES (?,?,?,?,?,?,?)',
            ((snapshot, i, e['source'], e['target'], e['kind'], e['status'], encoded(e))
             for i, e in enumerate(graph['edges'])))
        connection.executemany('INSERT INTO pm_map_files VALUES (?,?,?)',
            ((r['path'], r['module'], encoded({**r, 'graph_coverage': coverage.get(r['path']),
                'graph_input': r['path'] in coverage})) for r in files))
        connection.executemany('INSERT INTO pm_map_entries VALUES (?,?,?,?)',
            ((r.get('message'), r['name'], r['status'], encoded(r)) for r in graph.get('protocol', {}).get('results', [])))
        connection.executemany('INSERT INTO pm_map_providers VALUES (?,?,?,?,?)',
            ((r['id'], str(r.get('command', '')), r.get('path'), r.get('status'), encoded(r))
             for r in graph.get('protocol', {}).get('providers', [])))

        def diagnostics(value, scope=''):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in {'nodes', 'edges'} and not scope:
                        continue
                    location = scope + '/' + key
                    if key in {'diagnostics', 'limits'} and isinstance(child, list):
                        for item in child:
                            row = item if isinstance(item, dict) else {'kind': 'analysis_limit', 'description': item}
                            yield (row.get('path'), row.get('kind', 'diagnostic'), location, encoded(row))
                    elif isinstance(child, (dict, list)):
                        yield from diagnostics(child, location)
            elif isinstance(value, list):
                for i, child in enumerate(value):
                    if isinstance(child, (dict, list)):
                        yield from diagnostics(child, scope + '/' + str(i))

        connection.executemany('INSERT INTO pm_map_diagnostics VALUES (?,?,?,?)', diagnostics(graph))
        for module in modules:
            own = [r for r in files if r['module'] == module['path']]
            kinds = dict(connection.execute('''SELECT n.kind,count(*) FROM pm_fact_nodes n
                JOIN pm_map_files f ON n.path=f.path WHERE f.module=? GROUP BY n.kind''', (module['path'],)))
            item = {**module, 'graph_inputs': sum(r['path'] in coverage for r in own),
                'source_statuses': dict(Counter(coverage[r['path']]['status'] for r in own if r['path'] in coverage)),
                'inventory_statuses': dict(Counter(r['status'] for r in own)), 'node_kinds': kinds,
                'module_ownership': 'structural_nearest_manifest', 'semantic_completeness': 'not_established'}
            connection.execute('INSERT INTO pm_map_modules VALUES (?,?)', (module['path'], encoded(item)))
        connection.execute('''INSERT INTO pm_map_links SELECT fs.module,ft.module,e.kind,e.status,count(*)
            FROM pm_fact_edges e JOIN pm_fact_nodes s ON s.snapshot=e.snapshot AND s.id=e.source
            JOIN pm_fact_nodes t ON t.snapshot=e.snapshot AND t.id=e.target
            JOIN pm_map_files fs ON fs.path=s.path JOIN pm_map_files ft ON ft.path=t.path
            WHERE fs.module<>ft.module GROUP BY fs.module,ft.module,e.kind,e.status''')
        descriptor['counts'].update(entries=connection.execute('SELECT count(*) FROM pm_map_entries').fetchone()[0],
            diagnostic_records=connection.execute('SELECT count(*) FROM pm_map_diagnostics').fetchone()[0],
            providers=connection.execute('SELECT count(*) FROM pm_map_providers').fetchone()[0],
            module_relation_groups=connection.execute('SELECT count(*) FROM pm_map_links').fetchone()[0])
        descriptor['index_seconds'] = round(time.monotonic() - started, 4)
        connection.execute('INSERT INTO pm_map_info VALUES (?)', (encoded(descriptor),))
        connection.commit()
        connection.close()
        os.replace(private, destination)
    except BaseException:
        connection.close()
        private.unlink(missing_ok=True)
        raise
    return descriptor


@dataclass(frozen=True)
class Budget:
    seconds: float = 3
    nodes: int = 200
    edges: int = 500
    output_bytes: int = 131072

    def __post_init__(self):
        if not 0 < self.seconds <= 30 or not 1 <= self.nodes <= 5000 or not 1 <= self.edges <= 10000:
            raise ValueError('Use seconds in (0,30], nodes 1..5000, edges 1..10000')
        if not 4096 <= self.output_bytes <= 1048576:
            raise ValueError('Use output_bytes 4096..1048576')


class ProjectMap:
    """One snapshot, read-only SQLite, bounded results and graph exploration."""
    def __init__(self, index, *, budget=None, expected_snapshot=None):
        self.db = sqlite3.connect(Path(index).resolve().as_uri() + '?mode=ro', uri=True)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA query_only=ON')
        self.db.execute('PRAGMA cache_size=-8192')
        self.db.execute('PRAGMA temp_store=FILE')
        self.info = json.loads(self.db.execute('SELECT payload FROM pm_map_info').fetchone()[0])
        if self.info['schema'] != SCHEMA or expected_snapshot and self.info['snapshot'] != expected_snapshot:
            self.db.close()
            raise ValueError('Index schema/snapshot mismatch')
        self.budget = budget or Budget()
        self.deadline = None

    def close(self):
        self.db.close()

    def _begin(self):
        if self.deadline is not None:
            return
        self.started = time.perf_counter()
        self.deadline = self.started + self.budget.seconds
        self.db.set_progress_handler(lambda: int(time.perf_counter() >= self.deadline), 1000)

    def _finish(self, query, items, **extra):
        result = {'query': query, 'schema': SCHEMA, 'snapshot': self.info['snapshot'],
            'source_commit': self.info['source_commit'], 'graph_version': self.info['graph_version'],
            'navigation_version': self.info['navigation_version'],
            'evidence_kind': 'indexed_existing_source_facts', 'items': items,
            'budgets': {**asdict(self.budget), 'sqlite_cache_kib': 8192,
                'memory_policy': 'bounded_visits_and_output; SQLite cache is a target, not a process RSS cap'},
            'runtime_execution': 'unknown_unless_linked_run', 'missing_relation_meaning': 'unknown', **extra}
        result['elapsed_seconds'] = round(time.perf_counter() - self.started, 6)
        self.db.set_progress_handler(None, 0)
        return result

    def _cursor(self, spec, after):
        return base64.urlsafe_b64encode(encoded({'schema': SCHEMA, 'snapshot': self.info['snapshot'],
            'navigation_version': self.info['navigation_version'],
            'spec': spec, 'after': after}).encode()).decode()

    def _after(self, cursor, spec):
        if not cursor:
            return 0
        try:
            if len(cursor) > 16384:
                raise ValueError()
            value = json.loads(base64.urlsafe_b64decode(cursor))
            if value['schema'] != SCHEMA or value['snapshot'] != self.info['snapshot'] or value['spec'] != spec:
                raise ValueError()
            if value['navigation_version'] != self.info['navigation_version']:
                raise ValueError()
            if type(value['after']) is not int or value['after'] < 0:
                raise ValueError()
            return value['after']
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError('Cursor must belong to this snapshot and exact query') from exc

    def _page(self, query, sql, params=(), *, spec=None, limit=30, cursor=None, convert=None):
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError('Use limit 1..200')
        self._begin()
        spec = {'query': query, **(spec or {})}
        after = self._after(cursor, spec)
        items, last, more, reason = [], after, False, None
        used = 2500  # Envelope and cursor reserve; checked again before returning.
        try:
            rows = self.db.execute(sql, (*params, after, limit + 1))
            for row in rows:
                if time.perf_counter() >= self.deadline:
                    more, reason = True, 'wall_time_budget'
                    break
                if len(items) >= limit:
                    more = True
                    break
                item = convert(row) if convert else dict(row)
                size = len(encoded(item).encode())
                if not items and used + size > self.budget.output_bytes:
                    item = {'status': 'item_exceeds_output_budget', 'encoded_bytes': size,
                        'sequence': row['seq'], 'action': 'raise output budget or narrow the detail pointer'}
                    size = len(encoded(item).encode())
                if used + size > self.budget.output_bytes:
                    more, reason = True, 'output_budget'
                    break
                items.append(item)
                used += size
                last = row['seq']
        except sqlite3.OperationalError as exc:
            if 'interrupted' not in str(exc):
                raise
            more, reason = True, 'wall_time_budget'
        result = self._finish(query, items, next_cursor=self._cursor(spec, last) if more else None,
            page_complete=not more, stop_reason=reason, pagination='snapshot_bound_keyset')
        # Very large user-controlled filters/cursors must not bypass the output limit.
        if len(encoded(result).encode()) > self.budget.output_bytes:
            raise ValueError('Query envelope exceeds output budget; shorten selectors or raise output budget')
        return result

    @bounded_query
    def overview(self, **page):
        result = self._page('overview', 'SELECT rowid seq,payload FROM pm_map_modules WHERE rowid>? ORDER BY rowid LIMIT ?',
            convert=lambda r: json.loads(r['payload']), **page)
        result['repository'] = {k: v for k, v in self.info.items()
            if k not in {'graph_version', 'navigation_version', 'snapshot', 'source_commit', 'schema'}}
        return self._bounded(result)

    def _bounded(self, result):
        if len(encoded(result).encode()) > self.budget.output_bytes:
            raise ValueError('Response exceeds output budget; reduce page size or raise output budget')
        return result

    @bounded_query
    def links(self, module=None, **page):
        where = 'source=? OR target=?' if module else '1'
        return self._page('module_links', f'''SELECT rowid seq,* FROM pm_map_links
            WHERE ({where}) AND rowid>? ORDER BY rowid LIMIT ?''', (module, module) if module else (),
            spec={'module': module}, **page)

    @bounded_query
    def files(self, module=None, **page):
        return self._page('files', '''SELECT rowid seq,payload FROM pm_map_files
            WHERE (? IS NULL OR module=?) AND rowid>? ORDER BY rowid LIMIT ?''', (module, module),
            spec={'module': module}, convert=lambda r: json.loads(r['payload']), **page)

    @staticmethod
    def _node(row):
        return {k: row[k] for k in ('id', 'kind', 'name', 'path', 'line')}

    @bounded_query
    def search(self, text='', kind=None, module=None, **page):
        return self._page('search', '''SELECT n.rowid seq,n.id,n.kind,n.name,n.path,n.line FROM pm_fact_nodes n
            LEFT JOIN pm_map_files f ON n.path=f.path WHERE n.snapshot=? AND
            (? IS NULL OR n.kind=?) AND (? IS NULL OR f.module=?) AND
            (instr(lower(n.name),lower(?))>0 OR instr(lower(n.path),lower(?))>0)
            AND n.rowid>? ORDER BY n.rowid LIMIT ?''', (self.info['snapshot'], kind, kind, module, module, text, text),
            spec={'text': text, 'kind': kind, 'module': module}, convert=self._node, **page)

    @bounded_query
    def entries(self, name=None, **page):
        return self._page('entries', '''SELECT rowid seq,node,name,status,json_array_length(payload,'$.matches') matches,
            json_array_length(payload,'$.unknown_identities') unknown_identities FROM pm_map_entries
            WHERE (? IS NULL OR name=?) AND rowid>? ORDER BY rowid LIMIT ?''', (name, name), spec={'name': name},
            convert=lambda r: {**dict(r), 'detail': {'entity': 'entry', 'id': r['seq']}}, **page)

    @bounded_query
    def providers(self, text='', **page):
        return self._page('providers', '''SELECT rowid seq,id,command,path,status FROM pm_map_providers
            WHERE instr(lower(command),lower(?))>0 AND rowid>? ORDER BY rowid LIMIT ?''', (text,), spec={'text': text},
            convert=lambda r: {**dict(r), 'detail': {'entity': 'provider', 'id': r['id']}}, **page)

    @bounded_query
    def diagnostics(self, path=None, **page):
        return self._page('diagnostics', '''SELECT rowid seq,path,kind,scope,
            CASE WHEN length(CAST(payload AS BLOB))<1024 THEN payload END payload FROM pm_map_diagnostics
            WHERE (? IS NULL OR path=?) AND rowid>? ORDER BY rowid LIMIT ?''', (path, path), spec={'path': path},
            convert=lambda r: {'id': r['seq'], 'path': r['path'], 'kind': r['kind'], 'scope': r['scope'],
                'summary': json.loads(r['payload']) if r['payload'] else None,
                'detail': {'entity': 'diagnostic', 'id': r['seq']}}, **page)

    def resolve(self, selector):
        if not isinstance(selector, str) or not selector:
            raise ValueError('Supply --start with an exact node ID or unique callable/entry name')
        row = self.db.execute('SELECT id FROM pm_fact_nodes WHERE snapshot=? AND id=?',
            (self.info['snapshot'], selector)).fetchone()
        if row:
            return row['id']
        rows = self.db.execute('''SELECT id,json_extract(payload,'$.definition') defined FROM pm_fact_nodes
            WHERE snapshot=? AND name=? AND kind='callable'
            ORDER BY coalesce(json_extract(payload,'$.definition'),0) DESC LIMIT 2''', (self.info['snapshot'], selector)).fetchall()
        defined = [r for r in rows if r['defined']]
        rows = defined or rows
        if not rows:
            rows = self.db.execute('SELECT DISTINCT node id FROM pm_map_entries WHERE name=? AND node IS NOT NULL LIMIT 2', (selector,)).fetchall()
        if len(rows) != 1:
            raise ValueError('Use a node ID from search/entries for absent or ambiguous name: ' + selector)
        return rows[0]['id']

    @bounded_query
    def status(self, selector):
        self._begin()
        uid = self.resolve(selector)
        node = self.db.execute('''SELECT id,kind,name,path,line,json_extract(payload,'$.resolution') resolution,
            json_extract(payload,'$.status') local_status FROM pm_fact_nodes WHERE snapshot=? AND id=?''',
            (self.info['snapshot'], uid)).fetchone()
        file = self.db.execute('SELECT payload FROM pm_map_files WHERE path=?', (node['path'],)).fetchone()
        degrees = {}
        for direction, column in [('outgoing', 'source'), ('incoming', 'target')]:
            degrees[direction] = [dict(r) for r in self.db.execute(f'''SELECT kind,status,count(*) count FROM pm_fact_edges
                WHERE snapshot=? AND {column}=? GROUP BY kind,status''', (self.info['snapshot'], uid))]
        diagnostic_count = self.db.execute('SELECT count(*) FROM pm_map_diagnostics WHERE path=?', (node['path'],)).fetchone()[0]
        result = self._finish('status', [{**self._node(node), 'resolution': node['resolution'], 'local_status': node['local_status']}],
            file=json.loads(file[0]) if file else None,
            relations=degrees, diagnostics={'path': node['path'], 'query': 'diagnostics', 'records': diagnostic_count,
                'also_check_global': True},
            interpretation='local_resolution_flags_and_candidate_edges_must_be_read_together')
        return self._bounded(result)

    @bounded_query
    def neighbors(self, selector, direction='out', kinds=None, **page):
        if direction not in {'out', 'in'}:
            raise ValueError('Direction must be out or in')
        self._begin()
        uid = self.resolve(selector)
        column, other = ('source', 'target') if direction == 'out' else ('target', 'source')
        kinds = sorted(set(kinds or []))
        filter_sql = ' AND e.kind IN (' + ','.join('?' for _ in kinds) + ')' if kinds else ''
        return self._page('neighbors', f'''SELECT e.ordinal+1 seq,e.ordinal,e.source,e.target,e.kind,e.status,
            n.id,n.name,n.path,n.line,n.kind node_kind,
            json_array_length(e.payload,'$.evidence') evidence_count,
            json_array_length(e.payload,'$.conditions') condition_count FROM pm_fact_edges e
            JOIN pm_fact_nodes n ON n.snapshot=e.snapshot AND n.id=e.{other}
            WHERE e.snapshot=? AND e.{column}=? {filter_sql} AND e.ordinal+1>? ORDER BY e.ordinal LIMIT ?''',
            (self.info['snapshot'], uid, *kinds), spec={'node': uid, 'direction': direction, 'kinds': kinds},
            convert=lambda r: {'edge_id': r['ordinal'], 'source': r['source'], 'target': r['target'],
                'kind': r['kind'], 'status': r['status'], 'evidence_count': r['evidence_count'],
                'condition_count': r['condition_count'], 'node': {'id': r['id'], 'kind': r['node_kind'],
                    'name': r['name'], 'path': r['path'], 'line': r['line']},
                'detail': {'entity': 'edge', 'id': r['ordinal']}}, **page)

    @bounded_query
    def walk(self, selector, *, direction='out', depth=4, target=None, kinds=None):
        if direction not in {'out', 'in'} or type(depth) is not int or not 0 <= depth <= 64:
            raise ValueError('Use direction out/in and depth 0..64')
        self._begin()
        start = self.resolve(selector)
        goal = self.resolve(target) if target else None
        column, other = ('source', 'target') if direction == 'out' else ('target', 'source')
        kinds = sorted(set(kinds or []))
        filter_sql = ' AND kind IN (' + ','.join('?' for _ in kinds) + ')' if kinds else ''
        queue, seen, parents, edges = deque([(start, 0)]), {start}, {}, []
        examined, reason, depth_cut, found = 0, None, False, start == goal
        try:
            while queue and not found:
                if time.perf_counter() >= self.deadline:
                    reason = 'wall_time_budget'
                    break
                uid, level = queue.popleft()
                if level == depth:
                    # A depth boundary is scope, even when a subsequent query finds a leaf.
                    depth_cut = True
                    continue
                rows = self.db.execute(f'''SELECT ordinal,source,target,kind,status FROM pm_fact_edges
                    WHERE snapshot=? AND {column}=? {filter_sql} ORDER BY ordinal LIMIT ?''',
                    (self.info['snapshot'], uid, *kinds, self.budget.edges - examined + 1))
                for row in rows:
                    if examined == self.budget.edges:
                        reason = 'edge_budget'
                        break
                    examined += 1
                    nxt = row[other]
                    if nxt not in seen:
                        if len(seen) == self.budget.nodes:
                            reason = 'node_budget'
                            break
                        seen.add(nxt)
                        parents[nxt] = (uid, dict(row))
                        queue.append((nxt, level + 1))
                    edges.append(dict(row))
                    if nxt == goal:
                        found = True
                        break
                if reason:
                    break
        except sqlite3.OperationalError as exc:
            if 'interrupted' not in str(exc):
                raise
            reason = 'wall_time_budget'
        if goal and found:
            edges, current = [], goal
            while current != start:
                current, edge = parents[current]
                edges.append(edge)
            edges.reverse()
        shown, used = [], 3000
        for edge in edges:
            edge['detail'] = {'entity': 'edge', 'id': edge['ordinal']}
            size = len(encoded(edge).encode())
            if used + size > self.budget.output_bytes:
                break
            shown.append(edge)
            used += size
        result = self._finish('path' if goal else 'walk', shown, start=start, target=goal, direction=direction,
            kinds=kinds or 'all_indexed_relation_kinds', depth=depth, visited_nodes=len(seen), examined_edges=examined,
            stop_reason=reason, depth_scope_reached=depth_cut,
            found=found if goal else None, display_truncated=len(shown) != len(edges),
            search_status='found' if found else 'budget_stopped' if reason else 'depth_scoped' if depth_cut else 'exhausted_indexed_relations',
            continue_with={'query': 'neighbors', 'direction': direction, 'note': 'page each selected node to expand further'})
        return self._bounded(result)

    @bounded_query
    def detail(self, entity, uid, pointer='', **page):
        """Page JSON children without loading a large parent payload into Python."""
        locations = {'node': ('pm_fact_nodes', 'id'), 'edge': ('pm_fact_edges', 'ordinal'),
            'provider': ('pm_map_providers', 'id'),
            'entry': ('pm_map_entries', 'rowid'), 'diagnostic': ('pm_map_diagnostics', 'rowid')}
        if entity not in locations:
            raise ValueError('Use node/edge/entry/provider/diagnostic')
        table, key = locations[entity]
        if pointer and not pointer.startswith('/'):
            raise ValueError('Use a JSON pointer beginning with /')
        parts = [p.replace('~1', '/').replace('~0', '~') for p in pointer.split('/')[1:]] if pointer else []
        path = '$'
        for part in parts:
            parent = self.db.execute(f'SELECT json_type(payload,?) FROM {table} WHERE {key}=?', (path, uid)).fetchone()
            is_array = parent and parent[0] == 'array'
            if is_array and not part.isdigit():
                raise ValueError('Array pointer requires a nonnegative index')
            path += '[' + part + ']' if is_array else '.' + json.dumps(part)
        allowance = (self.budget.output_bytes - 2500) // 2
        def convert(row):
            value = row['value']
            if row['type'] in {'object', 'array'} and value is not None:
                value = json.loads(value)
            elif row['type'] in {'true', 'false'}:
                value = row['type'] == 'true'
            token = str(row['key']).replace('~', '~0').replace('/', '~1')
            child_pointer = pointer + '/' + token if row['key'] is not None else pointer
            return {'key': row['key'], 'type': row['type'], 'value': value,
                'value_truncated': row['large'] == 1, 'pointer': child_pointer,
                'detail': {'entity': entity, 'id': uid, 'pointer': child_pointer}}
        return self._page('detail', f'''SELECT j.id+1 seq,j.key,j.type,
            CASE WHEN length(CAST(j.value AS BLOB))<=? OR j.value IS NULL THEN j.value END value,
            CASE WHEN length(CAST(j.value AS BLOB))>? THEN 1 ELSE 0 END large
            FROM {table} t,json_each(t.payload,?) j WHERE t.{key}=? AND j.id+1>? ORDER BY j.id LIMIT ?''',
            (allowance, allowance, path, uid), spec={'entity': entity, 'id': str(uid), 'pointer': pointer},
            convert=convert, **page)

    @bounded_query
    def source(self, source, *, selector=None, path=None, line=None, context=8):
        self._begin()
        if source is None:
            raise ValueError('Source navigation requires a Git checkout via --source')
        if selector:
            uid = self.resolve(selector)
            row = self.db.execute('SELECT path,line FROM pm_fact_nodes WHERE snapshot=? AND id=?',
                (self.info['snapshot'], uid)).fetchone()
            path, line = row['path'], line or row['line']
        validate_path(path)
        if type(context) is not int or not 0 <= context <= 40 or type(line) is not int or line < 1:
            raise ValueError('Use source line >=1 and context 0..40')
        row = self.db.execute('SELECT payload FROM pm_map_files WHERE path=?', (path,)).fetchone()
        if not row:
            raise ValueError('Source path is not tracked in this snapshot')
        info = json.loads(row[0])
        if info.get('bytes') is None or info['bytes'] > 2 * 1024 * 1024:
            raise ValueError('Source file exceeds 2 MiB navigation budget')
        revision = self.info['source_commit']
        remaining = self.deadline - time.perf_counter()
        try:
            data = subprocess.run(['git', '-C', str(source), 'cat-file', 'blob', revision + ':' + path],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=max(0.001, remaining)).stdout
        except subprocess.TimeoutExpired:
            return self._finish('source', [], stop_reason='wall_time_budget')
        if len(data) > 2 * 1024 * 1024:
            raise ValueError('Source blob exceeds navigation budget')
        lines = data.decode('utf-8', errors='replace').splitlines()
        start, end = max(1, line - context), min(len(lines), line + context)
        items, used = [], 2500
        for number in range(start, end + 1):
            item = {'line': number, 'text': lines[number - 1]}
            if used + len(encoded(item).encode()) > self.budget.output_bytes:
                break
            items.append(item)
            used += len(encoded(item).encode())
        return self._bounded(self._finish('source', items, path=path, requested_line=line,
            source_kind='git_committed_blob', working_tree_read=False, decode='UTF-8 with replacement',
            display_truncated=len(items) != max(0, end - start + 1)))
