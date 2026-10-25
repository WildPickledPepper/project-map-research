# Python 进程调用、工作目录与环境来源

路径适配 0.7.0 将导入身份确认的 subprocess/asyncio 进程接口展开为逐调用事实。目标是把构建脚本中的 Cargo 调用连接到输出配置、启动器打包和 Rust 运行基址。程序名称、目录、参数及环境键从源码发现。

## 生产事实与查询

| 事实或关系 | 保存的信息 |
|---|---|
| `python_process_invocation` | 参数向量、原始表达式、字符串/数组形式、cwd、shell/env/executable/preexec_fn、调用帧、条件和缺项 |
| `python_environment_effect` | putenv/unsetenv、environ 下标写入/删除及未展开映射方法；键和值来源、是否同步 Python environ 映射 |
| PROCESS_CONTEXT / PROCESS_BOUNDARY | 原始调用、逐调用事实和已有进程边界 |
| PROCESS_ARGUMENT_SOURCE / PROCESS_ARGUMENT_COMPONENT | 实参和展开后的字面量、绑定、路径来源 |
| PROCESS_WORKING_DIRECTORY / PROCESS_SETTING_SOURCE | 工作目录与进程选项的源码位置 |
| PROCESS_CALL_STACK | 各层源函数调用位置 |
| PROCESS_ENVIRONMENT_EFFECT / ENVIRONMENT_EFFECT_SOURCE | 同一根调用中较早或顺序未定的环境操作，以及键/值来源 |

从 `query search --kind python_process_invocation` 查询调用，再沿上述关系展开。argv 保留空字符串、`./` 和选项中的分隔符原文；源码根路径保留符号基址。包装函数使用实际参数绑定，各调用点分别计算。只读数组可通过已解析源函数传递；数组修改、未知逃逸、星号展开和上下文预算耗尽保留必需缺项。

`python_process_values.resolve` 在显式宿主上下文中选择候选。shell、executable override、preexec_fn 及 Windows 命令字符串分别处理；当前直接程序/argv 连接在这些执行方式尚未展开时返回缺项。原生调用位置和完整源码参数继续保留。标准库成员被源码改写时，记录写入位置并要求进一步解析其顺序和身份。

已知 if/else 条件可以排除被后续赋值覆盖的旧值，避免命令选择依赖分支书写顺序。选择条件尚未知时保留到达定义缺项。

## 环境值的条件绑定

`environment_value` 使用同一根调用的源码顺序与分支，逐键计算继承环境的来源。较晚写入不回写已发生的启动，两个调用点分离，未知顺序和可选覆盖保持未知。当前调用自身要求的条件可作为前提，用于检查同一受控分支中更早的写入。Windows 环境键按大小写不敏感处理。

putenv/unsetenv 修改进程环境，environ 下标写入/删除同时修改 Python 映射；`env=` 显式映射作为另一份子进程环境处理。当前尚未展开该映射时，求值器给出缺项。未提供的根入口环境值保持未知，分析器不会读取自己的运行环境来填充答案。

环境绑定结果适用于“本次调用已到达、相应环境操作成功、启动前没有其他未建模环境写入”的条件。图中执行状态为 `not_observed`，实际采用由运行证据验证。

接口依据：[Python 3.11 subprocess](https://docs.python.org/3.11/library/subprocess.html)、[Python 3.11 os.putenv/environ](https://docs.python.org/3.11/library/os.html#os.putenv)。测试运行时为 Python 3.11.9，底层源码语义/引用复用 AST/Jedi 事实。

## 检查与剩余连接

21 项新检查覆盖调用配对、原文参数、平台数组、已知覆盖、数组修改/逃逸、直接和跨函数环境写入、覆盖顺序、同一调用条件、不同根隔离、循环顺序未知、Windows 键、显式 env、shell/override/preexec、asyncio、None cwd、空参数、展开及标准库成员改写。首次扩展负例发现成员改写仍被原生推断识别为标准库，现已增加源码写入检查；原始失败日志保留。首轮命令中误列一个不存在的测试模块，已更正为实际的调用上下文测试。

生产混合快照检查保留进程事实、环境关系和原有进程边界；真实 Insight 调用、Cargo 原生目标/输出、复制后的启动器目录及 Rust current_exe 基址分别继续验收。G02/G03/G04 保持未通过。

完整 Windows 回归 592 项通过，1 项按平台跳过。随后补充“已替换的环境 API 可能修改其他键”的负例，最终 121 项路径/调用/环境及混合建图检查通过。
