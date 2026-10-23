# 首个案例：timeline / unit/flows

研究对象：[MindStudio Insight](https://gitcode.com/Ascend/msinsight)，固定提交 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`。

状态：本文保留人工源码核对的参考链路。自动结果见 [P2 协议连接](../../experiments/2026-10-23-p2/README.md)和 [P3 数据增量](../../experiments/2026-10-23-p3/README.md)：前端到数据库候选可双向查询，完整选择与返回传播继续验收。动态场景尚未执行。

新增：[CodeGraph / code-map 原版实测](../../experiments/2026-10-23-unit-flows/README.md)，附自动输出、断点和复现脚本；[适配边界](adaptation-boundaries.md) 是人工源码补充审计，不能当作工具自动生成结果。

## 已核实的关键连接

```text
getUnitFlows
  → window.requestData(command='unit/flows', module='timeline')
  → createRequest / connector.fetch / 消息传输
  → 后端 moduleName 分发
  → Timeline 的 command → handler 注册表
  → QueryFlowsBySliceInfoHandler.HandleRequest
  → VirtualTraceDatabase.QueryUnitFlows
      → DbTraceDataBase.QueryUnitFlows（候选实现）
      → TextTraceDatabase.QueryUnitFlows（候选实现）
  → 响应传输、前端消费者与状态更新（待完整提取）
```

这是按业务关系压缩的参考路径。传输链所有中间步骤、具体实现选择条件、SQL/数据依赖和全部结果消费者尚未验收；箭头含请求、分发、注册、调用和候选实现等不同语义。

## 源码锚点

完整的机器可读锚点和分类见 [reference.json](reference.json)。路径均相对于 Insight 仓库，不要求把第三方源码复制到本仓库。

| 事实 | 文件与行号 |
|---|---|
| 请求 `timeline/unit/flows` | `modules/timeline/src/api/request.ts:175` |
| 全局请求函数绑定到封装 | `modules/timeline/src/bootstrap.tsx:89` |
| 通用请求封装携带 command/module | `modules/lib/src/utils/Request.ts:40` 附近 |
| 客户端 fetch 调用 send | `modules/lib/src/connection/index.ts:188` |
| 常量值为 unit/flows | `server/src/modules/defs/ProtocolDefs.h:88` |
| 命令注册到具体 handler | `server/src/modules/timeline/TimelineModule.cpp:87` |
| 按 moduleName 选择模块 | `server/src/modules/ModuleManager.cpp:63` |
| 按 command 取 handler 并分发 | `server/msinsight/src/base/BaseModule.cpp:28` 起 |
| Handler 调用数据库接口 | `server/src/modules/timeline/handler/QueryFlowsBySliceInfoHandler.cpp:57` |
| 数据库抽象接口 | `server/src/modules/timeline/core/database/VirtualTraceDatabase.h:83` |
| DB 候选实现 | `server/src/modules/timeline/core/database/DbTraceDataBase2.cpp:337` |
| Text 候选实现 | `server/src/modules/timeline/core/database/TextTraceDatabase.cpp:636` |

直接查看：[前端请求](https://gitcode.com/Ascend/msinsight/blob/d4e8d1cf9f90208bcbe5371c127088f6fd66c688/modules/timeline/src/api/request.ts)、[注册](https://gitcode.com/Ascend/msinsight/blob/d4e8d1cf9f90208bcbe5371c127088f6fd66c688/server/src/modules/timeline/TimelineModule.cpp)、[Handler](https://gitcode.com/Ascend/msinsight/blob/d4e8d1cf9f90208bcbe5371c127088f6fd66c688/server/src/modules/timeline/handler/QueryFlowsBySliceInfoHandler.cpp)。

## 静态验收题

| 编号 | 要求 |
|---|---|
| S01 | 从 getUnitFlows 找出准确的模块和命令，保留值来源 |
| S02 | 关联到对应注册项及 Handler，避免扩散到所有处理器 |
| S03 | 找到数据库接口、候选实现，并列出实现选择条件或未知项 |
| S04 | 展开请求参数、数据库处理、响应与前端消费者，明确尚未展开部分 |
| S05 | 从接口/数据库实现反向找到相关前端入口 |
| S06 | 新增、删除、重命名或修改命令值后，关系自动更新 |
| S07 | 对断点、歧义、过滤文件和版本差异提供可查询诊断 |

不能用“能搜索到两端定义”替代连接成功，也不能只靠同名方法或同路径匹配给出确定关系。

## 动态验收

详见 [动态方案](../../docs/03-runtime-and-review.md)。第一项验证正常查询；第二项控制响应延迟，查询中切换项目，检查旧响应不污染当前项目状态。二者都需要从 UI 到后端再返回 UI 的可关联证据。
