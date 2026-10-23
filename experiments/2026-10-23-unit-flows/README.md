# CodeGraph 与 code-map：unit/flows 原版实测

日期：2026-10-23。证据等级：执行实验、原始查询与源码核对；没有调用 LLM、启动 GUI、运行 Insight 或实现适配插件。

**结论：两个工具原版都没有贯通 Insight 的 `timeline/unit/flows`。CodeGraph 连到部分前端调用，但 C++ 方法提取本身有缺口；code-map 显式配置后只有前端文件 import 图。二者的 HTTP 对照都暴露了服务作用域问题，不能直接把其“跨服务”能力等同于 Insight 端到端能力。**

## 版本与输入

| 项目 | 固定版本与输入 |
|---|---|
| Insight | `d4e8d1cf9f90208bcbe5371c127088f6fd66c688` |
| CodeGraph | `7bac941c1916d34fae0e93dd0ffeaef360d741fb`；执行官方 Windows x64 v1.39.0，release tag 等于该提交，SHA256 与官方清单一致 |
| code-map | `d57c92bda4c3b1f62be8d2e75c9a45dddd430bb4`；直接执行 checkout 的 CLI，包版本 0.1.0 |
| CodeGraph 输入 | 42 个真实文件，858,403 bytes，包含全部 15 个参考锚点；含两个生产调用者及三个测试文件 |
| code-map 输入 | 46 个真实文件，包含全部 15 个参考锚点；24 个 JS/TS、14 个 C++、8 个项目元数据文件 |
| 环境 | Windows x64、Python 3.11.9；code-map Node 22.23.3、npm 10.9.9；CodeGraph 未启用 SCIP |

两组分别选取真实切片并保留相对路径，范围不同，都不是完整构建闭包。因此不按耗时、节点数或边数做跨工具性能排名，也不外推全仓召回率。

逐文件路径与原始 byte SHA256：[CodeGraph manifest](codegraph/slice-manifest.json)、[code-map manifest](code-map/manifest.json)。协调者逐一与固定源码核对，并补充 LF-normalized SHA256 便于不同 Git 换行配置下复现。

## 实际自动连到哪一步

| 链路阶段 | CodeGraph 原版 | code-map 原版 |
|---|---|---|
| 前端消费者 → getUnitFlows | 找到两条 Calls：一条归属于 getSingleFlow，一条只归属于 AscendUnit.tsx File，丢失其方法归属 | 找到两个消费者文件对 request.ts 的 imports；没有函数调用图 |
| getUnitFlows → 请求封装 | raw call 保留 window.requestData、行 175；未解析目标，无 module/command 参数值关系 | request.ts 和封装文件存在，只有文件依赖 |
| 请求 → timeline/unit/flows 接口 | 没有该业务接口节点 | 没有该业务接口节点 |
| 命令常量、注册、handler | .h 被按 C 解析；.cpp 内 HandleRequest 定义未提取，注册语义未恢复 | 输入含这些 C++ 文件，但没有 C++ 节点 |
| Handler → QueryUnitFlows | raw call 在 .cpp File、行 57；调用目标 0/1 resolved | 未建立 |
| 数据库接口 → 两实现/选择条件 | 关键限定方法与类型未正确提取；implementers 无结果 | 未建立 |
| 响应字段 → 前端状态消费者 | 能查局部前端调用，未形成跨协议字段与返回链 | 能查前端 import 邻域，未形成返回数据流 |
| 反向数据库 → 前端入口 | 未通过 | 未通过 |

这些是自动输出。人工基准、常量搜索和本研究文档中的参考箭头没有被当成工具恢复的边。

CodeGraph：577 nodes / 680 edges，完整重建进程约 0.26 秒；新输出目录重复约 0.22 秒。code-map：无配置默认检测 0/0；显式 frontend=modules、backend=server 后 24 文件节点/20 imports，约 0.45 秒。零结果默认检测只适用于该切片，不推断完整仓库的检测结果。

## 为什么必须测受支持的 HTTP 样例

### CodeGraph：共享节点存在，有向端到端路径仍不成立

自写 TS axios / Python Flask 小样例实际得到：

```text
loadPositive ──HttpCalls──→ GET /positive ←──HttpCalls── service-a/routes.py File

positive_handler ──Calls──→ db_positive
```

没有接口节点到 handler 的边。原生 `trace loadPositive positive_handler` 和 `trace loadPositive db_positive` 都返回 no path。公共节点可以提供关联线索，但不能替代可遍历的有向处理链。

两个有不同 baseURL 的客户端、两个 Python 服务都声明 GET `/shared` 时，仍合并成一个 route ID，节点定位只保留 service-b。POST 与 GET 能区分；绝对 URL 调用在该样例没有形成 HTTP 边。因此不能把未产生绝对 URL 连接解释成已经实现 host 隔离。

