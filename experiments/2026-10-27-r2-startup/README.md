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
