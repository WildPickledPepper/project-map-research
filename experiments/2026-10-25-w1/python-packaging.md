# Python 打包路径与文件操作

2026-10-25 开始接入，10-26 发布真实控制结果。基础适配、逐调用参数传播及目录项模式已接入默认生产建图流程；规则 9806c76 的 [Insight 全部 Python 输入基础控制检查](evidence/python-path-control.json)34 项、de7bc1d 的[调用上下文复验](evidence/python-path-contexts.json)28 项、5dd130d 的[目录模式与路径对应检查](evidence/python-directory-patterns.json)31 项通过。继续应用过滤条件、复制契约及动态文件名，连接完整打包链和构建产物。

## 自动提取的内容

`python_path_values` 复用 AST/Jedi 事实和既有导入绑定。库 API 按导入身份识别，项目函数、模块和路径名称从输入提取。独立夹具验证导入别名、类常量、同名本地模块、自定义 Path、不同参数及多个调用位置。

| 事实 | 内容 |
|---|---|
| `python_file_operation` | shutil.copyfile/copy/copy2/copytree/move 与 os.rename/replace 的消费位置、API、源码分支、选项和目标语义 |
| `FILE_SOURCE` / `FILE_DESTINATION` | 文件操作到原始参数的正反向连接 |
| `path_value` | os.path.join/dirname、pathlib 构造/joinpath/除法/parent、参数及常量的路径候选 |
| `PATH_VALUE_CANDIDATE` / `PATH_COMPONENT_SOURCE` | 参数到路径结果，以及路径到原始字面量、绑定与操作来源 |
| 必需缺项 | 路径未知表达式、未展开星号参数和缺失参数，保留具体源码位置 |

copyfile 的目标是精确路径；copytree 的目标是目录根；copy/copy2 和 move 还取决于目标是否已存在及其类型。适配器保存这些区别，以及 ignore、dirs_exist_ok、follow_symlinks 等显式参数，映射阶段据此处理目录内成员和覆盖行为。

Python 路径保留 Windows 与 Posix 两种显式运行候选，分析机器的系统不替产品选择平台。`__file__` 相对于所选源码布局定位；realpath 保留“实际规范路径符合此源码布局”的采用条件。真实路径、符号链接和发行根目录由部署/运行上下文确认。

## 检查与当前范围

12 项路径/文件操作检查、既有 Python 基础/接口、共享路径模型及混合生产建图，共 48 项定向检查通过。覆盖别名与类常量、原始来源、路径风格、精确文件/目录语义、独立参数、分支条件、同名负例、未知表达式及星号参数。重叠 AST 起始位置按完整范围区分；os.path.dirname 对常量 join 结果保留尾部分隔符语义。

接入后的完整 Windows 回归运行 491 项，结果通过，1 项按平台跳过；原生 Rust、CMake、统一导航和既有接口检查包含在内。

首轮测试缺少统一图验证所需的 fixture snapshot，补齐测试元数据后通过。生产适配在评分前运行，夹具的预期名称仅留在测试侧。

9806c76 基础版本的文件操作 `mapping_status` 为 `requires_control_flow_options_and_destination_context`：已保留路径和操作事实，调用参数上下文、目录项、循环过滤、提前 continue/return、复制选项与目录状态留待传播。该基线将参数保留为各函数自身身份；后续调用上下文适配见下节。动态 realpath 与缺少原始拼写的 dirname 表达式继续保留缺项。

本项已接入生产构图及统一索引可接受的 schema。完整 Insight 打包链、当前规则全仓、安装更新和 CMake/Rust 进程配对分别继续验收；G02/G03 保持未通过。skill 统一整理安排在工具能力稳定后。

```text
python -m unittest tests.test_python_path_values tests.test_python_boundaries tests.test_python_facts tests.test_path_values tests.test_project_snapshot.FullSnapshotTests.test_python_sources_and_owned_interface_join_enter_the_production_snapshot -v
```

## Insight 真实源码控制

源码固定 d4e8d1c，规则固定 9806c76；Jedi 0.19.2、Parso 0.8.5、Python 3.11.9。119 个 Python 输入从提交导出，执行生产 Python 语义、接口和路径适配，再经 Workspace.attach 建统一索引。得到 76,544 个节点、107,728 条关系；其中 28 个文件操作，114 个按参数角色和路径风格分别保留的路径候选。

独立源码参考验证了以下路径，图中的源码根保留 realpath 的布局采用条件：

| 消费位置 | 源路径 | 目标路径 |
|---|---|---|
| build/build.py:344 | 源码根 / server/output/build/server | 函数参数 profiler_path / server |
| build/build.py:384 | 源码根 / platform/resources | 源码根 / platform/preview/resources |
| build/build.py:347 | 源码根 / build/plugin_install.py | 函数参数 profiler_path / plugin_install.py |

