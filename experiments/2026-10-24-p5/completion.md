# P5 完成报告

日期：2026-10-24。**R01–R06 全部通过。** P1–P5 的本轮目标完成，到此停止；P6 历史问题资产适配和 P7 综合验收保持待办。

本轮在独立 MindStudio Insight 副本中完成真实构建、浏览器操作、跨层采集和状态断言。GitCode 远端与原下载副本保持不动；实验副本禁用推送，故障守卫已恢复到正常采集版本。工具、紧凑结果和复现说明提交到本研究仓库，产品构建及原始日志保留在仓库外。

## 验收结果

| 项目 | 实际执行与结果 | 证据 |
|---|---|---|
| R01 运行前提 | 构建 Framework、Timeline、C++ 后端；通过 UI 导入公开 Text trace 并显示泳道 | [构建与启动](evidence/boot.json) |
| R02 正常查询 | 三次实际点击 Enqueue，返回预期 flow；UI、API、请求、handler、数据库、响应及状态身份相连 | [正常场景](evidence/normal.json) |
| R03 项目切换 | 三次暂存 A 的真实响应，切到 B 后放行；旧响应被丢弃，B 的状态不变 | [切换场景](evidence/late.json) |
| R04 并发与缺口 | 两个不同请求同时等待时各自关联；漏采、错追踪、重复编号、交换结果均被识别 | [并发与负例](evidence/parallel.json) |
| R05 断言自检 | 显式放行旧响应后，B 连线被 A 覆盖，状态断言失败；关闭开关及恢复原守卫均通过 | [故障对照](evidence/fault.json) |
| R06 图与运行关联 | 五份真实记录映射到两个源码版本的图；跨源码或配置拒绝直接叠加，未映射事件和失败保留 | [版本关联](evidence/mapping.json) |

正常查询和迟到响应走不同路径，二者都满足各自的独立状态断言。故障实验则明确违反“B 不被 A 覆盖”的断言，保留实际采用旧响应的调用与状态记录。路径是否相同与结果是否正确分开判断。

## 运行记录怎样接入图

[P4 构图入口](../../scripts/refresh_project_map.py)从两个产品实验提交各自导出 157 个文件，生成并发布图，每份包含 25,480 个节点、36,709 条边，Kuzu 存储读回一致。两图数量相同，源码版本与条件内容分别保存。范围由 [graph-config.json](graph-config.json)声明。

[link_runtime.py](link_runtime.py)把采集点规则应用到已经提取的节点：API 定义、采集调用点、状态赋值，以及原生 RTTI 解码后的实际 handler/数据库实现。类型名称来自本次运行，节点来自静态提取；规则没有向静态图补写调用边。请求身份关联和静态邻接关系分别保存，静态邻边的执行情况保持未知。

| 记录 | 已映射源码锚点 | 未映射事件 | 独立场景结果 |
|---|---:|---:|---|
| 正常查询 | 14 | 3 | 通过 |
| 项目切换 | 12 | 3 | 通过 |
| 两个待返回请求 | 28 | 6 | 通过 |
| 故障开关关闭 | 12 | 3 | 通过 |
| 故障开关开启 | 14 | 4 | 按预期失败 |

一个运行事件可以同时关联采集点和实际被调函数，因此锚点数与事件数分别统计。未映射项是浏览器侧的 UI 动作、WebSocket 收发观察和故障启用事件；它们仍有原始证据和请求身份，未被丢弃。实际数据库目标为 `TextTraceDatabase::QueryUnitFlows`，handler 为 `QueryFlowsBySliceInfoHandler::HandleRequest`。

[runtime_records.py](runtime_records.py)复用 P4 的不可变记录与快照查询，额外比较源码、组件构建、运行配置、数据和场景上下文。同图同上下文允许叠加；跨版本只提供节点重定位候选；同图变更 strict mode 或故障开关也会拒绝直接叠加。旧记录保持原内容，旧验证不会自动成为新版本的验证。

构建来源由已执行的日志、源码提交和组件输入范围整理为 [正常构建记录](evidence/build-normal.json)与[故障构建记录](evidence/build-fault.json)。复用旧组件时，使用 Git 差异确认其输入范围与运行版本相同。构建记录属于来源证据，未重新核验二进制或源码文件哈希。

## 复现

构建、采集、正常/切换/并发及故障步骤见 [实验说明](README.md)。运行图关联时，以实际实验源码提交和构建日志更新构建记录，然后执行：

```sh
python scripts/refresh_project_map.py --source EXPERIMENTAL_CHECKOUT --revision NORMAL_COMMIT --store EXTERNAL_STORE --config experiments/2026-10-24-p5/graph-config.json --typescript TYPESCRIPT_JS
python scripts/refresh_project_map.py --source EXPERIMENTAL_CHECKOUT --revision FAULT_COMMIT --store EXTERNAL_STORE --config experiments/2026-10-24-p5/graph-config.json --typescript TYPESCRIPT_JS
python experiments/2026-10-24-p5/run_mapping_trial.py --source EXPERIMENTAL_CHECKOUT --store EXTERNAL_STORE --results EXTERNAL_RESULTS --output NEW_EXTERNAL_OUTPUT --demangler CXXFILT --normal-snapshot NORMAL_SNAPSHOT_ID --fault-snapshot FAULT_SNAPSHOT_ID
python experiments/2026-10-24-p5/check_completion.py
python experiments/2026-10-24-p5/query_runtime.py --store EXTERNAL_STORE --id RECORD_ID --snapshot SNAPSHOT_ID --context TARGET_CONTEXT_JSON
```

试验驱动读取 `p5-r06-normal-01`、`p5-r06-late-01`、`p5-r06-parallel-01`、`p5-fault-control-01`、`p5-fault-01` 五个目录。单个其他运行可用 `link_runtime.py --help` 中的参数接入。运行查询使用 `query_runtime.py`，同时传入图快照与目标执行上下文；P4 的通用记录查询只比较图版本。原始结果包含本机项目路径，仅保存在外置结果目录；公开证据保存相对源码路径、版本、计数和结论。

## 当前覆盖

运行验收覆盖 Framework、Timeline 和公开 Text 数据的 `unit/flows`，采用单条 WebSocket 连接；两个请求在 UI 侧同时等待，按请求顺序放行。推广到其他协议、重连、乱序响应及 DB 格式场景，需要相应采集点、场景和独立断言。当前首链提供了从真实交互到同版本图查询的完整实验方法。

回归结果与执行环境记录见 [测试清单](evidence/validation.json)。CI 检查紧凑证据、通用图与版本测试；真实产品运行由本机实验完成。历史证据中的 `remaining` 字段记录当时进度，当前完成状态以本报告为准。
