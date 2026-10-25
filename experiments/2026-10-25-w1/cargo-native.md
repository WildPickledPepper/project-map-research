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

## 默认源码建图的 Cargo 输出计划

[声明产物适配](../../adapters/cargo_declared_artifacts.py)已接入默认生产建图。它从源码中的 Cargo build 请求选择 cwd、清单、profile 和输出目录，调用离线 metadata 确认 workspace 默认成员、包、目标名和根文件；再用 rustc 的 `--print file-names` 查询目标平台的可执行文件前后缀，组合 Cargo 的公开 profile/target 目录布局。二进制名称来自 metadata，包含连字符的名称保留 Cargo 的输出命名规则。依据见 [Cargo target 名称](https://doc.rust-lang.org/cargo/reference/cargo-targets.html#the-name-field)、[输出目录](https://doc.rust-lang.org/cargo/reference/build-cache.html)及 [rustc print](https://doc.rust-lang.org/rustc/command-line-arguments.html#print-print-compiler-information)。

原生查询在选定输入的独立副本中执行，不编译产品、执行 build.rs 或加载 proc macros。生成的配置状态为 `declared_output_plan`，主要可执行文件标记 `expected_output_not_built`。默认分析可以沿构建请求、目标、预期文件及 Python 复制/改名展开；显式成功编译流仍提供 `native_build_succeeded` 和实际输出报告。存在匹配的编译记录时优先使用该记录，避免重复产物。

本地 Cargo 配置按 cwd 的祖先目录读取，保留配置路径、extensionless 文件优先及数组合并规则。未显式选择 target 时，生成带“源码 target 选择与此计划一致”条件的宿主默认候选；当前分析机的环境变量不会填充源码的未知环境。profile 的 debug assertions 保留声明/默认继承含义，以及环境、编译参数和构建脚本配置条件。

构建成功、目录布局、目标选择、feature 要求及编译参数保持输出规则等条件随原生产物进入复制图。未知源码参数、未支持配置 include/目标规格、包级 profile 选择、缺失工具及未选择构建上下文的 Cargo 清单均保留必需缺项。该适配当前投影默认构建选择中的主要二进制输出；库产物和 build-script 生成物另有必需诊断，例子/测试/bench 未被默认 build 选择时不投影。

独立控制使用两种目录布局、重命名 bin、嵌套清单、跨清单路径、自定义 profile、features 和显式 target。未编译的预期主要输出逐项对照真实 Cargo 编译报告；还检查 workspace 默认成员、模块新增/改名/删除、配置文件优先/数组合并及已存在原生报告的去重。混合 Workspace 同时验证显式编译记录和默认源码计划的进程调用到改名发行文件正反查。

7 项新增声明产物检查、原生接口/配对及生产建图回归通过；完整回归运行 626 项，通过，1 项按平台跳过。Insight 的固定版本声明产物与发行改名证据单独保存。

### Insight 声明产物与发行改名控制

规则 c141f19 对源码 d4e8d1c 的 135 个 Python/Rust/Cargo 输入执行当前 Cargo 查询、源码请求连接和复制投影，[39 项检查通过](evidence/cargo-declared-control.json)。Python 事实沿用 a487ce3，Rust 单个 Windows release/default 上下文沿用 6038f94；记录各自版本，当前阶段不重跑语义提取。

自动链条如下，产品和接口名称均由原生 metadata 与源码值取得：

```text
build/build.py:404 → 包装函数 → subprocess.Popen :644
  → Cargo 配置（platform/Cargo.toml，release）
  → MindStudioInsight 目标 → platform/src/main.rs 的 main 候选
  → platform/target/release/MindStudioInsight.exe（预期文件）
  → build/build.py:532 的复制
  → platform/preview/MindStudio-Insight.exe（条件复制位置）
```

82,575 个节点、124,033 条关系进入新索引；构建调用→配置、目标→入口、目标→发行文件和构建调用→发行文件的八个正反向查询通过，清单/main/复制位置均读取同一提交源码。Windows 宿主/目标及文件名模板由 Rust 1.94.0 原生查询取得；target 未显式给出时的源码环境/配置条件，以及构建成功、文件物化、顺序和复制条件继续保留。

platform/build.rs 的生成输出和 platform/linux/Cargo.toml 的另一构建上下文保留必需缺项。本次不是默认全仓重建，没有执行产品编译、build scripts、proc macros 或产品程序；原始 checkout 未修改，未重新核验文件哈希。Rust current_exe 基址和后端对端继续连接。

```text
python experiments/2026-10-25-w1/run_cargo_declared_control.py --source SOURCE --revision d4e8d1cf9f90208bcbe5371c127088f6fd66c688 --python-trial PYTHON_TRIAL --rust-trial RUST_TRIAL --parser-cache CACHE --output NEW_OUTSIDE_DIRECTORY
python experiments/2026-10-25-w1/score_cargo_declared_control.py --trial NEW_OUTSIDE_DIRECTORY --output NEW_SCORE.json
python experiments/2026-10-25-w1/check_path_evidence.py
```
