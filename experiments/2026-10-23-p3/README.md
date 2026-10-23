# P3：数据、状态与反向查询（实施中）

已交付第一组数据事实和查询：在 P2 图上，从 `getUnitFlows` 正反向查询 DB/Text 两个候选实现；解释请求字段如何选择查找函数、连接池有哪些创建来源；查询数据类型状态的写入者与读取者。**P3 的 D01–D05 尚未完整验收。**

输入为 Insight 固定提交 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688` 的 [134 文件](input-manifest.json)，沿用 P2 输入并加入连接池模板。实际执行证据见 [increment.json](evidence/increment.json)。预期名称仅在评分脚本中，提取器使用 C++ 语法、类型候选和标准容器规则。

## 已执行的检查

- 前端入口到 DB/Text 实现均为 9 段有向关系，正反查询通过；协议关系和虚方法候选保留各自语义。
- 请求中的 `dbPath.empty()` 决定按 rankId 或 fileId 查找，条件方向及实参来源可展开。
- 连接池表的写入关联到三个构造位置：普通池的 DB/Text 分支和派生池的 DB 构造。创建时的数据类型读取进一步关联到状态表及其显式写入。
- 连接池构造参数绑定到保存的回调成员，调用该回调的位置可查；实际执行与对象选择保持未知。
- `SetDataType → 写入 → 可能被读取 → GetDataType` 可双向查询。边保留同一运行实例、匹配键及中途未覆盖的条件。
- 15 项新增测试覆盖改名、同名成员/匿名命名空间隔离、遮蔽、动态覆盖、不同常量键、删除、回调绑定和容器下标可能隐式插入的行为。

本次图为 11,179 节点、17,728 关系；新增提取数据包括 161 个容器成员、460 个访问位置、132 个分配位置、83 个条件选择和 2 个回调绑定/调用记录。这些是所选源码的语法与候选事实数量。

## 下一步

1. 补齐容器迭代器值到连接池方法的类型传播、模板实参，以及提前返回和 switch 穿透条件，完成 D01 的选择说明。
2. 明确共享状态的实例身份；类成员同名并不足以证明是同一个运行对象。继续完成 D04。
3. 提取响应字段的生产、解包、前端消费及状态赋值，完成 D02/D03；在完整 P3 图上验证存储和统一缺口查询。
4. 登记一条跨模块真实链，供 P7 冻结规则后验收。

## 复现

依赖和 P2 基础图见 [P2 复现](../2026-10-23-p2/reproduce.md)。从研究仓库根目录运行，输出使用新的仓库外目录：

```sh
python scripts/build_data_graph.py --source /path/to/msinsight --base /outside/p2/graph.json --output /outside/new-p3
python experiments/2026-10-23-p3/score_increment.py --graph /outside/new-p3/graph.json --output /outside/new-p3/increment.json
python scripts/query_data_graph.py /outside/new-p3/graph.json --from getUnitFlows --to Dic::Module::FullDb::DbTraceDataBase::QueryUnitFlows
python scripts/query_data_graph.py /outside/new-p3/graph.json --from Dic::Module::FullDb::DbTraceDataBase::QueryUnitFlows --to getUnitFlows --reverse
python scripts/query_data_graph.py /outside/new-p3/graph.json --impact --from Dic::Module::Timeline::DataBaseManager::SetDataType --to Dic::Module::Timeline::DataBaseManager::GetDataType
python scripts/query_data_graph.py /outside/new-p3/graph.json --receiver cpp:a2e15a2a22054e9348abea55
python -m unittest tests.test_cpp_data tests.test_data_graph -v
```

该调用 ID 属于上述固定源码版本；其他输入应使用生成图中的 ID。`--receiver` 返回参数与别名来源、工厂、控制依赖、候选实现及剩余条件。当前依赖展开按源函数有界搜索，截断会标记；查询结果描述源码候选关系。

成功运行位于工作区相对路径 `work/repo-map-research/results/p3-data-04/`。构图检查 Git 版本、输入范围和图端点，不重新核验文件哈希。
