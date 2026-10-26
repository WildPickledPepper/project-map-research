# R0/R1 本轮交付与验收结果

**同日后续结果**：[三项原生补充与统一复核](reuse-followup.md)记录了头文件恢复、RAPx/SVF 数据流接入、4 GB 图的流式发布及最终 762 项 Python 回归。下文保留较早一轮的快照与首次缺口；最新严格状态仍为 partial，C++ 全程序原生分析资源阻塞及未覆盖配置继续列账。

2026-10-26。本轮已固定组件复用路线，将准入提供方接入正式建图流程，发布 Insight 同版本全仓快照，并完成组件事实账与查询复核。**实现与实测已交付；严格 R0/R1 验收为 partial，G02 尚未通过，当前未进入 R2。**

## 交付及实测

| 交付 | 最终结果 | 证据 |
|---|---|---|
| R0 组件选择与真实调用入口 | 继承此前工具调查；固定准入、限定使用和拒绝结果 | [准入决定](../../research/r0-provider-admission-2026-10-26.md) |
| R1 同版本全仓快照 | 正式 Workspace 发布成功；4,855 个跟踪文件、2,516 个选定输入；建图及索引发布 1,925.312 秒 | [快照收据](evidence/repository-snapshot-final.json) |
| 组件归属及事实账 | 124 个运行/库组件、5 个支持组件全部列账；6 项归属/版本/计数检查通过 | [129 组件表](module-facts-final.md)、[机器账本](evidence/module-fact-audit-final.json) |
| 既有无基础事实队列 | 41 → 0；包括 TypeScript 声明、include-only 文件、容器支持和纯命令脚本 | [快照差异](evidence/repository-snapshot-final.json) |
| 独立源码与公开查询检查 | 129 个组件共 450 项代表性声明/导入检查通过，失败 0 | [逐项结果](evidence/source-contract-review-final.json) |
| 最终集成检查 | 11 项通过；原生 ID/关系保留、精度标记、源码版本、Shell 查询和 C++ 正反向导航均通过 | [集成结果](evidence/final-integration-checks.json) |
| Python 完整回归 | 执行 749 项，结果通过，含 2 项平台条件跳过；315.510 秒 | [回归收据](evidence/repository-snapshot-final.json) |
| TS/JS 回归 | 124 项通过；沿用本轮相同 TS 实现的已执行结果 | [原始结果](evidence/typescript-declarations.json) |

源代码提交为 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`，核心规则提交为 `cd6992b9346e5ac4d75c1d81c23c9c6747219b7a`。最终快照为 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688:full:4c2b04f0c3d14586b8805d8b238678c1`。统一图有 774,284 个节点、1,474,265 条边；图内 29 个结构模块与独立验收的 129 个组件使用不同层级，验收分母沿用后者。

正式建图复用同源码提交、同编译上下文的 CBM、clangd 和 CMake 原生捕获，重新执行 TS/JS、Python/Jedi、Rust/RA 及既有适配。提供方事实通过默认 Workspace 流程进入统一图和 SQLite 导航索引。原始 Insight checkout 与 GitCode 上游均未修改，历史资产关闭，未读取封存验证题。

## 本轮接入产生的可查询结果

CBM 0.12.1 的 CLI/SQLite 提供函数、变量、环境、容器与进程候选；clangd 23.1.0 经固定 multilspy 客户端提供原生符号、引用、目标声明及编译配置。原生节点分别保留身份：33,031 个 CBM 节点、262,218 个 clangd 节点和 392,970 条既有 clangd 关系。推断及带诊断上下文继续使用候选精度。

最终图新增 200,526 条“函数词法范围包含引用”关系。8 个不同真实 C++ 文件通过“函数 → 引用 → 目标声明”的两步查询及反向查询，见集成收据中的实际文件、调用方和目标。该关系记录语法归属与原生定义跳转；运行分派仍由相应静态模型和运行证据判定。

Bash 补充直接使用现有 tree-sitter-language-pack 1.20.0 的原生命令语法，8 个脚本产出 340 个命令位置。原先只有文件/模块记录的安装脚本，现在能统一查询 npm、apt-get、update-alternatives 和 python3 的六处位置及参数。动态展开、包装启动的未解析项继续列账。

