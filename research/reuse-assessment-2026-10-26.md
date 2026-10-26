# 复用评估：把语言分析交还给现成工具

日期：2026-10-26。首版为现有实现审计、上游源码/文档核对和迁移决策，当时未执行新引擎。随后按用户要求完成[源码接口核实](reuse-source-contracts-2026-10-26.md)和[原生组件探针](../experiments/2026-10-26-reuse-audit/README.md)。**当前准入与取舍以这两份报告为准**：Clang/SQL/运行 SDK 有限定成功，Joern 有明确别名/Rust 缺口，CBM 的复用角色扩大到边界组件且保留启动阻塞。功能开发保持停止，整体 G01–G08 状态不变。

**先继承已有调研，不重新选型。** 工作顺序是：复用已经通过的组件 → 核查这些工具已有但未启用的扩展 → 为已确认缺口引入专门引擎。下文新增候选仅补最后一类缺口，不重新下载/重测所有已调查工具。

## 0. 已有工具的组件复用账

| 已调查项目 | 已有结果与具体组件 | 当前决定 |
|---|---|---|
| **CGC 0.6.13** | P1 已选事实/存储主底座；W1 已保留 185 文件原生解析输出。现成 `ScipIndexer`、`ScipIndexParser` 及 `tools/indexing/scip_pipeline.py` 负责索引器调度、SCIP 解析与入图，真实 SCIP 路径此前未执行 | 保留已通过的接口和原生记录。先复用现有 SCIP 导入/调度，不另写 Protobuf 解析器；索引器环境与精度单独验收。 |
| **CodeGraph 1.39.0** | P1 已验证 `pm_fact_*` 扩展及原版 SQL CLI 查询；`crates/codegraph-resolve/src/lib.rs::import_scip` 是现成 SCIP 合并入口 | 保留可替换底座与导入备选。该实现依赖已有节点并按文件/行映射，函数引用会投影为 Calls，字段/参数没有进入该关系投影；应保留引用性质，不能未经检查当作精确调用或字段流。 |
| **CBM 0.12.1** | 已执行过滤全仓索引、watcher 切换/删除及快照 fixture；同名、重载和覆盖调用有已知错连 | 导航/更新对照结果直接继承。现有维护底座已经可用，不为采用其 watcher 再重写发布系统；其调用边保持原证据等级。 |
| **code-map** | 已执行 46 文件切片及受支持 HTTP 对照；`src/core/endpoints.mjs` 有接口归一化/匹配和可组合 extractor | 标准 HTTP 机制优先审查这个现成扩展点；已有 `/api` 限定、多服务身份和 C++ 缺失结果直接继承。只有实际适配需要时接入，保留 AGPL-3.0 要求；不照抄一个缺少服务域的匹配器。 |
| **RPG/CoderMind** | 已运行 `DependencyGraph.build()/parse()` 和结构/增量测试；源码绑定、功能树与摘要的职责已有调查 | 依赖组织/地图接口保留复用资格；已有结构输出作为候选事实。完整 LLM 功能树放到可靠事实之后，避免重复写职责摘要系统。 |
| **RepoGraph** | 已下载和审计定义/引用图及检索方式；有记录结构不一致和同名身份问题 | 保留检索组织参考；不再运行相同选型试验，不把它提升为类型/字段流主引擎。 |
| **Code-Craft** | 官方实现与可执行版本尚未核实，未完成开源实现实测 | 保留待核实状态，不列为已测试或可直接迁移的组件。 |

继承证据：[最早实测](experiments/2026-10-23.md)、[CodeGraph/code-map](../experiments/2026-10-23-unit-flows/README.md)、[P1 选择及 SCIP 审计](../experiments/2026-10-23-p1/selection.md)、[P1 完成与存储](../experiments/2026-10-23-p1-completion/README.md)、[W1 原生输出](../experiments/2026-10-25-w1/README.md)。本轮又核对了本地源码扩展入口，未执行新测试。

## 1. 当前路线的问题

P1 选择 CGC/Kuzu 时，已验证的是必要符号、候选关系和存储维护。其[完成报告](../experiments/2026-10-23-p1-completion/README.md)明确记录 C++ SCIP 未执行，预处理、别名和重载没有经过编译器证明。

