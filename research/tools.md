# 工具调查

核对日期：2026-10-23。这里的“候选”不等于已经适配 Insight；不得把不同输入范围的结果排成准确率榜单。

## 已执行或审计的工具

| 工具 | 已核实的作用 | 证据等级与局限 |
|---|---|---|
| [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) | 结构索引、存储、查询、MCP、更新与快照 | 执行过过滤后的全仓及 watcher fixture；有同名错连、数据库漏边，未贯通自定义协议 |
| [CodeGraphContext](https://github.com/CodeGraphContext/CodeGraphContext) | 多语言图查询、导出、watcher，可选 SCIP | 真实切片和 watcher 执行过；全仓在观察边界主动中止；SCIP 未启用 |
| [RPG-ZeroRepo / CoderMind](https://github.com/microsoft/RPG-ZeroRepo/tree/main/CoderMind) | LLM 功能树、代码绑定、底层依赖图、查询与展示 | 只执行过非 LLM 核心结构模块及部分测试；完整功能地图、MCP 和语义更新未验收 |
| [RepoGraph](https://github.com/ozyyshr/RepoGraph) | 从定义/引用构图并给 agent 检索上下文 | 下载版有 namedtuple/dict 使用不一致和同名身份问题；不作为成熟多语言协议图证明 |

原始版本及结果见 [实测记录](experiments/2026-10-23.md)。当前没有一个默认配置通过端到端需求。CBM 只保留导航候选，不是最终选型结论。

RPG 的研究目录 `zerorepo/rpg_encoder` 中存在 `.py` 过滤，不能直接覆盖 C++/TS 为主的 Insight；同仓库 CoderMind 才是本轮多语言检查对象。

Code-Craft：做过论文层面调查，尚未取得可核实运行的官方开源实现，不纳入源码实测排行。

## 新一轮：接口发现与跨服务关联

CodeGraph 和 code-map 已追加原版实际执行：[unit/flows 结果与复现](../experiments/2026-10-23-unit-flows/README.md)。两个原版都未通过 Insight 端到端验收。

| 项目 | 已看到的实现/声明 | Insight 适配与状态 |
|---|---|---|
| [sina-parsania/CodeGraph](https://github.com/sina-parsania/CodeGraph) | 原版 v1.39.0 已扫描 42 文件切片；有前端局部调用和 HTTP hub | C++ 限定方法遗漏，unit/flows 未贯通；HTTP hub 缺到 handler 的有向边、服务身份合并，更新与 full rebuild 不等价 |
| [abbaing/code-map](https://github.com/abbaing/code-map) | 原版固定提交已扫描 46 文件切片；显式配置得到前端 import 图，React/.NET HTTP 对照有方向正确的关联 | C++ 未索引，自定义协议未恢复；同路径多服务合并；只验证了显式全量重扫，未测 watch |
| [OWASP Noir](https://github.com/owasp-noir/noir) | 按框架规则静态发现接口、参数和源码位置，AI fallback 可选 | 已核对官方材料；未运行。接口清单不等于完整链路，自定义协议支持待验证 |
| [MetaCall meta-ast](https://github.com/metacall/meta-ast) | 多语言统一符号/依赖结构，并含 MetaCall 特定连接检测 | 文档调查；“跨语言”不直接证明支持任意 HTTP/WS 协议关联 |

CodeGraph 指上述特定仓库，不是 CodeGraphContext。两者不能混用名称和结果。

code-map 的实际 `src/core/endpoints.mjs` 对路径有 `/api` 前缀约束，匹配边标为 medium；因此不把它表述为无框架限制、编译器级或任意项目可直接使用。

## 动态能力

- [OpenTelemetry](https://opentelemetry.io/docs/)：跨语言运行证据及上下文传播；自定义协议、异步边界和业务状态需接入。
- [Jaeger](https://github.com/jaegertracing/jaeger)：存储、查询与展示分布式追踪。
- [Playwright](https://playwright.dev/docs/trace-viewer)：前端场景及操作证据；不能自动替代 C++ 后端追踪。
- [Hypothesis stateful testing](https://hypothesis.readthedocs.io/en/latest/stateful.html)：状态机测试机制；不是 Insight 的现成行为模型。

以上动态方案尚未在本研究对象上接入。

## 许可证核对

许可证是候选筛选依据，下面仅记录所读文件，不作个案法律判断；实际复用时仍需核对所选提交及依赖。

| 项目 | 本轮读取的声明/文件 |
|---|---|
| CBM / CGC / RPG-ZeroRepo | 本地下载版本声明 MIT |
| CodeGraph | `LICENSE-MIT`，README 声明 MIT OR Apache-2.0 |
| code-map | `LICENSE` 为 AGPL-3.0 |
| Noir | `LICENSE` 为 MIT |
| meta-ast | Apache-2.0 |
| [Grafema](https://github.com/Disentinel/grafema) | FSL-1.1-ALv2，当前有用途限制，不归为当前宽松开源底座 |
| [graffiti](https://github.com/amazopic/graffiti) | Source-Available / Reuse-by-Permission，修改和复用需作者许可，不按可自由改造的开源库推荐 |

Grafema 官方文档明确描述了前端 HTTP 请求与 Express 路由的连接，证明该方向已有实现；同时限定了框架、动态 URL 和多匹配的行为。其许可证与技术支持范围均需单列，不能因功能接近就直接推荐为开源底座。
