# 来源与版本

调查时间：2026-10-23。外部默认分支可能变化，复现实验应使用固定提交；许可证也应核对所用版本。

## 项目与已下载工具

| 项目 | 链接 | 本轮版本 |
|---|---|---|
| Insight | https://gitcode.com/Ascend/msinsight | `d4e8d1cf9f90208bcbe5371c127088f6fd66c688` |
| CBM | https://github.com/DeusData/codebase-memory-mcp | 源码 `10ab613de30dfd573d0b251cd0ad648e1c7e5204`；执行 release v0.12.1 |
| CGC | https://github.com/CodeGraphContext/CodeGraphContext | `93c9685bff9151f50a3121e9913e5ba2d27c1191` |
| RPG / CoderMind | https://github.com/microsoft/RPG-ZeroRepo | `a4e6966c4ff59d84299bc56d6a47ae1f4f7b2885` |
| RepoGraph | https://github.com/ozyyshr/RepoGraph | `6c3977d87845993bf2c0359b4ac752278d7f3c45` |

论文题目及链接从作者官方仓库 README 追溯：RPG-Encoder、RepoGraph。Code-Craft 的作者版本和官方实现仍需补齐可核实条目，不在这里猜测链接或归属。

## 新候选的具体源码证据

- [CodeGraph README](https://github.com/sina-parsania/CodeGraph)，核对提交 `7bac941c1916d34fae0e93dd0ffeaef360d741fb`。
- [CodeGraph 路由提取与公共节点](https://github.com/sina-parsania/CodeGraph/blob/7bac941c1916d34fae0e93dd0ffeaef360d741fb/crates/codegraph-parse/src/lib.rs#L1210)。
- [CodeGraph HttpCalls 建边](https://github.com/sina-parsania/CodeGraph/blob/7bac941c1916d34fae0e93dd0ffeaef360d741fb/crates/codegraph-graph/src/lib.rs#L756)。
- [code-map README](https://github.com/abbaing/code-map)，核对提交 `d57c92bda4c3b1f62be8d2e75c9a45dddd430bb4`。
- [code-map 接口匹配器](https://github.com/abbaing/code-map/blob/d57c92bda4c3b1f62be8d2e75c9a45dddd430bb4/src/core/endpoints.mjs)。
- [code-map 分析支持边界](https://github.com/abbaing/code-map/blob/d57c92bda4c3b1f62be8d2e75c9a45dddd430bb4/ANALYSIS.md)。
- [Noir 接口提取及可选 AI](https://github.com/owasp-noir/noir#what-noir-does)。
- [meta-ast 的范围](https://github.com/metacall/meta-ast#scope)。
- [Grafema 跨服务方案](https://grafema.dev/docs/cross-service-tracing/)、[FSL 许可证](https://github.com/Disentinel/grafema/blob/main/LICENSE)。
- [graffiti 方案与许可证](https://github.com/amazopic/graffiti)、[具体许可文件](https://github.com/amazopic/graffiti/blob/main/LICENSE)。

## 运行时与场景验证

- [OpenTelemetry 官方文档](https://opentelemetry.io/docs/)、[语言 SDK](https://opentelemetry.io/docs/languages/)。
- [上下文传播](https://opentelemetry.io/docs/concepts/context-propagation/)、[自定义协议示例](https://opentelemetry.io/docs/languages/js/propagation/#custom-protocol-example)。
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)。
- [Jaeger](https://github.com/jaegertracing/jaeger)。
- [Playwright Trace Viewer](https://playwright.dev/docs/trace-viewer)。
- [Hypothesis 状态机测试](https://hypothesis.readthedocs.io/en/latest/stateful.html)。
