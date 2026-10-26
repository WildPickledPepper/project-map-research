# 原生分析成本与同进程身份诊断

日期：2026-10-26。范围：[实施计划 4.1](../../plans/semantic-impact-execution-plan.md)的一批交付，承接研究提交 `61dfc40`。诊断脚本提交 `49d28a2` 已在 [CI run 40339369105](https://github.com/WildPickledPepper/project-map-research/actions/runs/40339369105) 执行；结果见[完成报告](completion.md)。单次求解/同进程身份路径通过独立检查，真实 C++ 在 PAG 阶段触及预算，R0/R1 总体仍为 partial。

复用 PySVF `1.0.0.50`、既有 C++ 六项独立题，以及此前 411 个编译单元生成并经 LLVM O1 处理的 bitcode。资源采样复用 psutil `7.2.2`，覆盖被测进程树，每 0.1 秒采样；阶段事件另存内核自身峰值。输出与第三方环境在实验目录之外保存。

## 固定检查

1. 读取实际包接口，分别执行 `get_svfir` 和 `run_pta`，记录 PAG/PTA 阶段事件、资源和 PTA 对象的可调用方法。
2. 在同一次 `buildSVFModule` 调用中传递上游 `-write-ander`，导出当前 SVFG 及原生写出的 points-to。逐项验证所有非空关系的两端存在于当前 PAG，再允许标为同进程身份。旧 CLI 文件继续标记为跨进程未验证。
3. 同进程结果经统一索引执行原有六项值流题，期望不变。另用 [identity.cpp](identity.cpp)冻结三个指向关系：两个别名共享 `first_object`，另一个只指向 `second_object`；统一按原生全局对象身份检查。
4. 小题通过后，从既有 CI artifact 读取真实 O1 bitcode，先运行 PAG/PTA；成功才运行组合的完整构图。当前接口若不能独立构建 MemorySSA/SVFG，结果保留组合粒度，差值不作为这两个阶段的精确峰值。

原生每次上限 600 秒、进程树 13 GiB，单任务 30 分钟。真实 PTA 超限后跳过完整构图。默认复用原资源实验 run `40297126824` 的 `svf-replay-output`，可通过 workflow 输入指定同格式捕获。输入缺失时失败，不重新编译真实后端。

## 执行与验收

研究工作流 `native-reuse.yml` 手动选择 `provider=svf-diagnose`。输出 `svf-diagnostic-output` 包含 API、阶段事件、资源、六项值流检查及身份结果。CI 产物下载到 D 盘；Git 只保留脚本、报告和脱敏收据。

本地检查执行 `tests.test_svf_export` 与 `tests.test_native_value_flow`，验证格式损坏、缺失原生端点和跨进程未验证身份等失败路径。真实调用、身份正确性及实际成本以 CI 的独立题与资源结果判断，R0/R1 整体验收继续按原门槛。
