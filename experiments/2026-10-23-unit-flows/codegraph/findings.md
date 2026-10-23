# CodeGraph / MindStudio unit-flows execution evidence

## Result

**Executed experiment:** original CodeGraph v1.39.0 runs successfully on this Windows x64 host. It indexes the selected real MindStudio source and resolves two front-end calls into `getUnitFlows`. It does **not** recover the requested front-end → command registration → handler → database chain. A separate TS/Python HTTP fixture produces a common route node, but neither the positive handler nor its database helper is reachable from the client through directed graph traversal. Distinct service origins sharing a method/path collapse onto one route identity.

This experiment uses automatically generated CodeGraph nodes, native raw-call records, edges and CLI traversal results. No hand-built graph was substituted. Missing edges are measured coverage gaps, not evidence that the underlying product has no dependency.

## Versions and execution boundary

- Tool source: [sina-parsania/CodeGraph](https://github.com/sina-parsania/CodeGraph), pinned commit `7bac941c1916d34fae0e93dd0ffeaef360d741fb`, MIT OR Apache-2.0.
- Executed artifact: official [v1.39.0 Windows x64 release](https://github.com/sina-parsania/CodeGraph/releases/tag/v1.39.0), **not a locally compiled binary**. `--version` returns `codegraph 1.39.0`. `git rev-list -n 1 v1.39.0` equals the pinned commit. Tag correspondence is verified; reproducible equivalence of the release executable to a local source build was not tested.
- SHA256: `54156dd1f6481b4d7658f1435b97939a606ff7447caca196bb4b89499773df22`, matches both the official `sha256sums.txt` and GitHub release asset digest.
- Target source: MindStudio Insight commit `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`, verified before copying. Both tool and product checkouts were clean after execution.
- Host: Windows x64, Python version in `environment.json`; Rust tools absent from PATH and no existing user cargo/bin directory found. No compiler build, global installation, GUI, LLM, embedding, external oracle or MCP server was invoked. `CODEGRAPH_AUTO_SCIP=0` was set; cache is process-local to the experiment output directory.
- Source analysis only: MindStudio itself was not built or executed. No runtime request or database implementation selection was validated.

## Input scope

`slice-manifest.json` records every input path, byte length and SHA256: **42 files, 858,403 bytes**. The slice preserves repository-relative paths and includes all 15 reference anchors, all six `rg -l getUnitFlows modules` hits (API definition, two production callers and three tests), front-end request binding/transport, protocol constant/registration/dispatch, handler, database base declaration and two candidate implementations, their headers and database manager, and the Timeline protocol directory. This is a selected source slice, not a complete build dependency closure.

The manually audited reference is input coverage guidance only. It was not imported as graph edges. Tests included in the slice do not imply the complete test suite was run.

## Native results

Forced full slice index: **577 nodes, 680 edges** (`Calls=120`, `Defines=535`, `Inherits=2`, `Tests=23`). Every one of the 42 selected files appears in the indexed file count. Main measurement: 0.2603 s full rebuild; a fresh independent parameterized rerun into a previously nonexistent output/cache directory took 0.2152 s. These tiny single-host runs are not a general performance benchmark. Queries were roughly 0.04–0.06 s including process startup. Raw outputs and all measured durations are retained.

| Question | Executed result |
|---|---|
| Find front-end entry | `getUnitFlows`, Function, `modules/timeline/src/api/request.ts:174` |
| Find consumers | Two `Calls` edges with `ImportNarrowed`: `getSingleFlow` at `FilterLinkLine.tsx:434`; **File node** `AscendUnit.tsx` at line 793. The enclosing method for the latter call was not preserved. |
| Extract command/module values | Raw call records retain callee `requestData`, receiver `window`, line 175; no interface node representing `module=timeline, command=unit/flows`, no preserved literal argument-value link. |
| Find constant/registration | Exact SQL finds no `REQ_RES_UNIT_FLOWS` or `RegisterRequestHandlers` node. Fuzzy FTS results for these terms are not exact symbol extraction. `ProtocolDefs.h` has only File and two misclassified namespace/function nodes. |
| Handler method | The handler header yields a node named `QueryFlowsBySliceInfoHandler`, **Function / language=c**. Its `.cpp` has File plus namespace nodes, **no `HandleRequest` function definition**. This is not a correctly extracted handler method. |
| Database call | Raw native `calls` table contains `QueryUnitFlows` at `server/src/modules/timeline/handler/QueryFlowsBySliceInfoHandler.cpp:57`, receiver `Bare`, caller the `.cpp` **File node**. The method body was scanned; attribution and resolution are missing. `callers QueryUnitFlows` reports **0/1** resolved and one parser-verified textual fallback file. |
| Interface and implementations | No exact `QueryUnitFlows`, `DbTraceDataBase`, or `TextTraceDatabase` definition nodes. `VirtualTraceDatabase` appears as three Function nodes in `.h` files, not the intended class/interface type. `implementers VirtualTraceDatabase` returns none. The two `.cpp` implementation files were indexed, but their qualified `QueryUnitFlows` definitions are absent. |
| End-to-end / reverse traversal | `trace getUnitFlows QueryFlowsBySliceInfoHandler`: no path; `trace getUnitFlows QueryUnitFlows`: symbol not found; `impact QueryUnitFlows`: symbol not found. Finding strings or file nodes did not constitute a connected chain. |
| Diagnostics | Helpful `0/1` unresolved-call coverage and file fallback for the database call. However, `callees getUnitFlows` says the symbol makes no calls while the raw table contains its unresolved `window.requestData` call. Header language classification and lost qualified definitions require explicit SQL/source inspection; no specific parser warning was returned. |

Exact rows, native edge metadata, file attribution and relevant query output are in `compact-evidence.json`; complete CLI output is under `raw/`.

## HTTP direction and service-identity fixture

The self-authored fixture is embedded in the runner. A TypeScript axios client has separate service-A and service-B `baseURL`s. Python Flask service A provides `GET /positive` and `GET /shared`; service B separately provides `GET /shared`. Each handler calls a distinct database-named helper. It requires no package installation because CodeGraph parses source without executing the application.

The original index returns 17 nodes and 24 edges. Measured edges are:

- `loadPositive → route._positive.GET`, relation `HttpCalls`, metadata `justification=HttpPath`.
- `service-a/routes.py` **File** `→ route._positive.GET`, also `HttpCalls` with `HttpPath`.
- `positive_handler → db_positive`, relation `Calls`, metadata `SameFileUnique`.
- There is no outgoing route-to-handler edge, so `trace loadPositive positive_handler` and `trace loadPositive db_positive` both return **no path**. Reverse impact of the handler does not return the client.
- `loadSamePathA`, `loadSamePathB`, and the two Python service **File** registrations all point to **one** `route._shared.GET`. Both axios base URLs are ignored for this identity. The stored route location becomes `service-b/routes.py:5`; the separate service-A provider location is not represented on the route node. Initial `impact "GET /shared"` returns both service files and both client functions. This is a measured service-identity collision, not a confirmed application dependency across those services.
- `POST /shared` becomes a different route node, so HTTP method distinguishes it from `GET /shared`. That POST node exists solely from the client call; no fixture backend POST provider exists. Route enumeration is therefore not a provider-only endpoint list.
- An absolute `https://service-a.example/shared` client call does not create an `HttpCalls` route edge in this fixture; the relative `/shared` calls do. `callees loadAbsolute` prints no calls. Absolute-host routing was not inferred.

The JSON preserves the two edge directions, source line, `tier`, `confidence`, `justification`, route IDs, and the overwritten provider location. It does not treat the shared sink as a completed client-to-handler path.

## Update measurement

After the initial fixture index, the runner deletes `loadSamePathA` and changes `loadPositive` from `/positive` to `/renamed`.

1. `--no-autoheal search loadSamePathA` still returns the old definition, demonstrating the saved snapshot has not been updated by a background CLI process.
2. A normal `search loadSamePathA` triggers healing and returns only the fuzzy `loadSamePathB` hit, with the deleted exact name absent.
3. `routes` lists the new client-only `/renamed` hub, and directed `trace loadPositive "GET /renamed"` succeeds.
4. Ordered read-only SQL rows for all node identities/names/labels/source spans and all edge IDs/relations/data **differ** between the healed graph and a subsequent `index --full` of the same final fixture state (`update-comparison.json`). The surviving `GET /shared` hub is attributed to `frontend/client.ts:5` after healing, versus `service-b/routes.py:5` after full rebuild. The incremental graph has `frontend/client.ts File → hub` as a `Defines` edge, while full rebuild has `service-b/routes.py File → hub` instead. This is a structural relationship and source-location change, not merely metrics or JSON metadata order. All `Calls` and `HttpCalls` rows remain identical. `update-delta.json` preserves the exact two edge rows and changed node row. Metrics, manifest, metadata, and complete database bytes are not compared.

This verifies that **query-triggered autoheal runs** and updates the deleted consumer/path without an explicit reindex before the update query. It fails the tested semantic-equivalence check against full rebuild because shared hub ownership changes. The independent clean rerun reproduces the same difference. The separately documented MCP watcher and the entire deletion/rename/retry/version matrix remain untested. An earlier smaller fixture had matched full rebuild, but the later fixture that retains a second shared-path client exposes this difference; the earlier interim generalization of equivalence is withdrawn.

## C++ boundary check and source explanation

**Executed minimal fixture:** in `.cpp`, inline `QueryInline` and free `QueryFree` get Function nodes; class-external `ExternalDatabase::QueryExternal` gets no node. `.h` is classified as C and its C++ class appears as a Function; equivalent `.hpp` is classified as C++ and yields its Class, but the pure virtual member declaration gets no callable node. Native rows are included in the evidence JSON. This distinguishes actual extraction failures from missing slice files.

**Pinned source inspection, not a measured compiler oracle:** [extension selection](https://github.com/sina-parsania/CodeGraph/blob/7bac941c1916d34fae0e93dd0ffeaef360d741fb/crates/codegraph-parse/src/lib.rs#L118) maps `.h` to C. [C++ specification](https://github.com/sina-parsania/CodeGraph/blob/7bac941c1916d34fae0e93dd0ffeaef360d741fb/crates/codegraph-parse/src/lib.rs#L258) sets `inherit_fn: None`; [definition selection](https://github.com/sina-parsania/CodeGraph/blob/7bac941c1916d34fae0e93dd0ffeaef360d741fb/crates/codegraph-parse/src/lib.rs#L393) does not select member declarations as callable nodes. [C declarator name extraction](https://github.com/sina-parsania/CodeGraph/blob/7bac941c1916d34fae0e93dd0ffeaef360d741fb/crates/codegraph-parse/src/lib.rs#L2064) walks `declarator` fields and does not handle qualified identifiers, consistent with the measured external-definition gap. [HTTP extraction](https://github.com/sina-parsania/CodeGraph/blob/7bac941c1916d34fae0e93dd0ffeaef360d741fb/crates/codegraph-parse/src/lib.rs#L1216) requires a slash-prefixed literal for nondecorator calls; [hub creation](https://github.com/sina-parsania/CodeGraph/blob/7bac941c1916d34fae0e93dd0ffeaef360d741fb/crates/codegraph-parse/src/lib.rs#L1272) uses normalized path and method without service origin. [Graph linking](https://github.com/sina-parsania/CodeGraph/blob/7bac941c1916d34fae0e93dd0ffeaef360d741fb/crates/codegraph-graph/src/lib.rs#L756) creates caller-to-hub `HttpCalls` edges. These source explanations do not establish complete language/framework coverage.

## Acceptance coverage

| Criterion | Status in this run |
|---|---|
| S01 accurate module/command/value provenance | Not satisfied: symbol and raw request callee only |
| S02 exact registration and handler | Not satisfied |
| S03 database interface, candidate implementations, selection conditions | Not satisfied; runtime selection unknown |
| S04 parameters, database query, response, UI consumers | Partial: names/shapes and two callers; full chain, field flow and SQL dependencies unverified |
| S05 reverse database/interface-to-front-end | Not satisfied |
| S06 maintained after changes | Partial with a failed equivalence check: HTTP consumer/path changes update, but shared-hub location/Defines ownership differ from full rebuild; real custom-protocol update matrix untested |
| S07 queryable gaps/ambiguity/filter/version diagnostics | Partial: raw calls and coverage fallback help; C++ extraction gaps have no specific diagnostic; broad filter/version audit untested |

Untested: full repository; compiler-grade SCIP/oracle integration; MCP filesystem watcher; provider deletion; handler rename; custom module/command collision changes; rapid commits; reindex failure/retry; cross-version snapshots; both MindStudio runtime scenarios and behavior assertions. No complete runtime or automatic map claim follows from this run.

## Reproduction and artifacts

Clone the official tool and target repositories separately and checkout the pinned commits. Download the official Windows release binary and `sha256sums.txt`; verify the SHA256 above before execution. Run this independent parameterized runner against a **new output directory**:

```powershell
python run_experiment.py --source-repo <msinsight-checkout> --tool-repo <CodeGraph-checkout> --reference <reference.json> --binary <codegraph.exe> --output <new-output-directory> --phase all
```

The runner uses Python standard library plus `git` and `rg` already available on the host. It checks both commits, release-tag commit and binary hash; copies the real slice; writes hashed manifests; runs actual `index`, search, callers/callees, trace, impact, routes, implementers and read-only SQL; creates the two tiny fixtures; mutates only its own fixture; compares healed and full rebuilt semantic rows; and emits compact JSON plus exact update differences. Commands use argument arrays without a shell. Every process has a 90-second timeout. No source checkout mutation is necessary.

- `run_experiment.py`: standalone reproduction code, including complete self-authored fixture inputs.
- `binary-provenance.json`, `environment.json`: execution provenance.
- `slice-manifest.json`: per-file target source hashes and inclusion reasons.
- `fixture-manifest-before.json`, `fixture-manifest-after.json`, `cpp-fixture-manifest.json`: exact fixture hashes.
- `compact-evidence.json`: portable native tool rows/edge metadata and small raw CLI results; suitable for review/publication.
- `update-delta.json`: exact native row differences between healed and full rebuilt graph; preserves the failed equivalence check.
- `commands.json`: portable command arguments, elapsed times, exit codes and log paths. Root output preserves historical reruns; `reproduction-check/commands.json` is one clean parameterized run.
- `raw/`: all original stdout/stderr for local verification. Full index log lines contain local cache paths and should be sanitized before publication.
- `reproduction-check/`: independent new-output rerun with fresh cache; compact evidence and update comparison agree semantically with the main run.

Only runner, manifests, provenance and compact summaries are publication candidates. Do not publish binary, cache databases, copied third-party source slice, or complete raw logs without a path review. Summaries and compact JSON contain no user home path or credentials. The experiment followed directory/input/output separation from peer tools and did not read peer results or exchange intermediate conclusions; the shared filesystem remains a workflow boundary, **not security isolation**. The research repository was not modified or pushed by this experiment.
