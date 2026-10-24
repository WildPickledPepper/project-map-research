# Project map

Source: `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`

Query: overview. Items 0–34 of 34.
Truncated: false.

## Whole repository inventory

| Language | Tracked files | Graph input files |
|---|---:|---:|
| C++ | 725 | 39 |
| C/C++ header | 598 | 103 |
| CMake | 13 | 0 |
| JavaScript | 53 | 0 |
| Python | 119 | 0 |
| Rust | 13 | 0 |
| Shell | 8 | 0 |
| TypeScript | 549 | 31 |
| TypeScript/React | 384 | 7 |

Top-level directories (including unexpanded parts):

| Directory | Tracked | Graph inputs |
|---|---:|---:|
| .gitcode | 5 | 0 |
| <root> | 13 | 1 |
| assets | 1 | 0 |
| build | 14 | 0 |
| docker | 12 | 0 |
| docs | 1589 | 0 |
| e2e | 288 | 0 |
| modules | 1160 | 48 |
| platform | 24 | 0 |
| plugins | 57 | 0 |
| pre-commit | 3 | 0 |
| scripts | 120 | 0 |
| server | 1417 | 142 |
| streamer | 4 | 0 |
| test | 148 | 0 |

Use `coverage` for supported mechanisms and source candidates; lexical matches are not connections.

## Selected module navigation

| Module | Tracked files | Analyzed files | Semantic coverage |
|---|---:|---:|---|
| modules/build | 1 | 0 | not_expanded |
| modules/cluster | 73 | 0 | not_expanded |
| modules/compute | 77 | 0 | not_expanded |
| modules/framework | 69 | 13 | selected_files |
| modules/leaks | 145 | 0 | not_expanded |
| modules/lib | 159 | 7 | selected_files |
| modules/memory | 59 | 10 | selected_files |
| modules/memory-on-chip | 28 | 0 | not_expanded |
| modules/numa | 53 | 0 | not_expanded |
| modules/operator | 30 | 0 | not_expanded |
| modules/reinforcement-learning | 32 | 0 | not_expanded |
| modules/statistic | 33 | 0 | not_expanded |
| modules/testing | 16 | 0 | not_expanded |
| modules/timeline | 375 | 16 | selected_files |
| server/msinsight | 53 | 19 | selected_files |
| server/src/modules/advisor | 41 | 1 | selected_files |
| server/src/modules/base | 17 | 0 | not_expanded |
| server/src/modules/communication | 72 | 1 | selected_files |
| server/src/modules/defs | 7 | 1 | selected_files |
| server/src/modules/full_db | 45 | 4 | selected_files |
| server/src/modules/global | 43 | 3 | selected_files |
| server/src/modules/memory | 52 | 22 | selected_files |
| server/src/modules/memscope | 33 | 1 | selected_files |
| server/src/modules/memsnapshot | 37 | 0 | not_expanded |
| server/src/modules/numa | 22 | 1 | selected_files |
| server/src/modules/operator | 36 | 1 | selected_files |
| server/src/modules/rl | 25 | 1 | selected_files |
| server/src/modules/servitization | 27 | 1 | selected_files |
| server/src/modules/source | 52 | 1 | selected_files |
| server/src/modules/summary | 65 | 1 | selected_files |
| server/src/modules/timeline | 298 | 70 | selected_files |
| server/src/modules/triton | 23 | 1 | selected_files |
| server/src/protocol | 3 | 1 | selected_files |
| server/src/server | 6 | 6 | selected_files |

## modules/build

Responsibility: unspecified in selected package metadata; inspect the source entries below.

## modules/cluster

@insight/cluster — `modules/cluster/package.json:1`
Build/run scripts: `{"start": "cross-env NODE_OPTIONS=--openssl-legacy-provider craco start", "build": "cross-env NODE_OPTIONS=\"==--max-old-space-size=3072 --openssl-legacy-provider\" NODE_ENV=production GENERATE_SOURCEMAP=false CI=false craco build", "build:dev": "cross-env GENERATE_SOURCEMAP=true CI=false craco build", "build:vscode": "cross-env NODE_OPTIONS=\"==--max-old-space-size=3072 --openssl-legacy-provider\" NODE_ENV=production REACT_APP_IS_VSCODE=true GENERATE_SOURCEMAP=false CI=false craco build && node ../inline-build.js", "test": "node ../testing/run.cjs --module cluster", "test:dev": "node ../testing/run.cjs --module cluster --watch", "eject": "react-scripts eject", "lint": "eslint src --fix", "dt": "set BROWSER=none&&set REACT_APP_TEST=1&&react-scripts start"}`

