# R2 A：启动与部署边界

日期：2026-10-27。当前正在执行[计划 4.3](../../plans/semantic-impact-execution-plan.md)的 A 批；本页记录已验证增量，继续处理全家族覆盖与其余必需项。

## 原生进程事实接入

[生产适配器](../../adapters/native_process_sites.py)消费 CBM 0.12.1 已有 `SPAWNS` 关系，并在原生提供方导入后执行。它用源码路径、行和已绑定的库 API，关联 Python/Rust 边界或唯一 Shell 调用。一个源码行存在多个不同调用时保留歧义；程序名不参与跨程序身份匹配。

仓内目标直接沿用 CBM 已解析的原生节点，形成可双向查询的 `HAS_NATIVE_PROCESS_EVIDENCE → MAY_EXECUTE_SOURCE_MODULE`。所有关系保持候选精度、来源与运行条件。Rust `Command::new` 单独标记为命令构造，没有计作实际启动。

CBM 的无源码 `Process` 节点可能由多个启动位置共享，只能作为程序描述。新投影为每个原生位置生成独立节点，将描述 ID 保存在证据字段，不添加将这些位置当作同一运行实例的关系。原生关系仍原样保留；既有原生描述节点查询不能据此证明同一进程。

实测源码 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`，输入为现有统一索引中 CBM 0.12.1 及已提取的 Python/Rust/Shell 事实；未重新运行语言引擎。结果见[脱敏收据](process-bridge-evidence.json)：

| 项目 | 实测 |
|---|---|
| 原生候选处理 | 52/52；其中 4 个命令构造位置 |
| 唯一主图调用位置关联 | 40；其余 12 没有适用 API 锚点 |
| 仓内目标 | 3：两个容器入口及一个 Shell 脚本目标 |
| 未解析目标 | 33 个动态命令，16 个外部或未绑定程序 |
| 查询与处理检查 | 6/6，包括三条仓内目标正反查、Shell 调用到目标正反查和身份隔离 |
| 选择性索引 | 555 节点、147 边；最终执行 5.797 秒，未测内存峰值 |

调用锚点和目标状态是两个维度，不能相加作为独立边界覆盖率。52 个原生候选也不是全量启动信号分母。默认全项目快照尚未重建，G03/G04 保持未通过。

独立检查包括两个布局、同一行同 API 多调用、同名异目录排除、动态程序共享描述隔离、构造与启动区分、错版本与重复原生身份拒绝，以及生产建图中的 Shell→脚本查询。首轮夹具缺少原生边 evidence 字段已修正；回放首次读入全部语言 call_site 导致读取超时，改为按发现清单只读取 Shell 路径；处理数断言因可变列表别名失败，改为保留输入计数。原始失败目录在 Git 外保留，最终收据来自修正后的实际执行。

```text
python -m unittest tests.test_native_process_sites tests.test_native_provider_graph tests.test_project_snapshot.FullSnapshotTests.test_native_shell_container_facts_enter_the_production_workspace -v
python experiments/2026-10-27-r2-startup/run_process_bridge.py --index EXISTING_NAVIGATION.sqlite --revision d4e8d1cf9f90208bcbe5371c127088f6fd66c688 --output NEW_OUTPUT
```

下一项：对照全量启动/终止/WebView/容器/构建信号，区分已有两端、提供方未提取、身份未解析及源码缺失；沿用全项目分母推进，继续复用原生事实。

## 全家族信号处理账

[信号核查器](audit_signals.py)将 W0 冻结的启动、终止和 WebView 三类共 640 个信号逐项对照既有语义事实，见[完整处理账](signal-audit-evidence.json)。全部原始信号保留；行号或调用范围重叠只表示观察到相关事实，不升级为调用身份和对端验收。

| 家族 | 信号 | 观察到相应语义边界 | 仅观察到非进程 API | 尚无相应语义边界观察 |
|---|---:|---:|---:|---:|
| 启动 | 65 | 61 | 0 | 4 |
| 终止/等待 | 563 | 7 | 265 | 291 |
| WebView | 12 | 8 | 0 | 4 |

W0 的终止/等待正则也匹配 `.join()`；265 个位置的既有 Jedi 外部 API 事实只指向 `os.path.join` 等路径/字符串 API。它们仍留在处理账，状态不能用来证明同一源码行没有其它边界。另有线程等待、字符串/数组拼接及尚未解析位置，继续按实际机制核查。

启动的四个无边界观察位置分别是 Shell 内嵌 Python 的两个 `check_output`，以及 Rust 两个位置；后两者的编译/测试条件还需配对。WebView 四个位置均为导入语句，仍保留原始词法信号。多行 Rust 链式调用按既有调用范围对照，避免把表达式起始行和方法所在行不同直接判作漏提取。

CBM 另发现 11 个不在这三类词法信号位置中的候选，包括两个容器入口、Shell→脚本和 C++/JS 启动 API。它们另列进入发现账，不能把 W0 640 个信号当作全部实际边界。构建产物、资源加载和发行布局继续沿用原事实及独立参考核查。

实际核查耗时 0.171 秒；640 个 ID 无重复、无遗漏，四个独立源码位置的状态核对通过。该账展示缺口分布，G03/G04 仍未通过；继续跨家族连接和剩余必需项。

```text
python experiments/2026-10-27-r2-startup/audit_signals.py --inventory FROZEN_BOUNDARY_INVENTORY.json --index EXISTING_NAVIGATION.sqlite --process-replay PROCESS_BRIDGE_OUTPUT --output NEW_OUTPUT
```

## 多配置构建与可搬迁捕获

原 CMake 导入按项目/Release 名称只允许一个捕获，不能同时保留 Windows 与 Linux 的 Release 图。现有 [CMake 提供方](../../adapters/cmake_project.py)增加可选捕获 `context_key`：每个变体独立配置/目标/产物身份；无标签旧配置继续复用原入口，同项目同配置的重复未标识输入拒绝导入。捕获的原生系统、路径风格、编译配置继续来自 CMake File API，不根据标签推断。

已搬迁或从 CI 下载的捕获通过原 `command.json` 记录取得源/构建根，调用现有 File API 的 recorded-root 校验；无需复制原构建目录到原机路径，也无需重新配置产品。收据分别记录原生根与本次读取位置。原生回复、源码提交和所选项目不符仍拒绝。

真实控制同时读取原 Windows Release 与本次成功的 Linux Release 原生回复，复用既有 C++ main 声明，形成 2 个配置、66 个目标、1,108 个构建输入、17 个产物，两个目标→C++ 入口正反查与两项身份/输入核查全部通过，耗时 2.578 秒，见[收据](build-context-evidence.json)及[复现器](replay_build_contexts.py)。这次只重放构建事实，没有重新编译/运行产品，也未更新默认全图。

独立原生检查覆盖两个配置变体的不同输出、删除变体无残留、重复未标识上下文拒绝和搬迁后入口仍可查；现有 File API 的同名异目录、配置隔离、旧回复拒绝、系统来源及源码归属检查继续通过。首轮新增断言误将 Windows PDB 辅助产物计作主要可执行文件，按原生 `artifact_role=primary` 修正统计；独立期待的两个主要输出保持。

Cargo 的其它构建主机上下文、WebView 资源闭环和全部启动对端继续推进。Linux 原生构建可复用与 Infer 语义捕获失败分别记录，后者见[实际结果](../2026-10-26-infer-summary/README.md)。
