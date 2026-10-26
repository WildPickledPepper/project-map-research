# 可复用组件：源码入口、实际能力和接入决定

2026-10-26。本次核实覆盖此前六个工具、已有编译/语言组件，以及为明确缺口补查的语义、数据流、SQL 和运行组件。**源码审计和本轮组件试验已完成；产品开发保持停止。** 可直接接入的接口、需要适配的投影和暂不可选的路线分开列出。原生执行结果见[审计报告](../experiments/2026-10-26-reuse-audit/README.md)及[机器可读证据](../experiments/2026-10-26-reuse-audit/evidence/component-results.json)。

## 1. 此前六个工具已经核到哪里

| 工具与固定源码 | 具体入口与输入输出 | 已核实限制 | 接入决定 |
|---|---|---|---|
| **CGC 0.6.13**，`93c9685` | `tools/scip_indexer.py::ScipIndexer.run` 调外部索引器；`ScipIndexParser.parse` 读 SCIP，返回 files/symbol_table；`tools/indexing/scip_pipeline.py` 编排原生记录、Tree-sitter 补充和写库 | 索引器运行与导入是两件事。本轮人工索引探针复现空格/模板调用漏边；字段声明存在、字段读未投影；C++ 真实 SCIP 索引仍未生成 | 复用已有原生结果、SCIP Protobuf/导入和存储接口。调用边读取原生语法/位置来校正，不照搬其便利投影作为最终事实 |
| **CodeGraph 1.39.0**，`7bac941` | `crates/codegraph-resolve/src/lib.rs::import_scip` 将 SCIP occurrences 映射到已有节点；CLI `index --scip`；原版 SQL CLI 能查已验证的 `pm_fact_*` 表 | 以文件/行匹配，不能凭 SCIP 合并创造全部缺失节点；函数引用投成 Calls；字段/参数不在该投影；原版 `.h` 分类/类外定义问题有既有实测 | 复用 CLI、存储和可验证的合并结果；保持可替换资格。当前不为换底座搬迁全部存储，也不重写同一 SCIP 解码 |
| **CBM**，源码 `10ab613`；执行发布包 **v0.12.1** 的 tag 提交为 `a7158ac` | `pass_spawns.c` 提取启动 API；`pass_shell.c` 处理脚本/Make/CI 命令；`pass_docker.c` 处理镜像、COPY、入口与环境；`pass_envjoin.c` 限定容器内变量读者；`pass_route_nodes.c` 生成 HTTP/异步 Route；`pass_usages.c` 做 READS/WRITES；`pass_compile_commands.c` 读编译参数。外部调用优先 `cli index_repository/query_graph/trace_path` 或只读 SQLite | C 内部 pass 依赖 pipeline 上下文，不是几个可单独复制的函数。Hybrid LSP 是其嵌入实现，不等于实际语言服务器。新隔离缓存启动两次均在加载设置时失败，尚未测到这些边界；旧索引/watcher 成功记录保留。源码/发布包不在同一提交 | **扩大其复用角色到脚本、容器、进程、环境和路由**，优先排除启动问题并导入原生结果。不会因旧调用错连而丢弃这些组件；也不把源码存在当作已测通过 |
| **code-map**，`d57c92b` | 公共 `index.mjs` 导出 Graph、createScanPipeline、createProjectContext/writeGraph 等；内部 `src/core/endpoints.mjs` 提供归一化、参数路径兼容和组合 extractor | endpoint 内部模块不属于稳定包 exports；只接收 `/api` 路径；ID 没有服务域，本轮两个模块同路径合成一个节点。C++ 与自定义协议缺口已有实测。根 LICENSE 为 AGPL-3.0 | 标准框架优先复用其扫描/提取；通过 CLI/导出或明确维护的扩展接入。服务域、路径策略单列适配，不再写一套功能相同却无比较的匹配器 |
| **RPG/CoderMind**，`a4e6966` | `CoderMind/scripts/rpg/dep_graph.py::DependencyGraph.build/parse/update_files` 维护结构/依赖；`scripts/rpg_encoder` 做功能树/摘要更新；研究版 `zerorepo/rpg_encoder/RPGEncoder.encode` 返回 RPG、feature_tree、skeleton | 研究版语义文件遍历有 `.py` 过滤；CoderMind 才是已有多语言实测对象。Python >=3.12 的完整包与旧 3.11 核心模块实测要区分。完整 LLM 功能树未运行；更新代码使用 `HEAD~1` 的行为已有源码审计 | 复用结构组织和后续职责摘要接口；基础事实可靠后接入摘要。保持版本/过滤边界，避免另写摘要引擎 |
| **RepoGraph**，`6c3977d` | `repograph/construct_graph.py::CodeGraph.get_code_graph` 返回 tags 和 NetworkX 图；graph_searcher 提供邻域检索 | `Tag` 是 namedtuple，而 `tag_to_graph` 按字典读取；节点以 name 标识，引用同名匹配；入口枚举仅 `.py`。修接口错误也不会得到完整多语言身份/数据流 | 当前不作为主依赖；保留方法和论文对照，避免为它重建已有索引能力 |

