# Issue 655 implementation and validation

Date: 2026-10-28. Baseline: independent snapshot of upstream `207a0928b5ff8d10aaca6bb4a492750508099e94`.

## Implemented behavior

- Timeline summary/details commands use registered rank sources, a card-level derived Overlap source when available, and complete Free records. DB and Text evidence feeds the same status, deduplication, range/search, grouping, stable sorting and pagination logic.
- DB uses device-specific compute tasks and communication events, explicit CONNECTION_IDS/PYTORCH_API mappings, and excludes Python Stack. CANN mappings are unnecessary. Legacy communication tables without deviceId verify the device through TASK.
- Text uses async_npu s/t/f groups, verifies actual device endpoints, resolves true framework origins, preserves missing branches and ambiguity, and handles reused identifiers in complete ordered segments. Host/Device reverse clocks do not invalidate a single explicit relation. Per-track interval indexes, point/chain memoization and 400-value batches limit repeated work.
- Three-entry map cache stores whole-card records with weak source-pool identities, source/WAL observations, database change counters and table watermarks. Query-local pool handles are released after borrowed connections; cached records do not retain pools.
- Two-level ResizeTable view includes server-side search, independent pagination/sorting, complete candidate copy, per-candidate/source jumps, local retry, explicit all/range/empty conversion, Host/Device offsets, actual source readiness and relevant completion versions. Stale successes and failures cannot populate a new context.
- Optional copyColumns preserves other tables. Source-aware locating preserves old callers without source identity and Python Stack aliases. Chinese/English entry, tooltip, statuses, reasons and system tuning manuals were updated.

## Historical constraints reviewed

The supplied history library was consulted for R07 (offset ownership), R08 (import publication/reset order), R09 (Text/IE source routing) and R10 (rank/source/thread identity), including related issue bodies/comments and PR/patch records. Relevant issues include 344, 368, 375, 398, 404, 476, 488, 489, 501, 546, 559, 574, 588, 600 and 601. No project map or later upstream implementation was used. Existing Overlap generation and backend import/Reset behavior were not changed.

## Executed checks

- C++: 23 tests passed across FreeAttributionServiceTest, FreeAttributionProtocol and FreeAttribution. These execute current application objects against real shared-memory SQLite databases, including DB/Text compute/communication, independent SDMA/CANN evidence, strict boundaries, reverse clocks, Python Stack exclusion, missing framework branches, reused flow IDs, eight tied API instances, multiple sources, derived Overlap, source mutation, pool recreation and concurrent cold requests.
- Frontend: 28 tests passed in six suites (freeAttribution API helpers, FreeAttribution view, operatorUnit, jumpToUnitOperator, detailViews/Common and lib/ResizeTable). The view tests use mocked table/network boundaries and do not constitute browser layout or desktop end-to-end verification.
- TypeScript noEmit check of the Timeline workspace passed. A temporary config maps @insight/lib to this checkout, avoiding the read-only dependency workspace's package links.
- Targeted ESLint passed for the new API/view and changed locating utilities, with an explicit temporary TypeScript project path. No lint cache was written outside D:.
- `git -c core.whitespace=cr-at-eol diff --check` passed; existing repository blobs contain CRLF.
- All 466 CMake compilation steps completed with the supplied MinGW compiler. The default final link failed with duplicate `__stack_chk_fail` exported by the newly built msinsight DLL and libssp. After the final edits, DataBaseManager.cpp and FreeAttributionService.cpp were recompiled using their exact CMake compile arguments. Current application and test executables linked successfully with the local-only `-Wl,--allow-multiple-definition` workaround. Build configuration in the repository was not changed. The normal unmodified CMake link is therefore still a failed check in this environment.
- Newly linked current application executable ran `--scanPort=9087 --logPath=<D: workspace tmp>` successfully and returned `Available port: 9087`. This is a process-start smoke test, not an import or GUI test.

Frontend command:

```powershell
node modules/testing/run.cjs --module timeline --module lib --runInBand --testPathPattern 'freeAttribution.test|FreeAttribution.test|operatorUnit.test|jumpToUnitOperator.test|detailViews.*Common.test|ResizeTable.test' --cacheDirectory <worker>/cache/jest
```

C++ test files are included by the existing server test CMake source-directory discovery. For this environment the focused executable linked the current server object files (excluding main.cpp.obj), the two new test files and Google Test. Compiler/link response files and logs are under the assigned workspace's tmp/build directories.

## Measured synthetic baseline

Windows, MinGW GCC 11.5, application objects compiled with the repository Release flags. Query timings below are one separate benchmark run, in milliseconds; they exclude source import and Overlap generation.

| Dataset | First whole-card query | Cache hit | Range | Search | Sort | Page | Details |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DB: 10,000 Free, 10,000 device tasks, one API instance, one source | 93.122 | 18.985 | 5.406 | 20.094 | 19.825 | 19.718 | 29.225 |
| Text: 10,000 Free, 10,000 device events, 20,000 flow points, 30,001 slices, one API instance, one source | 189.028 | 15.810 | not measured | not measured | not measured | not measured | not measured |

The three-benchmark process (DB, Text and concurrency) had an observed peak working set of 95,170,560 bytes, including SQLite, test/runtime overhead and records; this is not a cache-only or per-phase memory measurement. Two concurrent cold requests on a one-Free/one-device/one-source dataset completed in 2.614 ms with identical totals; larger concurrent cold-miss duplication remains unmeasured. First and cached queries conserve the same Free count and full duration. These measurements are a local baseline, not a response-time guarantee.

## Unverified acceptance items

- Native Linux/macOS builds and desktop/WebView2 rendering.
- Real profiling imports, DB→Text→DB→Text switching, cache reentry during actual import publication, legal cross-project baseline and live same-project append.
- Pixel-level English/Chinese narrow-column layout, real clipboard integration, exact Timeline highlighting and existing flow display behavior in the running UI.
- Actual parser/Overlap waiting time; large multi-source/candidate-heavy memory growth; per-phase memory; large concurrent first-miss costs.
- Full repository test suite and production frontend bundle.

The implementation is locally reviewable and tested at the business, SQL/protocol and component boundaries above. These unverified items still require target-environment acceptance.
