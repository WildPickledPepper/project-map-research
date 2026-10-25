# W1：Rust 基础关系与平台接口接入

2026-10-25。**Rust 已进入生产发现、构图、自动更新和统一查询，W1/G02 尚未完成验收。** Rust 范围的真实生产图通过 41 项检查，独立安装与模块更新通过 22 项检查；包含全部语言的全仓重建正在执行。后端进程到 C++ 入口的产物/实例配对、完整运行模式及逐模块机制继续按全项目计划推进，skill 最后整理。

源码固定为 Insight `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`，生产规则与安装 wheel 为 `5f8079dba2a733e40bef6cae4eb35075b3e39cf1`。原始 GitCode checkout 未修改，未重新核验文件哈希。

## 组件与接入

先保存 CGC `0.6.13` / `93c9685bff9151f50a3121e9913e5ba2d27c1191` 的原生 Rust 结构输出，再用独立夹具对照 rust-analyzer。[12 项探针通过](evidence/rust-resolver-probe.json)。本次只对照 CGC 原生 parser，没有运行其全量跨文件解析器，因此不据此比较两套系统的正确率。

采用既有 Tree-sitter `0.25.2` / language-pack `1.20.0` 做精确位置与源码结构规范化，复用 rust-analyzer `0.3.3089-standalone (5ec20d044d 2026-10-18)` 的定义/实现导航。Cargo/rustc/rust-src `1.94.0` 提供目标、依赖和编译 cfg；依赖求解和模块解析交给原生 Cargo loader。二进制与官方归档在实验目录，未运行系统安装器。发布版本见 [rust-analyzer 2026-10-19](https://github.com/rust-lang/rust-analyzer/releases/tag/2026-10-19)。

统一图包含文件/模块、trait/impl、函数/闭包、绑定、参数、调用接收者、返回值、导入与值来源，保存 cfg/分支条件。同名符号按文件、声明位置和作用域区分。调用保留各 Cargo 上下文的目标；全部分析上下文给出同一个可调用目标时才生成唯一推断边，其他情况保留候选。trait 方法声明及实现候选分别记录；宏定义/调用来源位置保留为 origin，未被当成可执行函数。

接口按原生外部声明识别 std Command/Child/TCP、Wry WebView 与资源读取 API，再用绑定与接收者来源连接程序、选项、地址、URL、注册与回调。标准 `format!` 需先被原生分析器绑定到标准库，再连接参数 token 与隐式捕获；本地同名类型和宏不靠拼写归入外部 API。

官方能力依据：[Cargo metadata](https://doc.rust-lang.org/cargo/commands/cargo-metadata.html)、[rust-analyzer 项目上下文](https://rust-analyzer.github.io/book/non_cargo_based_projects.html)及[加载配置](https://rust-analyzer.github.io/book/configuration)。这些是接口依据，下表是实际执行结果。

## 实测证据

| 项目 | 已执行结果 | 范围 |
|---|---|---|
| 原版结构基线 | [13 个 Rust 文件](evidence/native-summary.json) | CGC 原生函数/调用/import 记录，不是归一化图 |
| 原版 API 对照 | [12 项通过](evidence/rust-resolver-probe.json) | alias/reexport、impl、trait、闭包绑定、cfg/path、遮蔽、宏来源、Unicode |
| Cargo/配置 | [最初 7 项](evidence/rust-project-context.json)，扩展后 Linux 9 项通过 | 自定义目标、workspace、改名依赖、共享源码的独立同名 package、目标增删改名、多入口工具调用 |
| 原生入口对照 | [80 项通过](evidence/rust-native-project.json) | 两个 Cargo 清单、24 组配置、552 次根文件原生定义查询；尚非生产图 |
| 新增规范化检查 | 11 项语法、8 项原生语义、3 项原生接口检查通过 | 作用域/位置/条件、trait 候选、闭包/回调、参数、库 API 与同名负例、命令对象不串线 |
| 混合生产接入 | 31 项边界/混合快照/发现/刷新检查及新增 Cargo 输入检查通过 | Rust 关系和进程边界在 TS/C++ 混合生产快照保留 |
| Rust 生产图 | [41 项通过](evidence/rust-production.json) | 13 文件、24 上下文；启动/WebView 双向查询、相容上下文、同 builder 注册/回调、启动参数来源、版本源码 |
| 独立安装 | [22 项通过](evidence/rust-installed.json) | 从仓库外用隔离 Python 调用 wheel；自定义 Cargo 根与跨目录模块、同名负例、新增/改名/删除及过期拒绝；TS/JS/Python/C++ 保留 |
| 全量回归 | Windows 434 项通过，1 项按平台跳过；[Linux CI 通过](https://github.com/WildPickledPepper/project-map-research/actions/runs/40190909725) | 既有功能和新增适配回归，保留失败记录 |

原始源码、工具、wheel、数据库和命令/失败日志均在仓库外；公开证据是可移植投影。历史资产未启用，未执行被分析源码，也未生成运行证据。

首次全部语言默认全仓构建在最终 JSON 输出阶段遇到磁盘空间不足，未发布快照。保留失败现场及日志，将三份已有成功快照的重复检查点归档，释放约 3.6 GB；全仓输出改到容量充足的独立目录重新构建。正式全仓评分在快照发布后执行。

## 真实平台图连到了哪里

Cargo 自动发现 `platform/Cargo.toml` 与 `platform/linux/Cargo.toml`，两者共享入口源码；前者使用 wry 0.36，后者使用改名的 wry 0.24.11。清单身份分别保留。源码出现的 Windows/Linux/macOS、debug 开关和 default feature 开关组合为每个清单的 12 个分析上下文，共 24 个。这是分析矩阵，支持的产品构建与运行组合还需继续核对。

Rust 控制范围由通用语言/清单过滤生成，16 个输入为 13 个 Rust 文件、两个 Cargo 清单和一份 Cargo 配置。生产图有 5,768 节点、9,203 边；185 个函数/闭包/签名节点、873 个调用点。117 个调用点保留条件候选，554 个记录外部声明，202 个保留未解析原因；其中包含未选择的 test/平台/架构代码，不能用这些数字计算正确率。29 个导航结构分组仍不等于 W0 的 129 个必需逻辑组件。

[独立参考](rust-reference.json)只由后置评分器读取，生产发现与连接不读取业务名称或端点答案。Windows 与 Linux 相容上下文分别验证：

- 入口 → `default::main` → `run_server` → 进程启动边界，共 6 步。
- 入口 → `default::main` → `webview::run_script` → `create_webview` → WebView URL 加载边界，共 8 步。
- 前端加载与资源协议注册落到同一 builder，协议注册可查到实际闭包；启动选项包含 wsPort、notStrict，隐式 port 捕获连接到函数参数。

三类目标的统一导航正向与反向查询均通过，并独立核对见证路径的上下文交集。49 个接口节点包含 14 个命令构造、12 个启动、4 个 WebView builder、4 个 URL 加载、4 个 UI 事件注册、3 个等待、3 个 TCP 监听、2 个资源协议注册、2 个文件读取、1 个停止。它们是源码关系与条件候选；实际进程、运行事件和对象生命周期由后续证据验证。

进程程序表达式已经可查，关联 C++ 后端入口所需的构建产物、部署及实例身份仍待 W2 完成。完整对象/调用上下文的数据传播、宏展开和资源生命周期继续按 W2/W3 展开。未变化的 feature/架构条件、build.rs 输出和缺少原始 Cargo.lock 均保留；分析锁只在导出副本中生成，不充当产品构建重放证明。全仓默认输入复验和逐模块覆盖门槛尚未通过，G02 保持未完成。

## 失败与修正

`cargo.noDeps=true` 的原生加载对照中，改名路径依赖没有目标；关闭后连接正确，两种会话都报告 health=ok。目标发现可用 --no-deps，语义加载保留原生依赖解析。Rust 1.90.0 初试被分析器提示低于支持版本，后改用 1.94.0。首次原生探针的两处手写列坐标和宏的双来源参考、一个夹具 cfg 括号随后修正，原始失败保留。

Linux CI 发现 Rustup 多入口工具不能把 cargo/rustc 符号链接解析为 rustup 可执行文件，现保留启动名并验证实际版本；新增同名 Cargo 清单、共享源码和 POSIX 多入口调用回归通过。CI runner.temp 环境变量改为在步骤分配后使用。

首次全量回归 434 项中出现一次 Windows kill 后立即获取锁失败，独立复跑通过。测试改为终止后最多等待 2 秒确认释放，保留存活进程互斥、半成品不发布和最新提交恢复的断言。生产锁逻辑没有改动；完整复验 434 项通过，1 项为 POSIX 测试在 Windows 跳过。

## 复现

按[工具说明](../../docs/07-tool-quickstart.md)提供固定版本 Rust 工具和 parser/TypeScript 环境，输出使用仓库外新目录：

```text
python experiments/2026-10-25-w1/probe_rust_resolvers.py --cgc CGC --parser-cache CACHE --dll-dir DLL --rust-analyzer RUST_ANALYZER --output NEW_OUTPUT
python -m unittest tests.test_rust_project tests.test_rust_facts tests.test_rust_semantics tests.test_rust_boundaries -v
python experiments/2026-10-25-w1/run_rust_trial.py --source SOURCE --revision d4e8d1cf9f90208bcbe5371c127088f6fd66c688 --typescript TYPESCRIPT --scope rust --output TRIAL
python experiments/2026-10-25-w1/score_rust_trial.py --trial TRIAL --output SCORE.json
python experiments/2026-10-25-w1/smoke_installed_rust.py --python INSTALLED_PYTHON --typescript TYPESCRIPT --parser-cache CACHE --dll-dir DLL --output SMOKE
```

全仓复验使用 --scope repository。原生入口对照保留 run_rust_project_trial.py 与 score_rust_project_trial.py；prepare_portable_rust.py 可解包官方工具链归档。依赖只在实验导出副本中准备，生产分析使用离线缓存。skill 的统一整理留到工具能力和验收稳定之后。