源码检查先从固定版本源码和标准 AST/语法树生成参考，再打开事实索引核查原名、位置、源码定位和邻接导航。450 项结果的含义是逐组件代表性保真；全量调用、数据和跨边界召回由对应验收项继续审查。

## 首轮失败和负例

首轮统一快照的规则为 `faad3e1`，仍有 1 个无基础事实脚本，缺少 Bash 命令位置和原生函数到引用的词法导航。本轮检查器对该旧快照返回失败，准确保留四项失败：无基础事实队列、两类新增事实、安装脚本查询和原生正反向导航。最终快照 11 项全部通过；[旧快照负例](evidence/final-verifier-negative.json)与[首轮快照](evidence/repository-snapshot.json)一并保留。

检查器开发时一次无界全图查询被停止，随后改用索引计数、30 秒 SQL 截止时间和有预算的公开邻接/路径查询；停止记录保存在原始实验目录。最终检查耗时约 3 秒，未因此改动生产事实或重建源码图。

Python 首轮完整回归中，旧测试把多提供方的同名 `main` 当作一个节点，产生一项失败。测试已改为沿原有构建/解码关系选择节点，保持各原生身份；最终完整回归通过。此前 CBM 启动、索引忽略范围、Clang builtin 头文件优先级和 Windows staging 发布的失败及修正保留在[实施记录](README.md)。

## 剩余项与严格验收

| 责任 | 已确认情况 | 剩余工作及判定 |
|---|---|---|
| R0 数据流替代准入 | Joern C++ 语义题 5/6，直接 const-reference 别名漏报；Rust 前端方法数为 0 | 固定失败出口；RA 保留 Rust 语言事实。C++ 别名与 Rust 通用数据流仍是 R3/G05 必需缺口，R0 为 partial |
| R1/G02 头文件语义 | 37 个非测试头文件有独立打开诊断；已用原编译参数检查 14 个真实编译单元，全部通过且实际包含覆盖 37 个头文件 | 复用真实编译单元上下文恢复头文件原生引用，并核查遗漏/歧义。[编译通过](evidence/header-contexts.json)与图的语义完整性分别记录，R1/G02 尚未通过 |
| R2 边界连接审查 | 事实账保留 8 个无跨组件出边、5 个无跨组件入边的组件审查标记 | 按职责与边界信号判定每项应有连接；结合 19 项独立参考按 A/B/C 横向批次验收。零边标记本身不能判定缺边或独立 |
| R3–R5 | SQLGlot 和 Python OTel 限定接口已准入，既有查询/更新/运行能力保留 | SQL/数据状态、85 项运行义务、更新与独立安装分别验收；skill 在 R5 最后整理 |

本轮结束全仓重建与组件探针，交付可用事实索引和上述有责任归属的剩余清单。后续按[复用优先计划](../../plans/reuse-first-execution-plan.md)的预算与失败出口分批处理，继续保留 G01–G09 的原始分母。

## 复核入口与数据位置

工具、环境、缓存、临时文件及原始实验数据均放 D 盘；Git 保存实现、紧凑收据和文档。原始结果目录依次为 `results/r1-repository-02`、`results/r1-module-fact-audit-02.json`、`results/r1-source-contract-review-02`、`results/r1-final-integration-checks-01.json` 与 `results/r1-header-context-review-01`，位于当前 D 盘工作根目录下。完整图、SQLite、AST 和日志不入 Git。

复核命令中的路径由操作者指定，输出使用新目录/文件：

```text
python experiments/2026-10-26-r0-r1/review_repository.py --trial FINAL_TRIAL --frozen-scope FROZEN_W0_SCOPE --output NEW_REVIEW
python experiments/2026-10-26-r0-r1/verify_final_repository.py --trial FINAL_TRIAL --audit FINAL_AUDIT --contracts NEW_REVIEW/review.json --output NEW_CHECKS.json
python -m projectmap --workspace FINAL_TRIAL/workspace query search --text build/mindstudio_insight_gui_set_environment.sh --kind call_site --limit 10
```

本轮只记录 Git 提交、工具版本与行为结果，按用户要求未另行核验文件哈希。
