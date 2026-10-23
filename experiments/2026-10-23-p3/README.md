# P3：数据、状态与反向查询（实施中）

已从源码连接前端入口、后端处理器、DB/Text 候选、连接池工厂和数据类型状态，并识别共享状态的接收对象。**D01、D04 在 140 文件的选定范围通过；D02、D03、D05 继续实施，P3 尚未完成。**

最新增量沿引用实参自动恢复响应字段的 7 个生产位置，并验证按调用位置替换参数后的对象路径；126 项 Python 测试及保存后的查询通过。D02 后续补序列化、解包和前端消费，见 [响应字段生产报告](output-fields.md)。该批输入为 [141 文件](output-manifest.json)，原始数据库选择证据沿用下述 140 文件范围。

输入为 Insight 固定提交 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688` 的 [140 文件](selection-manifest.json)。当前证据见 [数据库选择与实例报告](selection.md)、[selection.json](evidence/selection.json)。第一组 [134 文件](input-manifest.json) 的历史证据保存在 [increment.json](evidence/increment.json)，其中门槛状态反映当时的进度。预期名称仅在评分脚本中，提取器使用 C++ 语法、类型候选和标准容器规则。

## 已执行的检查

- 前端入口到 DB/Text 实现均为 9 段有向关系，正反查询通过；协议关系和虚方法候选保留各自语义。
- 请求中的 `dbPath.empty()` 决定按 rankId 或 fileId 查找，条件方向及实参来源可展开。
- 连接池表的写入关联到三个构造位置：普通池的 DB/Text 分支和派生池的 DB 构造。创建时的数据类型读取进一步关联到状态表及其显式写入。
- 连接池构造参数绑定到保存的回调成员，调用该回调的位置可查；实际执行与对象选择保持未知。
- 容器迭代器的 `.second` 传播到连接池模板方法，`T` 绑定为源码中的虚数据库类型；提前返回和 switch 入口条件随候选保存。
- `SetDataType → 写入 → 可能被读取 → GetDataType` 可按源对象双向查询。直接调用和引用别名解析到同一个静态对象，边保留进程/链接映像、匹配键及中途未覆盖的条件。
- 114 项 Python 测试通过，覆盖改名、同名不同作用域、不同实例、类型传播、条件、资源读写及存储操作。完整图在 CGC/Kuzu 副本中读回一致，替换、删除、恢复通过，790 条原生函数记录保持一致。

数据库选择批次的图为 12,388 节点、19,389 关系；提取数据包括 170 个容器成员、471 个访问位置、142 个分配位置、95 个条件选择和 2 个回调绑定/调用记录。加入字段生产事实后的图为 19,432 节点、27,756 关系，计数与复现见 [字段生产报告](output-fields.md)。这些是所选源码的语法与候选事实数量。

## 下一步

1. 在已恢复的响应字段生产关系上补序列化、解包、前端消费及状态赋值，完成 D02。
2. 从返回字段反查相关入口，保留请求上下文，完成 D03；数据库候选方向已经可查。
3. 汇总首链各阶段的来源、条件和缺口，完成 D05，并在完整 P3 图上再次验证存储。
4. 登记一条跨模块真实链，供 P7 冻结规则后验收。

## 复现

依赖和 P2 基础图见 [P2 复现](../2026-10-23-p2/reproduce.md)。从研究仓库根目录运行，输出使用新的仓库外目录：

```sh
python scripts/build_data_graph.py --source /path/to/msinsight --base /outside/p2/graph.json --manifest experiments/2026-10-23-p3/selection-manifest.json --output /outside/new-p3
python experiments/2026-10-23-p3/run_selection.py --graph /outside/new-p3/graph.json --cgc-db /outside/p1/cgc.kuzu --output /outside/new-p3-store --buffer-pool-mb 1024
python scripts/query_data_graph.py /outside/new-p3/graph.json --from getUnitFlows --to Dic::Module::FullDb::DbTraceDataBase::QueryUnitFlows
python scripts/query_data_graph.py /outside/new-p3/graph.json --from Dic::Module::FullDb::DbTraceDataBase::QueryUnitFlows --to getUnitFlows --reverse
python scripts/query_data_graph.py /outside/new-p3/graph.json --instance-impact --from Dic::Module::Timeline::DataBaseManager::SetDataType --to Dic::Module::Timeline::DataBaseManager::GetDataType
python scripts/query_data_graph.py /outside/new-p3/graph.json --receiver cpp:a2e15a2a22054e9348abea55
python -m unittest discover -s tests -v
```

该调用 ID 属于上述固定源码版本；其他输入应使用生成图中的 ID。`--receiver` 返回参数与别名来源、工厂、控制依赖、候选实现及剩余条件。当前依赖展开按源函数有界搜索，截断会标记；查询结果描述源码候选关系。

成功运行位于工作区相对路径 `work/repo-map-research/results/p3-selection-05/` 和 `work/repo-map-research/results/p3-selection-store-03/`。存储实验从关闭的原生数据库复制，使用 1 GB 缓冲区。构图检查 Git 版本、输入范围和图端点，不重新核验文件哈希。
