# abbaing/code-map：unit/flows 独立实测

执行日期：2026-10-23。结论类型分别标为**实测**、**源码核对**、**待实现/未测**。本次只报告 code-map，没有读取或汇总其他工具的试验输出。

**实测结论：原版能在显式根目录配置下提取真实切片的前端文件与 import 关系，但没有恢复 Insight 的 `timeline/unit/flows` 业务接口或任何 C++ 处理链。受支持 React/.NET 对照能按具体 HTTP 方法和路径连接；不同服务同方法同路径会合并到一个接口节点并关联两个提供方。更新验证使用显式全量扫描。**

## 固定版本与输入

- 工具：[abbaing/code-map@d57c92b](https://github.com/abbaing/code-map/tree/d57c92bda4c3b1f62be8d2e75c9a45dddd430bb4)，包版本 0.1.0；直接运行该 checkout 的 `cli.mjs`，未安装发布版、未修改上游实现。
- 产品：[Ascend/msinsight@d4e8d1c](https://gitcode.com/Ascend/msinsight/tree/d4e8d1cf9f90208bcbe5371c127088f6fd66c688)。输入为保留仓库相对路径的 46 文件切片，其中 24 个 JS/TS 源文件、14 个 C++ `.h/.cpp` 文件、8 个项目元数据文件。全部 15 个 reference 锚点均包含在切片中。
- 切片包含请求、bootstrap、两个 `getUnitFlows` 前端消费者、公共请求/通信封装、Framework 转发/响应处理、C++ 常量/注册/module 和 command 分发、handler、数据库基类、两实现及数据库管理器。切片不是完整模块或完整传输闭包；不据此宣称全仓覆盖。
- 基线逐文件 SHA-256 在 `manifest.json`；副本修改后清单在 `mutated-manifest.json`；HTTP 合成控制清单在 `http-manifest.json`。这些清单只有相对路径、大小和哈希，不含第三方源码。
- Windows 10、Node v22.23.3、npm 10.9.9、Python 3.11.9。`npm ci --omit=dev --ignore-scripts` 使用本工具 checkout 的本地依赖及独立 cache；无全局安装/配置。锁文件和 CLI 哈希见 `environment.json`。
- 所有扫描均为 `--scan`。未启动 GUI/HTTP/MCP 服务、未调用 LLM、未执行目标应用、未注入 `runtimeLinks`，未对产品原 checkout 作修改。

## 默认检测与显式配置分别实测

| 模式 | 配置/根目录 | 实测输出 |
|---|---|---|
| 无配置默认扫描 | 检测为 `unknown + none`，frontend=`src`，无 backend | 0 节点、0 边；进程成功退出 |
| 显式配置扫描 | frontend=`modules`，backend=`server`；默认模板启用 React/TS 和 .NET；补充两个 import alias | 24 个文件节点、20 条 `imports` 边；没有业务接口、调用边、C++ 节点 |
| 修改 C++ 后显式重扫 | 仅在切片副本改协议常量并删除 handler `.cpp` | 仍 24 节点、20 条 import 边；排序后的节点/边与基线完全相同 |

这说明本切片需要先修正自动根目录检测；显式根目录成功也不等于增加了 C++ 或自定义消息协议支持。默认检测的零结果只适用于该真实切片，不推断完整仓库检测行为。每次扫描约 0.32–0.45 秒，只是本机小切片进程耗时，不作跨工具性能排序。没有超时或主动中止。

**实测文件/关系粒度：** `request.ts`、bootstrap、公共 Request/connection、Framework connection、`FilterLinkLine.tsx`、`AscendUnit.tsx` 均有文件节点。两个 consumer 到 `request.ts` 有 `imports` 边，`Request.ts` 到 lib connection 有 import 边，bootstrap 到 lib 入口有 import 边。这些都是文件依赖；输出没有 `getUnitFlows` 函数节点、`window.requestData` 消息调用边或 `module=timeline, command=unit/flows` 接口节点。`unit/flows` 字符串没有出现在图中。

**实测查询/导出：** 以 `file:modules/timeline/src/api/request.ts` 为种子、`direction=both, depth=3` 执行 `submap create`，得到 10 节点/11 边并成功 `submap inspect --json`。这是 import 邻域，包含两个消费者及共享类型等依赖；没有得到端到端 handler/数据库路径。

**实测诊断：** 对不存在于图中的 C++ handler 文件作显式节点查询，返回结构化 `SUBMAP_SEED_NOT_FOUND`，原生进程退出码为 3。原版图的 warning 只有通用静态分析提示，没有逐个解释 14 个 C++ 输入为什么未索引。未发现边，不能解释为代码之间没有依赖。

## HTTP 正反例、方向、服务范围和歧义

合成 fixture 有 React `App.tsx → api.ts`、两个独立 namespace/`.csproj` 服务 ServiceA/ServiceB。未构建或运行这些应用。

| 输入 | 实测结果 |
|---|---|
| frontend GET `/api/items`；ServiceA GET 同路径 | 连接成功 |
| frontend POST `/api/onlyget`；provider 只有 GET 同路径 | 保留独立 POST endpoint，无连接到 GET provider |
| frontend GET `/api/absent`；无该路径 provider | 保留消费端 endpoint，无 provider 匹配 |
| frontend GET `/api/shared`；两个 service 都提供 GET 同路径 | 只有一个 `endpoint:GET /api/shared`，同时连接两个 controller |
| frontend 绝对 URL `https://other.invalid/api/items` | 没有提取该绝对 URL；不把它当跨 host 范围保护通过 |

**方向：** 前端文件 `--calls-api→ endpoint`；endpoint `--handled-by→ controller文件`；匹配还产生同方向的 `resolved-controller`。例如 GET items 的两条 provider 边都指向 ServiceA controller。图中没有反向 provider→consumer 边；可用 incoming/both 遍历反向查找。`handled-by` 与 `resolved-controller` 是两种关系，不代表两次请求或两条独立执行路径。

**服务范围：** 两个独立 `.csproj` 中的 GET shared 共享相同接口 ID。该节点同时有到 A/B 的 `handled-by` 和 `resolved-controller` 边，但 `meta.backend` 只留下 ServiceB 的单个 action/controller/path。图保留两个候选 provider 的边，元数据没有完整表达这项多义性。未观测到 service namespace、`.csproj`、host 或 module 参与接口身份，也没有专门的碰撞 warning；不应据此选定唯一服务。

**源码核对：** [endpoints.mjs:12](https://github.com/abbaing/code-map/blob/d57c92bda4c3b1f62be8d2e75c9a45dddd430bb4/src/core/endpoints.mjs#L12) 的 ID 由方法和规范化路径构成；[同文件:111](https://github.com/abbaing/code-map/blob/d57c92bda4c3b1f62be8d2e75c9a45dddd430bb4/src/core/endpoints.mjs#L111) 的匹配依据为具体方法/ANY 和路径。module 作为节点属性传入，未加入 ID 或此匹配条件。[graph-model.mjs:7](https://github.com/abbaing/code-map/blob/d57c92bda4c3b1f62be8d2e75c9a45dddd430bb4/src/core/graph-model.mjs#L7) 合并同 ID 节点并浅合并 meta，解释了单个 backend 描述被覆盖；自环被过滤，因此本例没有独立 `matches-endpoint` 自环。具体方法/路径负例通过，不等于 ANY、参数路径、动态常量或多服务范围全部通过。

## 更新方式与结果

1. 在 Insight 切片副本将 `REQ_RES_UNIT_FLOWS` 的值由 `unit/flows` 改为 `unit/flows/v2`，删除 `QueryFlowsBySliceInfoHandler.cpp`，再次执行 `--scan --config`。语义图未变；这些业务元素从未被索引，不能以未变视为正确增量维护。
2. 在 HTTP fixture 删除 ServiceB provider 后显式全量重扫，输出从 9 节点/12 边变为 8 节点/10 边；准确移除 B controller 及其两条 provider 关系，A 保留。
3. 将客户端 GET items 改为 GET renamed 后重扫，输出为 9 节点/9 边。旧 GET items provider 仍存在，但其消费/匹配关系消失；新增没有 provider 的 GET renamed 消费端。
4. 对相同最终源码另建无 `.code-map` 输出的干净 fixture，完整扫描后节点和边与第三步一致。

**这轮验证的是显式全量重扫，不是 watch、后台自动监视、增量索引或提交触发更新。** 清洁重建一致性只核对排序后的完整节点/边，时间戳等图顶层字段不参与比较。

## S01–S07 的边界

| 验收 | 结果 |
|---|---|
| S01 请求 module/command 与值来源 | 未恢复；只有 request 文件节点 |
| S02 精确注册/handler | 未恢复；C++ 注册/分发文件无节点 |
| S03 数据库接口/候选实现/选择条件 | 未恢复；这些文件存在于输入，但未被索引 |
| S04 参数/DB/响应/消费者 | 仅恢复两个 consumer 文件的 import；参数和结果流未恢复 |
| S05 后端反查前端入口 | 业务链未通过；前端文件 import 邻域可双向查询 |
| S06 关系更新 | HTTP 删除/改路径显式全量重扫通过；Insight 业务更新未通过；watch 未测 |
| S07 断点/歧义/过滤/版本诊断 | 有通用 warning 和缺失种子结构化错误；没有 C++ 排除原因或服务碰撞专项诊断；源码 commit 由实验外部记录 |

动态正常查询、延迟后切项目、旧响应断言、完整 SQL/表依赖、全仓分析、handler 重命名、consumer 删除、module/command 碰撞、目标类型变化、快速连续提交、失败重试和跨版本快照均未测。不能从静态 import 或 HTTP fixture 推断这些行为已通过。

## 缺少的适配与复用判断

**源码核对：** 后端默认 discovery 明确仅匹配 `.cs`，见 [templates/csharp.mjs:11](https://github.com/abbaing/code-map/blob/d57c92bda4c3b1f62be8d2e75c9a45dddd430bb4/templates/csharp.mjs#L11)。插件契约支持 `fileKinds / parsers / scanners / enrichers`，见 [templates/contracts.mjs](https://github.com/abbaing/code-map/blob/d57c92bda4c3b1f62be8d2e75c9a45dddd430bb4/templates/contracts.mjs)；加载需显式 `--allow-plugins`，见 [template-plugins.mjs](https://github.com/abbaing/code-map/blob/d57c92bda4c3b1f62be8d2e75c9a45dddd430bb4/templates/template-plugins.mjs)。这是已核对的扩展入口，不是已执行的 Insight 插件。

**待实现：** 至少需要 C++ 文件发现/解析与符号/调用/继承事实；常量求值；`(module, command, protocol, scope)` 接口身份；TS 自定义消息发起与 bootstrap 全局绑定/封装传播；C++ map 注册、module/command 动态分发；虚函数候选实现与数据库选择条件；响应消费者和状态数据流；缺边/过滤/多义诊断及版本证据。不能把填入人工 `command→handler` 的 runtimeLinks 当作自动提取。

本轮没有写插件。原版可复用候选是图/子图导出和前端 import 层；要贯通 Insight，需要上述真实提取能力。没有证据支持“只配个 React 根目录即可直接替代 C++ 分析器”。

## 许可证与产物

**上游声明：** [package.json](https://github.com/abbaing/code-map/blob/d57c92bda4c3b1f62be8d2e75c9a45dddd430bb4/package.json)、[LICENSE](https://github.com/abbaing/code-map/blob/d57c92bda4c3b1f62be8d2e75c9a45dddd430bb4/LICENSE) 为 `AGPL-3.0-only`；[COMMERCIAL.md](https://github.com/abbaing/code-map/blob/d57c92bda4c3b1f62be8d2e75c9a45dddd430bb4/COMMERCIAL.md) 另列商业授权路径，包括其所述闭源集成/扩展等场景。研究仓库自己的 MIT 不会重授予 code-map 的许可证。本轮仅外部运行工具，未复制上游实现；以后复用/分发/集成需单独按实际方案评估许可，不能预先宣称闭源插件无约束。

可公开产物：本报告、`evidence.compact.json`（保留实际接口节点、方向和删除边）、三个 hash manifest、`environment.json`、自写 `run_experiment.py` 和 `reproduce.md`。`evidence.json` 与 `raw/` 保存更完整本机结果；`fixtures/`、`preliminary-*`、npm cache、第三方源码与完整图不提交。进程输出中的异常诊断属于预期负例，不是扫描自然失败。

本任务采用目录/流程隔离，没有读取其他工具试验目录、没有联系其他子智能体或派生子智能体；共享文件系统不构成安全隔离。本报告不宣称安全隔离或严格盲测。
