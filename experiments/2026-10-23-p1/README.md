# P1：统一输入对照与事实补充 v0.1

日期：2026-10-23。本文保留第一轮统一对照及事实存储验证的当时结果。**P1 已在后续完成，最终状态、选型与新增证据见[完成报告](../2026-10-23-p1-completion/README.md)。**

本轮让 CBM、CodeGraphContext（CGC）、CodeGraph 读取相同的 65 个真实文件和 3 个自写 fixture。CGC 提取出了首链关键 C++ 方法定义；CodeGraph 在 TS 抽象类方法归属上更完整；CBM 的最小反例暴露了重载合并和智能指针同名错连。当前继续用 CGC 验证集成，CodeGraph 保留为底座备选，CBM 保留为导航与更新对照。

新增的 Tree-sitter 补充提取器独立于这三个工具，自动提取声明、限定名称、完整参数拼写、调用位置和属性赋值。已把这些事实接入 CGC 使用的 Kuzu 数据库，并验证查询、删除、恢复及失败回滚。调用目标解析和完整业务链仍待完成。

## 1. 输入、版本与原生输出

| 项目 | 固定版本 |
|---|---|
| Insight | `d4e8d1cf9f90208bcbe5371c127088f6fd66c688` |
| CBM | 官方 Windows amd64 v0.12.1；EXE SHA256 `39f6a789cd858d7428561ac5afaefb9a47b018dcba0ad6fa41ae71a45e0ed656` |
| CGC | 0.6.13，`93c9685bff9151f50a3121e9913e5ba2d27c1191`；原版 Tree-sitter 流程 |
| CodeGraph | 官方 Windows x64 v1.39.0，对应 `7bac941c1916d34fae0e93dd0ffeaef360d741fb` |
| 自有适配 | syntax_supplement 0.1.0；实现文件摘要见 provenance |
| 解析与存储 | Python 3.11.9、Tree-sitter 0.25.2、language-pack 1.20.0、Kuzu 0.11.3 |

真实输入是此前 42/46 文件清单的并集：22 TS、5 TSX、17 H、13 CPP、8 JSON，包含首链全部 15 个参考锚点。三个工具的输入 manifest 字节一致；源文件按 LF 归一化后逐个核对哈希。输入仍是研究切片，未补齐编译依赖闭包。

自写 fixture 检查：C++ 纯虚声明、两个重载、类外定义、相同类名处于不同命名空间、智能指针 `get()`；TS 抽象类、泛型覆盖、箭头回调和 `window.requestData` 绑定。参考答案进入测试断言和结果审查，提取阶段只读源码与文件清单。

相同输入下仍保留各工具原生过滤，并公开差异：

| 工具 | 原生 File 节点对应的输入文件 | 未出现 File 节点的输入 |
|---|---:|---|
| CBM moderate | 54 / 65 | 8 JSON、3 个测试文件；后者受目录/文件过滤影响 |
| CGC | 65 / 65 | 无；File 节点存在不代表其中全部语法或调用已解析 |
| CodeGraph | 57 / 65 | 8 JSON |

CBM 覆盖查询明确取回全部 65 项，未使用默认只返回 20 项的截断结果。计数与耗时按各工具原生定义保留，不作准确率或速度倍率排名。原生证据：[CBM](evidence/cbm.json)、[CGC](evidence/cgc.json)、[CodeGraph](evidence/codegraph.json)。

## 2. 同一机制的对照结果

