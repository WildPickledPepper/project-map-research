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

本项验证的是通用原生接口和生产查询。在 Insight 上，已提取的 Python Cargo 调用还需自动解释为 manifest、profile、target-dir、target 和 features，并关联实际目标；随后把启动器发行位置绑定到 Rust `current_exe` 基址，核对后端产物的配置与路径。产品实际编译/启动、冻结边界的其余模块和运行模式继续按[全项目计划](../../plans/project-wide-completion-plan.md)验收。