后续为了补链，自有适配逐步承担 C++ 类型恢复、跨函数参数传播、字段/对象关系，以及 Python/Rust 路径值解释。直接复用了语法树、TS 编译器、Jedi 和 rust-analyzer，但其中部分适配已经具有通用程序分析器的职责。当前 `adapters` 有 105 个文件；文件数只用于说明审计规模，不作质量评价。

近期重复投入的具体位置包括 `cpp_value_types.py`、`cpp_field_flow.py`、`cpp_instances.py`、`cpp_argv_origins.py`，以及尚未提交的 `cpp_member_returns.py`。这些能力应先比较现成语义索引和数据流引擎，再决定保留的范围。原版工具缺少完整业务链，并不能推出每个语言分析环节都要自己实现。

## 2. 按能力选择提供方

“保留”表示已有实测可继续使用；“优先试接”表示查到可用接口，尚未在本环境证明替代效果。每种能力只锁定一个主提供方，备选仅在主提供方失败后启用。

| 能力 | 复用决定 | 我们负责的部分 | 当前证据 |
|---|---|---|---|
| 文件/模块地图、版本、SQLite 导航、CLI/MCP、更新发布 | 保留现有实现和 SQLite；保留已经验证的 CGC 结果与存储接口 | 统一来源、覆盖状态、提供方输出导入 | 已有 P/A/W 阶段实测；不再迁移一套图数据库 |
| TS/JS 定义、调用、类型和引用 | 保留 TypeScript Compiler API | 导出为统一节点/边；业务边界模型消费编译器事实 | 已有真实仓库及变更实测 |
| Python 符号与调用候选 | 保留 AST/Jedi | 包上下文和图归一化 | 已有 119 文件实测；不再写第二套解析器 |
| Rust 符号与配置 | 保留 Cargo/rust-analyzer | 保留 cfg、crate、源位置和原生目标身份 | 已有 13 文件及配置/更新实测 |
| C++ 定义、引用、重载、成员及返回类型 | 先核查 CGC 已有 SCIP 入口；当前 Windows 环境若不能生成可用索引，则试接 clangd；SCIP 仅提供其实际包含的语义 | 编译数据库/依赖上下文、符号与源位置映射；语义 AST 补索引未提供的返回类型信息 | 旧 P1 已记录 SCIP 未执行及平台问题；clangd 官方接口核对 |
| 跨函数数据依赖、控制依赖、字段流 | 已调查图工具缺少相应实测能力，限定引入 Joern 补这个空缺，首先验证 C++；保留可用的 TS/Python 原生链 | 查询脚本、输出归一化、模型配置；保留候选与精度来源 | 已有工具缺口记录及本轮源码核对；Joern 官方接口/源码核对，未运行 |
| Rust 数据流 | 先保留已验证的有限边界模板；R0 单列验证 Joern rust2cpg | 导入实际可用的输出；不继续扩成自有 Rust 通用解释器 | 固定版本有 rust2cpg 源码和测试；等价精度未验证 |
| SQL AST、表/列及 SELECT 血缘 | 优先试接 SQLGlot | 从宿主代码取得 SQL/参数；绑定数据库实例、结果字段和消费者 | 官方 lineage API 和 MIT 文件核对；未运行 |
| CMake/Cargo 目标、编译输入、产物和配置 | 保留 CMake File API、Cargo metadata/JSON | 将原生输出与源码/部署边界关联；能取构建收据时优先取收据 | 已有真实 CMake/Cargo 控制；不再手写构建系统 |
| Shell、容器和声明资源 | 复用现有 Tree-sitter 的对应 grammar 及标准配置解析库 | exec/ENTRYPOINT/环境/卷等有限机制模型 | 现有账本已暴露整块缺项；本轮仅确定路线，待实测 |
| 标准框架接口发现 | 已有模型继续用；需要扩展时先核对 OWASP Noir 的对应框架规则 | 导入接口位置/参数，再与语义事实连接 | Noir 官方实现/文档核对；不作为任意自定义协议解法 |
| 运行采集、关联和导出 | 优先复用 OpenTelemetry SDK、可用的现成 instrumentation 和 OTLP | 自定义协议传播、状态事件、静态图映射及独立断言 | SDK 官方接口核对；既有采集结果保留，OTel 新接入未测 |
| 浏览器驱动和界面证据 | 复用 Playwright 及已有 P5/A5 场景 | 业务结果、切换/取消/清理和资源断言 | 既有场景已实测；不再写浏览器驱动或 trace viewer |
| 项目职责摘要 | 先用模块/导出/依赖生成确定性地图；RPG/CoderMind 可后置提供摘要 | 摘要绑定源码版本和事实，不参与确定连接判定 | RPG 的结构模块有既有实测；完整 LLM 地图未验收 |

