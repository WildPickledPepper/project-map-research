# Rust 边界参数与共同值来源

日期：2026-10-26。证据类型：独立机制及默认建图检查。W2 继续展开进程参数、地址和前端加载关系。

[参数适配器](../../adapters/rust_argument_templates.py)复用现有 Rust 语法树、rust-analyzer 声明/引用和按调用位置的参数帧，提取 Command.arg、直接数组形式的 args、WebView URL 和网络边界的字符串模板。标准 format 宏须有原生声明来源；源码字面量、槽位、格式选项和参数词边界分别保存。格式语义依据 Rust 1.94 的 [format](https://doc.rust-lang.org/1.94.0/std/fmt/index.html) 与 [Command.arg](https://doc.rust-lang.org/1.94.0/std/process/struct.Command.html#method.arg)。含空格的一个 arg 保留为一个参数词。

模板的 `source_scalar_value` 沿原生绑定、参数传递、别名、唯一返回值和闭包捕获追溯。身份包括源码位置、调用帧及分析上下文：同一个选择结果进入两个不同函数时共享来源；不同作用域、调用或配置分别保留。Option 模式投影保留选择条件及原始绑定，动态端口仍为符号值。cfg 使用三值判断，当前上下文确定不启用的调用退出候选，未知自定义 cfg/features 保留条件。

```text
进程 / URL / 网络边界
  → BOUNDARY_ARGUMENT_TEMPLATE → boundary_argument_template
       ├─ ARGUMENT_TEMPLATE_SOURCE → 原始表达式
       └─ TEMPLATE_VALUE_SLOT → source_scalar_value
            → SCALAR_VALUE_SOURCE → 参数 / 绑定 / 调用
```

查询先从一个模板查到值，再反查该值的其他模板消费者。结果同时保留源码参数、调用和宏捕获关系，支持继续核对所选参数帧。`complete` 表示当前模板的文字及槽位来源已经展开；运行中选出的端口、实际参数求值、闭包触发、Command 的其他修改及进程实例有各自条件。运行字段保持 `not_observed`。

动态格式宽度、尚未展开的表达式/实例字段、参数集合及递归/迭代身份预算形成必需缺口。对已发现的赋值和 String 修改，适配器保留 reaching-write 缺口，不复用旧字面量。图中共同值来源为后续进程 CLI→参数解码→监听端配对提供输入；服务实例还须结合已恢复的程序/部署身份继续核对。

机制检查使用原生 Rust 1.94/rust-analyzer 固定夹具，覆盖隐式/位置/命名槽位、转义括号、格式选项、参数词边界、动态共同来源、跨函数与闭包捕获、同名/跨调用隔离、cfg 选择、写入和未知表达式。生产夹具把不同名称和布局的 Rust、Python 打包及 CMake 后端自动建图，验证新增模板、配置隔离及值来源的正反查，原有 Rust→C++ 入口查询同时保留。

13 项专项机制检查通过，增强生产夹具通过；完整回归运行 649 项，通过，1 项按平台跳过。首轮增强夹具把两个分析上下文当作一个，产生 4 个模板而非预期的 2 个；现按上下文分别检查两个消费者，并验证不同配置的值身份各自独立。原始失败日志保留在仓库外。

```text
python -m unittest tests.test_rust_argument_templates tests.test_project_snapshot.FullSnapshotTests.test_default_rust_current_exe_chain_reaches_cmake_backend_entry -v
python -m unittest discover -s tests -v
```

真实源码控制按下列命令复用版本固定的原生 Rust 事实，重新执行模板投影与导航索引。提取程序不读取评分答案；评分器在图生成后核对 Insight 的源码位置、共同值来源和未知项。

```text
python experiments/2026-10-25-w1/run_rust_argument_control.py --source SOURCE --revision REVISION --base-trial NATIVE_RUST_TRIAL --parser-cache CACHE --output NEW_OUTSIDE_DIRECTORY
python experiments/2026-10-25-w1/score_rust_argument_control.py --trial NEW_OUTSIDE_DIRECTORY --output NEW_SCORE.json
```
