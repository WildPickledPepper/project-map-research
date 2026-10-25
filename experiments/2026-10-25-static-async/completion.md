# 异步返回、分页连接与 A5 准备

日期：2026-10-25。**五项指定静态连接验收通过；A5 环境准备完成。** [验收门槛](evidence/evaluation.json)和[逐项连接](evidence/chains.json)保留条件、诊断与截断状态。

| 请求 | 返回字段 | 指定前端目标 | 结果 |
|---|---|---|---|
| queryIterations | `iterationOrRankId` | `getiterationOptions` | 已连接 |
| queryStages | `data` | `getStageOptions` | 已连接 |
| getBlocksGraphData | `blocks` | `getBarNewData` | 已连接 |
| getSnapshotBlocks | `blocks` | `fetchSnapshotViewBlocksPaginated` | 已连接 |
| getSnapshotBlocks | `blocks` | `getBarNewData` | 已连接 |

`getBlocksGraphData` 对应 memscope 的单次请求；`getSnapshotBlocks` 对应 snapshot 的分页请求。两个分支在 `getBarNewData` 汇合，转交 `workerSetMemoryBlockData`。Worker 入口按参数转交登记，内部数据使用和实际绘制另行验证。

## 实现

复用现有 TypeScript 编译器解释器和 Tree-sitter 类型候选，补齐本轮已确认的机制：

- 标准 Promise 的 resolve/reject、保存的回调、剩余/展开参数、局部 Map、定时任务与队列；保留首次结算、取消和调度条件。
- 有界循环、break/continue、数组累积与排序；传播字段来源，区分被覆盖的 spread 字段，保留嵌套异常守卫后的成功路径。
- 调用别名按函数身份连接；已知函数的参数转交与 helper 返回分别登记。
- 前端接口分析纳入已发现的发送方，保留未匹配接口的消费者；C++ 类型候选沿可见的多层 namespace 导入查找，并保留歧义。规则依据 [C++ using directive 条款](https://eel.is/c++draft/namespace.udir#5)，源码候选继续保留编译上下文限制。
- 组合查询同时返回前端和返回值分析的预算诊断。

## 验证

345 项 Python、110 项 TypeScript 测试通过；既有六条请求、六个响应字段和两个状态目标回归通过。13 项刷新、26 项导航、19 项 P7 检查及前端组件重复提取一致性结果分别见 [更新](evidence/updates.json)、[导航](evidence/navigation.json)、[既有链](evidence/known-regression.json)、[组件比较](evidence/frontend-repeat.json)及[测试](evidence/tests.json)。修复回调后完成完整重建并通过复验；组件比较覆盖前端阶段的全部 JSON 内容。

首次八项机制检查为 3 项通过、5 项失败。第一次完整构建完成后，五个组合查询均未连接，既有返回链也失败：分支复制产生的回调候选未被回调表读取展开。修复后重新完整构建及评分。[失败记录](evidence/development-failures.json)保留这些结果，以及 A4 评分在 6 GiB 分析预算下停止的记录；最终该评分采用明确的 8 GiB 分析预算。

完整构建用时 1044.1 秒，峰值进程树工作集 5.21 GiB，构建预算 1,800 秒 / 6 GiB。最终图包含 282,168 个节点、413,390 条关系、2,315 个输入。完整成本见 [构建](evidence/build.json)和[查询测量](evidence/measurements.json)。

源码为独立实验副本 `8b2d4deaf2c995fac11efb280e9ec3b7a1610be9`，事实提取版本为 `b8eac24190eae0a36f2ff2f3f97954670bc25198`。六条既有材料和本轮五项连接属于开发回归；历史验证候选未用于调规则。

## 覆盖与下一步

循环按 3 轮预算展开，定时回调采用显式的候选调度顺序。查询中仍有预算截断、外部调用和其他未展开路径；五项成绩表示指定连接已找到。真实分页次数、缓存命中/失效、并发处置、Worker 采用与资源指标进入 A5 场景验证。

A5 已构建 Cluster、Leaks 页面，启动 Chromium 143，并检查公开 snapshot 输入：2 个 segment、717 条原始 block、8,092 条 trace event。构建后独立副本保持干净且禁用推送。[准备证据](evidence/runtime-preparation.json)中的真实产品场景数为 0；浏览器探针运行于 about:blank，产品页面的隔离头、OPFS 与实际渲染由场景执行验证。[A5 计划](../../plans/a5-runtime-validation.md)已写明正常、异常、切换、并发、缓存与故障对照。

原 GitCode 仓库和原下载副本保持不变。历史问题契约库的真实接入继续由 P6 跟进。
