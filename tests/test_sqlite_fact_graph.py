"""Storage-contract checks; the small graph is authored test data, not extraction."""

import copy
import json
import sqlite3
import tempfile
from pathlib import Path
import unittest

from adapters.sqlite_fact_graph import delete_snapshot, replace_snapshot


def graph(snapshot="v1"):
    return {
        "snapshot": snapshot, "provenance": {"commit": "fixture-v1", "producer": "test"},
        "nodes": [
            {"id": "client", "kind": "Function", "path": "client.ts", "line": 3,
             "name": "load", "payload_extra": {"language": "typescript", "unicode": "来源"}},
            {"id": "handler", "kind": "Method", "path": "server.cpp", "line": 5,
             "name": "handle"},
            {"id": "db", "kind": "Method", "path": "db.cpp", "line": 8,
             "name": "query"},
        ],
        "edges": [
            {"source": "client", "target": "handler", "kind": "request",
             "status": "resolved", "condition": {"command": "unit/flows"},
             "evidence": [{"path": "client.ts", "line": 4, "producer": "test"}]},
            {"source": "handler", "target": "db", "kind": "calls",
             "status": "candidate", "condition": {"backend": "sqlite"},
             "evidence": [{"path": "server.cpp", "line": 6}], "confidence": 0.7},
        ],
    }


def read_graph(connection, snapshot):
    metadata = connection.execute(
        "SELECT payload FROM pm_fact_snapshots WHERE snapshot=?", (snapshot,)
    ).fetchone()
    if metadata is None:
        return None
    return {
        **json.loads(metadata[0]),
        "nodes": [json.loads(row[0]) for row in connection.execute(
            "SELECT payload FROM pm_fact_nodes WHERE snapshot=? ORDER BY rowid", (snapshot,))],
        "edges": [json.loads(row[0]) for row in connection.execute(
            "SELECT payload FROM pm_fact_edges WHERE snapshot=? ORDER BY ordinal", (snapshot,))],
    }


class SQLiteFactGraphTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.addCleanup(self.connection.close)

    def test_full_payload_parallel_edges_and_metadata_round_trip(self):
        value = graph()
        value["edges"].append(copy.deepcopy(value["edges"][1]))
        value["edges"][2]["condition"] = {"backend": "text"}
        value["edges"].append(copy.deepcopy(value["edges"][0]))
        self.assertEqual(replace_snapshot(self.connection, value),
                         {"snapshot": "v1", "nodes": 3, "edges": 4})
        self.assertEqual(read_graph(self.connection, "v1"), value)

    def test_forward_reverse_recursive_queries_and_conditions(self):
        replace_snapshot(self.connection, graph())
        for start, end, source, target in (("client", "db", "source", "target"),
                                          ("db", "client", "target", "source")):
            rows = self.connection.execute(f"""
                WITH RECURSIVE reachable(id) AS (
                    SELECT ? UNION SELECT e.{target} FROM pm_fact_edges e
                    JOIN reachable r ON e.{source}=r.id WHERE e.snapshot=?
                ) SELECT id FROM reachable ORDER BY id
            """, (start, "v1")).fetchall()
            self.assertIn((end,), rows)
            self.assertEqual(len(rows), 3)
        self.assertEqual(self.connection.execute("""
            SELECT kind,status,json_extract(payload,'$.condition.backend'),
                json_extract(payload,'$.evidence[0].path')
            FROM pm_fact_edges WHERE snapshot='v1' AND source='handler'
        """).fetchone(), ("calls", "candidate", "sqlite", "server.cpp"))

    def test_snapshot_ids_replacement_deletion_and_empty_graph(self):
        replace_snapshot(self.connection, graph("v1"))
        other = graph("v2")
        other["nodes"][0]["name"] = "different"
        replace_snapshot(self.connection, other)
        updated = graph("v1")
        updated["nodes"] = updated["nodes"][:1]
        updated["edges"] = []
        replace_snapshot(self.connection, updated)
        self.assertEqual(read_graph(self.connection, "v1"), updated)
        self.assertEqual(read_graph(self.connection, "v2"), other)
        self.assertEqual(delete_snapshot(self.connection, "v1"),
                         {"snapshot": "v1", "snapshots": 1, "nodes": 1, "edges": 0})
        self.assertIsNone(read_graph(self.connection, "v1"))
        self.assertEqual(read_graph(self.connection, "v2"), other)
        self.assertEqual(delete_snapshot(self.connection, "absent")["snapshots"], 0)
        replace_snapshot(self.connection, {"snapshot": "v2", "nodes": [], "edges": []})
        self.assertEqual(self.connection.execute("SELECT count(*) FROM pm_fact_nodes").fetchone()[0], 0)

    def test_invalid_input_preserves_prior_snapshot(self):
        original = graph()
        replace_snapshot(self.connection, original)
        mutations = [
            lambda g: g["nodes"].append(copy.deepcopy(g["nodes"][0])),
            lambda g: g["edges"][0].update(target="missing"),
            lambda g: g["edges"][0].update(evidence="not a list"),
            lambda g: g["nodes"][0].update(line=True),
            lambda g: g["nodes"][0].update(line=-1),
            lambda g: g["nodes"][0].update(extra=float("nan")),
            lambda g: g["nodes"][0].update(extra={1: "integer key"}),
            lambda g: g["edges"][0].update(condition=("tuple",)),
            lambda g: g.update(snapshot=""),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                broken = copy.deepcopy(original)
                mutate(broken)
                with self.assertRaises(ValueError):
                    replace_snapshot(self.connection, broken)
                self.assertEqual(read_graph(self.connection, "v1"), original)

    def test_cross_snapshot_endpoints_and_direct_sql_foreign_keys(self):
        replace_snapshot(self.connection, graph("v1"))
        other = graph("v2")
        other["nodes"] = other["nodes"][:1]
        with self.assertRaises(ValueError):
            replace_snapshot(self.connection, other)
        other["edges"] = []
        replace_snapshot(self.connection, other)
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute("""INSERT INTO pm_fact_edges VALUES
                ('v2',0,'client','db','calls','candidate','{}')""")
        self.assertEqual(self.connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_caller_rollback_includes_replace_delete_and_first_schema(self):
        replace_snapshot(self.connection, graph())
        self.assertTrue(self.connection.in_transaction)
        self.connection.rollback()
        self.assertEqual(self.connection.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE 'pm_fact_%'"
        ).fetchall(), [])
        replace_snapshot(self.connection, graph())
        self.connection.commit()
        replace_snapshot(self.connection, graph("v2"))
        delete_snapshot(self.connection, "v1")
        self.connection.rollback()
        self.assertEqual(read_graph(self.connection, "v1"), graph())
        self.assertIsNone(read_graph(self.connection, "v2"))

    def test_mid_write_failure_rolls_back_replacement_not_caller_work(self):
        replace_snapshot(self.connection, graph())
        self.connection.execute("""CREATE TRIGGER reject_fact BEFORE INSERT ON pm_fact_edges
            WHEN NEW.status='reject' BEGIN SELECT RAISE(ABORT,'injected failure'); END""")
        self.connection.commit()
        self.connection.execute("CREATE TABLE caller_work(value TEXT)")
        self.connection.execute("INSERT INTO caller_work VALUES ('keep')")
        broken = graph()
        broken["nodes"][0]["name"] = "changed"
        broken["edges"][1]["status"] = "reject"
        with self.assertRaisesRegex(sqlite3.IntegrityError, "injected failure"):
            replace_snapshot(self.connection, broken)
        self.assertEqual(read_graph(self.connection, "v1"), graph())
        self.assertEqual(self.connection.execute("SELECT * FROM caller_work").fetchall(), [("keep",)])
        self.assertTrue(self.connection.in_transaction)

    def test_active_transaction_without_foreign_keys_is_rejected(self):
        self.connection.execute("BEGIN")
        with self.assertRaisesRegex(sqlite3.ProgrammingError, "foreign_keys"):
            replace_snapshot(self.connection, graph())
        self.assertTrue(self.connection.in_transaction)
        self.assertEqual(self.connection.execute("SELECT name FROM sqlite_master").fetchall(), [])

    def test_other_reader_sees_only_committed_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "facts.db"
            writer = sqlite3.connect(path)
            reader = sqlite3.connect(path)
            try:
                writer.execute("PRAGMA journal_mode=WAL")
                replace_snapshot(writer, graph())
                writer.commit()
                reader.execute("BEGIN")
                self.assertEqual(read_graph(reader, "v1"), graph())
                updated = graph()
                updated["nodes"][0]["name"] = "new"
                replace_snapshot(writer, updated)
                self.assertEqual(read_graph(reader, "v1"), graph())
                writer.commit()
                self.assertEqual(read_graph(reader, "v1"), graph())
                reader.commit()
                self.assertEqual(read_graph(reader, "v1"), updated)
            finally:
                reader.close()
                writer.close()

    def test_native_schema_rows_and_sqlite_sequence_unchanged(self):
        self.connection.execute("CREATE TABLE nodes(id TEXT PRIMARY KEY, data TEXT)")
        self.connection.execute("CREATE TABLE edges(src TEXT, dst TEXT)")
        self.connection.execute("CREATE TABLE results(id INTEGER PRIMARY KEY AUTOINCREMENT)")
        self.connection.execute("INSERT INTO nodes VALUES ('native','payload')")
        self.connection.execute("INSERT INTO results DEFAULT VALUES")
        self.connection.commit()
        before = [row for row in self.connection.iterdump()]
        replace_snapshot(self.connection, graph())
        delete_snapshot(self.connection, "v1")
        self.connection.commit()
        for table in ("nodes", "edges", "results", "sqlite_sequence"):
            self.assertEqual([row for row in self.connection.iterdump() if f'"{table}"' in row],
                             [row for row in before if f'"{table}"' in row])


if __name__ == "__main__":
    unittest.main()
