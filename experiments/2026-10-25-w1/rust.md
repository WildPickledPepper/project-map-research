# W1：Rust 接入记录

2026-10-25。原版组件、Cargo 上下文和真实平台入口配置对照已完成，生产统一图与平台接口接入继续执行。W1/G02 尚未通过。源码范围沿用 W0 与 [119/53/13 文件基线](README.md)，未介入历史资产，skill 留到最后整理。

## 已执行：原版组件对照

下载并运行 rust-analyzer `0.3.3089-standalone (5ec20d044d 2026-10-18)`，对应官方 [2026-10-19 发布](https://github.com/rust-lang/rust-analyzer/releases/tag/2026-10-19)。二进制、压缩包、原始 LSP 响应和日志均在仓库外；没有安装系统 Rust 工具链或修改系统 PATH。

对照 CGC `0.6.13` / `93c9685bff9151f50a3121e9913e5ba2d27c1191` 的原生 Rust parser，在相同独立源码上执行 12 项检查，全部通过。[公开证据](evidence/rust-resolver-probe.json)保存两者的原生输出投影：

| 机制 | 实测结果 |
|---|---|
| module/use、别名与重导出 | `api::invoke` 定位到实际文件内的 `run`；另一个同名函数未被选中 |
| 内联模块、super、glob | 定位到正确模块定义 |
| impl 接收者 | `a.run()` 定位到 A 的实现，同名 B 实现未被选中 |
| trait 对象 | 定义导航指向 trait 方法声明；implementation API 列出两个实现。它们仍需按分派条件作为候选 |
| 闭包绑定 | `callback()` 指向局部绑定，需要适配器继续连接绑定和值来源，不能把变量位置当作函数定义 |
| cfg 与 path | 分别给定 windows/unix 上下文时，同一 module 声明选择相应文件；显式路径覆盖也成立 |
| 参数遮蔽 | 指向函数参数，没有误连全局同名函数 |
| 声明宏 | 定义导航同时返回宏内生成定义的位置及宏调用位置，需要保留展开来源 |
| Unicode 位置 | 调用前存在非 BMP 字符时，UTF-16 请求仍定位正确 |

每个 fixture 的 `rust-project.json` 是明确的实验上下文，由测试驱动提供。此处未测自动 Cargo 项目发现，也没有把人工上下文计为自动提取。rust-analyzer 支持 JSON 项目描述和内联 `linkedProjects`，这是此次未安装 Cargo 仍能运行探针的基础；生产接入仍需自动提供 crate、依赖和配置上下文。[官方项目描述文档](https://rust-analyzer.github.io/book/non_cargo_based_projects.html)

本次禁用 Cargo 构建脚本、proc-macro 和保存时检查，没有执行被分析源码；声明宏由分析器展开。所有会话都收到 quiescent/ok 状态。LSP 使用初始化配置和状态通知等待加载；其接口依据见[官方 LSP 扩展](https://rust-analyzer.github.io/book/contributing/lsp-extensions.html)。

CGC 原生记录保留了结构与调用拼写；本批调用记录没有列坐标，实例方法接收者类型为空，闭包未单列为函数，trait 的签名声明也未列入 functions。这些是本批原生 parser 的观察，未运行 CGC 的全量跨文件解析器，不据此给两套系统计算正确率。

首轮探针有两个手写列位置错误；宏导航还返回两处来源，原参考只写了一处。核对 fixture 后修正参考，第二轮 12 项通过。原始失败保留在仓库外。这次验证支持优先复用 rust-analyzer 处理解析与定义导航；统一身份、闭包值来源、候选、配置条件和接口图仍由接入工作检验。

## 已执行：Cargo 上下文与原生加载

新增生产适配 `rust_project.py`，通过 `cargo metadata --offline --no-deps --format-version 1` 自动读取 workspace、package、非标准目标路径、改名依赖和 Cargo feature 定义。此步骤负责发现目标，依赖关系的语义解析继续交给 rust-analyzer 原生 Cargo loader；没有另写 Cargo 依赖求解器。配置矩阵由源码出现的 OS/feature 条件与 rustc 的目标 cfg 生成，每个会话保留目标、feature 和 debug 选择。未遍历的 feature、架构条件、构建脚本输出和预算缺项明确登记，矩阵不等同于受支持产品构建列表。

[7 项独立检查通过](evidence/rust-project-context.json)：自动发现 workspace/自定义目标/改名依赖；新增、改名、删除目标；输入外依赖缺项；缺少编译器缺项；OS/feature/debug 矩阵；原生 Cargo 路径依赖查询；feature 与 debug 两组替代模块的实际定义导航。最后两项启动固定版本 rust-analyzer，其余项使用实际 Cargo/rustc。带写文件和 panic 的构建脚本哨兵未运行。

原生加载对照确认 `cargo.noDeps=true` 会让本批改名路径依赖的定义导航返回空，关闭此选项后定位到 `worker/code/engine.rs`；两种会话都报告 health=ok，因此健康状态不能代替关系检查。发现阶段的 `--no-deps` 与语义加载阶段分别处理。Cargo 原生目标/依赖输出的能力依据见[官方 metadata 文档](https://doc.rust-lang.org/cargo/commands/cargo-metadata.html)，加载配置依据见[官方配置文档](https://rust-analyzer.github.io/book/configuration)。

工具链使用官方归档解包到实验目录，未运行安装器或修改系统 PATH。初试 Rust 1.90.0 时，分析器报告最低支持 1.94.0；改用便携的 Cargo/rustc/rust-src 1.94.0 后执行上述最终检查。源码夹具中的一个 cfg 括号错误在首轮失败后修正。配置加载器已加入专门的 Linux CI 检查；截至本次本地提交，CI 结果待观察。

首轮工作流在分配 runner 之前引用 `runner.temp`，调整为步骤环境变量后开始执行。随后 Linux 检查发现工具路径的符号链接被解析为 `rustup`，改变了按启动文件名分派的行为；改为保留 `cargo` / `rustc` / `rust-analyzer` 启动路径，并对实际可执行版本做可用性检查。新增 POSIX 多入口工具的实际调用回归；Windows 上原 7 项通过，POSIX 回归由 Linux CI 复验。

真实仓库发现两个独立 Cargo 配置共享平台源码；适配输出增加 workspace 归属。新增同名 package、自定义相同目标名、共享外部源码路径的独立夹具，两个 manifest 的身份和上下文分开保留。Windows 当前 8 项通过，另 1 项 POSIX 调用测试交由 Linux CI 执行。文件路径相同不能替代 crate/构建上下文身份。

[Linux CI 复验通过](https://github.com/WildPickledPepper/project-map-research/actions/runs/40187760036)：专门的 Rust 作业 9 项全部执行并通过；全量回归 410 项 Python 测试通过，其中 3 项按环境跳过，121 项 Node 检查通过。Rust 原生集成由专门作业实际执行，跳过项没有计成运行证明。

## 已执行：真实平台入口配置对照

Insight 原始提交通过自动发现选中 13 个 Rust 文件及 Cargo 清单/配置；由 Cargo 找到 `platform/Cargo.toml` 和 `platform/linux/Cargo.toml`，两者共享 `platform/src/main.rs`。Linux 清单使用改名的 wry 0.24.11，主清单使用 wry 0.36；这来自实际清单和 metadata。两个 Cargo 会话分别保留。

配置适配规则对应 `11434368cdf5da62246ac311266bafcd4c55980f`。本次矩阵为 x86_64 下源码出现的 Windows/Linux/macOS、debug 开/关、default feature 开/关，两个 manifest 共 24 个原生分析会话。对各 manifest 的 Cargo target 根文件取调用点：主清单 37 个，Linux 清单 9 个，总计发出 552 次定义查询。生成器不读取[独立源码参考](rust-project-reference.json)，后置评分器据此核对入口选择。

[80 项检查通过](evidence/rust-native-project.json)：24 项核对当前配置的入口目标，48 项核对未选分支没有得到目标定义，另 8 项核对源码版本、工具版本、范围、上下文和证据边界。default 关闭时定位到 `http::main`；default 开启、release 时到 `default::main`；debug 时 Windows/macOS 到 `dev.rs`，Linux 到 `dev_legacy.rs`。全部会话报告 health=ok。

这里完成的是原生分析器的入口定义对照。13 个文件是输入范围，查询范围是 Cargo target 根文件；其他模块由分析器加载，尚未导入统一关系图。进程/WebView 参数和实际边界仍待接入。这批跨配置查询也没有证明这些配置全部是可构建、可运行的产品模式。

分析显式保留了未逐一变化的 Cargo feature、未重放的 `build.rs` 输出和未变化的架构条件。原提交未跟踪 Cargo.lock，由独立源码审计登记；实验只在导出副本中解析/缓存公开依赖，生成两个分析用 lockfile，原始版本和系统环境未修改，没有执行构建脚本或产品程序。生成锁不作为原产品构建的重放证明。

## 下一项

把语法事实与已验证的语义导航接入统一图，保留 crate/配置身份和宏展开来源，继续连接闭包、参数、进程与 WebView 接口。缺失依赖、未选配置和输入外目标应各自可查。完整跨进程配对继续按 W2 的产物和实例身份完成。

## 复现

```text
python experiments/2026-10-25-w1/probe_rust_resolvers.py --cgc CGC --parser-cache CACHE --dll-dir DLL --rust-analyzer RUST_ANALYZER --output NEW_OUTPUT
python experiments/2026-10-25-w1/prepare_portable_rust.py --version 1.94.0 --target x86_64-pc-windows-msvc --output TOOLCHAIN
python -m unittest tests.test_rust_project -v
python experiments/2026-10-25-w1/run_rust_project_trial.py --source SOURCE --revision d4e8d1cf9f90208bcbe5371c127088f6fd66c688 --output TRIAL --prepare-dependencies
python experiments/2026-10-25-w1/score_rust_project_trial.py --trial TRIAL --output SCORE.json
```

固定原版 CGC 提交和官方 rust-analyzer 版本，输出使用仓库外新目录。脚本复用现成解析器和 LSP API，实验过程不生成生产关系图。

真实平台对照需要固定版本 Cargo/rustc/rust-src 与 rust-analyzer 可执行文件，并设置已有 parser 环境。`--prepare-dependencies` 只在导出副本中解析与下载依赖；以后可复用实验缓存，以离线模式重做原生查询。完整平台编译不属于这一步。
