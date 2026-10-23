# 响应字段生产：按调用位置展开引用参数

从 `QueryFlowsBySliceInfoHandler::HandleRequest` 的响应对象出发，已经自动查到 `unitAllFlows` 的 7 个生产位置：DB 候选 5 个、Text 候选 2 个。每条结果包含两层调用、实参到形参的绑定、最终写入位置和各函数内的条件。**这一增量完成字段生产关系的提取，D02 的序列化、前端解包和状态消费继续实施。**

证据类型：实际执行源码提取、上下文查询、自动测试与数据库读回。Insight 固定提交为 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`；规则冻结于 `b613890`。输入 [141 文件](output-manifest.json) 在前一批输入中加入 `TextTraceDatabaseChart.cpp`，其中定义了文本数据库的响应组装函数。完整记录见 [output-fields.json](evidence/output-fields.json)。

## 提取机制

提取器把每个形参和局部声明作为独立的对象根，再记录成员、指针所指对象和下标路径。引用别名继续指向原对象；按值复制得到新的对象根。对象身份由声明作用域确定，同名变量在不同函数或嵌套作用域中保持分离。

每个调用位置记录候选函数、可写引用/指针形参以及对应实参。查询遇到辅助函数的字段写入时，用该次调用的实际对象替换形参，逐层回到调用者。虚方法的候选来自 P1 的声明、继承与覆盖关系，并保留运行时实现未知的状态。

在真实案例中，处理器的 `response` 引用来自 `*responsePtr.get()`。进入数据库函数时传入 `response.body`，数据库函数又把该参数传给组装函数。七处写入最终都投影为同一个对象路径：

```text
responsePtr → 所指对象 → body → unitAllFlows
```

类名、函数名、字段名和参数名均取自源码。预期名称与七处写入的断言放在验收脚本中。改名、复制与引用、两次调用使用不同实参、同名遮蔽、指针重新赋值、虚实现分支及未执行 lambda 均有测试。

## 实测结果

| 项目 | 结果 |
|---|---|
| DB 字段生产 | 4 个组装函数内的 5 处 `push_back` |
| Text 字段生产 | 仿真分支和常规组装中的 2 处赋值 |
| 处理器查询 | 返回 9 个字段/对象写入候选，其中 7 个对应目标字段；未截断 |
| 源码事实 | 2,293 个声明根、3,424 个对象路径、1,321 个写入、968 个含可写参数绑定的调用 |
| 完整图 | 19,432 个节点、27,756 条关系 |
| 测试 | 126 项 Python 测试通过 |
| Kuzu | 完整载荷读回一致，读回图仍找到七处写入，790 条原生函数记录保持一致 |

图中新增对象声明、对象路径、字段写入及局部关系。跨调用的写入关系由查询按调用位置组合，避免把共用形参连接到其他调用者的对象。

分析保存未解析调用等缺口：全输入有 1,355 条此类诊断，本次处理器查询涉及 42 条。这些调用的副作用尚未完整展开，因此七处写入是已经恢复的源码候选。条件按所在函数分别保存；异常控制流、动态别名、隐式 `this` 成员副作用和 lambda 执行仍有缺口。

## 复现

依赖与 P2 基础图准备见 [P2 复现](../2026-10-23-p2/reproduce.md)。使用关闭的原生 CGC 数据库作为副本来源，输出写到新的仓库外目录：

```sh
python scripts/build_data_graph.py --source /path/to/msinsight --base /outside/p2/graph.json --manifest experiments/2026-10-23-p3/output-manifest.json --output /outside/new-output-graph
python scripts/query_data_graph.py /outside/new-output-graph/graph.json --writes Dic::Module::Timeline::QueryFlowsBySliceInfoHandler::HandleRequest
python experiments/2026-10-23-p3/run_output_fields.py --graph /outside/new-output-graph/graph.json --cgc-db /outside/p1/cgc.kuzu --output /outside/new-output-store
python scripts/check_p3_output_fields.py
```

成功运行记录位于工作区相对路径 `work/repo-map-research/results/p3-output-fields-01/` 与 `work/repo-map-research/results/p3-output-store-01/`。数据库缓冲区为 1 GB。沿用 Git 版本和行为检查，不重新核验文件哈希。
