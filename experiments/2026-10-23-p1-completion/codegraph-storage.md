# CodeGraph SQLite fact-extension maintenance

**Executed experiment, 2026-10-23:** independently implemented storage in three
`pm_fact_*` tables alongside copies of the completed native CodeGraph graphs.
Both native graphs accept the extension without changing any of their 25
original tables. The original CodeGraph read-only SQL CLI queries these tables,
including recursive traversal and JSON condition/evidence selection. Native
`trace` does not discover extension-only symbols.

This tests storage and query interoperability. The input graph is supplied
structured data; the adapter does not recover program semantics. Automatic
input consists only of a mechanical projection of native nodes/edges. A separate
authored storage-contract fixture exercises conditions and parallel edges and is
not presented as an automatically extracted cross-language chain.

## Version, scope, and isolation

- CodeGraph source: [sina-parsania/CodeGraph](https://github.com/sina-parsania/CodeGraph),
  pinned `7bac941c1916d34fae0e93dd0ffeaef360d741fb`.
- Executed artifact: original Windows x64 v1.39.0 release, SHA256
  `54156dd1f6481b4d7658f1435b97939a606ff7447caca196bb4b89499773df22`.
  The runner checks this hash and records `codegraph 1.39.0`.
- Input: completed `p1-codegraph-04/cache/*/graph.db` native graphs. Roles are
  determined from the read-only `meta.repo_root` and node rows. No peer adapter,
  new extraction result, or intermediate conclusion was consumed.
- Output, relative to the workspace:
  `work/repo-map-research/results/p1-codegraph-storage/final-run/`.
  `compact-evidence.json` contains sanitized CLI commands/output and hashes;
  `raw/` contains individual sanitized logs. Databases and copied sources remain
  outside the research repository.
- Each database is copied with SQLite's backup API before extension writes.
  CLI commands use this run's `CODEGRAPH_CACHE_DIR`, `CODEGRAPH_AUTO_SCIP=0`, and
  `--no-autoheal`. Original source paths are used only to satisfy the read-only
  identity gate; no index or autoheal command is issued. Input database byte
  hashes and all input source-file hashes are unchanged after the experiment.
- Isolation is separate files, copied databases, and process-local cache settings
  on a shared filesystem. It is workflow isolation, not a security boundary.
  No commit, push, upstream edit, or shared-result write was performed.

## Interface and persistence contract

Implementation: [sqlite_fact_graph.py](../../adapters/sqlite_fact_graph.py).
It requires Python's standard-library `sqlite3` with JSON SQL functions; the
executed runtime versions are recorded in compact evidence.

```python
counts = replace_snapshot(connection, graph)
# {'snapshot': graph['snapshot'], 'nodes': ..., 'edges': ...}
connection.commit()

deleted = delete_snapshot(connection, graph['snapshot'])
# {'snapshot': ..., 'snapshots': ..., 'nodes': ..., 'edges': ...}
connection.commit()
```

`graph` contains `snapshot`, `nodes`, and `edges` under the agreed interface.
Node fields are `id`, `kind`, `path`, `line`, `name`; edge fields are `source`,
`target`, `kind`, `status`, `evidence`. All original node/edge fields, including
extra payload, conditions, nested evidence, and Unicode, are saved in JSON.
Additional top-level metadata is stored in the snapshot JSON. Empty paths/names
and line zero are supported; line must be a nonnegative integer. Non-JSON values,
NaN, duplicate node IDs within a snapshot, and missing endpoints are rejected.

| Table | Identity and content |
|---|---|
| `pm_fact_snapshots` | Snapshot primary key and metadata JSON |
| `pm_fact_nodes` | `(snapshot, id)` primary key, indexed identity fields, full node JSON |
| `pm_fact_edges` | `(snapshot, ordinal)` primary key, source/target/kind/status, full edge JSON |

Edges have composite foreign keys to both endpoints in the same snapshot.
Deletion cascades from snapshot to nodes and incident edges. Per-snapshot
ordinals preserve parallel edges, including otherwise identical edges with
different conditions or evidence. Forward and reverse indexes start with
`(snapshot, source)` and `(snapshot, target)` respectively.

Successful operations remain in the caller's transaction and never commit it.
The adapter starts a transaction when needed and uses a savepoint for each
operation. Validation runs before writes; an injected mid-insert failure also
restores the previous complete snapshot. Existing caller work survives that
failure. If foreign keys are disabled in an already active transaction, the
adapter raises `sqlite3.ProgrammingError` rather than silently relying on the
ineffective in-transaction `PRAGMA foreign_keys=ON`. Enable foreign keys before
starting such a caller transaction. Every other direct writer must also enable
SQLite foreign keys on its own connection.

## Measured compact evidence

| Input | Source files | Native nodes / edges | Projected nodes / edges | Original tables unchanged |
|---|---:|---:|---:|---|
| Native fixtures | 3 | 19 / 21 | 19 / 21 | 25 / 25 |
| Native source slice | 65 | 728 / 883 | 728 / 883 | 25 / 25 |

All stored projected node and edge JSON records round-trip exactly. Each
projection is also inserted into a second snapshot with the same IDs and then
deleted; only that second snapshot disappears. On the source copy, that deletion
removes 728 nodes and 883 edges; on the fixture copy, it removes 19 nodes and 21
edges. `PRAGMA foreign_key_check` is empty for both copies.

The native-table digest covers every original schema object and all sorted rows
of the 25 original tables, including FTS shadow tables, metadata, and
`sqlite_sequence`. Extension tables and their automatically generated indexes
are excluded by ownership, not just by index name. Before/after digests match:

```text
fixtures: fd3b5efbd65cc9b3cc4e3f9ae17f607fd0a938b378357fc7a3e11c9a38d096da
source:   a20aef766faa1734ed905d5c891e4b02df02a8cb5f16654f4540dfe9622cbc83
```

The original, shared input database bytes also remain unchanged:

```text
fixtures: 138938ad2be79d9dc98ae07c9bf58e6209b3c0100eb2bf0005e6bce2400ade48
source:   04e394814f5dd895c1a862d101a091d505a1b13fd2ee8e29ce784128042ceb58
```

**Executed native SQL CLI results:** all extension selects exit 0. Native
projection forward/reverse recursive-query outputs exactly match Python SQLite
results: fixture example 10 / 2 reachable IDs, source example 16 / 3. The chosen
query seeds and full commands are in compact evidence. These queries traverse
all supplied edge kinds and test SQL interoperability, not a recovered business
execution path.

The authored contract has three nodes and three edges, including two parallel
candidate edges with different backend conditions. Forward traversal from
`client` and reverse traversal from `database` each return the same three IDs.
An executed native CLI condition/evidence query returns:

```text
kind | status | backend | evidence_path
candidate-implementation | candidate | sqlite | fixture/server.cpp
candidate-implementation | candidate | text | fixture/server.cpp
```

Representative native CLI query, with the cache environment already pointing to
the independent copied database:

```sh
codegraph --no-autoheal query "SELECT kind,status,json_extract(payload,'$.condition.backend') FROM pm_fact_edges WHERE snapshot='contract/v1' AND source='handler' ORDER BY ordinal" --path <original-native-input-path>
```

Both copies reject `DELETE FROM pm_fact_snapshots` through the original CLI with
nonzero exit status and `attempt to write a readonly database`. Their extension
rows remain unchanged. This matches the pinned
[read-only query implementation](https://github.com/sina-parsania/CodeGraph/blob/7bac941c1916d34fae0e93dd0ffeaef360d741fb/crates/codegraph-store/src/lib.rs#L2321),
which opens SQLite with `SQLITE_OPEN_READ_ONLY` and accepts arbitrary SQL without
a table allowlist. That implementation was inspected locally at the pinned commit.

## Verification and boundaries

**Executed:** [10 targeted unittest cases](../../tests/test_sqlite_fact_graph.py)
pass. They cover full JSON round-trip and parallel edges; forward/reverse
recursive traversal and condition selection; same-ID snapshot replacement,
deletion, and empty replacement; invalid payload rejection; cross-snapshot
endpoint rejection and actual SQLite foreign-key errors; caller rollback of
replacement, deletion, and initial schema creation; injected mid-write failure
without losing caller work; rejection of disabled foreign keys in an existing
transaction; separate-reader committed-snapshot visibility; and preservation of
native schema/rows/`sqlite_sequence`.

The reader test explicitly uses WAL: a reader transaction keeps its old view
through another connection's successful commit and sees the replacement after
ending its own transaction. This is distinct from the logical version isolation
provided by the snapshot column.

**Executed boundaries:**

- A database moved beside a copied source tree is rejected, even with
  `--no-autoheal`, because `meta.repo_root` still identifies the original path.
  The runner copies the database into the new path's cache slot and measures this
  failure; it does not rewrite native metadata. The pinned
  [identity check](https://github.com/sina-parsania/CodeGraph/blob/7bac941c1916d34fae0e93dd0ffeaef360d741fb/crates/codegraph-cli/src/index.rs#L539)
  explains the rejection. Using the original identity path with an isolated
  copied cache permits read-only SQL while leaving the original tables intact.
- `trace "Storage Client" "Storage Database"` returns `not found` on both
  copies although these nodes exist in extension tables. SQL compatibility does
  not automatically extend native search, trace, impact, or graph analytics.
  Only `trace` was directly checked among those native semantic commands.
- Native reindex/autoheal, GC, export/import, schema upgrades, concurrent writers,
  and crash recovery were not tested for extension preservation. The application
  must explicitly call `replace_snapshot` after producing new facts; this adapter
  does not install a watcher or infer a version from changed source files.
- Namespacing allows a database to hold both graphs without native-schema edits.
  Version management for the custom schema and a supported lifecycle policy
  still belong to a future integration.

**Recommendation:** use this adapter as a small SQL persistence boundary for
supplied structured facts, retain provenance/status/conditions in payload, and
make snapshot replacement part of the extraction transaction. Keep queries
explicitly scoped by snapshot. Choose whether future integration uses a separate
database or CodeGraph's cache only after native rebuild/import lifecycle tests;
the current result establishes read-only SQL interoperability and independent
fact maintenance, not native end-to-end semantic coverage.

## Reproduction

From the research repository, with an existing completed native input directory
and the verified official executable, choose a previously nonexistent output
directory outside the repository:

```sh
python -m unittest discover -s tests -p test_sqlite_fact_graph.py -v
python experiments/2026-10-23-p1-completion/run_codegraph_storage.py --input <completed-native-run> --binary <codegraph.exe> --output <new-output-directory>
```

The [runner](run_codegraph_storage.py) creates independent cache/database/source
copies, executes the original CLI, checks source and database immutability,
records every command, and emits path-sanitized compact evidence. Its input is
the native graph and original source identity only; it does not load any other
adapter's output. The first local attempt exposed an ownership-filter bug in the
measurement harness (new SQLite autoindex names were counted as native schema);
the table rows already matched. The filter was corrected, and the complete
`final-run` above passed with exact node/edge payload checks enabled.
