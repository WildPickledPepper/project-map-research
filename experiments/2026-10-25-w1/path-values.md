# 启动路径值传播：已验证的基础与待补关系

2026-10-25，已执行 Windows/std-only 独立 Rust 探针，[5 项检查通过](evidence/native-path-primitives.json)。该记录固定规则 07dcab6 的原生能力和缺口。循环基础事实现已补齐，完整路径传播及进程对端配对继续实施。

原生 rust-analyzer 已将 to_path_buf、push、set_extension 绑定到标准库 Path/PathBuf 声明；同名本地 PathBuf.push 没有被归为标准库。真实平台代码中这些 API 也已有原生声明身份。路径适配可以复用这些身份，避免按调用拼写识别库语义。

原探针的统一语法事实没有为 for 循环的 piece 建立 binding。它保留常量数组、循环、调用及 cfg(windows)，尚未表示依次追加后的路径结果。

循环基础事实已实现：每个 for 有独立 iteration，绑定记录有效范围和模式投影；ITERATION_SOURCE / ITERATES_VALUE 保存元素来源，数组/元组成员保存顺序，重复数组的长度单列 repeat_count。原生定义导航将两个相邻循环的同名变量及外层同名变量分别绑定。新增 2 项语法、1 项原生语义检查，与既有 Rust 检查共 25 项通过；首轮数组元数据分支位置错误已由测试发现并修正。路径变更后的值由下一步适配计算。

接下来按三段连接：

1. Rust：补循环绑定和常量数组元素来源；在已确认的标准 Path/PathBuf API 上传播路径，保存顺序、接收者及目标平台条件。动态片段保留其来源和剩余表达式。
2. Python：复用现有导入、参数和值关系，提取 os.path/pathlib 路径及 shutil 复制；展开已知目录与文件模式，保留循环、过滤和调用位置条件。输出构建产物到发行路径的关系。
3. 跨语言：按原生构建上下文、完整路径、复制来源及平台入口来源配对；增加相异名称/布局、同名不同目录及增删改名负例，然后验证真实启动到 C++ 入口的正反向查询。

平台条件还须与 CMake/Cargo 上下文对应。编译器/系统信息、入口产物放置及运行根目录分别保留，不能仅凭文件名推断同一产物或同一实例。实际进程和参数采用结果由后续运行记录验证。

```text
python experiments/2026-10-25-w1/probe_path_primitives.py --output NEW_OUTSIDE_DIRECTORY
python experiments/2026-10-25-w1/check_path_evidence.py
```

使用 Rust/Cargo/rust-src 1.94.0 及 rust-analyzer 2026-10-19，目标为 Windows 原生工具链。分析不执行示例程序；原始事实、源码副本和 native 日志在仓库外。第一次原始探针随后补了执行前的规则版本记录，正式证据来自第二次执行。旧探针保存当前缺口断言，后续修正通过新的路径验收记录证明。