路径和来源的 8 个正反向查询、同版本源码导航、119 输入导航投影及路径/操作索引保留通过。评分同时确认两个资源目标来自同一辅助函数参数。34 项检查的参考只供独立评分，未传入提取器。原 checkout 状态未变，未重新核验文件哈希。

48 个候选为符号基址路径，66 个保留未解析项；这是本次输出的状态分布。build_server 的目录项复制、启动器文件名的字典/平台选择和辅助函数参数调用上下文继续展开。文件操作保存目标语义和显式选项，完整发行映射与运行采用仍待验收。

本次为全部 Python 输入的生产适配器/索引控制；当前规则默认多语言全仓刷新和独立安装另行验证。原始源码、完整图和日志保存在仓库外，公开证据记录版本、路径、检查与缺项。G02/G03 保持未通过。

```text
python experiments/2026-10-25-w1/run_python_path_control.py --source SOURCE --revision d4e8d1cf9f90208bcbe5371c127088f6fd66c688 --output NEW_OUTSIDE_DIRECTORY
python experiments/2026-10-25-w1/score_python_path_control.py --trial NEW_OUTSIDE_DIRECTORY --output NEW_SCORE_FILE
python experiments/2026-10-25-w1/check_path_evidence.py
```

## 目录项模式与完整路径匹配

当前路径适配按原生绑定身份识别 for 目标，并核对 os.listdir 的实际导入与调用参数。`path_iteration` 保存循环绑定、目录、调用上下文和路径风格；ITERATION_BINDING、ITERATION_SOURCE、ITERATION_DIRECTORY、ITERATION_CALL_CONTEXT 及 PATH_ITERATION_SOURCE 可展开来源。

目录项表示一个有来源约束的文件名变量，路径的 `resolution=pattern`。它保留固定片段、变量身份和枚举目录，`display_path` 供展示；完整具体路径在匹配时产生。嵌套目录、不同循环中的同名变量和外层调用分别保留。目录表达式按创建枚举时的位置计算，后来的赋值不回写该目录。

`path_patterns` 按完整路径匹配，检查根目录、固定片段、重复变量、路径风格和目录成员约束，再代入目标路径。copytree 可保留成员后缀。另一目录出现同名文件不会建立同一文件身份；缺少变量或未知根目录也不会按文件名补齐。调用方可显式保留尚待运行/输入验证的目录成员条件，结果仍带条件。

7 项 Python 循环与 6 项语言无关匹配检查加入既有路径检查，共 52 项定向检查通过。覆盖嵌套目录、两个相邻循环、创建时目录与后续改值、外层捕获、目录成员未验证、有限字面量项、同名自定义 listdir、循环外读取、隐式 cwd 和元组投影。字面量迭代保留项目索引，以供源/目标条件兼容性检查；动态非 listdir、未绑定 cwd 及未展开模式产生具体缺项。

接入后的完整 Windows 回归运行 520 项，结果通过，1 项按平台跳过；混合生产建图已验证模式、循环事实及既有语言关系共同保留。

本项建立目录成员的路径表示和匹配基础。源码过滤谓词已保留在图中；将谓词、复制选项和目标目录状态应用到构建产物传播继续单独实施。G02/G03 保持未通过。

### Insight 目录模式复验

规则 5dd130d 在同一 d4e8d1c、119 个 Python 输入上重算路径和索引，原生语义/接口事实按前述不变条件复用。`build/build.py:189` 自动产生两个路径模式：

```text
server/output/{tmp}/bin/{file}
  → server/output/build/server/{file}
```

两个变量保存独立循环身份及枚举目录；源和目标共用同一文件变量。6 个正反向查询可展开循环、目录和后缀谓词，同版本源码导航通过。目录基址已知的这次复制不再作为“未知文件名表达式”报告。

独立评分读取此前已发布的 CMake 原生产物记录，显式选择 Windows 路径解释，使用完整产物路径核对这些模式。匹配器计算出归一化文件位置，并用随后目录复制的完整前缀算得桌面与插件包路径：

```text
server/output/build/server/profiler_server.exe
platform/preview/resources/profiler/server/profiler_server.exe
plugins/jupyterlab/mindstudio_insight_jupyterlab/resources/profiler/server/profiler_server.exe
```

这项路径对应评价共 31 项通过，参考产物和预期仅供评分，未作为 Python 提取输入。改变文件名可复用相同规则，同名但目录不同、缺少目标变量及不相容根目录均拒绝补连。

