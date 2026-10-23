# P4 完成报告

日期：2026-10-24。U01、U02、U03、U04、U06 通过；U05 因增量关闭而不适用。完整 Python 套件 274 项通过。P5 的真实运行验收继续实施。

## 交付与证据

| 门槛 | 已执行检查 | 证据 |
|---|---|---|
| U01 自动刷新 | 后台监听 Git；新增/删除处理器、注册和消费者后自动发布，无旧节点/连接残留 | [监听测试](../../tests/test_snapshot_watch.py)、[自动刷新报告](automatic-refresh.md) |
| U02 跨文件失效 | 只改 C++ 命令常量，未改 TS 消费者的旧匹配失效；单独变更部署配置重新关联 | [Insight 监听证据](evidence/watch-trial.json)及监听测试 |
| U03 重命名与身份 | 文件/处理器改名，加入其他作用域同名方法；旧资产锚点悬空；复用 ID 改义和多候选不会继承验证 | [记录测试](../../tests/test_snapshot_records.py)、[记录报告](versioned-records.md) |
| U04 失败与追赶 | 真实进程被终止、锁冲突、两次连续提交、发布前后故障；旧入口保留，恢复追到最新目标 | [控制器测试](../../tests/test_snapshot_refresh.py)、Insight 监听证据 |
| U05 增量等价 | 首版使用全量重建，增量关闭 | 不适用 |
| U06 旧证据与摘要 | 四类记录在原快照读回，源码/配置/工具变化阻止直接叠加；旧验证保留原版本；未提交源码不纳入 | [记录试验证据](evidence/record-trial.json)、记录测试 |

真实 Insight 监听试验使用独立 checkout：原版 154 文件图为 25,355 节点、36,605 关系，P3 的 D01–D05 继续通过。实验修改协议常量后，新图为 25,281 节点、36,482 关系，原消费者正确显示失配；两份 Kuzu 数据库完整读回通过。原始源码副本和 GitCode 远端均未修改。

记录试验使用上述两份真实图，追加四类明确标为 synthetic 的记录。每类记录都保留原版本与 payload；新图中原客户端为候选、原注册锚点悬空、未映射事件保持缺口；图发布状态没有变化。该试验验证版本机制，产品运行由 P5 执行。

## 复现与运行边界

自动刷新和原图评分命令见 [全量构建](README.md)与 [监听试验](automatic-refresh.md)。历史记录试验：

```sh
python experiments/2026-10-23-p4/run_record_trial.py \
  --store ../work/repo-map-research/results/p4-watch-trial-01/store \
  --output ../work/repo-map-research/results/p4-record-trial \
  --before c655ac04f09748e29a82bf28a1476e5e \
  --after 12d860beb00541d3bb8fd2662bd689e5
```

复现监听试验会生成新的快照 ID，应将当次 `state.json` 的两个已发布 ID 传入。记录生产者提交 `a93bafff11e6ac985b08412372953cc2ceec2a31`；图构建工具版本保留在各自收据中。原始测试日志和记录查询输出保存在仓库外 `results/p4-record-tests-01/`、`results/p4-record-trial-01/`。

当前 Insight 配置明确选定 154 个路径；新增范围外文件须更新配置，通配范围的自动新增由合成测试验证。控制器监听本地已提交的 Git 引用，远端拉取交给仓库同步流程。跨版本技术候选不自动成为适用契约；P6 的真实资产接入暂不执行。

按 2026-10-24 更新的工作目标，后续完成 P5 后暂停，P6–P7 保留在总设计中。
