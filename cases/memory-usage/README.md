# 第三条真实链登记：Memory/view/memoryUsage

状态：**已登记，人工源码审计，待 P7 冻结规则后执行自动提取验收。** 输入提交为 Insight `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`。本例覆盖 memory 模块、timeline 数据库管理与时间偏移、MemoryParse 缓存，以及前端曲线状态。

选择这条链，是为了检验已有规则能否从新的请求包装和模块作用域恢复连接，并把缓存命中、数据库查询和响应采用条件区分开。具体业务名称只供评分，不写入提取规则。

## 已核对的参考锚点

下列位置由源码审计形成，尚未计入自动建图结果。仓库文件可从 [固定版本](https://gitcode.com/Ascend/msinsight/tree/d4e8d1cf9f90208bcbe5371c127088f6fd66c688)查看。

| 阶段 | 源码位置 | 参考事实 |
|---|---|---|
| 前端 API | `modules/memory/src/utils/RequestUtils.ts:91` | memoryCurveGet 请求 Memory/view/memoryUsage |
| 请求包装 | `modules/memory/src/bootstrap.tsx:55` | window.request 调用 connector.fetch 并解包 body；保留请求频率与失败分支 |
| 模块身份 | `modules/memory/src/connection/index.ts:22` | 连接器配置 module 为 memory |
| 命令定义 | `server/src/modules/defs/ProtocolDefs.h:158` | REQ_RES_MEMORY_VIEW 定义请求命令 |
| 注册 | `server/src/modules/memory/MemoryModule.cpp:47` | 命令注册到 QueryMemoryViewHandler |
| 解码/序列化 | `server/src/modules/memory/protocol/MemoryProtocol.cpp:35`、`:48` | 请求与响应回调注册 |
| 缓存命中 | `server/src/modules/memory/handler/QueryMemoryViewHandler.cpp:42` | Exist → ComputeCurve → response.data.lines → SendResponse |
| 查询与缓存写入 | 同文件 `:50`、`:58`、`:60` | QueryCurveData → PutCurve → ComputeCurve → response.data.lines |
| 数据库候选 | 同文件 `:65`、`:83` | timeline 数据库管理器提供对象，调用 QueryMemoryView；比较模式另有双数据库查询 |
| 前端消费者 | `modules/memory/src/components/DynamicLineChart.tsx:105`、`:129` | 请求编号筛选后，将 resp.lines 交给图表状态 |

## P7 验收约定

1. 在执行本例提取前登记规则提交和输入清单，原样保存首次输出与失败项。
2. 自动发现 window.request 的实际绑定、memory 作用域、命令注册、解码与 handler，禁止使用上表生成连接。
3. 展开 lines 的生产、序列化、返回和图表状态；缓存命中与数据库查询分支分别给条件和来源。
4. 从数据库方法、lines 字段和缓存资源反查前端入口，区分普通查询和比较模式。
5. 删除注册、改命令、使用不同缓存实例/键、替换返回字段时，检查失配和隔离；请求编号不匹配时不得生成无条件的前端采用关系。
6. 发现新机制时保留首次失败证据，明确新增通用规则，再回归 unit/flows 与第二条真实链。

本登记完成 P3 的第三链选定事项。Q03 的自动复用验收与真实运行证据仍在后续阶段执行。
