# P7 验收报告

P7 独立交付范围已完成：项目地图、统一查询和跨模块复用的源码验收 20 项通过，正式版本的隔离 AI 复验 11/11 通过。外部资产接入 P6 保持待办，M3 联合验收等待真实资产。

## 交付与范围

- [能力架构与覆盖矩阵](../../docs/06-capability-coverage.md)：11 个系统组成部分、18 类机制，连接调研结果、当前适配及后续缺口。
- [自动生成的项目地图](evidence/project-map.md)：34 个按目录规则识别的模块组、包/CMake 依赖和源码入口；同时显示全仓顶层目录与语言。职责说明来自包元数据和提取实体，没有生成 LLM 职责摘要。
- [查询入口](query.py)：`overview`、`search`、`trace`、`impact`、`resource`、`explain`、`assets`、`runs`、`coverage`。JSON 与 Markdown 展示同源，返回源码版本、条件、分页和深度截断。
- [源码验收](evidence/validation.json)：20 项通过，包含新目录重建；[AI 评估](ai-evaluation.md)单独报告每题事实、引用与用量。

全仓结构枚举为 4,855 个版本控制文件，词法预检扫描 2,487 个源码/清单文本。语义图输入为 191 个文件，产生 31,298 个节点、45,196 条边、2,837 条成员效应记录。输入状态为 parsed 179、包元数据 6、未应用配置 5、语法错误 1；语法错误来自 `server/src/modules/timeline/core/database/DbTraceDataBase.cpp`。图规模不等于语义覆盖率，Python 119 个、Rust 13 个文件的语义图输入均为 0。

## Q01–Q05

| 检查 | 结果与证据 |
|---|---|
| Q01 地图 | 全仓文件和语言枚举；34 个结构模块组；未展开模块及 18 类词法机制候选可查询。结构分组不等于完整功能分解 |
| Q02 查询 | 正反向、影响、资源、解释、覆盖与旧运行记录可查；资产入口明确返回 `not_connected` / `not_evaluated`。版本、条件、截断保留 |
| Q03 复用 | unit/flows、timeline/rankOffset、Memory/view/memoryUsage 的不同作用域注册均恢复；unit/flows 与 memory 的返回字段连接到前端状态。首轮失败、新规则和回归分别保留 |
| Q04 AI 任务 | 两名隔离参与者首次测试为 A 10/11、B 11/11。修正查询易用性后，正式输入的独立复验为 11/11；逐题评分见 AI 评估 |
| Q05 重建 | 在新目录从相同提交和规则重新构图；仅去掉两处快照 ID 后直接比较完整 JSON，相等。不核验文件哈希 |

P6 所属 H01–H06 尚未验收。Q02/Q04 当前检验资产未接入时的准确表达；真实资产的双向检索、版本适用性及运行关联随 P6 完成。

## 三条链实际得到什么

| 入口 | 自动提取的关键关系 | 证据状态 |
|---|---|---|
| getUnitFlows | timeline 注册 → QueryFlowsBySliceInfoHandler → DB/Text 候选 → unitAllFlows → 两处 singleLinkLine 状态；反向可达 | 有条件的源码链；保留选择、传输、生命周期及未建模调用条件 |
| queryTimelineOffset | timeline/rankOffset → 独立注册 → RankOffsetHandler；可正反向查询 | 本轮验收协议/处理器，未把它统计为完整返回数据链 |
| memoryCurveGet | memory 注册 → QueryMemoryViewHandler；缓存命中/查询后写缓存 → ComputeCurve 返回值 → lines 序列化/传输 → lineChartData；DB/Text 方法和缓存均能反查入口 | 有条件的源码链；请求编号守卫保留，尚无该链真实运行验证 |

memory 查询保留普通模式与比较模式、缓存命中与未命中、DB/Text 候选，以及前端 `requestId !== requestIdRef.current` 的返回条件。资源查询提供 key、title、legends、flatData 等成员的读写/使用位置，源码可导航到 PutCurve、ComputeCurve、Clear 和 MemoryParse::Reset。组合键等价、实际实例选择、锁跨多个调用的原子性、容量释放及运行内存占用仍需进一步分析或采集。