当前评分验证路径对应；CMake 平台自动绑定、过滤谓词和复制契约的应用、生产产物传播边以及实际文件复制由下一步分别验证。原始图/源码保持在仓库外，公开收据单列这些状态。整体验收继续按 G01–G08 判定。

```text
python experiments/2026-10-25-w1/recheck_python_paths.py --source SOURCE --base-trial PREVIOUS_PYTHON_CONTROL --output NEW_OUTSIDE_DIRECTORY
python experiments/2026-10-25-w1/score_python_patterns.py --trial NEW_OUTSIDE_DIRECTORY --output NEW_SCORE_FILE
python experiments/2026-10-25-w1/check_path_evidence.py
```

## 2026-10-26：调用上下文、路径返回与读取位置

当前路径适配从原生 STATIC_CALL_TARGET/CANDIDATE、BINDS_ARGUMENT、HAS_PARAMETER 和 DEFAULT_VALUE 建立逐次调用帧。复制源和目标共同关联 `file_operation_context`，通过 FILE_OPERATION_CONTEXT、CONTEXT_PATH_VALUE 和 PATH_CALL_CONTEXT 查询，避免将不同调用位置的两端交叉配对。未发现静态调用者的函数标明 `root_basis=no_resolved_static_callers`，参数保留符号身份。

支持跨文件包装、位置/关键字参数、字面量默认参数、单一返回的源函数，以及直接嵌套函数的外层参数。库 API 按每次调用的实际参数和可见赋值重新确认。同一个本地声明作用域中的赋值按读取位置或调用位置选择；右值读取排除尚未完成的本次赋值。全局变量在两次调用之间改值时，两次结果分别保留。

每条路径保存前置 Return/Raise/Break/Continue 未被采用的条件，以及外围 if 分支。PATH_GUARD_SOURCE 指向实际谓词节点；这些是可查询的源码条件，实际执行仍由运行证据验证。已完成的前序循环中的 break 不作为后续语句的退出条件。

16 项上下文检查与基础 Python、接口、共享路径及混合生产建图共 64 项定向检查通过。检查覆盖跨文件/嵌套调用、两组配对、库变量改值、读取时机、字面量默认值、递归、星号参数、多返回缺项及调用预算。扩展检查首轮发现库变量重赋值使发现阶段只看到最后一次写入，已修正为候选发现后逐调用筛选；原始失败日志保留。

接入后的完整 Windows 回归运行 507 项，结果通过，1 项按平台跳过；包括原生 Rust/CMake、统一图和已有接口检查。

调用深度上限为 12，调用上下文上限为 32，剩余部分产生必需缺项。非字面量默认值的定义时刻、多返回函数的控制选择、目录枚举、复杂对象/别名写入以及异常/上下文管理器的控制效果继续展开。当前文件映射状态仍要求控制条件、复制选项和目标目录上下文；G02/G03 保持未通过。

### Insight 调用上下文复验

提取规则 de7bc1d，在相同 d4e8d1c 和 119 个 Python 输入上重新执行路径适配及统一索引。原生语言/接口事实复用自 9806c76：执行前核对三项语义/接口组件的 Git 变更、Jedi/Parso/Python 版本及输入配置，均未变。重新导出提交源码供 AST 和路径计算使用。本次没有重跑 Jedi 原生阶段，也没有重新核验文件哈希；这些口径在证据中单列。

后端 copytree 的相同源目录 `server/output/build/server` 已分别连接到：

| 调用上下文 | 目标（相对源码根） | 已解析调用位置数 |
|---|---|---|
| 桌面发行 | platform/preview/resources/profiler/server | 1 |
| JupyterLab 插件 | plugins/jupyterlab/mindstudio_insight_jupyterlab/resources/profiler/server | 2 |

源和目标按同一个 file_operation_context 配对。JupyterLab 目标还连到 BUILD_JUPYTERLAB 谓词及前序返回守卫。6 个正反向查询、同版本源码导航、复用条件和必需缺项检查共 28 项通过。当前快照有 76,626 个节点、110,680 条关系；该统计保留本次控制输入的含义。

目录项复制仍有源码定位的必需缺项，当前记录不含完整文件成员映射、CMake/Rust 产物配对、默认多语言全仓刷新或新版本安装验收。旧 9806c76 的参数基址记录原样保留，本记录证明后续已展开的调用关系。

```text
python experiments/2026-10-25-w1/recheck_python_paths.py --source SOURCE --base-trial PREVIOUS_PYTHON_CONTROL --output NEW_OUTSIDE_DIRECTORY
python experiments/2026-10-25-w1/score_python_contexts.py --trial NEW_OUTSIDE_DIRECTORY --output NEW_SCORE_FILE
python experiments/2026-10-25-w1/check_path_evidence.py
```
