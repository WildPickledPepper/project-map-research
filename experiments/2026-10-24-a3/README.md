# A3：可展开项目地图与查询

状态：实施中。输入复用 A2 已发布的全仓事实图，源码固定为 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`。源码与图的生成规则沿用 A2；本阶段独立记录导航规则版本。

目标是让 AI 从概览定位模块，从任意已发现入口或符号查看处理状态，沿已有关系正向、反向展开，检查证据和缺口，并读取相同提交的源码。

## 复用与首轮结果

P7 的 `ProjectQuery` 已提供协议、字段和资源查询。首轮复用该实现加载 A2 图：JSON 载入 7.61 秒，邻接索引 0.922 秒；查询后工作集约 2.59 GiB。概览仍标记为 selected source；分页发生在结果物化之后，查询没有时间或访问量预算。单条 getUnitFlows 协议结果约 70 KB。原始记录保存在 Git 外。

A3 复用 SQLite 事实存储的节点、边与索引结构，将完整节点/边 payload 保存到导航索引。模块与文件归属重新调用 A1 的仓库发现器，读取同一提交的 Git 对象。协议消费方、提供方及诊断分别分页。原始提取 JSON 仍是完整提取产物；索引的顶层元数据是导航投影。

该选择对应本次测出的载入和分页成本。原有 P7 的字段整链账本继续保留；A3 负责通用导航与逐层展开。

## 验收门槛

| ID | 检查 | 通过条件 |
|---|---|---|
| M01 | 同一事实集与自动概览 | 全部节点、平行边及 payload 与 A2 逐项直接比较；29 个结构模块、4,855 文件、2,310 输入均进入索引 |
| M02 | 任意发现入口可查询 | 消费方全量分页与原始结果一致，含歧义/未知/未匹配；每个有节点的入口可查状态和一层关系；无节点项保留原因 |
| M03 | 关系正反查 | 既有三条协议链在索引上有证据路径；资源与字段/状态可检索并展开；关系类型、条件、证据可读 |
| M04 | 分页及预算 | 游标绑定快照、导航版本、过滤条件；节点、边、深度、时间与输出限制可区分；循环和平行边不导致无限展开 |
| M05 | 源码导航 | 读取固定 Git 提交，忽略工作区修改；非法路径、版本不一致和过大读取被拒绝 |
| M06 | 全仓查询成本 | 记录索引一次性构建成本、冷启动查询时间与工作集、响应大小；查询进程不载入原始 JSON |

历史验证候选保持保留。既有链用于回归，新增控制使用自建 fixture。本阶段不执行新运行场景。

## 接口

工具入口：[scripts/project_map.py](../../scripts/project_map.py)。使用标准 Python 和 SQLite；构建索引复用仓库发现，无需启动服务。

```sh
python scripts/project_map.py build --graph <A2-graph.json> --source <Insight-checkout> --output <outside-Git>/map.sqlite
python scripts/project_map.py query --index <map.sqlite> overview
python scripts/project_map.py query --index <map.sqlite> links --module modules/timeline
python scripts/project_map.py query --index <map.sqlite> entries --name getUnitFlows
python scripts/project_map.py query --index <map.sqlite> search --text QueryFlowsBySliceInfoHandler --kind callable
python scripts/project_map.py query --index <map.sqlite> status --start <node-id>
python scripts/project_map.py query --index <map.sqlite> neighbors --start <node-id> --direction out --limit 10
python scripts/project_map.py query --index <map.sqlite> impact --start <resource-node-id> --depth 4
python scripts/project_map.py query --index <map.sqlite> detail --entity edge --id <edge-ordinal> --pointer /conditions
python scripts/project_map.py query --index <map.sqlite> source --source <Insight-checkout> --start <node-id> --context 8
```

`next_cursor` 用于同一查询的下一页；每页可调整 `--limit`。节点 ID、边 ordinal 和协议结果序号均属于当前快照。`trace`/`impact` 以方向区分；`path --target` 返回证据路径。`--kinds` 可限制边类型，默认使用全部已索引关系，查询结果保留其状态。

默认预算：3 秒、200 节点、500 条检查边、128 KiB 输出、深度 4；最大可设 30 秒、5,000 节点、10,000 边、1 MiB 输出、深度 16。SQLite 页缓存目标为 8 MiB，访问量和输出限制控制 Python 对象规模；缓存参数不等于进程 RSS 硬上限。索引构建另计完整图的加载和校验成本。

诊断保留提取器作用域，可能包含同一来源在不同阶段的重复记录，不能当作独立问题数量。局部文件状态与全局限制一起读取；关系缺失的解释是未知。静态候选、部署条件与运行观察沿用 A2 的区分。
