# 三种新增语言的同一全仓快照复验

2026-10-25，默认全仓构建及后置评分通过。Insight 源码固定为 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`，提取规则为 `5f8079dba2a733e40bef6cae4eb35075b3e39cf1`；快照 ID 为 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688:full:d8307de144c240ae8c7b3f820053f399`。W1/G02 继续逐模块及实际边界验收。

## 执行结果

构建使用生产 Workspace.update，scope 为默认 `*`，角色为 product/build_tool/test，没有语言过滤或业务模块白名单。全部 4,855 个跟踪路径保留发现状态；2,496 个源码与清单输入生成 371,674 个节点和 537,678 条关系。JSON 事实图完成闭包校验后发布，随后生成 SQLite 导航索引。29 个导航结构分组与 W0 的 129 个必需逻辑组件分别保留。

| 评分 | 同一快照上的结果 | 公开证据 |
|---|---|---|
| Rust 平台链 | 13 文件、24 分析上下文；41 项通过 | [Rust 全仓记录](evidence/multilang-repository-rust.json) |
| Python 代理链与范围 | 119 文件；137 项通过 | [Python 全仓记录](evidence/multilang-repository-python.json) |
| TS→JS 混合链 | 14 项通过，保留动态选择候选与双向路径 | [JS 链记录](evidence/multilang-repository-javascript.json) |
| JS 文件与解析状态 | 53 文件；1,218 项通过 | [JS 范围记录](evidence/multilang-repository-javascript-scope.json) |

评分器只读已发布索引与独立源码参考。Rust 的启动/WebView 路径另核对条件交集；Python 的代理注册/转发/释放、TS→JS 的构造/方法/导入及正反向查询在同一生产快照保留。JS 链评分改为按需读取 SQLite，避免重复加载约 1.28 GB 的整图 JSON；评分要求和独立参考不变。

本次复验确定了三种新增语言与既有全仓流水线的兼容性。各模块机制的正确连接、进程到 C++ 对端、数据/状态的完整展开及运行证据仍按 G02–G08 检查。解析率、节点数与检查项数均不作为定位正确率或全项目完成率。历史资产关闭。

## 首次失败与恢复

首次构建在最终 JSON 写入时磁盘空间耗尽，没有发布成功快照；失败现场和日志保留，状态通过刷新器 API 记为 failed。三份旧成功快照的重复中间检查点归档到独立数据盘，释放约 3.6 GB；旧的最终图、源码和日志保留。本次使用数据盘新目录重建，正式返回 ready。未重新核验文件哈希。

本次原始源码、检查点、完整图、导航数据库和命令日志均在仓库外。公开记录绑定同一源码、规则与快照，旧语言实验记录保持原版本及原范围。

## 复现

先按[环境说明](../../docs/07-tool-quickstart.md)准备 TypeScript、parser、Jedi 和固定 Rust 工具，使用仓库外新输出目录：

```text
python experiments/2026-10-25-w1/run_rust_trial.py --source SOURCE --revision d4e8d1cf9f90208bcbe5371c127088f6fd66c688 --typescript TYPESCRIPT --scope repository --output TRIAL
python experiments/2026-10-25-w1/score_rust_trial.py --trial TRIAL --output RUST_SCORE.json
python experiments/2026-10-25-w1/score_python_trial.py --trial TRIAL --output PYTHON_SCORE.json
python experiments/2026-10-25-w1/score_javascript_trial.py --trial TRIAL --output JAVASCRIPT_SCORE.json
python experiments/2026-10-25-w1/assess_javascript_scope.py --trial TRIAL --output JAVASCRIPT_SCOPE.json
python experiments/2026-10-25-w1/check_evidence.py
```