源码：

- [CGC SCIP 组件](https://github.com/CodeGraphContext/CodeGraphContext/blob/93c9685bff9151f50a3121e9913e5ba2d27c1191/src/codegraphcontext/tools/scip_indexer.py)、[pipeline](https://github.com/CodeGraphContext/CodeGraphContext/blob/93c9685bff9151f50a3121e9913e5ba2d27c1191/src/codegraphcontext/tools/indexing/scip_pipeline.py)。MIT。
- [CodeGraph 合并器](https://github.com/sina-parsania/CodeGraph/blob/7bac941c1916d34fae0e93dd0ffeaef360d741fb/crates/codegraph-resolve/src/lib.rs)、[许可证](https://github.com/sina-parsania/CodeGraph/tree/7bac941c1916d34fae0e93dd0ffeaef360d741fb)。MIT/Apache-2.0。
- [CBM pipeline](https://github.com/DeusData/codebase-memory-mcp/tree/10ab613de30dfd573d0b251cd0ad648e1c7e5204/src/pipeline)、[watcher 接口](https://github.com/DeusData/codebase-memory-mcp/blob/10ab613de30dfd573d0b251cd0ad648e1c7e5204/src/watcher/watcher.h)、[v0.12.1](https://github.com/DeusData/codebase-memory-mcp/releases/tag/v0.12.1)。MIT。内部 watcher 成功/失败回调控制变更基线，复用时仍需接本项目的版本发布约定。
- [code-map 端点组件](https://github.com/abbaing/code-map/blob/d57c92bda4c3b1f62be8d2e75c9a45dddd430bb4/src/core/endpoints.mjs)、[公共入口](https://github.com/abbaing/code-map/blob/d57c92bda4c3b1f62be8d2e75c9a45dddd430bb4/index.mjs)。AGPL-3.0。
- [CoderMind 依赖图](https://github.com/microsoft/RPG-ZeroRepo/blob/a4e6966c4ff59d84299bc56d6a47ae1f4f7b2885/CoderMind/scripts/rpg/dep_graph.py)、[研究版 encoder](https://github.com/microsoft/RPG-ZeroRepo/blob/a4e6966c4ff59d84299bc56d6a47ae1f4f7b2885/zerorepo/rpg_encoder/rpg_encoder.py)。MIT。
- [RepoGraph 构图](https://github.com/ozyyshr/RepoGraph/blob/6c3977d87845993bf2c0359b4ac752278d7f3c45/repograph/construct_graph.py)、[LICENSE](https://github.com/ozyyshr/RepoGraph/blob/6c3977d87845993bf2c0359b4ac752278d7f3c45/LICENSE)。Apache-2.0。

## 2. 底层能力的复用接口

| 能力 | 提供方和入口 | 实际可取得的内容 | 我们保留的接合工作 |
|---|---|---|---|
| TS/JS 语义 | 已用 TypeScript Compiler API：Program/TypeChecker、getResolvedSignature 等 | 符号、声明、类型、调用目标和语法结构 | 把这些结果导入统一图，补消息/注册 API 模型；继承既有全仓和更新证据 |
| Python 语义 | 已用 AST/Jedi Script.infer | 定义、包/导入和调用候选 | 明确环境/包上下文和图身份；不另写 Python 解析器 |
| Rust 语义与构建 | 已用 rust-analyzer 的 definition 等请求、Cargo metadata/JSON | crate/cfg 下符号、原生定义和目标/产物 | 保留配置和边界参数模型；不改为未经验证的 Joern Rust 路线 |
| C++ 语义 | **clangd 23.1.0 + multilspy**：LanguageServer.create、request_definition、request_hover、server.send_request("textDocument/ast") | 本轮 11 项通过：定义/重载/命名空间、返回类型及语义 AST | 接入真实编译数据库、依赖和配置；做统一符号/位置映射。通用语言服务通信由库负责 |
| C++ 依赖分析 | **Joern 4.0.665**：joern-parse、importCpg、CPGQL/reachableByFlows、图导出 | 本轮 5/6 源码语义检查匹配，包含成员/getter；独立编译结果核实 1 项引用别名遗漏 | 查询、图归一化及现成库语义配置；路径保持候选，配置/深度保留；不以自写别名求解器填遗漏 |
| SQL | **SQLGlot 30.24.0**：parse_one、exp.Table/Column/Placeholder、lineage | 5 项探针通过；AST 与 SELECT 表/列依赖。原生叶子的 name 可含别名，物理表在 Table AST | 宿主 SQL/参数来源、连接身份和结果消费者；UPDATE 的 AST 与 SELECT lineage 区分 |
| 构建/产物 | 已用 CMake File API、Cargo metadata/compiler-artifact JSON | 原生目标、编译输入、配置及产物路径 | 对应部署/进程身份；优先复用收据，不自行解释整个构建系统 |
| 运行追踪 | **OpenTelemetry Python SDK 1.45.1**：TracerProvider、span/context、add_event、exporter | 本轮 4 项通过：父子关系、显式线程传播、未传播保持独立和状态事件 | 自定义协议/异步传播、状态/资源事件和静态图映射。其它语言 SDK 与实际产品采集分开验收 |
| 浏览器与存储/查询 | 已用 Playwright、SQLite、项目快照/CLI/MCP | 既有场景与维护证据直接保留 | 补对应模块的场景和断言；不重写浏览器驱动、图存储和版本维护 |

multilspy 源码 `62acb3cf2d7a0746992ca08767d8a4fded402ebb`，包声明 0.1.1，MIT；[clangd 包装器](https://github.com/microsoft/multilspy/blob/62acb3cf2d7a0746992ca08767d8a4fded402ebb/src/multilspy/language_servers/clangd_language_server/clangd_language_server.py)支持 `server_binary`，本次显式选择已下载 clangd，避免默认下载的 19.1.2 与实测 23.1.0 混用。它的依赖在独立环境，不改已有 Jedi/CGC 环境。

Joern 的[原生语义](https://github.com/joernio/joern/blob/d7a5615a30cbce12986f7a0dae9a938a5b99985e/dataflowengineoss/src/main/scala/io/joern/dataflowengineoss/DefaultSemantics.scala)和[查询引擎](https://github.com/joernio/joern/blob/d7a5615a30cbce12986f7a0dae9a938a5b99985e/dataflowengineoss/src/main/scala/io/joern/dataflowengineoss/queryengine/Engine.scala)已核对；本版默认 maxCallDepth 为 4，未知外部方法的保守传播也会引入额外候选。CLI/CPGQL 是接入边界，不复制求解器。根许可证 Apache-2.0。

## 3. 只作为明确缺口的条件候选

| 项目 | 已核对内容 | 当前决定 |
|---|---|---|
| **OWASP Noir**，`c946c10b7312aa4008ec9d850b4c5554c227ee9a` | [Aiohttp analyzer](https://github.com/owasp-noir/noir/blob/c946c10b7312aa4008ec9d850b4c5554c227ee9a/src/analyzer/analyzers/python/aiohttp.cr)已有 router.add_get/add_route 与装饰器处理，产出接口和参数位置 | 标准 aiohttp 端点先复用现成模型；源码审计，未运行；不把它当自定义 WS 消息或完整调用链工具，LLM fallback 关闭 |
| **SVF**，`482b6f792ad73eb8357c31d86fa1494169955101` | [README](https://github.com/SVF-tools/SVF/blob/482b6f792ad73eb8357c31d86fa1494169955101/README.md)及 LICENSE.TXT；现成 LLVM IR 指针/值流框架，含库与 Python 绑定路线；AGPL-3.0 | 复杂别名的条件备选。需要相应 LLVM 版本、bitcode/构建及源码位置映射；未安装/运行，不纳入当前默认依赖，也不因此自己写一个替代算法 |
| **CodeQL** | 官方 CLI/支持语言与独立条款已查 | 不并行搭第二套全仓系统；若后续确需精度对照，先明确实际使用/分发条件 |
| **Code-Craft** | [论文](https://arxiv.org/html/2504.08975v1)说明修改版 multilspy、分层摘要和检索。此次从论文追到原生可复用 LSP 客户端 | 官方完整实现仍未核实；复用确认存在的 multilspy，不将同名 GitHub 项目当成论文实现 |
| **Semgrep CE / MetaCall meta-ast** | 保留此前规则发现/统一结构调查 | 本轮不增加主依赖，不重复运行选型；对应机制出现真实缺口时再决定 |
| **Grafema / graffiti** | 此前已记录用途/再使用许可限制 | 保持排除出可自由改造默认底座的决定，不用功能接近替代许可核实 |

## 4. 实施决定

1. **语言语义直接复用已有编译/语言服务**。C++ 接入已实际可调用的 clangd/multilspy 接口；CGC/CodeGraph 的 SCIP 组件保留格式和互操作价值，使用前校验投影精度。
2. **进程、Shell、容器、环境与标准路由先接现有组件**。CBM 的这些 pass 是优先复用项；先解决发布包的隔离启动/版本问题，再取原生图，不从 Tree-sitter 开始重写同类传播。标准 HTTP 可按适用框架选 code-map/Noir。
3. **数据与 SQL 使用现成引擎**。Joern 先承担已验证的依赖候选，SQLGlot 承担 SQL AST/SELECT 血缘。引用别名残余另列能力缺项，不把 5/6 小样例写成完整实例分析通过。
4. **项目地图、维护与查询保留**。现有成功快照、统一图、SQLite、CLI/MCP、分页和版本隔离不推倒。RPG 职责摘要后接，skill 最后整理。
5. **我们写的部分限于互操作和机制模型**：工具输出映射、配置/身份、发送/注册/序列化/数据消费模型、覆盖状态及运行映射。输入中的模块/接口名自动提取，新增模块进入发现和更新；不加入业务名称白名单。

## 5. 剩余准入问题和退出状态

本轮已回答每个候选有哪些入口、能输出什么、怎样调用、哪些限制有原生输出支持。以下保留为具体准入任务：

- clangd 在 Insight 真实编译参数、依赖和条件下的全仓接入；本轮只使用独立 fixture。
- CBM 新隔离缓存读取设置失败的原因，以及源码 pass 与已执行发布包的实际对应能力；不把启动失败解释为边界能力不存在。
- Joern Rust 目录输入零方法的原因，以及 C++ 局部引用别名的精度路线；不会用非空 CPG/成功退出代替能力验收。
- 标准框架组件的产品适用性、跨语言接口/实例配对和全模块机制覆盖；本轮没有执行产品建图或整体验收。
- OTel 在产品其它语言/协议中的传播、实际运行场景及资源指标；Python SDK 探针只证明其接口可复用。

这些问题不再通过无限追加自有语言规则推进。下一步是按现成接口解决准入和批量接入；若不能通过，发布具体技术阻塞并继续独立批次，G02–G08 保持未通过。