响应字段查询中的 `database_reverse_paths` 是沿用的字段名；memory 的两条直接生产者路径包含缓存 ComputeCurve 方法，不能把这个数解释为两个已执行数据库对象。两类 QueryMemoryView 数据库候选另有独立反向检查。

## 首轮失败与修复

[首次留出结果](evidence/first-pass.json)使用预先冻结的规则：memory 注册未匹配、前端曲线状态未提取，Kuzu 512 MiB 缓冲在扩展图事务中耗尽，发布失败。首次结果原样保留。

新增通用支持包括：相对 `using namespace` 的作用域查找；Promise.then 成功值与命名 useState setter；返回对象字段的值来源；有作用域的标量/容器成员效应。构建缓冲调为 1 GiB。业务名只进入案例评分，不参与提取规则。对应测试覆盖相对/全局命名空间、遮蔽、改名、不同对象/键、参数调用与返回值调用的区分，以及未知重赋值和深度截断。

四个事实副本负例验证删除提供方、改命令、改模块、移除 lines 序列化时不会保留旧匹配。它们检验查询隔离；源代码变更触发自动刷新的验收来自 P4。

首次 A/B 测试还暴露 CLI 参数提示不足、帮助被包装器截获、资源结果过大及运行选择摘要难找。随后补齐帮助与示例、符号反向查询、资源摘要的条数上限，以及从运行映射生成实际分派目标摘要。首次答案及错误说明保留，后续复验不给参与者旧答案或评分。

## 源码与运行版本

| 用途 | 源码提交 | 快照末段 |
|---|---|---|
| 正式静态地图 | `d4e8d1cf9f90208bcbe5371c127088f6fd66c688` | `bef7b86942a4416cb1e1719aeeaf7c1b` |
| 正式独立重建 | 同上 | `a9af00c2b30a481cbaf2694e848433a0` |
| P5 埋点版本回归及首次 A/B | `ccd0d88080861b0c7185bcca70a85bd61f823168` | `03cde2c328e748b5b721e97c0821b58a` |

P5 埋点版本在 `request.ts:179` 把响应对象传给动态观察函数，返回值分析因此报告潜在未知修改，unit/flows 的返回桥接保持 unresolved。[该次回归失败](evidence/instrumented-regression.json)保留，未按 probe 名字开白名单。正式交付回到原始源码版本构图，从独立 clone 导出；原 GitCode 仓库和原下载副本没有修改。

`runs` 读取 P5 的 5 条真实记录：normal、late、parallel、fault_control、fault，保留各自源码/快照/断言与未映射事件。它们记录过 TextTraceDatabase 的实际选择，以及旧响应丢弃和故障断言；不会继承为当前 P7 快照或 memory 链的运行验证。运行复现见 [P5 完成报告](../2026-10-24-p5/completion.md)。

## 复现与当前边界

构图规则提交为 `2e3553435d2a53704c4694932d9c8fa9df6c2d0c`，查询版本记录在 AI 输入元数据中。环境为 Python 3.11.9、Node 22.23.3、TypeScript 5.9.3、Tree-sitter 0.25.2、language-pack 1.20.0、Kuzu 0.11.3。构图、全仓预检和查询命令见 [README](README.md)；独立评分由 [run_acceptance.py](run_acceptance.py)执行，紧凑证据由 [package_evidence.py](package_evidence.py)生成。

本轮完整回归 294 项 Python、80 项 TypeScript 通过；随后查询易用性修改的 7 项定向回归通过。查询实现提交 `859f27d` 的 CI 完整套件通过；发布提交的 CI 同时检查公开证据一致性。图、数据库、第三方源码和原始运行数据留在仓库外。

当前交付是可重建的研究原型，覆盖清单决定下一步扩展范围：Python/Rust/FFI、其他事件与后台入口、取消/重试、跨调用并发、全量数据血缘和资源占用。词法候选用于发现这些区域；每类需要对应提取机制、正反例和运行证据。后续先依据覆盖矩阵选代表链，再实施适配与留出验证。
