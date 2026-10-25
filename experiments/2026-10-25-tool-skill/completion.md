# 项目地图 skill 分发及限定范围验收记录

**整体状态更正：全项目关系覆盖尚未通过。** 本记录验证分发、安装及已有事实查询，保留原始检查结果；359 项 Python 实现测试不表示 Python 产品源码已有语义提取。当前补齐范围和整体判定见[全项目实施计划](../../plans/project-wide-completion-plan.md)及[整体验收矩阵](../../plans/project-wide-acceptance.md)。

日期：2026-10-25。证据类型：执行工具安装、提取与查询检查；研究登记。当前交付为 `project-map-assistant` skill 和 `project-map-tool 0.2.1`，历史资产接入暂缓，AI 正确率实验待冻结协议后开展。

## 使用与组成

[skill 入口](../../skills/project-map-assistant/SKILL.md)说明按任务查模块、接口、数据及影响，并展开同版本源码和运行证据。附带独立环境 bootstrap、命令转发脚本和工具 wheel；安装后可用 `$project-map-assistant` 发起项目理解任务。[使用说明](../../docs/07-tool-quickstart.md)给出安装、建图和分发包构建方法。

工具复用既有实现：全仓发现、TS/C++ 提取、版本刷新、SQLite 导航、组合字段查询和运行记录上下文检查。查询入口已统一为 CLI，可选 MCP 提供四个只读工具。提取和查询不依赖 AI 生成边；skill 引导 AI 检索与解释这些结果。

图状态位于源码仓库之外。更新成功后发布图和导航版本，失败保留上一成功结果；查询报告所选提交、未提交改动及不同提取/导航规则版本。skill 和 wheel 的内容白名单排除了 datasets/cases/experiments/tests 及研究检查脚本。

## 执行结果

完整数据见 [results.json](evidence/results.json)，复现脚本为 [独立仓库检查](../../scripts/smoke_installed_tool.py)和[已有全仓图检查](run_attached_smoke.py)。原始图、依赖、安装包和日志保存在 Git 外。

| 检查 | 结果 |
|---|---|
| 新建 TS/C++ 仓库 | 17 项通过：自动发现、真实提取、重复更新复用、函数改名重建、旧名称退出、反向查询、源码版本及工作区改动隔离 |
| Insight 已有全仓图 | 20 项通过：模块/入口/提供方/诊断导航、unit/flows 协议路径、反向影响、证据展开、字段账本两页、运行上下文正反例、CLI/MCP 一致 |
| Python 完整回归 | 359 项通过，包含实际 stdio MCP 客户端调用 |
| TypeScript 回归 | 110 项通过；之后未修改 TypeScript 提取器 |
| skill 结构 | skill-creator 验证通过；完整包在独立虚拟环境安装，入口以 Python 隔离模式运行 |
| 包内容 | 76 个 wheel 条目，未包含评测材料；当前关闭历史资产接入 |

新仓库检查执行时不导入研究模块，以安装后的 Python 包运行。它复用可用的 C++ parser 缓存和 Windows native 依赖目录，并在新地图目录安装 TypeScript 5.9.3。初次干净安装及后续升级均保留日志。

Insight 查询复用 A5 的 2,311 输入图：4,856 个跟踪路径、29 个模块、282,132 个节点和 412,929 条关系。源码为隔离实验副本提交 `b7a30457ce32e06172fc1dfb33e0dab75f1bfcce`；提取规则为 `b8eac24190eae0a36f2ff2f3f97954670bc25198`，导航索引规则为 `919132203f4dc7b513dee27dfaa87a71a3ae501e`，安装后工具为 `f794393f77d6f958d3f56cdc2a8fcc82a169c9bc`。本轮没有重提取整个 Insight 或重新采集运行证据。

unit/flows 到处理器的路径包含 EMITS_MESSAGE、MATCHES_REGISTERED_PROTOCOL、DECODES_MESSAGE、DISPATCHES_REGISTERED_HANDLER 和 RESOLVES_HANDLER 五类边。`unitAllFlows` 组合账本恢复 303 条关系，本轮读取前两页，各 5 条；提取/展开截断标记仍为 true。页数与已恢复总数不代表未知路径已被补齐。运行列表包含 9 条既有记录，使用原 A5 上下文检查匹配，再改变场景验证拒绝叠加；这验证查询适用性，不新增场景执行结论。

## 失败及改进

首轮完整回归为 356 项、2 个错误：迁移查询实现后测试仍 patch 旧模块，以及 Windows 刷新并发中的 state.json 短暂共享冲突。测试改为 patch 实际实现，旧导入保留兼容；读取端增加有界共享冲突重试并验证恢复，最终完整回归通过。

全仓查询驱动先后暴露三个操作问题：子串搜索先选中了类型节点、无关系筛选的路径查询达到 200 节点预算、变更子进程目录后传入相对上下文路径。驱动分别增加 callable 筛选、协议关系筛选和绝对输入路径，原始失败结果保留；skill 补充了前两项查询方法。实测后还补齐组合账本 offset 分页与固定 snapshot，防止只读到第一页。

## 当前范围与下一步

此版本支持 TS/TSX 与 C++ 的现有机制，其他语言保留清单与未展开状态。运行证据需要项目采集接入；当前更新采用全量重建，组合字段和单条运行映射仍加载原图，耗时高于 SQLite 导航。性能、截断和条件见结果文件及查询输出。

用户提到的新增材料对应 [7 条历史改动回归候选](../../datasets/msinsight-regressions/historical-change-regressions.md)，引入提交为 `a1371ec`。本轮阅读登记及已有核对结论，未扩充训练输入或逐条复现，集合仍未分配；原 [24 条划分](../../datasets/msinsight-regressions/split.md)保持不变。

下一步先按全项目计划完成 W0–W6 与 G01–G08，再冻结 W7/G09 的 issue 定位对照；需要修复的任务另报修复正确性与新增回归。历史资产作为第三阶段新增输入单独评价。
