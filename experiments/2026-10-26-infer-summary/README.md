# Infer 可组合效果准入检查

**2026-10-27 真实输入验证工作单**：复用已成功执行的 Linux CMake 配置流程，按提交导出清单选择原生 compilation database 中的自有源码，执行 [insight_probe.py](insight_probe.py)。只使用已限定准入的 Infer 1.3.0，不增加引擎；capture/analyze/export 分阶段最多 600 秒、进程树 4 GiB，任一阶段失败即保留收据。同步保存 Linux CMake File API 与编译配置供 R2 部署连接复用。原生数据库只读取公开表的计数，不解析 OCaml 二进制；命令成功、摘要数量和语义验收分别记录。该工作单执行期间继续 R2 独立边界项，实际结果另附。

真实输入首次执行：[CI 40435676086](https://github.com/WildPickledPepper/project-map-research/actions/runs/40435676086)，研究提交 `f59b71e`。Linux CMake 配置成功，33 个目标；原生 compilation database 499 条，其中 411 条来自提交选择的自有源码。[首轮收据](insight-first-evidence.json)记录 capture 5.971 秒、采样进程树峰值 878,104,576 字节后退出 1，没有到达分析阶段。Infer 在 `/usr/include/c++/14/bits/atomic_base.h` 的 `std::atomic_flag::test_and_set` 遇到 `AtomicExpr` 翻译断言；本次 CMake 配置编译器为 GCC 13.3.0。原生 capture.db 含中途写入的 2,999 个过程、0 个完成 source_files，不能采用为项目语义捕获。

唯一复验显式使用原生编译器 `-print-libgcc-file-name` 取得安装目录，向分析编译参数加入 Clang `--gcc-install-dir`，使标准库头文件选择与配置编译器一致。其余源码、411 个输入和头文件捕获要求保持；调整与实际目录写入新收据，不使用 `--keep-going` 将失败输入跳过后冒充完成。Linux CMake 原始回复已下载并可独立复用，Infer 失败不取消该构建证据。

日期：2026-10-26。范围：[计划 4.2](../../plans/semantic-impact-execution-plan.md)唯一新增候选的 45 分钟准入窗口。候选为 Infer `v1.3.0`，下载源码提交 `410a6d9394b9c9794bf9469ee0e1aa8d3ae91031`，本地源码位于 D 盘工具区；运行采用上游 Linux 二进制。[限定准入完成](completion.md)：唯一复验后两个布局各 10 项效果检查通过，通用 SVF 替代资格与真实项目成本保持待验。

**首次执行**：研究提交 `47a4d2d` 的 [CI run 40341615457](https://github.com/WildPickledPepper/project-map-research/actions/runs/40341615457) 成功导出两个布局各 14 个过程的原生摘要。检查发现 `after_copy` 含跳过的头文件隐式构造与 `unknown_values=true`，不能用返回值暂时不相等来认定复制隔离通过。原始结果保留，唯一复验改为上游 `capture --headers`，保持 fixture 与期望不变。

源码已检查：[摘要 JSON 开关](https://github.com/facebook/infer/blob/410a6d9394b9c9794bf9469ee0e1aa8d3ae91031/infer/src/base/Config.ml)、[debug 导出实现](https://github.com/facebook/infer/blob/410a6d9394b9c9794bf9469ee0e1aa8d3ae91031/infer/src/integration/InferCommandImplementation.ml)、[Pulse 摘要结构](https://github.com/facebook/infer/blob/410a6d9394b9c9794bf9469ee0e1aa8d3ae91031/infer/src/pulse/PulseSummary.ml)。采用现成 `capture`、`analyze` 和 `debug --procedures --procedures-summary-json --dump-json-summaries`，不读取 OCaml 内部二进制或编写摘要求解器。

冻结 fixture 包含两个编译单元及头文件，分别放进两个独立布局，检查参数返回、字段写读、引用返回、值复制、全局读写、条件选择、跨文件组合和回调。预期：`composed` 返回 input，`isolated` 和 `after_copy` 返回初始 0，`through_global` 返回 input，`conditional` 依 enabled 分支；回调目标未解析时保留未知。摘要需保留原生对象/条件身份，能力逐项判断。

执行先检查固定二进制版本与导出 schema，再核对实际原生 pre/post 是否表达这些关系。JSON 非空、出现 heap 或 summary 字样只算结构可读，不能代替语义准入；原有六项 SVF 值流题继续由对应查询器保持标准。本候选是否能作为其通用替代由实际事实接口和精度决定。

每次 capture/analyze/export 采用既有 psutil 监控：进程树 4 GiB、300 秒，单次工作流最多 15 分钟。只做本候选，不扩展第二个引擎；限额内不能导出所需事实则发布限定能力和 required gaps。原生头文件/第三方编译兼容和 Rust 支持与此小题分开报告。
