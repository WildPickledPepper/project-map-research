# 启动路径值传播：已验证的基础与待补关系

2026-10-25，已执行 Windows/std-only 独立 Rust 探针，[5 项检查通过](evidence/native-path-primitives.json)。该记录固定规则 07dcab6 的原生能力和缺口。循环事实与第一版 Rust 路径传播已接入生产图；规则 6038f94 的真实 Windows 单配置控制检查 [33 项通过](evidence/rust-path-control.json)。继续补 Python 打包及进程对端配对。

原生 rust-analyzer 已将 to_path_buf、push、set_extension 绑定到标准库 Path/PathBuf 声明；同名本地 PathBuf.push 没有被归为标准库。真实平台代码中这些 API 也已有原生声明身份。路径适配可以复用这些身份，避免按调用拼写识别库语义。

原探针的统一语法事实没有为 for 循环的 piece 建立 binding。它保留常量数组、循环、调用及 cfg(windows)，尚未表示依次追加后的路径结果。

循环基础事实已实现：每个 for 有独立 iteration，绑定记录有效范围和模式投影；ITERATION_SOURCE / ITERATES_VALUE 保存元素来源，数组/元组成员保存顺序，重复数组的长度单列 repeat_count。原生定义导航将两个相邻循环的同名变量及外层同名变量分别绑定。新增 2 项语法、1 项原生语义检查，与既有 Rust 检查共 25 项通过；首轮数组元数据分支位置错误已由测试发现并修正。路径变更后的值由下一步适配计算。

路径接入检查发现 Rust 1.94 的部分 const impl/约束超出了当前 grammar 覆盖，Option.unwrap 丢失 impl 结构，Result.unwrap 未得到命名声明。外部声明规范化现可从 rust-analyzer 返回的精确 selection 读取并核对源码标识符，记录 native_selection_token 及未解析结构；不从使用处的调用拼写补名字。标准库来源、模块和版本上下文继续保留。新增原生 Result/Option 检查通过，路径入口的辅助函数检查也能追到可执行文件目录。

## 已实现的路径传播

`path_values` 保存语言无关的路径表达式；`rust_path_values` 使用原生库声明、实际调用目标和源码位置建立结果。模型支持有限字面量数组循环、追加/扩展名/文件名、克隆、借用别名、简单条件分支、函数参数及可执行文件目录。每次消费按当时位置计算，后来的修改不回写已有程序参数；各调用点和 Cargo 上下文分别保留。

路径结果分为常量、相对符号基址、未解析。分支保留条件，Some 模式及 unwrap 保留成功采用条件；绝对片段替换基址，盘符相对路径、动态片段等保留具体缺项。表达式使用 DAG 保存共享前缀，并设调用、迭代和候选预算。`path_value` 通过 PATH_VALUE_CANDIDATE、PATH_COMPONENT_SOURCE、PATH_CALL_CONTEXT 连接消费点、原始常量/参数/操作与调用上下文，可由统一查询展开。

控制范围检查覆盖不同名称、两个路径对象、克隆快照、构造时捕获、可变参数、调用上下文、同名自定义 PathBuf 以及未知修改负例。路径与生产混合建图 24 项检查通过；完整 Windows 回归 478 项通过，1 项按平台跳过。随后新增经可变参数传递到 std::mem::swap 的负例，与公共路径检查共 12 项复验通过。正式提交前，最终路径与公共模型定向复验 24 项通过。

路径重赋值、动态/非直接数组迭代、未展开宏、引用逃逸、隐式捕获及未知可变调用暂保留必需缺项，不能沿用修改前的路径作为精确结果。第一轮测试发现可变引用包装和跨函数参数效果遗漏；修正后测试通过。真实源码、安装、全量更新及与构建产物的连接分别验收，G02/G03 保持未通过。

## Insight 真实 Windows 路径控制

源码固定 d4e8d1c，提取规则固定 6038f94。执行生产 Rust 原生语义、边界和路径适配器，再通过 Workspace.attach 建立统一查询索引。选择 platform/Cargo.toml、x86_64-pc-windows-msvc、Release、default feature；13 个 Rust 文件及 3 个 Cargo/配置输入进入记录。产物有 5,579 个节点、8,068 条关系和 12 个路径候选。

`platform/src/default.rs:164` 的 Command::new(path) 得到：

```text
current_executable_directory
  / resources / profiler / server / profiler_server.exe
```

路径来源包括第 42 行的四个常量、第 80 行的扩展名、标准库 current_exe/parent/to_path_buf，以及 main → default::main → run_server 调用位置。Some(path)、两次成功 unwrap 和源函数返回条件保留。进程启动到路径、路径到基址、常量及调用来源共 8 个正反向查询通过，同版本源码导航通过。另一处 WebView 文件读取的复杂表达式仍有必需缺项。

首轮控制运行遗漏了 3 个已选清单的 coverage 行，导致导航投影未标为输入；控制脚本已采用生产混合建图相同的补齐方法，第二次从新目录重跑通过。首份原始图保留。独立评分首轮误读 external_symbol 的声明字段层级，修正评分器后 33 项通过；提取规则未变，评分参考没有传入提取器。

本项覆盖一个显式配置的生产适配器与索引。默认全仓 24 配置刷新、独立安装、打包来源、C++ 对端和实际启动分别继续验收；本记录保持 G02/G03 未通过。原始源码、图、native 日志均在仓库外，原 checkout 状态未变，未重新核验文件哈希。

```text
python experiments/2026-10-25-w1/run_rust_path_control.py --source SOURCE --revision d4e8d1cf9f90208bcbe5371c127088f6fd66c688 --manifest platform/Cargo.toml --output NEW_OUTSIDE_DIRECTORY
python experiments/2026-10-25-w1/score_rust_path_control.py --trial NEW_OUTSIDE_DIRECTORY --output NEW_SCORE_FILE
python experiments/2026-10-25-w1/check_path_evidence.py
```

## 后续连接

按三段推进：

1. Rust：循环绑定、常量数组及标准 Path/PathBuf 的 Windows 控制已通过；扩展其他配置及剩余动态表达式，保持顺序、接收者和目标平台条件。
2. Python：[基础路径与文件操作](python-packaging.md)已接入生产构图，48 项定向检查及 119 个 Python 输入的 34 项真实源码/索引检查通过；接下来展开目录项、循环过滤及跨函数参数，保留调用位置和复制选项，形成构建产物到发行路径的关系。
3. 跨语言：按原生构建上下文、完整路径、复制来源及平台入口来源配对；增加相异名称/布局、同名不同目录及增删改名负例，然后验证真实启动到 C++ 入口的正反向查询。

平台条件还须与 CMake/Cargo 上下文对应。编译器/系统信息、入口产物放置及运行根目录分别保留，不能仅凭文件名推断同一产物或同一实例。实际进程和参数采用结果由后续运行记录验证。

```text
python experiments/2026-10-25-w1/probe_path_primitives.py --output NEW_OUTSIDE_DIRECTORY
python experiments/2026-10-25-w1/check_path_evidence.py
```

使用 Rust/Cargo/rust-src 1.94.0 及 rust-analyzer 2026-10-19，目标为 Windows 原生工具链。分析不执行示例程序；原始事实、源码副本和 native 日志在仓库外。第一次原始探针随后补了执行前的规则版本记录，正式证据来自第二次执行。旧探针保存当前缺口断言，后续修正通过新的路径验收记录证明。