### code-map：支持的框架能够连接，但服务身份未隔离

自写 React/.NET 样例产生 `前端文件 --calls-api→ endpoint --handled-by→ controller`，同时有同向 resolved-controller。具体方法不同、路径不同的负例没有错连。

两个独立 namespace / csproj 都提供 GET `/api/shared` 时，合并为一个 endpoint，向两个 controller 都连边，而 backend 元数据只保留其中一个。它展示了可复用的端到端连接机制，也展示了需要显式处理的多服务歧义。

## C++ 提取与更新另外存在的问题

CodeGraph 的最小 C++ fixture 复现：内联方法和自由函数能提取；类外 `ExternalDatabase::QueryExternal` 定义遗漏；`.h` 被按 C 处理；`.hpp` 中纯虚成员声明仍没有 callable 节点。这不是因为输入缺少产品实现文件。

| 更新实验 | 结果及边界 |
|---|---|
| CodeGraph：删 TS 消费者、改相对路径 | 普通查询触发 autoheal，旧消费者移除，新路径出现；没有测 MCP watch |
| CodeGraph：与相同最终源码的 full rebuild 对照 | **不等价**：共享 GET hub 的源文件与 Defines 归属改变；Calls/HttpCalls 相同。不是仅耗时或度量变化 |
| code-map：改 C++ 命令值、删除 handler 后重扫 | 图仍 24/20；这些内容未索引，不能算业务更新正确 |
| code-map：HTTP 删 provider、改客户端路径 | 显式全量重扫正确清理旧关系；最终节点/边与干净扫描相同；没有测 watch 或增量 |

CodeGraph 差异原文见 [update-delta.json](codegraph/update-delta.json)。完整图维护一致性未通过，不能沿用更早、更小 fixture 的阶段性通过结论。

## 需要什么适配

共同缺口是自动提取 TS 消费接口与 C++ 提供接口，按服务/连接、协议、module、command 关联，再连接分发与返回数据。请求字段在多层封装中传播，需要保留值来源和条件。

此外：

- **CodeGraph** 先补可靠的 C++ 头文件/声明/限定方法/虚接口解析，或验证编译器索引路径；再修接口方向、服务身份和共享节点更新一致性。不能认为只加一条命令匹配规则就够。
- **code-map** 需要增加 C++ discovery、parser 与事实提取器，TS 自定义消息提取器、注册关联器和返回字段分析。它有已核对的插件入口，但本轮未实现插件；现成 React/.NET 模板不能替代这些能力。
- 两者都需要明确未解析、过滤和歧义诊断。code-map 原版没有逐个报告 C++ 未索引原因；CodeGraph 的 raw-call coverage 有帮助，但不能解释全部方法提取缺口。

具体源码机制见 [适配边界审计](../../cases/unit-flows/adaptation-boundaries.md)。采用建议：两者继续作为可复用机制的对照，**本轮不选择任一个作为 Insight 现成端到端底座**。先验证某个底座的 C++ 事实层和自定义协议扩展入口，再决定是否投入适配。

## 材料与复现

- [CodeGraph 详细报告](codegraph/findings.md)、[原生精简证据](codegraph/compact-evidence.json)、[二进制来源](codegraph/binary-provenance.json)。
- [code-map 详细报告](code-map/findings.md)、[原生精简证据](code-map/evidence.compact.json)、[复现说明](code-map/reproduce.md)。
- [完整复现步骤](reproduce.md)、[协调者独立重跑结果](coordinator-reproduction.json)。

公开 runner 只增加了输入/输出边界检查、clean checkout 校验和基于实际 manifest 的锚点覆盖检查，没有修改第三方工具。协调者用发布版 runner 在全新输出目录各执行一次；关键原生结果、输入范围及更新差异与独立试验一致。

这些材料不包含第三方 checkout、npm 环境、二进制、数据库、完整原始日志或目标数据。CodeGraph 采用 MIT OR Apache-2.0；code-map 是 AGPL-3.0-only，复用需要遵循所选工具的许可。

## 隔离与未测项

子智能体采用独立上下文、工具目录、缓存、fixture 和输出，不读取对方结果、不互发中间结论，由协调者汇总。它们共享公开基准，属于流程隔离，不宣称安全隔离或严格盲测。

未测：全仓、完整 SQL/表依赖、SCIP 精度、MCP watcher、动态场景、unit/flows 完整变更矩阵、快速提交、失败重试及跨版本快照。具体 S01–S07 覆盖与各自未测项在详细报告中，不能把部分更新实验写成全部验收通过。
