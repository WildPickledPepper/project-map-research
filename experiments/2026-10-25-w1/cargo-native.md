# Cargo 原生产物接口与统一查询

日期：2026-10-26。证据类型：独立夹具的原生构建与生产建图测试。W2 正在连接 Python 构建调用、Cargo 启动器、发行布局及 Rust 进程路径；G02/G03/G04 保持未通过。

## 本项交付

复用 Cargo 的 `metadata --no-deps --offline` 与 `build --message-format=json`。metadata 提供包、清单、目标和入口文件身份；成功编译流提供实际文件名、profile 和已启用 features。产物路径直接采用原生 `compiler-artifact` 记录。

实现分为三部分：

- [原生捕获](../../adapters/cargo_native.py)：将选定输入复制到新的独立目录，记录工具版本、原生命令、stdout/stderr、宿主/目标 cfg 和成功/失败收据。
- [记录归一化](../../adapters/cargo_file_api.py)：核对源码版本、workspace 包、目标签名、入口文件及原生完成状态，生成带配置身份的目标和产物。
- [生产图导入](../../adapters/cargo_artifact_graph.py)：校验捕获收据的版本、上下文和输入范围，重定位逻辑源码路径，加入已有 Rust 事实及 Python 复制图。

原生捕获是显式构建操作，会执行 Cargo 构建脚本和 proc macros；使用独立输入副本，不启动产出的产品程序。默认源码分析仍使用原有关闭构建脚本与 proc macros 的 Rust 语义流程。将捕获记录传入建图配置后，导入阶段只读取记录。

## 图中的含义

```text
build_configuration
  └─ CONFIGURES_BUILD_TARGET → build_target
       ├─ CARGO_TARGET_SOURCE → Rust 根文件
       ├─ EXECUTABLE_ENTRY_CANDIDATE → 默认 main 候选
       └─ PRODUCES_ARTIFACT → build_artifact
            └─ COPIES_ARTIFACT_TO → copied_artifact（保留复制条件）
```

每个构建单元保留包清单、目标类型、profile、features 和构建上下文。可执行主产物、测试程序及其他输出分别记录；依赖包输出计入未展开数量。宿主/目标系统与架构来自本次 rustc 的基础 cfg 查询，实际 profile/features 来自编译流。基础 cfg 不替代 build-script cfg、编译参数及完整条件选择。

Rust 入口连接保留链接和 cfg 选择条件。`no_main` 生成自定义入口缺项；宏生成的默认入口、未进入语言事实的根文件也保留必需缺项。`reported_by_successful_native_build` 表示捕获目录中成功构建的原生报告，运行状态继续为 `not_observed`。Python 复制边保留物化、调用、过滤和顺序条件。

失败或截断的流、重复完成记录、目标/清单不一致、未被原生输出列表包含的 executable，以及旧源码版本均被拒绝。导入器在修改图之前校验全部捕获；生产刷新失败沿用原有机制保留上一份成功地图。

## 执行范围

使用 Cargo/rustc 1.94.0，在两种独立项目布局中实际构建：

| 控制 | 原生结果及验证目的 |
|---|---|
| 根目录清单、重命名 bin、非默认源码路径 | 读取实际 release 文件名，默认 features 保留 |
| 嵌套清单、清单外但仓库内源码、自定义 inspect profile | `CARGO_TARGET_DIR` 相对工作目录解析，debug assertions、关闭默认 feature 及 extra feature 保留 |
| 显式传入宿主 target | 采用原生 `<target>/debug` 输出，与未传 target 的目录结构区分 |
| 编译失败、日志损坏、版本/身份错误 | 不发布部分构建事实，保留失败输出或必需诊断 |
| 生产 Workspace 建图与导航 | Cargo 目标、实际产物、Python 改名后的发行文件正反查，清单/复制位置读取同版本源码 |
| 源码提交推进但仍配置旧捕获 | 刷新失败，旧成功快照仍可显式查询 |

Windows 夹具用 bundled rust-lld 构建无标准库的小程序，避免依赖 MSVC SDK；它带 `no_main`，检验适配器不会杜撰默认 main。所有夹具产物均未运行。Linux CI 使用普通 Rust main。

本地 16 项原生接口/配置检查及 5 项混合生产构图检查通过；完整回归运行 610 项，通过，1 项按平台跳过。现有路径证据收据和研究文档链接检查通过。版本固定的捕获与独立评分另存正式实验记录。

首轮保留了 Windows 链接器路径含空格时的参数失败、跨卷解析器缓存配置失败，以及导入测试夹具遗漏 snapshot 标识。链接参数改用 Cargo 的编码参数接口，测试显式使用已有解析器缓存，夹具补齐统一图标识。实际产品构建条件继续独立验收。

```text
python -m unittest tests.test_cargo_file_api tests.test_project_snapshot -v
python -m unittest discover -s tests -v
python scripts/check_research.py
```

## 配置与下一段连接

