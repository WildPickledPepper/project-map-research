# Python 打包路径与文件操作

2026-10-25 开始接入，10-26 发布真实控制结果。基础适配已接入默认生产建图流程；规则 9806c76 的 [Insight 全部 Python 输入控制检查](evidence/python-path-control.json)34 项通过。它将 Python 导入、常量和路径计算连接到复制、移动和改名操作，为构建产物到发行目录的传播提供来源。下一步展开跨函数参数、目录枚举及过滤，再进行完整打包链和产物配对验收。

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

当前文件操作的 `mapping_status` 为 `requires_control_flow_options_and_destination_context`：已保留路径和操作事实，调用参数上下文、目录项、循环过滤、提前 continue/return、复制选项与目录状态由下一步传播处理。参数保持各函数自身身份，避免将不同调用者的参数合并。动态 realpath 与缺少原始拼写的 dirname 表达式保留缺项。

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