| 检查 | CBM 原版 | CGC 原版 | CodeGraph 原版 |
|---|---|---|---|
| 真实 Handler 与 DB/Text 方法定义 | 能找到定义；数据库调用有缺口 | 三个关键定义均找到 | 三个关键方法定义缺失；头文件按 C 分类 |
| fixture 两个 Live::query 定义 | 合并为一个，保留第 4 行 | 第 3、4 行分别保留；第二个参数丢失 const/指针拼写 | 两个定义均未提取 |
| fixture 纯虚 query 声明 | 未提取 callable | 未提取 callable | 未提取 callable |
| fixture 智能指针 get | 错连 CacheGuard.get | 未生成这条调用边 | 未生成这条调用边；保留 raw call |
| fixture 回调中的 this.send | 归属 File 且目标是基类 send | callback → 子类 send | callback → 子类 send |
| TS 抽象基类 send 的所属类 | 有 BaseConnector | 方法存在，原生 owner 为 null | 正确保留 BaseConnector |
| 真实 ClientConnector.fetch → send | 此前及本轮存在基类错连 | 指向本类覆盖方法，第 178 行 | 指向本类覆盖方法，第 178 行 |
| 自定义消息到后端的完整链 | 未通过 | 未通过 | 未通过 |

未生成边的条目表示目标未恢复。CBM 的 C++ 反例中，`consume(Store&)` 调用 `query(1)` 却连到唯一保留的 `query(const char*)` 定义，不能作为确定调用发布。CGC fixture 没有 C++ 调用边；这比错误目标更容易显式保留未知，但尚未满足候选调用需求。

CodeGraph 的 TS 方法归属优势保留在比较中。此前 HTTP 方向、服务身份与共享节点更新的问题仍以[上一轮报告](../2026-10-23-unit-flows/README.md)为证据，本轮没有重复执行那些场景。

## 3. 新增的自动事实

[syntax_supplement.py](../../adapters/syntax_supplement.py) 复用现有 Tree-sitter 语法包，补充以下内容：

- C++ 头文件方法声明、纯虚标记、类外定义、命名空间、参数和签名原文；不同重载保留不同源码实体。
- TS 抽象类及泛型方法归属、嵌套回调的词法归属。
- 调用表达式及参数原文；全部标记为 `unresolved`，保留未解析原因。
- `window.requestData = createRequest(connector)` 等属性赋值，执行条件标为尚未求值。
- 解析错误的位置及被跳过的声明，明确预处理、类型检查、调用目标与绑定目标尚未求解。

65 个输入中，57 个 C++/TS 文件进入提取，8 个 JSON 明确列为范围外；产出 2,041 个声明/定义等 callable 记录、6,418 个调用位置、260 个属性赋值。这里的“调用位置”记录源码出现了什么表达式，尚未建立到目标函数的调用边。

真实首链已自动补齐：

| 源码事实 | 位置 |
|---|---|
| VirtualTraceDatabase::QueryUnitFlows 纯虚声明 | VirtualTraceDatabase.h:83 |
| DbTraceDataBase 方法声明 / 定义 | DbTraceDataBase.h:114 / DbTraceDataBase2.cpp:337 |
| TextTraceDatabase 方法声明 / 定义 | TextTraceDatabase.h:81 / TextTraceDatabase.cpp:636 |
| QueryFlowsBySliceInfoHandler::HandleRequest 声明 / 定义 | 对应头文件:31 / CPP:28 |
| BaseConnector.send 的词法类归属 | modules/lib/src/connection/index.ts:78 |
| window.requestData 属性赋值 | modules/timeline/src/bootstrap.tsx:89 |

完整限定名称及源码哈希在 [syntax.json](evidence/syntax.json)。DbTraceDataBase.cpp 的 2126、2160、2164 行出现解析错误，涉及 `process.operator bool()` 一类表达式；对应方法范围记录诊断并跳过 callable 提取。这是本次语法解析结果，未经过编译器判断。

## 4. 存储与维护验证

[kuzu_fact_store.py](../../adapters/kuzu_fact_store.py) 在 CGC 数据库副本中建立自有表，原生节点和关系保留原样：

- `PMFact` 存储声明、调用位置及属性赋值，附快照、源码哈希和完整证据。
- `PMSyntaxEdge` 表达“这个函数中观察到这处调用”，方向是所属函数 → 调用位置。
- `PMRefines` 按同一已核实输入中的唯一路径/行号关联原生 Function 与补充事实。它是源码位置关联，不证明类型等价。

