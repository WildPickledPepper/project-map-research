# 响应序列化：从 C++ 字段到 JSON 路径

已从源码恢复 `unit/flows` 的响应序列化回调、注册位置及 **34 个字段或集合路径**：业务 `body` 内 26 个，公共响应信息内 8 个。字段来自形参、成员访问、循环元素和辅助函数的逐层替换，字符串转换保留重载候选。当前图可从注册项查到序列化回调，再查字段来源及 JSON 路径。**D02 继续补生产对象与序列化的上下文连接、传输、前端解包和消费。**

证据类型：实际执行源码提取、自动测试及存储读回查询。Insight 提交为 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`，规则冻结于 `967f0aa`，输入沿用 [141 文件](output-manifest.json)。完整结果见 [serialization.json](evidence/serialization.json)，验收逻辑见 [run_serialization.py](run_serialization.py)。

## 提取机制

复用 Tree-sitter、P1 的类型与函数候选以及 P2 的注册提取。新增规则识别 RapidJSON 的类型别名、`AddMember`、`PushBack` 和字符串构造；项目自己的包装函数通过源码展开。变量、回调、字段键和模板特化名称均来自输入。具体业务名称只出现在验收脚本中。

每次调用按实参替换形参；范围循环追加元素路径；JSON 构造对象记录成员和数组追加操作。类型条件排除不匹配的字符串、向量和可选值重载，等价操作合并来源。条件、未解析步骤与展开预算一并保留。

例如，在已注册的回调内，可以查询：

```text
response.body.unitAllFlows
  → JSON body.unitAllFlows
response.body.unitAllFlows[element].flows[element].from.dbPath
  → JSON body.unitAllFlows[*].flows[*].from.dbPath
```

源对象路径和 JSON 字段都按回调作用域建节点。同名字段在不同回调中保持独立；数组的集合来源与元素字段依赖分别记录。

## 实测与边界

| 检查 | 结果 |
|---|---|
| 目标回调 | 模板特化与响应类型转换自动展开，注册键为 `unit/flows` |
| 字段路径 | 34 个，包括 2 个集合路径；保留 55 条转换候选 |
| 业务字段 | 26 个路径，与源成员/循环元素路径逐项对应 |
| 公共响应字段 | 8 个路径，包含可选错误信息及回调编号 |
| 图 | 22,687 个节点、33,269 条关系 |
| 回归 | 142 项 Python 测试通过；改名、嵌套数组、重载、条件、作用域隔离和预算耗尽有覆盖 |
| 存储 | 完整载荷读回一致，读回图重新执行映射断言；790 条原生函数记录保持一致 |
| 前一增量 | 处理器字段生产查询仍恢复 7 处写入 |

55 条候选中包含直接传值与字符串构造等不同源码展开方式，表示静态依赖。编译器的最终重载选择、分支执行、数组长度和实际发送结果仍需编译或运行证据。公共 `type` 字段的常量定义位于本轮输入范围之外，对应 7 条未解析诊断；业务 `body` 的映射通过检查。其他不支持的表达式、局部类型别名和未知 JSON 修改保留缺口。

生产查询和序列化查询目前分别可用。下一步按协议实例、注册及响应对象来源连接两段，再补传输和前端消费；仅凭类型或字段名称相同不能建立这条连接。D02、D03、D05 保持未完成。

## 复现

环境和 P2 基础图见 [P2 复现](../2026-10-23-p2/reproduce.md)。使用关闭的原生 CGC 数据库作为副本来源，输出写到新的仓库外目录：

```sh
python scripts/build_data_graph.py --source /path/to/msinsight --base /outside/p2/graph.json --manifest experiments/2026-10-23-p3/output-manifest.json --output /outside/new-serialization
python scripts/query_data_graph.py /outside/new-serialization/graph.json --serialization Dic::Protocol::TimelineProtocol::ToUnitFlowsResponseJson
python experiments/2026-10-23-p3/run_serialization.py --graph /outside/new-serialization/graph.json --cgc-db /outside/p1/cgc.kuzu --output /outside/new-serialization-store
python scripts/check_p3_serialization.py
```

成功运行位于工作区相对目录 `work/repo-map-research/results/p3-serialization-01/` 和 `work/repo-map-research/results/p3-serialization-store-01/`，Kuzu 缓冲区为 1 GB。记录 Git 版本与行为结果，不重新核验文件哈希。
