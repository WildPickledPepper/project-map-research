# R1 最终逐组件事实账

源码 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`；统一快照 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688:full:4c2b04f0c3d14586b8805d8b238678c1`。

沿用 W0 冻结的 124 个运行/库组件与 5 个支持组件。归属、文件和计数核对通过；G02 仍待语义与诊断审查。本表按最接近的必需祖先归属文件，不重复累计嵌套组件。多提供方原生身份分别保留。

无基础事实文件为 0；37 个带独立头文件诊断的源文件仍在审查队列。完整关系种类、逐文件状态和审查标记见[机器账本](evidence/module-fact-audit-final.json)，验收解释见[本轮报告](completion.md)。

| 组件 | 非测试程序源 | 语言 | 无基础事实 | 非 parsed | 入边数 | 出边数 |
|---|---:|---|---:|---:|---:|---:|
| `build` | 11 | python, shell | 0 | 0 | 1 | 11 |
| `docker` | 1 | shell | 0 | 0 | 10 | 0 |
| `modules` | 5 | javascript | 0 | 0 | 63 | 17 |
| `modules/build` | 1 | python | 0 | 0 | 6 | 0 |
| `modules/cluster` | 49 | javascript, tsx, typescript | 0 | 0 | 1346 | 1111 |
| `modules/cluster/src/components/summary/expert-load-balancing` | 3 | tsx | 0 | 0 | 7 | 84 |
| `modules/cluster/src/connection` | 3 | typescript | 0 | 0 | 35 | 85 |
| `modules/cluster/src/store` | 4 | typescript | 0 | 0 | 180 | 15 |
| `modules/compute` | 61 | javascript, tsx, typescript | 0 | 0 | 315 | 827 |
| `modules/compute/src/connection` | 4 | typescript | 0 | 0 | 40 | 64 |
| `modules/compute/src/store` | 3 | typescript | 0 | 0 | 31 | 7 |
| `modules/framework` | 31 | javascript, tsx, typescript | 0 | 0 | 428 | 1421 |
| `modules/framework/src/components/KbdShortcuts` | 1 | tsx | 0 | 0 | 2 | 25 |
| `modules/framework/src/connection` | 7 | typescript | 0 | 0 | 544 | 313 |
| `modules/framework/src/store` | 3 | typescript | 0 | 0 | 110 | 7 |
| `modules/framework/src/utils` | 10 | tsx, typescript | 0 | 0 | 714 | 365 |
| `modules/framework/src/vscode-adapter` | 4 | typescript | 0 | 0 | 141 | 21 |
| `modules/leaks` | 67 | javascript, tsx, typescript | 0 | 0 | 1454 | 1511 |
| `modules/leaks/src/connection` | 3 | typescript | 0 | 0 | 21 | 122 |
| `modules/leaks/src/leaksWorker/blockWorker` | 12 | typescript | 0 | 0 | 797 | 601 |
| `modules/leaks/src/leaksWorker/blockWorker/webgl/shaders` | 2 | typescript | 0 | 0 | 2 | 0 |
| `modules/leaks/src/leaksWorker/stateWorker` | 10 | typescript | 0 | 0 | 75 | 194 |
| `modules/leaks/src/leaksWorker/stateWorker/webgl/shaders` | 2 | typescript | 0 | 0 | 2 | 0 |
| `modules/leaks/src/store` | 3 | typescript | 0 | 0 | 37 | 7 |
| `modules/lib` | 5 | javascript, typescript | 0 | 0 | 462 | 14 |
| `modules/lib/src/LocalStorage` | 2 | typescript | 0 | 0 | 55 | 9 |
| `modules/lib/src/SharedConfigProvider` | 1 | tsx | 0 | 0 | 1 | 3 |
| `modules/lib/src/components` | 18 | tsx, typescript | 0 | 0 | 199 | 70 |
| `modules/lib/src/components/BaseContainer` | 1 | tsx | 0 | 0 | 2 | 3 |
| `modules/lib/src/components/CollapsiblePanel` | 1 | tsx | 0 | 0 | 28 | 11 |
| `modules/lib/src/components/Layout` | 1 | tsx | 0 | 0 | 1 | 1 |
| `modules/lib/src/components/MIContextMenu` | 1 | tsx | 0 | 0 | 1 | 36 |
| `modules/lib/src/components/MIDescriptions` | 1 | tsx | 0 | 0 | 8 | 4 |
| `modules/lib/src/components/MIText` | 1 | tsx | 0 | 0 | 1 | 5 |
| `modules/lib/src/connection` | 1 | typescript | 0 | 0 | 203 | 638 |
| `modules/lib/src/hooks` | 5 | typescript | 0 | 0 | 27 | 16 |
| `modules/lib/src/i18n` | 1 | typescript | 0 | 0 | 59 | 10 |
| `modules/lib/src/icon` | 2 | tsx, typescript | 0 | 0 | 53 | 37 |
| `modules/lib/src/resize` | 6 | tsx, typescript | 0 | 0 | 98 | 129 |
| `modules/lib/src/theme` | 5 | tsx, typescript | 0 | 0 | 120 | 21 |
| `modules/lib/src/useDraggableContainer` | 3 | typescript, tsx | 0 | 0 | 56 | 27 |
| `modules/lib/src/utils` | 14 | typescript, tsx | 0 | 0 | 1288 | 178 |
| `modules/memory` | 28 | javascript, tsx, typescript | 0 | 0 | 172 | 299 |
| `modules/memory-on-chip` | 12 | javascript, tsx, typescript | 0 | 0 | 27 | 91 |
| `modules/memory-on-chip/src/api` | 2 | typescript | 0 | 0 | 34 | 19 |
| `modules/memory-on-chip/src/connection` | 2 | typescript | 0 | 0 | 21 | 4 |
| `modules/memory-on-chip/src/connection/handler` | 3 | typescript | 0 | 0 | 2 | 46 |
| `modules/memory-on-chip/src/pages/Home` | 2 | tsx, typescript | 0 | 0 | 2 | 29 |
| `modules/memory-on-chip/src/stores` | 3 | typescript, tsx | 0 | 0 | 53 | 23 |
| `modules/memory/src/connection` | 3 | typescript | 0 | 0 | 28 | 77 |
| `modules/memory/src/store` | 4 | typescript | 0 | 0 | 28 | 13 |
| `modules/numa` | 36 | javascript, tsx, typescript | 0 | 0 | 35 | 144 |
| `modules/operator` | 19 | javascript, tsx, typescript | 0 | 0 | 133 | 277 |
| `modules/operator/src/connection` | 3 | typescript | 0 | 0 | 90 | 53 |
| `modules/operator/src/store` | 3 | typescript | 0 | 0 | 19 | 7 |
| `modules/reinforcement-learning` | 11 | javascript, tsx, typescript | 0 | 0 | 18 | 53 |
| `modules/reinforcement-learning/src/api` | 2 | typescript | 0 | 0 | 20 | 8 |
| `modules/reinforcement-learning/src/components/common/LocaleProvider` | 1 | tsx | 0 | 0 | 2 | 6 |
| `modules/reinforcement-learning/src/components/common/ThemeProvider` | 1 | tsx | 0 | 0 | 2 | 4 |
| `modules/reinforcement-learning/src/connection` | 2 | typescript | 0 | 0 | 24 | 4 |
| `modules/reinforcement-learning/src/connection/handler` | 4 | typescript | 0 | 0 | 2 | 39 |
| `modules/reinforcement-learning/src/pages/Home` | 3 | tsx | 0 | 0 | 2 | 85 |
| `modules/reinforcement-learning/src/stores` | 4 | typescript, tsx | 0 | 0 | 55 | 16 |
| `modules/statistic` | 22 | javascript, tsx, typescript | 0 | 0 | 46 | 180 |
| `modules/statistic/src/connection` | 3 | typescript | 0 | 0 | 22 | 47 |
| `modules/statistic/src/store` | 4 | typescript | 0 | 0 | 22 | 13 |
| `modules/timeline` | 70 | javascript, tsx, typescript | 0 | 0 | 2435 | 1203 |
| `modules/timeline/src/actions` | 33 | typescript, tsx | 0 | 0 | 401 | 725 |
| `modules/timeline/src/cache` | 4 | typescript | 0 | 0 | 94 | 61 |
| `modules/timeline/src/cache/strategies` | 7 | typescript | 0 | 0 | 33 | 129 |
| `modules/timeline/src/components/ChartContainer` | 8 | tsx, typescript | 0 | 0 | 98 | 220 |
| `modules/timeline/src/components/ChartContainer/Units` | 5 | tsx, typescript | 0 | 0 | 118 | 305 |
| `modules/timeline/src/components/ChartContainer/Units/hooks` | 3 | tsx | 0 | 0 | 30 | 55 |
| `modules/timeline/src/components/base` | 13 | tsx, typescript | 0 | 0 | 112 | 32 |
| `modules/timeline/src/components/charts` | 18 | tsx, typescript | 0 | 0 | 200 | 450 |
| `modules/timeline/src/components/charts/ChartInteractor` | 8 | tsx, typescript | 0 | 0 | 76 | 331 |
| `modules/timeline/src/components/detailViews` | 18 | tsx | 0 | 0 | 148 | 875 |
| `modules/timeline/src/connection` | 5 | typescript | 0 | 0 | 65 | 336 |
| `modules/timeline/src/platforms` | 3 | typescript | 0 | 0 | 36 | 8 |
| `modules/timeline/src/renderEngine` | 1 | tsx | 0 | 0 | 11 | 10 |
| `modules/timeline/src/store` | 4 | typescript | 0 | 0 | 70 | 27 |
| `modules/timeline/src/utils` | 27 | tsx, typescript | 0 | 0 | 548 | 262 |
| `platform` | 13 | rust | 0 | 0 | 20 | 16 |
| `plugins/ProfilerServerProxy` | 9 | python | 0 | 0 | 142 | 45 |
| `plugins/ProfilerServerProxy/core` | 1 | python | 0 | 0 | 0 | 0 |
| `plugins/ProfilerServerProxy/core/proxy` | 2 | python | 0 | 0 | 19 | 62 |
| `plugins/ProfilerServerProxy/core/server` | 2 | python | 0 | 0 | 36 | 91 |
| `plugins/jupyterlab` | 17 | python, tsx, typescript, javascript | 0 | 0 | 185 | 25 |
| `plugins/jupyterlab/mindstudio_insight_jupyterlab` | 2 | python | 0 | 0 | 0 | 7 |
| `scripts/MemSnapDump/base` | 2 | python | 0 | 0 | 440 | 1 |
| `scripts/MemSnapDump/simulate` | 9 | python | 0 | 0 | 41 | 400 |
| `scripts/MemSnapDump/tools` | 2 | python | 0 | 0 | 0 | 3 |
| `scripts/MemSnapDump/tools/adaptors` | 2 | python | 0 | 0 | 2 | 213 |
| `scripts/MemSnapDump/tools/adaptors/database` | 4 | python | 0 | 0 | 52 | 100 |
| `scripts/MemSnapDump/util` | 6 | python | 0 | 0 | 179 | 15 |
| `scripts/cpu_binding_tools` | 7 | python, javascript | 0 | 0 | 35 | 104 |
| `scripts/cpu_binding_tools/cpu_binding_utils` | 4 | python | 0 | 0 | 93 | 0 |
| `scripts/flame_graph` | 2 | javascript, python | 0 | 0 | 0 | 23 |
| `scripts/ftrace_tools` | 4 | python | 0 | 0 | 13 | 9 |
| `scripts/ftrace_tools/examples` | 3 | python | 0 | 0 | 12 | 24 |
| `scripts/memscope_adaptors/memscope` | 4 | python | 0 | 0 | 54 | 92 |
| `scripts/memscope_adaptors/prof2memscope` | 4 | python | 0 | 0 | 0 | 63 |
| `scripts/memscope_adaptors/utils` | 2 | python | 0 | 0 | 111 | 0 |
| `server` | 4 | python | 0 | 0 | 2 | 9 |
| `server/msinsight` | 52 | cpp | 0 | 2 | 32075 | 599 |
| `server/src/defs` | 1 | cpp | 0 | 0 | 5 | 1 |
| `server/src/entry/server/bin` | 1 | cpp | 0 | 0 | 22 | 496 |
| `server/src/modules` | 8 | cpp | 0 | 0 | 1095 | 346 |
| `server/src/modules/advisor` | 41 | cpp | 0 | 1 | 351 | 1960 |
| `server/src/modules/base` | 17 | cpp | 0 | 1 | 9960 | 1008 |
| `server/src/modules/communication` | 72 | cpp | 0 | 0 | 3121 | 5677 |
| `server/src/modules/defs` | 7 | cpp | 0 | 2 | 2853 | 219 |
| `server/src/modules/full_db` | 45 | cpp | 0 | 0 | 691 | 6554 |
| `server/src/modules/global` | 43 | cpp | 0 | 1 | 1676 | 2080 |
| `server/src/modules/memory` | 52 | cpp | 0 | 7 | 335 | 4228 |
| `server/src/modules/memscope` | 33 | cpp | 0 | 2 | 290 | 2715 |
| `server/src/modules/memsnapshot` | 37 | cpp | 0 | 0 | 331 | 2604 |
| `server/src/modules/numa` | 22 | cpp | 0 | 0 | 42 | 510 |
| `server/src/modules/operator` | 36 | cpp | 0 | 3 | 246 | 3079 |
| `server/src/modules/rl` | 25 | cpp | 0 | 0 | 42 | 547 |
| `server/src/modules/servitization` | 27 | cpp | 0 | 1 | 147 | 962 |
| `server/src/modules/source` | 52 | cpp | 0 | 3 | 1940 | 3790 |
| `server/src/modules/summary` | 65 | cpp | 0 | 3 | 1053 | 5737 |
| `server/src/modules/timeline` | 297 | cpp | 0 | 11 | 7152 | 19455 |
| `server/src/modules/triton` | 23 | cpp | 0 | 0 | 66 | 769 |
| `server/src/protocol` | 3 | cpp | 0 | 0 | 163 | 102 |
| `server/src/server` | 6 | cpp | 0 | 0 | 190 | 389 |
| `server/src/utils` | 5 | cpp | 0 | 0 | 124 | 49 |
| `streamer` | 2 | python | 0 | 0 | 1 | 0 |
