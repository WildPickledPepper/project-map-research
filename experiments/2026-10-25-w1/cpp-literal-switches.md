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
