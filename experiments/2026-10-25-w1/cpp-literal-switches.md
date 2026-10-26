# 字面开关、控制分支与成员写入

日期：2026-10-26。证据类型：独立机制与默认生产建图检查。W1/W2 的选项/监听链继续展开，整体门槛按全项目账本判定。

[字符串分支提取器](../../adapters/cpp_string_switches.py)从标准 string/string_view 类型、源码常量和比较表达式发现字面开关。它记录 `==` 的真分支、`!=` 的显式 else 分支，以及分支内的成员赋值和调用位置。比较两侧可交换；方法名、参数名、键和目录均从源码读取。空字符串比较也保留为源码分支。

[成员效果投影](../../adapters/cpp_member_effects.py)把已有成员读写事实接入统一图。函数到写入位置，再到成员声明形成可查询路径；读、接收对象使用分别保留。声明身份继续与对象实例分开，图不会由同名字段推定同一运行对象。

```text
Command 参数模板
  → 该程序的 argv 来源绑定
  → string_key_decoder（string_equality）
  → STRING_BRANCH_MEMBER_WRITE_CANDIDATE
  → source_member_effect
  → WRITES_SOURCE_MEMBER_CANDIDATE
  → source_member_storage
```

argv 提取器使用原始比较操作数的位置追踪来源。所选部署目标、入口、编译/链接范围、Command 和调用/配置身份沿用现有配对条件。字面开关配对要求整个源码参数词已知且相等；前缀或包含关系不能替代相等。未知后缀、已知非空的无条件拼接分别报告缺口。条件拼接保留，准备后的输入仍需满足相等分支；`payload_equivalence=not_established`，运行身份仍为 not_observed。

自定义同名字符串类型不进入标准字符串规则。常量无法选择、复合布尔条件、以及没有显式相等分支的后续控制流会报告具体必需缺口。闭包中的写入不算作定义闭包时已执行的写入。比较采用标准字符串相等语义也作为源码候选条件保留。

76 项相关机制检查和 6 项默认生产建图检查通过；完整回归运行 724 项，通过，1 项按平台跳过。跨语言生产夹具从普通 Cargo/CMake/Python 打包源码自动恢复 Rust 字面参数到 C++ 字段的正反查询，同时保留既有数值参数到解码函数的路径。真实 Insight 控制待执行。

```text
python -m unittest tests.test_cpp_string_switches tests.test_process_argument_bindings tests.test_cpp_argv_origins tests.test_cpp_data tests.test_cpp_nested_members tests.test_cpp_member_declarations -v
python -m unittest tests.test_project_snapshot -v
python -m unittest discover -s tests -v
python experiments/2026-10-25-w1/run_cpp_string_decoder_control.py --literal-switches --argv-origins --source SOURCE --revision REVISION --parser-cache CACHE --output CPP_OUTPUT
python experiments/2026-10-25-w1/score_literal_switch_control.py --trial CPP_OUTPUT --output CPP_SCORE.json
python experiments/2026-10-25-w1/run_process_argument_control.py --source SOURCE --revision REVISION --startup-trial STARTUP_OUTPUT --rust-argument-trial RUST_OUTPUT --cpp-argv-trial CPP_OUTPUT --output PROCESS_OUTPUT
python experiments/2026-10-25-w1/score_literal_switch_control.py --trial PROCESS_OUTPUT --output PROCESS_SCORE.json
```

固定源码控制将当前成员/分支/argv 投影与版本化启动和 Rust 参数事实合并。复用范围及版本分别记录；已存在的容器成员保留其导航类型，并补充当前声明信息。原始语言和构建事实的复用不记为重新执行默认全仓建图。

## 首轮真实源码提取失败与类型循环修正

[首轮记录](evidence/cpp-literal-switch-first-failure.json)：规则 39621d0 对固定源码的 1,323 个 C++ 输入执行控制时，在提取成员效果阶段发生 RecursionError，未完成图和导航索引。嵌套成员查找重新调用类型推断时重置了 depth/seen 上下文，使 auto 对象通过自身成员更新时的循环绕过原有边界。

独立的 `current = current.children[0]` 反例复现同样错误。修正将深度、访问过的绑定及模板绑定沿成员查找继续传递；遇到循环或深度边界时，保留 `cpp_value_type_unresolved` 的必需诊断及源码位置。48 项成员/类型/默认生产建图检查通过。全 C++ 开发复验已完成，识别 273 个字符串相等分支，八项 argv 来源完整，保留其它条件/调用与八处类型循环缺口；该探针运行于修正中的工作树，正式版本化控制继续执行。首轮失败不作为查询通过证据。

## Insight 全 C++ 正式控制

固定源码 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`，提取规则 `0ab74ef6c18e2b579b5129365f1fa85edbd8f531`。全部 1,323 个 C++/头文件重新提取，建立 145,487 个节点、234,300 条关系的控制索引。[30 项检查通过](evidence/cpp-literal-switch-control.json)，包括四项正反路径和三项版本化源码查询。

源码自动识别 ParamsParser.cpp:66 的 `data == symbolNotStrict`，经 :67 的 `option.strictMode=false` 连接到 ParamsParser.h:41 的成员声明。C++ main 经 argv 来源绑定到该成员为五条边；比较分支到成员为两条边。条件拼接的两步及两个调用帧保留，所有来源仍属于同一 main。成员实例身份未选择。

提取到 273 个相等分支、84 项受控成员写入；成员读写投影共 41,696 项。全图的八项 argv 来源均完整，另有 272 个未绑定到入口的字符串分支。必需缺口继续登记：162 项复合条件、82 项输入/键未选择、17 项无显式相等分支、10 项调用递归/预算、4 项成员所属定义未选择、8 项类型循环，以及原 strlen 截取偏移的一项缺口。它们的具体位置保留在图中；本次目标路径通过不改变全项目门槛。

[首轮后置评分](evidence/cpp-literal-switch-first-score.json)保留 28/30 通过：两项参考行号比固定源码晚一行。核对源码后将比较/赋值参考改为 66/67，重新评分同一图，未改提取产物。类型修正后的完整回归运行 725 项，通过，1 项按平台跳过。Rust 参数合并控制继续执行。
