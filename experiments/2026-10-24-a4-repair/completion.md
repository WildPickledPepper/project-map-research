# A4 修复与复验报告

**本轮规定的静态连通、更新与重建验收通过。** [15 项门槛](evidence/evaluation.json)全部通过；[首轮未通过结果](../2026-10-24-a4/report.md)完整保留。

| 检查 | 首轮复核 | 修复复验 |
|---|---:|---:|
| 六条请求正确匹配提供方 | 3/6 | 6/6 |
| 指定数据生产函数正反向候选路径 | 3/6 | 6/6 |
| 指定响应字段序列化关系 | 2/6 | 6/6 |
| 两个指定前端状态 | 0/2 | 2/2 |
| 六条请求的额外错误提供方 | 0 | 0 |

六项材料已用于修复，成绩属于开发回归。[逐项结果](evidence/chains.json)保留条件、未知项、来源和查询截断状态。这里统计静态候选关系，运行行为由 A5 验证。

| 请求 | 后端处理器 | 指定字段 | 状态目标 |
|---|---|---|---|
| `queryIterations` | `IterationsHandler::HandleRequest` | `iterationOrRankId` | helper 返回另计 |
| `queryStages` | `GroupHandler::HandleRequest` | `data` | helper 返回另计 |
| `queryOperatorCategory` | `QueryOpCategoryInfoHandler::HandleRequest` | `data` | `opTypeData` 已连接 |
| `queryOperatorComputeUnit` | `QueryOpComputeUnitHandler::HandleRequest` | `data` | `computeData` 已连接 |
| `getBlocksGraphData` | `QueryMemScopeBlockHandler::HandleRequest` | `blocks` | Worker 转交另计 |
| `getLeaksAllocationsData` | `QueryMemScopeAllocationHandler::HandleRequest` | `allocations` | helper/会话更新另计 |

## 实际修正

- 直接平台发送成为入口；沿编译器调用身份发现导出的公共请求包装器调用者。工厂回调保留源身份与导出名称。
- 剩余参数、展开参数、局部 Map 保存与定时回调保留参数来源。模块级 Map 的此前运行状态继续标为未知，避免把连接表误判为空。
- C++ 显式模板注册保留具体类型与依赖静态调用；智能指针工厂、参数限定符、模板成员类型和虚函数序列化保留类型来源。
- 数组映射把元素字段传到状态更新；helper 返回和外部参数转交独立登记。支持括号形式的 `std::optional(...)` JSON 返回。
- 外部构造器继承输出诊断；路径条件采用紧凑描述，值描述受节点预算限制。
- 指定字段查询约束整对象消费，删除 `lines` 后不会用其他字段证明消费链。发布校验复用已有 `validate_graph`，保留版本、范围、端点和结果计数检查。

业务名称用于参考评分与回归输入，未写入解析规则。实现继续复用现有 TypeScript 编译器、Tree-sitter、C++ 事实与类型框架、JSON 构建分析和 SQLite 导航。

## 新材料与反例

补充的 compute 两条请求与强化学习一条请求，首次结果为 2/3，`getTraceData` 漏入口；修复公共包装器发现后为 3/3。这三项随后用于开发，首次结果见 [first-repair.json](evidence/first-repair.json)。

协议规则冻结后，另选 NUMA 和片上内存各一条请求，均正确匹配预期 handler，源坐标一致。这两项评价协议身份与处理器连接；源码此前已进入全仓提取，不属于严格盲测。返回解释器的健壮性随后修正，两项参考未用于定向调整协议规则。见[冻结参考](final-reference.json)与[评分](evidence/retest.json)。

开发中的失败分别保留：[中止与崩溃](evidence/development-failures.json)、[序列化仅 5/6 的完整图](evidence/first-complete-repair-chains.json)、[字段删除反例失败](evidence/query-first-regression.json)、[发布校验超预算](evidence/controller-first-validation.json)。最终[字段删除复查](evidence/missing-field-probe.json)为修改前 7 条、删除后 0 条连接。

## 更新、规模与成本

- [13 项真实刷新控制](evidence/direct-updates.json)、[26 项全图导航检查](evidence/navigation.json)、[19 项既有链回归](evidence/known-regression.json)全部通过。
- 2,315 个自动输入生成 **280,559 个节点、401,303 条边**；导航覆盖 4,860 个受版本控制路径、31 个结构模块。范围包含 5 个自编新增文件和 2 个新增结构模块，产品基线为 4,855 个路径、29 个结构模块。
- 119 个提供方候选、271 条连接结果记录中，137 条为唯一有条件匹配；其他未知、未匹配、歧义及未找到传输的记录保留。这些数量不是全仓正确率。
- [两次独立完整构建](evidence/builds.json)分别约 925 秒、922 秒，采样进程树工作集峰值约 4.93、4.77 GiB，均满足 1,800 秒和 6 GiB 预算。两次构建并行运行，工作集采样可能重复计算共享页。
- [完整 JSON 比较](evidence/rebuild.json)一致，仅排除快照 ID 与 `version.snapshot`。[最终全图发布校验](evidence/publication.json)约 19.62 秒、4.93 GiB，通过原 6 GiB 限额；这里验证校验步骤，真实刷新生命周期另由 13 项控制验证。
- [340 项 Python、97 项 TypeScript 测试](evidence/tests.json)通过。全图使用 JSON 保存完整提取结果，SQLite 提供导航；本轮没有执行全图 Kuzu 存储往返。

事实提取版本为 `573330f`，最终查询与发布校验版本为 `3537a62`。后一次变化只涉及查询函数和刷新校验；构建使用的 `iframe_links` 等提取函数保持一致，[源码 AST 差异检查](evidence/component-versions.json)确认事实提取未变。因此在已有两份事实图上重跑最终查询与发布校验，并分别记录版本。

## 后续覆盖与运行工作

指定的两个 React 状态已贯通。防抖 Promise 返回值跨保存队列的传播、分页循环到 Worker 的字段传播仍有断点；同文件中的字段消费候选不能代替指定 helper 或 Worker 的最终消费证明。现有接口、调用事实与断点可查询，后续静态扩展继续覆盖这些机制。

A5 接着验证真实执行、状态采用、缓存、并发和资源指标。本轮新增运行复现为 0；12 条历史验证候选沿用首轮的版本/静态覆盖登记，未用于本轮规则调整。历史问题契约库的真实接入继续由 P6 跟进。

原 GitCode 仓库及原下载副本保持不变。源码变更只在独立实验副本；原始图、数据库、日志和诊断输出均保存在研究 Git 外。
