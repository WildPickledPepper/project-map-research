# MindStudio Insight 历史问题测试候选

[下载 24 条测试样本表（Excel）](msinsight-24-test-candidates.xlsx)

2026-10-26：[全体样例的修改影响信息分析](../../research/regression-context-gaps-2026-10-26.md)逐项检查原 24 条及 7 条补充候选暴露的身份、条件、状态、时序和资源依赖。本轮为已见归因讨论，未新增运行评分或调整工具规则；现有集合划分保持不变。

新增：[历史遗留分类中的改动回归候选说明](historical-change-regressions.md)及[候选表（Excel）](historical-change-regression-candidates.xlsx)。筛查 33 条历史遗留记录，源码复核其中 7 条关联改动；单独登记，原 24 条及其集合划分保持不变。

后续用途按[样本划分 v1](split.md)执行：8 条开发、4 条关联回归、12 条验证候选。本轮用户推进 A4，已按[冻结协议](../../experiments/2026-10-24-a4/protocol.md)启动验证候选的源码与静态覆盖评价；规则保持冻结，运行复现另记。

共 24 条原始记录：首轮筛选 11 条，加上仓库历史复核后补出的 13 条，按原表行号去重。同一记录内的多个子问题保留在同一行。

表格包含关联 Issue、引入 PR／提交、后续修复 PR、问题原因、触发条件和来源证据。研究对象为 [Ascend/msinsight](https://gitcode.com/Ascend/msinsight)。

证据类型：原始问题记录及源码历史核对。该表是待执行的测试候选集，运行复现尚未执行；具体分支及归因限制见表内说明。
