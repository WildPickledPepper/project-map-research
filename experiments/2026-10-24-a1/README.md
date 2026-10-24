# A1：全仓自动发现与输入生成

状态：**A1 已完成**。按[下一阶段计划](../../plans/full-repository-plan.md)交付自动输入发现、构建/模块清单、逐文件基础事实和处理状态。实测结果见[完成报告](completion.md)：2,256 个源码和 54 个清单自动纳入，完整测试 305 Python / 80 TS 通过。历史样本按[开发/验证划分](../../datasets/msinsight-regressions/split.md)约束；本轮使用全仓常规发现和自编模块实验，不开展验证候选定向研究。

## 入口与产物

`scripts/discover_repository.py` 从指定 Git 提交读取全树，默认纳入第一方产品、测试和构建工具中的 TS/TSX 与 C++/头文件，读取包、tsconfig、CMake、TOML、requirements 及已有编译命令清单。第三方、生成内容、其他语言和非分析文件保留分类及原因。

输出目录位于仓库外，包含：

- `discovery.json`：全部路径、结构模块归属、构建上下文、状态和事实文件引用。
- `input-manifest.json`：自动产生的固定版本导出清单；`source/` 为对应 Git blob 导出。
- `build-config.json`：包含 `scope.discovery` 的策略配置，可交给已有刷新器，在每个新提交重新发现输入。
- `facts/*.json`：逐文件符号、类型/接口声明、导入、未解析调用、注册/入口/资源候选或构建元数据。
- `summary.json`、`workers.log`：计数、诊断与 worker 错误记录。

模块归属取最近的受版本控制包/CMake 等清单，缺少清单时按顶层目录分组。TS 文件集由 TypeScript 配置解析记录，分析范围保守包含全部符合策略的 tracked 文件；CMake 表达式与构建变体记录为未求值，编译命令不执行。

## 执行与恢复

环境沿用 P7：Python 3.11、Node 22、TypeScript 5.9.3，以及 requirements-store.txt 中的现有依赖。Windows 配置已有 parser cache 和 Node 路径。`$SOURCE` 指向独立 clone，`$OUT` 为新建外部目录，`$TS` 为固定 TypeScript 模块路径。

```powershell
python scripts/discover_repository.py --source "$SOURCE" --revision d4e8d1cf9f90208bcbe5371c127088f6fd66c688 --output "$OUT" --typescript "$TS" --seconds 1200 --file-timeout 30
python scripts/discover_repository.py --source "$SOURCE" --revision d4e8d1cf9f90208bcbe5371c127088f6fd66c688 --output "$OUT" --typescript "$TS" --resume
```

可选 `--policy` 提供 roles、exclude、max_file_bytes，`--deployment` 读取已有 graph config 的部署绑定。输入范围无需业务文件表。生成的策略配置能被 `scripts/refresh_project_map.py --config` 使用；完整关系图的全仓成本和连接覆盖在 A2 继续验收。

每个文件有明确的纳入/排除与处理状态。`--max-files`、`--seconds` 限制本次执行，未完成任务标为 pending_budget；`--file-timeout` 超时会终止对应 worker 并允许后续文件继续。`--resume` 要求相同源码提交、策略和提取器版本，复用已有完整结果；`--retry-errors` 重试 worker/读取等错误。语法错误保留可恢复事实及诊断；大小预算与不支持项保留原因。

预算包括每次执行时间、单文件解析时间、单文件输入大小和 Node worker 256 MiB heap；C++ worker 没有跨平台硬性内存上限，退出时记录 worker_exit。未完成或失败不能作为无依赖证据。

时间预算在文件边界检查；Git 发现、源码导出和 checkpoint 写入不抢占中断。若导出中止，部分输入保留，需要新的输出目录重试；完成导出后的提取任务支持 `--resume`。

## 验收方法

1. 从固定 Insight 原始提交执行全仓发现与提取，报告语言、角色、纳入/排除及诊断分母。
2. 用 [run_mutation_trial.py](run_mutation_trial.py) 在独立 clone 添加自编 TS/C++ 模块，验证接口/注册候选被提取、预算中断可恢复，改名和删除随自动策略更新。
3. 用新增测试验证失败、编码、符号身份与刷新接入；运行既有完整回归。
4. 在既有 191 文件基准重新构图并核对三条链。该固定切片只作为历史回归，不作为全仓入口的输入策略。

基础事实使用既有 Tree-sitter 补充与 TypeScript 编译器 AST。注册拼写提示和成员声明作为候选单列；调用目标、跨语言匹配、全量字段/资源关系和运行行为按 A2–A5 分别验收。全仓源码没有按历史验证候选排除，样本评分和归因不进入提取输入。

公开证据检查：`python experiments/2026-10-24-a1/check_completion.py`。紧凑产物由 `package_evidence.py --results <external-results-root>` 汇总，不读取历史样本表或评分答案。
