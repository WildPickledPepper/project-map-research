# Rust Linux Debug 补图执行单

日期：2026-10-26。范围：[计划 4.2](../../plans/semantic-impact-execution-plan.md)剩余原生配置；复用已准入的 Cargo/rustc LLVM 捕获、PySVF `1.0.0.50` 和第一批同进程导出。

**2026-10-27 收口**：[实际配置已捕获并通过独立查询](../2026-10-26-native-budget/rust-debug-completion.md)。原生分析/导出 131.303 秒、采样峰值约 2.67 GiB；六项 Rust 准入和六项实际捕获查询检查通过。新捕获尚未合入默认全项目快照，相关状态分开报告。

目标为固定 Insight 源码的 `platform/linux/Cargo.toml`、`platform/linux-desktop-debug` 上下文。保留 Cargo 实际 cfg 和 debug assertions，分析优化显式设为 O1；它是记录在收据里的分析覆盖项，不能拿 Release 的 bitcode 充当 Debug。只补该配置及独立准入题，不重编全部 C++ 或重跑其他 Rust 平台。

工作流 `provider=rust-linux-debug` 沿用上游工具链/依赖与 Cargo 缓存。真实配置捕获步骤最多 10 分钟；原生分析逐目标最多 600 秒、进程树 13 GiB，使用已实测的 psutil 监控。成功后检查源码/配置/模块及活 PAG 端点；失败保留原始日志和具体配置，不发布成功快照。

必交付：实际 cfg/编译收据、同进程原生输出、资源、原 Rust 六项值流结果和原生配置缺口变化。抓到 LLVM 或导出非空分别记账，全项目语义验收继续按 G02。