## modules/compute

@insight/compute — `modules/compute/package.json:1`
Build/run scripts: `{"start": "cross-env NODE_OPTIONS=--openssl-legacy-provider craco start", "build": "cross-env NODE_OPTIONS=--openssl-legacy-provider NODE_ENV=production GENERATE_SOURCEMAP=false CI=false craco build", "build:vscode": "cross-env NODE_OPTIONS=--openssl-legacy-provider NODE_ENV=production GENERATE_SOURCEMAP=false CI=false REACT_APP_IS_VSCODE=true craco build && node ../inline-build.js", "build:dev": "cross-env GENERATE_SOURCEMAP=true CI=false craco build", "test": "node ../testing/run.cjs --module compute", "test:dev": "node ../testing/run.cjs --module compute --watch", "eject": "react-scripts eject", "lint": "eslint src --fix", "dt": "set BROWSER=none&&set REACT_APP_TEST=1&&react-scripts start"}`

## modules/framework

@insight/framework — `modules/framework/package.json:1`
Build/run scripts: `{"build:vscode": "cross-env NODE_OPTIONS=--openssl-legacy-provider NODE_ENV=production REACT_APP_IS_VSCODE=true DISABLE_ESLINT_PLUGIN=true GENERATE_SOURCEMAP=false CI=false craco build && node ../inline-build.js", "start": "cross-env NODE_OPTIONS=--openssl-legacy-provider REACT_APP_ENV=development craco start", "staging": "cross-env NODE_OPTIONS=--openssl-legacy-provider craco start", "build": "cross-env NODE_OPTIONS=--openssl-legacy-provider NODE_ENV=production GENERATE_SOURCEMAP=false CI=false craco build", "test": "node ../testing/run.cjs --module framework", "eject": "react-scripts eject", "test:dev": "node ../testing/run.cjs --module framework --watch"}`
- protocol_message: memoryTypeGet message — `modules/framework/src/centralServer/websocket/connection.ts:284`
- protocol_message: resourceTypeGet message — `modules/framework/src/centralServer/websocket/connection.ts:284`
- protocol_message: staticOpMemoryListGet message — `modules/framework/src/centralServer/websocket/connection.ts:284`
- protocol_message: staticOpMemoryGraphGet message — `modules/framework/src/centralServer/websocket/connection.ts:284`
- protocol_message: operatorsMemoryGet message — `modules/framework/src/centralServer/websocket/connection.ts:284`
- protocol_message: memoryCurveGet message — `modules/framework/src/centralServer/websocket/connection.ts:284`
- protocol_message: fetchTableDataByComponent message — `modules/framework/src/centralServer/websocket/connection.ts:284`
- protocol_message: fetchOperatorPosition message — `modules/framework/src/centralServer/websocket/connection.ts:284`
- protocol_message: fetchDynamicOperatorMaxMin message — `modules/framework/src/centralServer/websocket/connection.ts:284`
- protocol_message: fetchStaticOperatorMaxMin message — `modules/framework/src/centralServer/websocket/connection.ts:284`
- protocol_message: queryFtraceStat message — `modules/framework/src/centralServer/websocket/connection.ts:284`
- protocol_message: parseCards message — `modules/framework/src/centralServer/websocket/connection.ts:284`
Entry list truncated; use trace/search for the remaining entries.

## modules/leaks

@insight/leaks — `modules/leaks/package.json:1`
Build/run scripts: `{"start": "cross-env NODE_OPTIONS=--openssl-legacy-provider craco start", "build": "cross-env NODE_OPTIONS=--openssl-legacy-provider NODE_ENV=production GENERATE_SOURCEMAP=false CI=false craco build", "build:vscode": "cross-env NODE_OPTIONS=--openssl-legacy-provider NODE_ENV=production REACT_APP_IS_VSCODE=true GENERATE_SOURCEMAP=false CI=false craco build && node ../inline-build.js", "build:dev": "cross-env GENERATE_SOURCEMAP=true CI=false craco build", "test": "node ../testing/run.cjs --module leaks", "test:dev": "node ../testing/run.cjs --module leaks --watch", "eject": "react-scripts eject", "lint": "eslint src --fix", "dt": "set BROWSER=none&&set REACT_APP_TEST=1&&react-scripts start"}`

## modules/lib

@insight/lib — `modules/lib/package.json:1`
Build/run scripts: `{"start": "cross-env NODE_OPTIONS=--openssl-legacy-provider craco start", "test": "node ../testing/run.cjs --module lib", "eject": "react-scripts eject", "test:dev": "node ../testing/run.cjs --module lib --watch"}`

