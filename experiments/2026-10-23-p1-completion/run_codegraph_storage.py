"""Isolated SQLite-extension test against two completed native CodeGraph graphs.

Only the new output directory is mutated. Original source paths are supplied to
--no-autoheal queries solely to satisfy CodeGraph's read-only identity gate.
No peer adapter or intermediate result is consumed. Python standard library only.
"""

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time

RESEARCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RESEARCH))
from adapters.sqlite_fact_graph import delete_snapshot, replace_snapshot

COMMIT = "7bac941c1916d34fae0e93dd0ffeaef360d741fb"
BINARY_SHA256 = "54156dd1f6481b4d7658f1435b97939a606ff7447caca196bb4b89499773df22"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_path(path):
    value = str(path.resolve())
    return "\\\\?\\" + value if os.name == "nt" and not value.startswith("\\\\?\\") else value


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def sql_literal(value):
    return "'" + value.replace("'", "''") + "'"


def json_row(row):
    return json.dumps([{"bytes": value.hex()} if isinstance(value, bytes) else value
                       for value in row], ensure_ascii=False, separators=(",", ":"))


def native_digest(connection):
    schema = connection.execute("""SELECT type,name,tbl_name,sql FROM sqlite_master
        WHERE name NOT LIKE 'pm_fact_%' AND tbl_name NOT LIKE 'pm_fact_%'
        ORDER BY type,name""").fetchall()
    total = hashlib.sha256(json.dumps(schema).encode())
    tables = {}
    for kind, name, _, _ in schema:
        if kind != "table":
            continue
        rows = sorted(json_row(row) for row in connection.execute(f"SELECT * FROM {quote(name)}"))
        table_hash = hashlib.sha256("\n".join(rows).encode()).hexdigest()
        tables[name] = {"rows": len(rows), "sha256": table_hash}
        total.update(name.encode())
        total.update(table_hash.encode())
    return {"sha256": total.hexdigest(), "tables": tables}


def extension_dump(connection):
    return {table: connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
            for table in ("pm_fact_snapshots", "pm_fact_nodes", "pm_fact_edges")}


def native_projection(connection, role):
    """Mechanical mapping of native records; does not add semantic edges."""
    nodes = []
    for node_id, label, path, line, name, payload in connection.execute(
        "SELECT id,label,file_path,line_start,name,data FROM nodes ORDER BY id"
    ):
        nodes.append({"id": node_id, "kind": label, "path": path or "", "line": line or 0,
                      "name": name or "", "native": json.loads(payload)})
    edges = []
    for source, target, relation, tier, confidence, path, line, payload in connection.execute(
        "SELECT src,dst,relation,tier,confidence,src_file,src_line,data FROM edges ORDER BY src,dst,relation"
    ):
        edges.append({"source": source, "target": target, "kind": relation,
                      "status": "native-observed", "condition": None,
                      "evidence": [{"producer": "CodeGraph", "commit": COMMIT,
                                    "path": path, "line": line, "tier": tier,
                                    "confidence": confidence}], "native": json.loads(payload)})
    return {"snapshot": role + "/native-v1", "nodes": nodes, "edges": edges,
            "producer": "mechanical projection of native automatic graph",
            "tool_commit": COMMIT, "conditions": "not supplied by this projection"}


def contract_graph(snapshot="contract/v1"):
    return {
        "snapshot": snapshot, "producer": "authored storage fixture; not extracted semantics",
        "nodes": [
            {"id": "client", "kind": "Function", "path": "fixture/client.ts", "line": 3,
             "name": "Storage Client", "extra": {"unicode": "来源", "nullable": None}},
            {"id": "handler", "kind": "Method", "path": "fixture/server.cpp", "line": 4,
             "name": "Storage Handler"},
            {"id": "database", "kind": "Method", "path": "fixture/db.cpp", "line": 5,
             "name": "Storage Database"},
        ],
        "edges": [
            {"source": "client", "target": "handler", "kind": "request", "status": "resolved",
             "condition": {"command": "unit/flows"},
             "evidence": [{"path": "fixture/client.ts", "line": 3, "producer": "contract"}]},
            {"source": "handler", "target": "database", "kind": "candidate-implementation",
             "status": "candidate", "condition": {"backend": "sqlite"},
             "evidence": [{"path": "fixture/server.cpp", "line": 4}]},
            {"source": "handler", "target": "database", "kind": "candidate-implementation",
             "status": "candidate", "condition": {"backend": "text"},
             "evidence": [{"path": "fixture/server.cpp", "line": 6}]},
        ],
    }