真实切片导入了 **8,719 条事实、6,279 条调用位置归属关系、762 条原生位置关联**。3 处同一行有多个补充实体，保留歧义记录，没有强行合并。未建立所属函数关系的调用位置仍以节点保存。

删除该快照后，其补充事实为 0；原生 Function 数量始终为 790，包含真实切片 776 个和 fixture 14 个。恢复后事实与关系计数一致。合成接口试验也通过了自定义节点、带条件的有向关系、查询和删除。见 [integration.json](evidence/integration.json) 与 CGC 的 `extension_probe`。

22 项本地测试通过，包含删除清理、跨快照保留、写入失败回滚、重复导入、错误输入拒绝、同一行歧义和语法反例。CI 增加独立测试任务。当前验证覆盖数据库/API 层，尚未实现统一 MCP 查询入口或仓库提交自动刷新。

## 5. 决策与下一步

**工作路线：CGC + 独立语法补充，继续验证调用与类型事实。** 已验证 CGC 能保留首链关键定义且能维护扩展事实。原生关系仍需按解析依据审查，不统一升级为确定事实。

**CodeGraph 保留为底座备选。** 相同输入证明其 C++ 原生提取缺口仍在，也证明其 TS 方法归属的优势。补充提取器可以复用于它；接入其存储、查询和更新的成本尚未实测。当前不能给出总改造成本排名。

**CBM 保留导航与更新对照。** 最小反例中的重载合并和错误目标使其现有调用关系不适合直接充当确定事实。

code-map 的接口/子图机制、CoderMind 的职责组织继续按相应层评估。P1 同时改造多个完整底座的数量受工作量约束，候选资格不受该数量限制。详细比较见[候选决策与编译索引准备](selection.md)。

下一轮 P1 按顺序完成：

1. 规范化类、方法声明/定义与候选实现，保留重载、命名空间和选择依据。
2. 恢复有证据的接收者类型与 TS 请求绑定；未知与多候选保持可查询，重跑本轮负例。
3. 检验 CodeGraph 接入同一补充事实的最小成本，再比较查询/更新接口；避免仅因 CGC 已接入就锁定选择。
4. 在具备真实编译上下文的环境验证 C++ SCIP，分别审查两个工具的导入结果；不能用合成索引代替编译器测量。
5. F02/F03 完整门槛通过后进入 P2 协议提取。运行环境准备继续独立推进。

## 6. 验收状态与复现

| 检查 | 本轮状态 | 证据与剩余部分 |
|---|---|---|
| F01 输入/覆盖 | 通过，限本轮切片 | 一致 manifest；各工具 File 清单、过滤信息；补充提取逐文件诊断 |
| F02 C++ 事实 | 部分检查已执行，完整项未通过 | 必要声明/定义已补齐；类型、声明/定义关联与候选目标待完成 |
| F03 TS 事实 | 部分检查已执行，完整项未通过 | 泛型/类归属/回调与赋值可查；全局绑定传播待完成 |
| F04 扩展维护 | 通过，限数据库/API 层 | 合成接口与真实事实均完成查询/删除；事务回滚和快照隔离测试通过 |
| F05 参考独立性 | 通过，本轮 runner | 提取不读取 reference.json；命名查询仅筛选已生成输出 |

P1 整体保持进行中。P2–P7 及真实运行场景尚未验收。

复现入口：[reproduce.md](reproduce.md)。[provenance.json](evidence/provenance.json) 固定实现、输入与解析器缓存的哈希。公开证据可由检查脚本核对；完整数据库、源码副本和原始日志保留在仓库外。

调试中遇到的 Windows IPC 路径过长、CGC 查询使用非 POSIX 路径、CBM 覆盖分页、CodeGraph SQL 排序字段以及跨平台换行问题均已在 runner 中修正并重新执行。它们属于实验脚本/环境问题，不计为工具能力失败。
