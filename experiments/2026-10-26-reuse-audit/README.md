# 可复用工具源码与原生组件核实

2026-10-26。状态：**本轮组件审计完成，替代准入部分通过；产品功能开发保持停止。** 本轮继承已完成的工具调查，核查源码入口，并执行此前缺少的组件探针。结果见[原生输出摘要](evidence/component-results.json)，迁移取舍见[源码接口清单](../../research/reuse-source-contracts-2026-10-26.md)。这次没有修改 Insight，没有读取封存 issue 材料，没有核验文件哈希。

## 1. 实际执行结果

所有新输入都是公开在本目录的通用 fixture。SCIP 输入是人工构造的索引，用来隔离导入组件的行为；它不是编译器生成的索引，也不是自动恢复的产品图。

| 提供方与输入 | 实际输出 | 复用判断 |
|---|---|---|
| CGC 0.6.13 `ScipIndexParser`，同一人工 SCIP/源码 | `target(1)` 导入成功；`target (1)`、`generic<int>(1)` 没有调用边；函数地址引用没有被当作调用；字段声明保留、字段读取没有投影成读边 | 可复用索引格式读取和定义记录，现成调用投影需适配；不能直接获得完整字段流 |
| CodeGraph 1.39.0 `index --scip`，同一索引/源码 | 三个真正调用都有 SCIP Calls；`auto saved=&target` 也得到 Calls；字段读取没有投影关系 | 可复用 CLI、合并及存储；调用与引用需按语法区分，字段不能指望这个投影补齐 |
| code-map 固定源码的 endpoint 组件 | 归一化和参数路径匹配成功；非 `/api` 路径返回 null；两个模块的同路径端点合为一个节点 | 可复用受支持框架的接口提取，服务域/路径策略要调整；内部模块不是稳定包导出 API |
| clangd 23.1.0 + multilspy 固定源码 0.1.1 | 7 项定义定位、3 项 getter 类型和 1 项语义 AST 查询通过。值、引用、指针返回和两个重载无需自写类型规则 | 原生语义接口已可调用；适合替换相应自写语法/类型推断职责，实际项目编译上下文另验 |
| SQLGlot 30.24.0 | 物理表/列的别名、CTE、JOIN、参数 AST，以及拒绝把 UPDATE 当作 SELECT 血缘，共 5 项通过 | 直接复用 SQL AST 和 SELECT 血缘；宿主参数、连接身份和动态拼接由边界适配提供 |
| Joern 4.0.665 C++ CPG/原生数据流 | 跨函数、成员、getter 有路径；两个对象隔离、复制后写原对象的负例正确；局部 `const Cell& alias=first` 漏掉路径，6 项匹配 5 项 | 可复用 CPG/依赖查询，原生路径保持候选及配置；尚不能整体替代对象/别名分析 |
| 同一 C++ fixture 的独立 g++ 11.5.0 编译/执行 | 6 个函数分别输入 17、83，12 个实际结果符合独立预期；引用别名确实传递输入 | Joern 的别名遗漏由另一执行方式核实，预期未随引擎输出修改 |
| Joern 4.0.665 Rust 前端 | 文件输入没有找到必查函数；目录输入成功退出但 `method_count=0`，没有调用或必查路径 | 当前 Windows 发布包/配置未通过准入；原因未确定，保留 rust-analyzer，不替换 |
| OpenTelemetry Python SDK 1.45.1 | 父子 span、显式线程传播、未传播线程保持独立、状态事件属性共 4 项通过 | 直接复用 SDK；自定义协议/线程传播和应用事件仍需接入；C++/Rust/浏览器及网络 exporter 本轮未测 |
| 既有 CBM 0.12.1，Python/Shell/Docker/Compose 通用 fixture | 两个新隔离缓存启动均返回 `could not load saved runtime settings`，尚未进入索引 | 保留历史索引/watcher 成功证据；本轮边界原生试验阻塞。源码中的现成边界组件仍列为优先复用项 |

成功数描述各自小样例，不合成全仓准确率。原生图、下载包、环境及详细日志都在仓库外。

## 2. 本轮纠正的认识