def reachable_sql(snapshot, start, reverse=False):
    source, target = ("target", "source") if reverse else ("source", "target")
    return f"""WITH RECURSIVE reachable(id) AS (
        SELECT {sql_literal(start)} UNION SELECT e.{target} FROM pm_fact_edges e
        JOIN reachable r ON e.{source}=r.id WHERE e.snapshot={sql_literal(snapshot)}
    ) SELECT id FROM reachable ORDER BY id"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path,
                        help="Completed native run containing cache/, source/, fixtures/")
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    input_root, binary, output = args.input.resolve(), args.binary.resolve(), args.output.resolve()
    if output.exists():
        raise SystemExit("Output must be a new directory")
    if output.is_relative_to(input_root) or output.is_relative_to(RESEARCH):
        raise SystemExit("Output must be separate from input and the research repository")
    if digest(binary) != BINARY_SHA256:
        raise SystemExit("Unexpected CodeGraph release executable hash")
    output.mkdir(parents=True)
    (output / "raw").mkdir()
    env = os.environ.copy()
    env.update(CODEGRAPH_CACHE_DIR=str(output / "cache"), CODEGRAPH_AUTO_SCIP="0")
    replacements = [(input_root, "<native-input>"), (binary, "<codegraph>"),
                    (output, "<output>"), (RESEARCH, "<research>")]

    def portable(text):
        for path, label in replacements:
            text = text.replace(canonical_path(path), label)
            text = text.replace(str(path), label).replace(path.as_posix(), label)
        return text

    commands = []

    def run(label, arguments, *, expected=0, cwd=output):
        start = time.perf_counter()
        result = subprocess.run([str(value) for value in arguments], cwd=cwd, env=env,
                                capture_output=True, timeout=90)
        stdout = portable(result.stdout.decode("utf-8", errors="replace"))
        stderr = portable(result.stderr.decode("utf-8", errors="replace"))
        (output / "raw" / (label + ".stdout.txt")).write_text(stdout, encoding="utf-8")
        (output / "raw" / (label + ".stderr.txt")).write_text(stderr, encoding="utf-8")
        record = {"label": label, "argv": [portable(str(value)) for value in arguments],
                  "exit_code": result.returncode, "elapsed_seconds": round(time.perf_counter()-start, 4),
                  "stdout": stdout.strip(), "stderr": stderr.strip()}
        commands.append(record)
        if expected is not None and result.returncode != expected:
            raise AssertionError(record)
        return record

    run("version", [binary, "--version"])
    unit = run("unittests", [sys.executable, "-m", "unittest", "discover", "-s", "tests",
                            "-p", "test_sqlite_fact_graph.py", "-v"], cwd=RESEARCH)
    # The executable path is host-specific; publish only its role.
    unit["argv"][0] = "<python>"
    results = []
    inputs = sorted((input_root / "cache").glob("*/graph.db"))
    assert len(inputs) == 2, "Expected the source and fixtures native graphs"
    for original_db in inputs:
        original_file_hash = digest(original_db)
        with sqlite3.connect(original_db.as_uri() + "?mode=ro", uri=True) as original:
            stamp = original.execute("SELECT value FROM meta WHERE key='repo_root'").fetchone()[0]
            role = Path(stamp).name
            assert role in ("source", "fixtures")
            source_root = input_root / role
            assert stamp == canonical_path(source_root)
            assert original_db.parent.name == hashlib.sha256(stamp.encode()).hexdigest()[:16]
            before = native_digest(original)
            destination = output / "cache" / original_db.parent.name / "graph.db"
            destination.parent.mkdir(parents=True)
            with sqlite3.connect(destination) as target:
                original.backup(target)
        source_hashes = {path.relative_to(source_root).as_posix(): digest(path)
                         for path in source_root.rglob("*") if path.is_file()}
        connection = sqlite3.connect(destination)
        try:
            assert native_digest(connection) == before
            projected = native_projection(connection, role)
            counts = replace_snapshot(connection, projected)
            connection.commit()
            stored_nodes = [json.loads(row[0]) for row in connection.execute(
                "SELECT payload FROM pm_fact_nodes WHERE snapshot=? ORDER BY id",
                (projected["snapshot"],))]
            stored_edges = [json.loads(row[0]) for row in connection.execute(
                "SELECT payload FROM pm_fact_edges WHERE snapshot=? ORDER BY ordinal",
                (projected["snapshot"],))]
            assert stored_nodes == projected["nodes"]
            assert stored_edges == projected["edges"]
            for row in connection.execute("SELECT payload FROM pm_fact_nodes ORDER BY id"):
                payload = json.loads(row[0])
                native = connection.execute("SELECT data FROM nodes WHERE id=?", (payload["id"],)).fetchone()
                assert payload["native"] == json.loads(native[0])
            native_rows_round_trip = True
            projected_clone = copy.deepcopy(projected)
            projected_clone["snapshot"] += "-same-ids"
            replace_snapshot(connection, projected_clone)
            deleted = delete_snapshot(connection, projected_clone["snapshot"])
            assert deleted["nodes"] == counts["nodes"] and deleted["edges"] == counts["edges"]
            connection.commit()
            contract = contract_graph()
            replace_snapshot(connection, contract)
            connection.commit()
            control_before = extension_dump(connection)
            delete_snapshot(connection, projected["snapshot"])
            replace_snapshot(connection, contract_graph("contract/v2"))
            connection.rollback()
            assert extension_dump(connection) == control_before
            connection.execute("""CREATE TRIGGER pm_fact_inject_error BEFORE INSERT ON pm_fact_edges
                WHEN NEW.status='reject' BEGIN SELECT RAISE(ABORT,'injected failure'); END""")
            connection.commit()
            broken = copy.deepcopy(projected)
            broken["edges"][-1]["status"] = "reject"
            try:
                replace_snapshot(connection, broken)
            except sqlite3.IntegrityError:
                pass
            else:
                raise AssertionError("injected write failure did not fire")
            assert extension_dump(connection) == control_before
            connection.execute("DROP TRIGGER pm_fact_inject_error")
            connection.commit()
            assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
            assert native_digest(connection) == before

            def query(label, sql, expected=0, path=source_root):
                return run(role + "-" + label,
                           [binary, "--no-autoheal", "query", sql, "--path", path, "--limit", "10000"],
                           expected=expected)

            observed = query("snapshot-counts", """SELECT s.snapshot,
                (SELECT count(*) FROM pm_fact_nodes n WHERE n.snapshot=s.snapshot) AS nodes,
                (SELECT count(*) FROM pm_fact_edges e WHERE e.snapshot=s.snapshot) AS edges
                FROM pm_fact_snapshots s ORDER BY s.snapshot""")
            selected = next(edge for edge in projected["edges"] if edge["kind"] == "Calls")
            native_queries = []
            for reverse, start in ((False, selected["source"]), (True, selected["target"])):
                sql = reachable_sql(projected["snapshot"], start, reverse)
                expected_ids = [row[0] for row in connection.execute(sql)]
                record = query("native-reverse" if reverse else "native-forward", sql)
                assert record["stdout"].splitlines()[1:] == expected_ids
                native_queries.append({"reverse": reverse, "start": start,
                                       "reachable_count": len(expected_ids)})
            for reverse, start in ((False, "client"), (True, "database")):
                record = query("contract-reverse" if reverse else "contract-forward",
                               reachable_sql("contract/v1", start, reverse))
                assert record["stdout"].splitlines()[1:] == ["client", "database", "handler"]
            typed = query("conditions", """SELECT kind,status,
                json_extract(payload,'$.condition.backend') AS backend,
                json_extract(payload,'$.evidence[0].path') AS evidence_path
                FROM pm_fact_edges WHERE snapshot='contract/v1' AND source='handler'
                ORDER BY ordinal""")
            assert "candidate-implementation | candidate | sqlite | fixture/server.cpp" in typed["stdout"]
            assert "candidate-implementation | candidate | text | fixture/server.cpp" in typed["stdout"]
            rejected_write = query("readonly-rejects-delete", "DELETE FROM pm_fact_snapshots", expected=None)
            assert rejected_write["exit_code"] != 0
            assert "readonly" in rejected_write["stderr"].lower()
            trace = run(role + "-native-trace", [binary, "--no-autoheal", "trace",
                        "Storage Client", "Storage Database", "--path", source_root], expected=None)
            assert "not found" in (trace["stdout"] + trace["stderr"]).lower()
            relocated = output / ("relocated-" + role)
            shutil.copytree(source_root, relocated)
            relocated_db = output / "cache" / hashlib.sha256(canonical_path(relocated).encode()).hexdigest()[:16] / "graph.db"
            relocated_db.parent.mkdir(parents=True)
            with sqlite3.connect(relocated_db) as moved:
                connection.backup(moved)
            rejected_move = query("relocated-identity", "SELECT count(*) FROM pm_fact_nodes",
                                  expected=None, path=relocated)
            assert rejected_move["exit_code"] != 0 and "was built for" in rejected_move["stderr"]
            after = native_digest(connection)
            assert after == before
            assert extension_dump(connection) == control_before
            assert digest(original_db) == original_file_hash
            assert source_hashes == {path.relative_to(source_root).as_posix(): digest(path)
                                     for path in source_root.rglob("*") if path.is_file()}
            results.append({"input": role, "native_counts": {
                "nodes": before["tables"]["nodes"]["rows"], "edges": before["tables"]["edges"]["rows"]},
                "extension_projection_counts": counts, "native_rows_round_trip": native_rows_round_trip,
                "native_queries": native_queries, "same_ids_snapshot_delete": deleted,
                "rollback_and_injected_failure": "passed", "foreign_key_check": [],
                "source_files_count": len(source_hashes), "source_files_unchanged": True,
                "input_db_bytes_unchanged": True, "original_db_sha256": original_file_hash,
                "native_schema_and_rows_sha256_before": before["sha256"],
                "native_schema_and_rows_sha256_after": after["sha256"],
                "native_table_count": len(before["tables"]),
                "cli_extension_queries": "passed", "cli_write_rejected": True,
                "cli_relocated_identity_rejected": True, "native_trace_extension_symbols": "not found",
                "native_snapshot_count_stdout": observed["stdout"]})
        finally:
            connection.close()
    evidence = {"tool": "CodeGraph 1.39.0", "tool_commit": COMMIT,
                "binary_sha256": BINARY_SHA256, "python": sys.version.split()[0],
                "sqlite": sqlite3.sqlite_version, "unit_tests": "10 passed",
                "evidence_type": "executed experiment",
                "fact_inputs": ["mechanically projected native automatic records",
                                "authored storage contract fixture, not semantic extraction"],
                "isolation": "separate outputs/cache/db copies; shared filesystem is workflow isolation",
                "results": results, "commands": commands}
    serialized = json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    # Keep the publication candidate free from local account/workspace paths.
    assert str(Path.home()).lower() not in serialized.lower()
    (output / "compact-evidence.json").write_text(serialized, encoding="utf-8")
    print(json.dumps({"unit_tests": "10 passed", "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