## modules/memory

@insight/memory — `modules/memory/package.json:1`
Build/run scripts: `{"start": "cross-env NODE_OPTIONS=--openssl-legacy-provider craco start", "build": "cross-env NODE_OPTIONS=--openssl-legacy-provider NODE_ENV=production GENERATE_SOURCEMAP=false CI=false craco build", "build:vscode": "cross-env NODE_OPTIONS=--openssl-legacy-provider NODE_ENV=production REACT_APP_IS_VSCODE=true GENERATE_SOURCEMAP=false CI=false craco build && node ../inline-build.js", "build:dev": "cross-env GENERATE_SOURCEMAP=true CI=false craco build", "test": "node ../testing/run.cjs --module memory", "test:dev": "node ../testing/run.cjs --module memory --watch", "eject": "react-scripts eject", "lint": "eslint src --fix", "dt": "set BROWSER=none&&set REACT_APP_TEST=1&&react-scripts start"}`

## modules/memory-on-chip

@insight/triton-new — `modules/memory-on-chip/package.json:1`
Build/run scripts: `{"start": "craco start", "build": "craco build", "test": "node ../testing/run.cjs --module memory-on-chip", "test:dev": "node ../testing/run.cjs --module memory-on-chip --watch"}`

## modules/numa

@insight/numa — `modules/numa/package.json:1`
Build/run scripts: `{"start": "craco start", "build": "craco build", "test": "node ../testing/run.cjs --module numa", "test:dev": "node ../testing/run.cjs --module numa --watch"}`

## modules/operator

@insight/operator — `modules/operator/package.json:1`
Build/run scripts: `{"start": "cross-env NODE_OPTIONS=--openssl-legacy-provider craco start", "build": "cross-env NODE_OPTIONS=--openssl-legacy-provider NODE_ENV=production GENERATE_SOURCEMAP=false CI=false craco build", "build:vscode": "cross-env NODE_OPTIONS=--openssl-legacy-provider NODE_ENV=production GENERATE_SOURCEMAP=false CI=false REACT_APP_IS_VSCODE=true craco build && node ../inline-build.js", "build:dev": "cross-env GENERATE_SOURCEMAP=true CI=false craco build", "test": "node ../testing/run.cjs --module operator", "test:dev": "node ../testing/run.cjs --module operator --watch", "eject": "react-scripts eject", "lint": "eslint src --fix", "dt": "set BROWSER=none&&set REACT_APP_TEST=1&&react-scripts start"}`

## modules/reinforcement-learning

@insight/learning — `modules/reinforcement-learning/package.json:1`
Build/run scripts: `{"start": "craco start", "build": "craco build", "build:vscode": "cross-env NODE_OPTIONS=--openssl-legacy-provider NODE_ENV=production GENERATE_SOURCEMAP=false CI=false REACT_APP_IS_VSCODE=true craco build && node ../inline-build.js", "test": "node ../testing/run.cjs --module reinforcement-learning", "test:dev": "node ../testing/run.cjs --module reinforcement-learning --watch"}`

## modules/statistic

@insight/statistic — `modules/statistic/package.json:1`
Build/run scripts: `{"start": "cross-env NODE_OPTIONS=--openssl-legacy-provider craco start", "build": "cross-env NODE_OPTIONS=--openssl-legacy-provider NODE_ENV=production GENERATE_SOURCEMAP=false CI=false craco build", "build:vscode": "cross-env NODE_OPTIONS=--openssl-legacy-provider NODE_ENV=production GENERATE_SOURCEMAP=false CI=false REACT_APP_IS_VSCODE=true craco build && node ../inline-build.js", "build:dev": "cross-env GENERATE_SOURCEMAP=true CI=false craco build", "test": "node ../testing/run.cjs --module statistic", "test:dev": "node ../testing/run.cjs --module statistic --watch", "eject": "react-scripts eject", "lint": "eslint src --fix", "dt": "set BROWSER=none&&set REACT_APP_TEST=1&&react-scripts start"}`

## modules/testing

Responsibility: unspecified in selected package metadata; inspect the source entries below.

## modules/timeline

