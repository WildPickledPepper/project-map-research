# A4：冻结规则的模块评价与版本更新验收

状态：**首轮评估完成；工具连通性未通过，待修正复验**。见[结果报告](report.md)、[冻结协议](protocol.md)、[修正计划](repair-plan.md)。

本轮保留原始参考、首次结果和评分参考修正。未修改提取或连接规则；源码事实与自动更新的正确性分别评价。

## 工具与产物

| 入口 | 作用 |
|---|---|
| [score_chains.py](score_chains.py) | 对独立源码参考评分，未知、未匹配、错误连接分别统计 |
| [prepare_update.py](prepare_update.py) | 建立独立产品副本，提交自建模块新增、改名、删除；断言仅五个最终路径改变 |
| [run_updates.py](run_updates.py) | 调用真实刷新控制器和提取器，验证 13 项更新控制 |
| [audit_updated_map.py](audit_updated_map.py) | 在更新后的完整导航索引上核对身份和直接传输发现缺口 |
| [audit_history.py](audit_history.py) | 读取原表 12 条保留记录、Git 修复前后版本及当前图覆盖 |
| [history_pair.py](history_pair.py) | 提取第 24 条修复前后全部修改 C++ 文件的事实 |
| [compare_graphs.py](compare_graphs.py) | 完整图解析 JSON 直接比较，仅排除两处快照身份 |
| [run_regression.py](run_regression.py) | 复用 P7 的 19 项已知链回归，模块清单来自 A1 自动发现 |
| [probe_publication.py](probe_publication.py) | 单独测量控制器对完整图的发布前校验 |
| [package_evidence.py](package_evidence.py) | 保存紧凑证据，保留负结果及首次执行/评分问题 |

## 复现顺序

在已具备项目 Python/Node 依赖和解析器缓存的环境执行。输出保持在研究 Git 和产品源码之外。

```sh
python experiments/2026-10-24-a4/score_chains.py --graph <A2-graph.json> --reference experiments/2026-10-24-a4/reference.json --output <first-score>
python experiments/2026-10-24-a4/prepare_update.py --source <Insight-readonly-checkout> --output <A4-copy>
python experiments/2026-10-24-a4/run_updates.py --output <fixture-updates> --typescript <typescript.js>
```

读取 `<A4-copy>/preparation.json` 的 `final_revision`，用 `<A4-copy>/config.json` 和 source 调用原有全量构建器，两次使用不同的输出目录：

```sh
python experiments/2026-10-24-a2/probe_full_build.py --source <A4-copy>/source --revision <final_revision> --config <A4-copy>/config.json --typescript <typescript.js> --output <full-first> --seconds 1800
python experiments/2026-10-24-a2/probe_full_build.py --source <A4-copy>/source --revision <final_revision> --config <A4-copy>/config.json --typescript <typescript.js> --output <full-rebuild> --seconds 1800
python experiments/2026-10-24-a4/compare_graphs.py --first <full-first>/build/graph.json --second <full-rebuild>/build/graph.json --output <comparison.json>
python scripts/project_map.py build --graph <full-first>/build/graph.json --source <A4-copy>/source --output <map.sqlite>
python experiments/2026-10-24-a4/score_chains.py --graph <full-first>/build/graph.json --reference experiments/2026-10-24-a4/reference-reviewed.json --output <reviewed-score>
```

历史对象不足时，在 A4 实验副本设置 GitCode fetch 地址和 promisor 读取，保留 prepare_update 已配置的禁用 push 地址，再运行审计。原下载仓库不作为缺失历史对象的写入目标。`audit_history` 的当前图基准使用源码 `d4e8d1c` 对应的 A3 索引：

```sh
python experiments/2026-10-24-a4/audit_history.py --source <A4-copy>/source --index <A3-map.sqlite> --output <history>
python experiments/2026-10-24-a4/history_pair.py --source <A4-copy>/source --history <history>/history.json --output <history-pair>
python experiments/2026-10-24-a4/run_regression.py --source <A4-copy>/source --build <full-first>/build --runtime-store <P5-store> --output <known-regression>
```

历史候选的当前实体覆盖、双文件版本差异、完整历史快照建图和运行复现均有独立字段。公开证据仅包含实际执行项；完整 raw 图、补丁与日志留在 Git 外。
