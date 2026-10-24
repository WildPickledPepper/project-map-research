# P7：项目地图、统一查询与 AI 验收

执行中。目标是交付全仓结构与覆盖清单、所选范围的代码/接口/数据查询、运行记录入口、跨模块复用结果和固定 AI 任务评估。外部历史资产 P6 保持待接入，`assets` 返回 `not_connected`。

先读[能力架构与覆盖清单](../../docs/06-capability-coverage.md)。三条链的验收与全仓支持状态分别报告。

## 输入与版本

- 首轮留出链：`Memory/view/memoryUsage`；规则与输入见 [freeze.json](evidence/freeze.json)。首轮失配和存储失败保留在 [first-pass.json](evidence/first-pass.json)。
- 实验源码 `ccd0d88080861b0c7185bcca70a85bd61f823168`，192 个输入，包含 P5 观察埋点。
- 发布源码 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`，191 个输入；使用 [upstream-graph-config.json](upstream-graph-config.json)。仅移除该版本不存在的实验头文件。
- 原 GitCode 仓库及原下载副本不修改。刷新从独立实验 clone 的指定提交导出源文件。
- 输入清单和机制规则分别版本化；按用户要求不核验文件哈希。

## 重建与查询

依赖：Python 3.11、Node 22、TypeScript 5.9.3、项目 requirements-store.txt 中的解析/存储环境。Windows 还需要可用的 parser cache、Kuzu 运行库和 c++filt；与 P1–P5 使用同一环境。Kuzu 构建缓冲配置为 1 GiB，实际进程内存另计。

以下 `$SOURCE` 为独立 clone，`$OUT` 为全新外部输出目录，`$TS` 为 TypeScript 模块路径。示例采用 PowerShell；把快照 ID 替换为刷新输出的实际值。

```powershell
python scripts/refresh_project_map.py --source "$SOURCE" --revision d4e8d1cf9f90208bcbe5371c127088f6fd66c688 --store "$OUT/store" --config experiments/2026-10-24-p7/upstream-graph-config.json --typescript "$TS"
python experiments/2026-10-24-p7/build_inventory.py --source "$SOURCE" --revision d4e8d1cf9f90208bcbe5371c127088f6fd66c688 --module-pattern 'modules/*' --module-pattern 'server/src/modules/*' --module-pattern 'server/msinsight' --module-pattern 'server/src/protocol' --module-pattern 'server/src/server' --output "$OUT/inventory.json"
$GRAPH="$OUT/store/snapshots/<snapshot-id>/graph.json"
python experiments/2026-10-24-p7/coverage_catalog.py --source "$SOURCE" --graph "$GRAPH" --output "$OUT/coverage-catalog.json"
python experiments/2026-10-24-p7/query.py --graph "$GRAPH" --inventory "$OUT/inventory.json" --catalog "$OUT/coverage-catalog.json" --limit 500 overview
python experiments/2026-10-24-p7/query.py --graph "$GRAPH" --catalog "$OUT/coverage-catalog.json" coverage --capability ffi_native_plugin
python experiments/2026-10-24-p7/query.py --graph "$GRAPH" trace memoryCurveGet --field '["lines"]'
python experiments/2026-10-24-p7/query.py --graph "$GRAPH" resource CurveContainer
python experiments/2026-10-24-p7/query.py --graph "$GRAPH" impact --changed-path server/src/modules/memory/parser/CurveContainer.cpp
python experiments/2026-10-24-p7/query.py --graph "$GRAPH" assets --target memoryCurveGet
```

`trace --target` 和 `--reverse` 提供定向路径；`explain --node` 返回节点、相邻关系和函数摘要，`--edge` 接受包含 source/target/kind 的 JSON，`--gap` 搜索诊断。`runs --store` 读取 P5 记录并保留原始运行上下文、快照、断言和映射；旧记录不会自动成为新图的验证。

所有查询返回版本、分页、截断和证据类别。`--format markdown` 与 JSON 使用同一查询结果。未知接口返回未提取状态，空结果不能用作独立性或无风险证明。

## 留出与 AI 测试

[run_acceptance.py](run_acceptance.py) 读取提取结果，对照独立案例验收，不参与生成图。删除提供方、修改命令、切换模块、删除序列化字段的负例作用于事实副本；源码自动更新另由 P4 验收。不同实例/键的隔离由通用 fixture 回归检验。

[ai-tasks.json](ai-tasks.json) 与 [ai-gold.json](ai-gold.json) 在智能体执行前冻结。输入包只含问题、图、来源文件和查询工具，不含评分答案。两个参与者使用独立目录；禁止互读和互相通信，协调者在完成后汇总。共享文件系统不是安全隔离边界。

工具记录每题耗时、查询/读取次数和输出字节。智能体接口未提供实际 token、上下文占用及费用时标为 unavailable。该试验测量图辅助任务的可用性，不与源码搜索基线比较，也不外推整体正确率。