1. **SCIP 是索引，导入器仍可能丢失语义。** CGC 的调用检测检查引用后是否立即为 `(`；CodeGraph 将函数引用映射成 Calls，并依赖已经存在的节点。两者有可复用入口，仍需核查导入后的关系性质。
2. **CBM 不应只列为导航候选。** 已核对 `pass_spawns.c`、`pass_shell.c`、`pass_docker.c`、`pass_envjoin.c`、`pass_route_nodes.c`、`pass_compile_commands.c` 和 `pass_usages.c`，分别承担进程、脚本、容器、环境、路由、编译配置及读写关系。优先导入这些现成结果，避免再写相同的解析/传播组件。
3. **CBM 源码与发布包必须区分。** 本地源码为 `10ab613de30dfd573d0b251cd0ad648e1c7e5204`；官方 v0.12.1 tag 对应 `a7158ac2f48ca646b4527341b76f930f2aeff87e`。本轮核实了该差异，不能把源码中的所有行为归给已执行发布包。
4. **LSP 客户端也有现成实现。** Code-Craft [论文 3.1 节](https://arxiv.org/html/2504.08975v1#S3.SS1)指向 multilspy；本轮实际复用其 `LanguageServer.create`、定义/hover 查询、通用 `send_request` 和 `server_binary` 配置，没有实现 JSON-RPC 通信层。
5. **数据依赖候选与对象等同是不同能力。** Joern 在本组样例有可复用依赖结果，也有明确别名缺口；Clang 能给声明和类型，不能据此宣称实际实例已经配对。更高精度别名能力有 SVF 等现成路线，要求 LLVM IR 和构建环境，当前只做源码调查，不自写求解器补这个空缺。

## 3. 固定版本与输入输出

| 组件 | 固定版本或提交 | 进入方式 |
|---|---|---|
| CGC | 0.6.13 / `93c9685bff9151f50a3121e9913e5ba2d27c1191` | 原有环境、只读 checkout，直接调用组件 |
| CodeGraph | 1.39.0 / `7bac941c1916d34fae0e93dd0ffeaef360d741fb` | 原有官方 Windows 二进制，独立缓存 |
| code-map | `d57c92bda4c3b1f62be8d2e75c9a45dddd430bb4` | 原有源码模块，Node 22.23.3 |
| multilspy | 源码 `62acb3cf2d7a0746992ca08767d8a4fded402ebb`，包声明 0.1.1 | 固定源码包，独立 Python 3.11 环境 |
| clangd | 官方 23.1.0 Windows x86_64 | 显式 `server_binary`，本组自有 compile_commands |
| Joern | 官方 v4.0.665 / `d7a5615a30cbce12986f7a0dae9a938a5b99985e` | Windows 分发包；Temurin JRE 21.0.12.1+1；CLI/Scala 查询 |
| SQLGlot | 30.24.0 | 独立 Python 环境 |
| OpenTelemetry | SDK/API 1.45.1；semantic-conventions 0.66b1 | 独立 Python 环境，内存 exporter，无网络服务 |
| 独立语义检查 | MinGW g++ 11.5.0，C++17、O0 | 编译 `joern-oracle.cpp` 后执行 |

依赖环境和原生工具分开运行，不改原有 CGC/Jedi/RA 环境。实际安装的版本已记录；没有执行供应链文件哈希复验。没有启动 GUI。

## 4. 首轮问题和处理

- SCIP 驱动首次使用 Windows 默认 GBK 读取 CLI UTF-8 输出，汇总失败；改成显式 UTF-8，使用新输出目录，原始目录保留。
- SQL 首次评分将 lineage 的别名节点 `a.value` 当作物理表名。原生 Table AST 已包含 `readings AS a`；改为读取 Table 节点和 Column AST。首次结果保留，未修改库。
- Joern 首次 CLI 参数在 Windows launcher 中解析失败，改用两个环境参数；首次 Scala 查询误将 overlays 字符串列表 flatten，改为直接读取列表。均为探针调用问题，保留原日志。
- 初版 C++ 隔离负例未初始化第二个对象。最终改为值初始化，重新提取，并由独立编译程序核对 12 项观察；初版源码和结果保留，不计入最终准入结果。
- Rust 从文件改为目录输入复验一次，仍无必查方法；CBM 创建缓存目录后复验一次，仍在读取设置时失败。两条支线停止，没有修改上游或追加自有分析算法。

## 5. 复现

以下 `RAW`、工具路径和 Python 环境由调用者提供；每次选择新的输出目录。所有下载/解压路径位于仓库外。SCIP 探针使用既有 CGC 环境，其他 Python 探针使用隔离环境。

```text
python probe_scip_imports.py --cgc CGC_CHECKOUT --codegraph CODEGRAPH_EXE --output RAW/scip-imports-02
python probe_frontends.py --clangd CLANGD_EXE --code-map CODE_MAP_CHECKOUT --node NODE_EXE --output RAW/frontends-02
python probe_runtime_sdk.py --output RAW/otel-01.json
python probe_cbm_boundaries.py --binary CBM_EXE --output RAW/cbm-02
joern-parse joern-probe.cpp --language C --output RAW/joern-cpp-02/cpg.bin
joern-parse RUST_SOURCE_DIRECTORY --language RUST --output RAW/joern-rust-02/cpg.bin
```

对两个 CPG 分别设 `PROJECT_MAP_AUDIT_CPG` 和 `PROJECT_MAP_AUDIT_OUTPUT` 的绝对路径，执行 `joern --script probe_joern.sc`。Rust 目录含 `joern-probe.rs`；首轮文件输入结果也保留。编译 `g++ -std=c++17 -O0 joern-oracle.cpp -o oracle` 后执行，保存 stdout 为 `oracle.log`。`publish_evidence.py --raw RAW --output NEW_EVIDENCE` 根据已执行原生输出生成摘要；脚本中保留本次原始目录名，后续复现实验按相同布局保存。

本目录[证据检查](check_evidence.py)核对小样例预期、成功和失败均被保留，以及未继承产品验收：

```text
python experiments/2026-10-26-reuse-audit/check_evidence.py
python scripts/check_research.py
```