`build.cargo.captures` 接受捕获目录、40 位固定源码提交和唯一 `context_key`，见[工具用法](../../docs/07-tool-quickstart.md#cargo-原生构建记录)。同一源码可导入不同平台/feature 的独立上下文；目录必须保持不可变，源码变更需要新捕获。

本项验证通用原生接口和生产查询。Insight 的实际目标/产物绑定及启动器发行位置到 Rust `current_exe` 基址继续展开；产品实际编译/启动、冻结边界的其余模块和运行模式继续按[全项目计划](../../plans/project-wide-completion-plan.md)验收。

## 源码构建调用与原生配置配对

[源码配置解释器](../../adapters/cargo_source_bindings.py)复用已提取的 Python 进程参数、cwd 和环境写入，解析 Cargo build 的 profile、manifest、target-dir、target、features 及 no-default-features。相对 manifest/输出目录按已绑定的进程 cwd 解释；默认清单从 cwd 向上在选定输入中查找。CLI target-dir 与源码环境分别记录，规则依据见 [cargo build](https://doc.rust-lang.org/cargo/commands/cargo-build.html) 和 [Cargo 配置](https://doc.rust-lang.org/cargo/reference/config.html)。

生产建图导入捕获后，自动核对源码请求与原生配置的 cwd、manifest、profile、feature 请求、target 模式和输出根。生成 `cargo_build_request`，连接如下：

```text
python_process_invocation
  → SOURCE_BUILD_REQUEST → cargo_build_request
  → REQUESTS_BUILD_CONTEXT_CANDIDATE → build_configuration
  → CONFIGURES_BUILD_TARGET → build_target
  → PRODUCES_ARTIFACT → build_artifact
  → COPIES_ARTIFACT_TO → copied_artifact
```

这条连接保留源码调用被执行、命令实际解析到相应 Cargo、环境写入成功、外部配置/工具链与捕获一致等条件。环境值的源码布局条件也进入连接；未给定的根环境、build.target 和外部配置保留待满足的原生上下文条件。捕获由显式构建接口取得，源码中的 subprocess 调用继续是静态候选。

未知选项、配置覆盖、未展开的目标/包选择、继承或未绑定 cwd、shell/进程执行覆盖形成必需缺项并阻止配对。不同 profile/目标的捕获分别核对；某个组合被排除时，其他匹配组合可以保留。全部组合都不匹配时生成必需缺项。源码请求记录数按“调用位置 × 原生配置”统计。

生产混合夹具已验证源码进程调用到改名发行文件的完整正反向查询，并保留原生编译报告和源码条件。机制检查另覆盖两种布局、Windows 路径/环境键、CLI 输出目录优先、profile/manifest/target 不匹配、未知选项及多个配置。Insight 的固定版本源码配置控制随后保存独立评分。

9 项新增配置/配对检查通过；完整回归运行 619 项，通过，1 项按平台跳过。随后显式加入调用到达/成功条件，47 项原生接口、源码配对、进程及生产查询相关检查通过。

### Insight 源码配置控制

规则 b8a4779 对源码 d4e8d1c 的已保存 Python 进程事实重跑 Cargo 配置解释，[30 项独立参考检查通过](evidence/cargo-source-requests.json)。输入按当前通用发现策略核对，119 个 Python 输入与已存事实范围一致，两个 Cargo 清单从选定输入自动取得。Python 原生语义及进程事实沿用规则 a487ce3 的版本，不重新执行。

显式 Windows 源码条件下，两条 Cargo 记录中有一条可解析的 build 请求：

| 字段 | 自动解释结果 |
|---|---|
| argv | `cargo.exe build --release` |
| cwd | `platform`，相对于源码根 |
| manifest | `platform/Cargo.toml`，由 cwd 向上查找 |
| profile | `release` |
| target-dir | `platform/target`，来自 build/build.py:373 的 os.putenv |
| features | 未显式请求，默认 feature 保持启用 |
| target | 未提供；保留源码环境/配置与原生上下文一致的条件 |

请求来自 build/build.py:404，经包装函数到 :644 的进程 API。源码环境值中的 canonical layout 条件进入配置请求；调用到达/成功、命令身份、环境写入及外部配置条件保留。另一条 `cargo fetch` 保留为未支持的命令，未生成可执行程序构建请求。

本次是当前解释器作用于旧版本事实的源码控制，没有新建生产 Workspace、重新运行语义提取、Cargo 原生构建或产品程序，也未接通 Insight 实际产物/进程对端。原始 checkout 未修改，未重新核验文件哈希。

```text
python experiments/2026-10-25-w1/run_cargo_source_requests.py --source SOURCE --revision d4e8d1cf9f90208bcbe5371c127088f6fd66c688 --process-trial PREVIOUS_PROCESS_TRIAL --output NEW_OUTSIDE_DIRECTORY
python experiments/2026-10-25-w1/score_cargo_source_requests.py --trial NEW_OUTSIDE_DIRECTORY --output NEW_SCORE.json
python experiments/2026-10-25-w1/check_path_evidence.py
```
