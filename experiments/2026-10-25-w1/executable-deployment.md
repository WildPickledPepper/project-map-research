# 可执行文件身份、current_exe 与后端产物

日期：2026-10-26。证据类型：独立机制/生产建图检查。W2 执行中；当前工作连接源码中的启动路径、构建目标及发行布局，G03/G04 保持未通过。

[生产适配](../../adapters/executable_deployment_graph.py)把 Cargo 主要可执行文件及其复制后位置转换为 `executable_deployment` 候选。Rust 的 current_exe 相对路径只有在目标 workspace、target、profile/test 状态和 feature 请求相符，并具有入口调用帧或原生模块归属依据时才展开。不同二进制即使位于同一 workspace，也须各自满足源码归属。

适配器用所选程序位置计算目录和完整消费路径，再匹配同一目标系统下的构建/复制产物。它从 PRODUCES_ARTIFACT 找到实际生产目标，区分命令程序与普通文件读取。模块名、程序名及业务目录由事实取得。生产查询可以沿以下关系展开：

```text
Cargo 目标 → Rust main / 调用 / Command 程序参数 → 原始 path_value
  → PATH_DEPLOYMENT_BINDING → deployed_path_candidate
      ├─ MATCHES_DEPLOYED_ARTIFACT_CANDIDATE → 后端发行文件
      └─ RESOLVES_EXECUTABLE_TARGET_CANDIDATE → CMake 后端目标
           → EXECUTABLE_ENTRY_CANDIDATE → C++ main
```

图中最后两条关系都从 `deployed_path_candidate` 出发；分别提供文件映射与可执行目标导航。DEPLOYS_EXECUTABLE_CANDIDATE 和 RESOLVES_DEPLOYED_PATH_CANDIDATE 连接程序位置、配置及路径依据，原始 Rust 参数/调用链继续保留。

每个结果保留程序身份、相对部署布局、路径可达、cfg/features、复制与物化、生产来源没有被替换，以及文件系统解析没有重定向等条件。函数通过模块归属进入二进制时，callback 实际被调用仍是条件。多个生产目标落在同一完整位置时，`match_status=ambiguous_conditional_producers` 并列出全部候选；某个程序位置未找到文件时单独记录，不影响其他已匹配的部署位置。

CMake 的处理器字段保留声明含义。进程之间使用目标系统和完整文件位置配对；体系结构是否可由目标 OS loader 加载有独立条件，既有声明不升级为编译器架构验证。runtime_execution 继续为 not_observed；PID、实际启动及动态库/文件系统状态由运行场景采集。

## 独立检查

机制检查覆盖两种布局和路径风格、启动器改名、同名异目录排除、profile/features/target/test 隔离、同 workspace 的另一二进制、模块 callback 归属、父目录及 .. 路径、同位置多生产方和预算/未解析路径。

生产夹具由普通 Cargo 清单、Rust current_exe/Command、CMake 后端及 Python 复制脚本自动建图；没有显式 Cargo 捕获输入。CMake 目标名、产物名、Cargo bin 名和发行文件名各不相同。通过 Rust main→C++ main 的正向与反向查询，验证从构建/打包身份和完整路径连接两种语言。生产程序未编译/运行；CMake 执行配置和工具链探测，Rust 只执行 metadata/print 及原有语义查询。

首轮集成断言修正了 C++ 基础符号未统一携带 language 字段的筛选方式；随后发现导航 API 的 16 层上限，已在独立提交 cf54608 扩展可选深度至 64，并用 24 层正反查及预算截断验证。两次原始失败日志保留在仓库外。

8 项机制检查与新增生产夹具通过；完整回归运行 636 项，通过，1 项按平台跳过。

```text
python -m unittest tests.test_executable_deployment_graph tests.test_project_snapshot.FullSnapshotTests.test_default_rust_current_exe_chain_reaches_cmake_backend_entry -v
python -m unittest discover -s tests -v
```

Insight 的 C++/CMake、Python、Rust 同版本配对和索引查询证据见下节。其他启动模式、代理/插件和冻结边界继续按[全项目计划](../../plans/project-wide-completion-plan.md)展开。

## Insight Windows release/default 控制

规则 91f16b8 在源码 d4e8d1c 的 1,471 输入控制中，通过[46 项独立检查](evidence/executable-deployment-control.json)。C++/CMake 事实沿用 45a9fdc（1,336 输入），Python 沿用 a487ce3（119 输入），Rust 单 Windows release/default 上下文沿用 6038f94（16 输入）。当前 Cargo 查询、复制和程序身份/路径配对重新执行，语言语义和 CMake 配置未重跑。

工具自动连接：

```text
构建调用 → Cargo 目标 / Rust main
  → platform/preview/MindStudio-Insight.exe 的程序身份候选
  → platform/src/default.rs:164 的 Command 程序路径
  → :175 的 spawn 使用同一 Command
  → platform/preview/resources/profiler/server/profiler_server.exe
  → CMake profiler_server 目标
  → server/src/entry/server/bin/main.cpp 的 main 候选
```

程序名和目录来自 metadata、源值及完整复制映射。后端文件可反查到 `server/output/win_mingw64/bin/profiler_server.exe` 的原生产物和中间归一化复制。原始构建目录中的启动器也生成独立部署候选；该目录下没有所需后端文件，继续保留未匹配记录。

新索引含 300,443 个节点、467,230 条关系。十二个正反向查询均通过，其中 Rust main→C++ main 为 11 条边，源码构建调用→C++ main 为 15 条边，spawn→C++ main 为 6 条边。消费路径、C++ 入口和打包操作的源码导航均绑定同一提交。

当前连接是选定模式下的静态候选，保留 cfg/features、程序身份、复制/物化、文件系统布局和 OS loader 条件。CMake AMD64 字段继续表示声明，不升级为实际编译器架构验证。没有重新构建或运行产品、观察 PID/实际启动，也不是默认全仓重建；原始 checkout 未修改，未重新核验文件哈希。其余边界/启动模式及运行身份继续验收，G03/G04 保持未通过。

```text
python experiments/2026-10-25-w1/run_executable_deployment_control.py --source SOURCE --revision d4e8d1cf9f90208bcbe5371c127088f6fd66c688 --cpp-trial CPP_CMAKE_TRIAL --python-trial PYTHON_TRIAL --rust-trial RUST_TRIAL --parser-cache CACHE --output NEW_OUTSIDE_DIRECTORY
python experiments/2026-10-25-w1/score_executable_deployment_control.py --trial NEW_OUTSIDE_DIRECTORY --output NEW_SCORE.json
python experiments/2026-10-25-w1/check_path_evidence.py
```
