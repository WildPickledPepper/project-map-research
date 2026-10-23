"""Store structured facts beside an existing SQLite graph, without changing it.

Only ``pm_fact_*`` tables/indexes are owned here. Node IDs are scoped to a
snapshot; edge ordinals preserve parallel edges and their complete payloads.
Both public operations leave successful writes uncommitted. The caller must
commit/rollback, and must enable foreign_keys before starting its own transaction.
These functions persist supplied facts; they do not infer code relationships.
"""

from contextlib import contextmanager
import json
import sqlite3
import uuid


_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS pm_fact_snapshots (
        snapshot TEXT PRIMARY KEY,
        payload TEXT NOT NULL CHECK(json_valid(payload))
    )""",
    """CREATE TABLE IF NOT EXISTS pm_fact_nodes (
        snapshot TEXT NOT NULL,
        id TEXT NOT NULL,
        kind TEXT NOT NULL,
        path TEXT NOT NULL,
        line INTEGER NOT NULL CHECK(line >= 0),
        name TEXT NOT NULL,
        payload TEXT NOT NULL CHECK(json_valid(payload)),
        PRIMARY KEY(snapshot, id),
        FOREIGN KEY(snapshot) REFERENCES pm_fact_snapshots(snapshot)
            ON DELETE CASCADE
    )""",
    """CREATE TABLE IF NOT EXISTS pm_fact_edges (
        snapshot TEXT NOT NULL,
        ordinal INTEGER NOT NULL,
        source TEXT NOT NULL,
        target TEXT NOT NULL,
        kind TEXT NOT NULL,
        status TEXT NOT NULL,
        payload TEXT NOT NULL CHECK(json_valid(payload)),
        PRIMARY KEY(snapshot, ordinal),
        FOREIGN KEY(snapshot, source) REFERENCES pm_fact_nodes(snapshot, id)
            ON DELETE CASCADE,
        FOREIGN KEY(snapshot, target) REFERENCES pm_fact_nodes(snapshot, id)
            ON DELETE CASCADE
    )""",
    """CREATE INDEX IF NOT EXISTS pm_fact_edges_outgoing
        ON pm_fact_edges(snapshot, source, kind, status, target)""",
    """CREATE INDEX IF NOT EXISTS pm_fact_edges_incoming
        ON pm_fact_edges(snapshot, target, kind, status, source)""",
)


def _text(value, location, *, nonempty=True):
    if not isinstance(value, str) or (nonempty and not value):
        raise ValueError(f"{location} must be a {'nonempty ' if nonempty else ''}string")
    return value


def _json(value):
    """Require lossless JSON-compatible payloads (including all extra fields)."""
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
        if json.loads(encoded) != value:
            raise ValueError("payload is not losslessly JSON compatible")
        return encoded
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"payload must contain JSON-compatible values: {exc}") from exc


def _prepare(graph):
    if not isinstance(graph, dict):
        raise ValueError("graph must be a dictionary")
    snapshot = _text(graph.get("snapshot"), "snapshot")
    nodes, edges = graph.get("nodes"), graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("nodes and edges must be lists")
    node_rows, edge_rows, node_ids = [], [], set()
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise ValueError(f"nodes[{index}] must be a dictionary")
        node_id = _text(node.get("id"), f"nodes[{index}].id")
        if node_id in node_ids:
            raise ValueError(f"duplicate node ID in snapshot: {node_id}")
        node_ids.add(node_id)
        for key in ("kind", "path", "name"):
            _text(node.get(key), f"nodes[{index}].{key}", nonempty=key == "kind")
        line = node.get("line")
        if type(line) is not int or line < 0:
            raise ValueError(f"nodes[{index}].line must be a nonnegative integer")
        node_rows.append((snapshot, node_id, node["kind"], node["path"], line,
                          node["name"], _json(node)))
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            raise ValueError(f"edges[{index}] must be a dictionary")
        for key in ("source", "target", "kind", "status"):
            _text(edge.get(key), f"edges[{index}].{key}")
        if not isinstance(edge.get("evidence"), list):
            raise ValueError(f"edges[{index}].evidence must be a list")
        if edge["source"] not in node_ids or edge["target"] not in node_ids:
            raise ValueError(f"edges[{index}] endpoints must exist in the same snapshot")
        edge_rows.append((snapshot, index, edge["source"], edge["target"],
                          edge["kind"], edge["status"], _json(edge)))
    metadata = {key: value for key, value in graph.items() if key not in ("nodes", "edges")}
    return snapshot, _json(metadata), node_rows, edge_rows


@contextmanager
def _atomic(connection):
    if not connection.execute("PRAGMA foreign_keys").fetchone()[0]:
        if connection.in_transaction:
            raise sqlite3.ProgrammingError(
                "Enable PRAGMA foreign_keys=ON before starting the caller transaction"
            )
        connection.execute("PRAGMA foreign_keys=ON")
        if not connection.execute("PRAGMA foreign_keys").fetchone()[0]:
            raise sqlite3.ProgrammingError("SQLite foreign key enforcement is required")
    started = not connection.in_transaction
    if started:
        connection.execute("BEGIN")
    savepoint = "pm_fact_" + uuid.uuid4().hex
    connection.execute(f"SAVEPOINT {savepoint}")
    try:
        for statement in _SCHEMA:
            connection.execute(statement)
        yield
    except BaseException:
        connection.execute(f"ROLLBACK TO {savepoint}")
        connection.execute(f"RELEASE {savepoint}")
        if started:
            connection.rollback()
        raise
    else:
        connection.execute(f"RELEASE {savepoint}")


def replace_snapshot(connection: sqlite3.Connection, graph: dict) -> dict:
    """Atomically replace one snapshot; return inserted node/edge counts.

    Required fields follow the structured-fact contract. Extra graph metadata,
    node fields, conditions, evidence, and parallel edges are retained as JSON.
    On error, earlier caller work and the previous snapshot remain intact.
    On success, call ``connection.commit()`` to persist the change.
    """
    snapshot, metadata, nodes, edges = _prepare(graph)
    with _atomic(connection):
        connection.execute("DELETE FROM pm_fact_snapshots WHERE snapshot=?", (snapshot,))
        connection.execute("INSERT INTO pm_fact_snapshots VALUES (?, ?)", (snapshot, metadata))
        connection.executemany("INSERT INTO pm_fact_nodes VALUES (?, ?, ?, ?, ?, ?, ?)", nodes)
        connection.executemany("INSERT INTO pm_fact_edges VALUES (?, ?, ?, ?, ?, ?, ?)", edges)
    return {"snapshot": snapshot, "nodes": len(nodes), "edges": len(edges)}


def delete_snapshot(connection: sqlite3.Connection, snapshot: str) -> dict:
    """Delete one snapshot and its facts; return deleted counts, without commit."""
    _text(snapshot, "snapshot")
    with _atomic(connection):
        counts = {
            table: connection.execute(
                f"SELECT count(*) FROM pm_fact_{table} WHERE snapshot=?", (snapshot,)
            ).fetchone()[0]
            for table in ("snapshots", "nodes", "edges")
        }
        connection.execute("DELETE FROM pm_fact_snapshots WHERE snapshot=?", (snapshot,))
    return {"snapshot": snapshot, **counts}
