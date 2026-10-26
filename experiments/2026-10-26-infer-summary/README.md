# Infer 可组合效果准入检查

日期：2026-10-26。范围：[计划 4.2](../../plans/semantic-impact-execution-plan.md)唯一新增候选的 45 分钟准入窗口。候选为 Infer `v1.3.0`，下载源码提交 `410a6d9394b9c9794bf9469ee0e1aa8d3ae91031`，本地源码位于 D 盘工具区；运行采用上游 Linux 二进制。此处先固定检查，结果另行提交。

源码已检查：[摘要 JSON 开关](https://github.com/facebook/infer/blob/410a6d9394b9c9794bf9469ee0e1aa8d3ae91031/infer/src/base/Config.ml)、[debug 导出实现](https://github.com/facebook/infer/blob/410a6d9394b9c9794bf9469ee0e1aa8d3ae91031/infer/src/integration/InferCommandImplementation.ml)、[Pulse 摘要结构](https://github.com/facebook/infer/blob/410a6d9394b9c9794bf9469ee0e1aa8d3ae91031/infer/src/pulse/PulseSummary.ml)。采用现成 `capture`、`analyze` 和 `debug --procedures --procedures-summary-json --dump-json-summaries`，不读取 OCaml 内部二进制或编写摘要求解器。

冻结 fixture 包含两个编译单元及头文件，分别放进两个独立布局，检查参数返回、字段写读、引用返回、值复制、全局读写、条件选择、跨文件组合和回调。预期：`composed` 返回 input，`isolated` 和 `after_copy` 返回初始 0，`through_global` 返回 input，`conditional` 依 enabled 分支；回调目标未解析时保留未知。摘要需保留原生对象/条件身份，能力逐项判断。

执行先检查固定二进制版本与导出 schema，再核对实际原生 pre/post 是否表达这些关系。JSON 非空、出现 heap 或 summary 字样只算结构可读，不能代替语义准入；原有六项 SVF 值流题继续由对应查询器保持标准。本候选是否能作为其通用替代由实际事实接口和精度决定。

每次 capture/analyze/export 采用既有 psutil 监控：进程树 4 GiB、300 秒，单次工作流最多 15 分钟。只做本候选，不扩展第二个引擎；限额内不能导出所需事实则发布限定能力和 required gaps。原生头文件/第三方编译兼容和 Rust 支持与此小题分开报告。