### 固定版本与平台核对

- **Joern v4.0.665**，提交 `d7a5615a30cbce12986f7a0dae9a938a5b99985e`，Apache-2.0。已核对 [README](https://github.com/joernio/joern/blob/d7a5615a30cbce12986f7a0dae9a938a5b99985e/README.md)、[发布页](https://github.com/joernio/joern/releases/tag/v4.0.665)及 [LICENSE](https://github.com/joernio/joern/blob/d7a5615a30cbce12986f7a0dae9a938a5b99985e/LICENSE)。该版要求 JDK 21，提供 Windows x86_64 分发包，压缩包约 1.78 GB；安装和下载需单独计时。无需为试接先编译 Joern。
- 该版 [jssrc2cpg](https://github.com/joernio/joern/blob/d7a5615a30cbce12986f7a0dae9a938a5b99985e/joern-cli/frontends/jssrc2cpg/README.md)明确处理 JS/TS；源码有 [rust2cpg](https://github.com/joernio/joern/tree/d7a5615a30cbce12986f7a0dae9a938a5b99985e/joern-cli/frontends/rust2cpg)。在线 frontends 总表未列 Rust，故以固定分发包实际探测为准，不把源码目录存在当作生产能力通过。
- **scip-clang** 核对提交 `14423f07d164e640b7ffe2de937789653d63708c`。[README](https://github.com/sourcegraph/scip-clang/blob/14423f07d164e640b7ffe2de937789653d63708c/README.md)列出的二进制平台是 Linux x86_64 和 macOS arm64，依赖编译数据库。当前 Windows 环境优先 clangd，不能把 scip-clang 写成可立即安装的 Windows 主路线。SCIP 是符号索引格式，不等于数据流引擎。
- **clangd** 的[特性](https://clangd.llvm.org/features)和[语义 AST 扩展](https://clangd.llvm.org/extensions#ast)提供复用接口；实际工具版本、可用调用层级、编译参数及依赖缺失由 R0 记录，当前尚未锁定一个已安装版本。
- SQLGlot、OpenTelemetry、Playwright 新增依赖在 R0/对应接入阶段锁定版本；已有 Playwright 场景保留原版本。当前文档核对不是新版本行为实测。

## 3. 必须保留的连接层

我们的工程工作集中在以下接口，并优先使用上游已有 API、查询语言和模型扩展点：

1. **结果归一化**：将不同工具的符号、依赖和源码证据映射到同一个版本化图；保留提供方原生 ID、配置和精度。函数调用、数据依赖、可能别名和运行观察使用不同关系。
2. **机制模型**：描述项目实际采用的消息字段、注册表、回调表、序列化、进程/文件边界和缓存 API。规则根据调用/声明结构发现名称与两端，不填写业务端点答案。
3. **跨边界连接**：将发送和注册、启动和监听、SQL 与宿主参数、返回字段与消费者按身份和条件连接。标准框架先导入现成模型，自定义封装再补有限模型。
4. **运行与覆盖适配**：在实验副本中增加必要传播/状态事件，将实际记录映射回静态事实；提供分母、断点、预算续查及失败恢复。

缓存所有者、请求身份、结果采用和生命周期含有应用语义。现成引擎提供分析能力，具体 API 的模型和结果断言仍需接入。新模型不能偷偷实现一套重载解析、别名求解或通用控制/数据流算法。

## 4. 对其他已调查工具的处理

| 工具 | 本轮处理与依据 |
|---|---|
| CGC / CBM / CodeGraph | 保留已经完成的对照与可复用接口。它们的原生调用/索引缺口见 [P1](../experiments/2026-10-23-p1-completion/README.md)；CodeGraph 存储可用，但换存储不能填补语义缺口。停止同时维护多个完整主底座。 |
| code-map | 已有 [unit/flows 实测](../experiments/2026-10-23-unit-flows/README.md)显示前端 import/特定 HTTP 连接有价值，C++ 与自定义链未贯通；本轮不引入为主依赖，避免再维护一套地图。 |
| RepoGraph | 已有定义/引用构图及同名身份缺口，继续保留研究证据，不承担新的类型/数据流职责。 |
| RPG/CoderMind | 功能摘要后置；避免把模型推断当作基础连接，当前不投入完整 LLM 地图。 |
| CodeQL | 现行官方文档覆盖本项目几种主要语言，值得作为精度对照；CLI 有独立使用条款，不作为可随本项目自由改造分发的默认开源核心。本轮不并行搭建第二套全仓数据流系统。 |
| Semgrep CE / Noir | 可复用的确定性规则或标准框架发现候选。Semgrep CE 不承担本方案的跨文件数据流主引擎，Noir 的 LLM fallback 默认关闭。仅在账本出现相应需求时启用，避免工具堆叠。 |

## 5. 替换顺序与保留方式

| 现有部分 | 决策 |
|---|---|
| `projectmap/*`、模块/覆盖账本、SQLite 导航、快照维护 | 保留，提供方从接口接入；本轮不重写查询和发布系统。 |
| TS Compiler API、Python/Jedi、Cargo/rust-analyzer、CMake File API | 保留原生复用；只修复实测显示的集成问题。 |
| `cpp_value_types.py`、`cpp_library_types.py`、基础声明/引用补充 | 停止扩展，优先以 clangd/Joern 原生信息替换职责；旧输出保留候选标记及回归基线。 |
| `cpp_field_flow.py`、`cpp_instances.py`、`cpp_argv_origins.py`、通用路径值递归 | 停止增加通用求解规则；用 Joern 的原生依赖/调用查询对照后逐项迁移。现有已验收结果不会因替换而无依据降级或消失。 |
| 协议、注册、序列化、窗口/Worker、进程和路径边界模型 | 保留可验证语义，改为消费原生事实；逐个模型列保留/改接/淘汰决定，不整块推倒。 |
| 新增 getter 返回开发稿 | 冻结在工作区，不并入本轮文档提交，不再继续完成该自研路线；是否需要其中的输出字段由 R0 原生对照决定。 |

替换以职责为单位。旧实现作为固定版本回归参照，达到对应验收后再移出默认执行路径；同一事实域不能同时有两套无优先级的“确定事实”。

## 6. 上游依据

- Joern：[图导出](https://docs.joern.io/export/)、[数据流查询](https://docs.joern.io/cpgql/data-flow-steps/)、[自定义语义](https://docs.joern.io/dataflow-semantics/)。未建模外部方法会保守传播到多个参数/返回值，不能将任意 reachableBy 路径直接当作精确对象链。
- SCIP：[协议与索引器](https://github.com/scip-code/scip/blob/d556dd3c24b3c1787e0b62cd31f25188300e3098/README.md)。用于符号/定义/引用互操作。
- SQLGlot：[lineage API](https://sqlglot.com/sqlglot/lineage.html)、[MIT](https://github.com/tobymao/sqlglot/blob/main/LICENSE)。SELECT 血缘和宿主对象/动态 SQL 绑定分开验收。
- OpenTelemetry：[zero-code 范围](https://opentelemetry.io/docs/zero-code/)、[C++ 接入](https://opentelemetry.io/docs/languages/cpp/instrumentation/)、[上下文](https://opentelemetry.io/docs/specs/otel/context/)。应用自定义状态与协议仍需有限接入。
- Playwright：[trace viewer](https://playwright.dev/docs/trace-viewer)。复用浏览器操作、网络和 DOM 证据，不用它推定后端已执行。
- CodeQL：[支持语言](https://codeql.github.com/docs/codeql-overview/supported-languages-and-frameworks/)、[CLI 与条款入口](https://docs.github.com/en/code-security/concepts/code-scanning/codeql/codeql-cli)。
- Semgrep：[CE](https://semgrep.dev/products/community-edition/)、[跨文件功能边界](https://semgrep.dev/docs/writing-rules/experiments/join-mode/overview)；Noir：[官方仓库](https://github.com/owasp-noir/noir)。