@insight/timeline — `modules/timeline/package.json:1`
Build/run scripts: `{"start": "cross-env NODE_OPTIONS=--openssl-legacy-provider craco start", "build": "cross-env NODE_OPTIONS=\"==--max-old-space-size=3072 --openssl-legacy-provider\" NODE_ENV=production GENERATE_SOURCEMAP=false CI=false craco build", "build:vscode": "cross-env NODE_OPTIONS=\"==--max-old-space-size=3072 --openssl-legacy-provider\" NODE_ENV=production REACT_APP_IS_VSCODE=true GENERATE_SOURCEMAP=false CI=false craco build && node ../inline-build.js", "build:dev": "cross-env GENERATE_SOURCEMAP=true CI=false craco build", "test": "node ../testing/run.cjs --module timeline", "test:dev": "node ../testing/run.cjs --module timeline --watch", "eject": "react-scripts eject", "lint": "eslint src", "eslintfix": "eslint --fix src", "dt": "set BROWSER=none&&set REACT_APP_TEST=1&&react-scripts start"}`

## server/msinsight

cmake_build — `server/msinsight/CMakeLists.txt:1`

Dependencies declared in source:

- target_link_libraries: ${PROJECT_NAME} shlwapi  — `server/msinsight/CMakeLists.txt:15`
- target_link_libraries: ${PROJECT_NAME} pthread dl stdc++fs  — `server/msinsight/CMakeLists.txt:17`
- target_link_libraries: ${PROJECT_NAME} pthread dl  — `server/msinsight/CMakeLists.txt:19`

## server/src/modules/advisor

Responsibility: unspecified in selected package metadata; inspect the source entries below.

## server/src/modules/base

Responsibility: unspecified in selected package metadata; inspect the source entries below.

## server/src/modules/communication

Responsibility: unspecified in selected package metadata; inspect the source entries below.

## server/src/modules/defs

Responsibility: unspecified in selected package metadata; inspect the source entries below.

## server/src/modules/full_db

Responsibility: unspecified in selected package metadata; inspect the source entries below.

## server/src/modules/global

Responsibility: unspecified in selected package metadata; inspect the source entries below.

## server/src/modules/memory

Responsibility: unspecified in selected package metadata; inspect the source entries below.
- protocol_registration: Memory/view/memoryUsage — `server/src/modules/memory/MemoryModule.cpp:47`

## server/src/modules/memscope

Responsibility: unspecified in selected package metadata; inspect the source entries below.

## server/src/modules/memsnapshot

Responsibility: unspecified in selected package metadata; inspect the source entries below.

## server/src/modules/numa

Responsibility: unspecified in selected package metadata; inspect the source entries below.

## server/src/modules/operator

Responsibility: unspecified in selected package metadata; inspect the source entries below.

## server/src/modules/rl

Responsibility: unspecified in selected package metadata; inspect the source entries below.

## server/src/modules/servitization

Responsibility: unspecified in selected package metadata; inspect the source entries below.

## server/src/modules/source

Responsibility: unspecified in selected package metadata; inspect the source entries below.

## server/src/modules/summary

Responsibility: unspecified in selected package metadata; inspect the source entries below.

## server/src/modules/timeline

Responsibility: unspecified in selected package metadata; inspect the source entries below.
- protocol_registration: systemView/systemViewFtraceStat — `server/src/modules/timeline/TimelineModule.cpp:121`
- protocol_registration: parse/cards — `server/src/modules/timeline/TimelineModule.cpp:91`
- protocol_registration: systemView/overall — `server/src/modules/timeline/TimelineModule.cpp:113`
- protocol_registration: systemView/overall — `server/src/modules/timeline/TimelineModule.cpp:113`
- protocol_registration: systemView/overall/more/details — `server/src/modules/timeline/TimelineModule.cpp:114`
- protocol_registration: memcpy/total/list — `server/src/modules/timeline/TimelineModule.cpp:118`
- protocol_registration: memcpy/detail/list — `server/src/modules/timeline/TimelineModule.cpp:120`
- protocol_registration: unit/setCardAlias — `server/src/modules/timeline/TimelineModule.cpp:89`
- protocol_registration: expertAnalysis/AICoreFreq — `server/src/modules/timeline/TimelineModule.cpp:116`
- protocol_registration: query/all/same/operators/duration — `server/src/modules/timeline/TimelineModule.cpp:110`
- protocol_registration: unit/kernelDetail — `server/src/modules/timeline/TimelineModule.cpp:109`
- protocol_registration: create/curve — `server/src/modules/timeline/TimelineModule.cpp:117`
Entry list truncated; use trace/search for the remaining entries.

## server/src/modules/triton

Responsibility: unspecified in selected package metadata; inspect the source entries below.

## server/src/protocol

Responsibility: unspecified in selected package metadata; inspect the source entries below.

## server/src/server

Responsibility: unspecified in selected package metadata; inspect the source entries below.

Structure covers tracked files. Semantic coverage is limited to the selected graph inputs. P6 historical assets: not connected.
