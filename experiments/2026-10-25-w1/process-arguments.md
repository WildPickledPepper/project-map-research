# 启动参数与所选后端的 argv 解码

日期：2026-10-26。证据类型：独立机制与默认生产建图检查。W2 继续连接进程、参数准备、解码、选项及监听端。

[参数配对器](../../adapters/process_argument_bindings.py)读取已有 Command 身份、参数模板、部署程序、CMake 目标/入口和 C++ argv 来源。只有同一 Command、Rust 调用帧和分析上下文下的启动词，才能进入该部署目标的解码查询。它沿同一 CMake 配置的编译输入及带代码链接依据的依赖核对入口、调用和解析函数归属；头文件定义通过源码 include 可见性关联到编译单元。

CMake File API 的 dependency 同时包含构建前置和链接依赖，见官方 [codemodel target 接口](https://cmake.org/cmake/help/v3.31/manual/cmake-file-api.7.html#codemodel-version-2-target-object)。配对器核对创建依赖的内层回溯命令，识别 target_link_libraries、target_sources 等代码关系；单纯 add_dependencies、另一可执行程序及不同配置不提供当前解码器的代码归属。独立夹具同时验证了这些负例。

```text
启动参数模板
  → BIND_PROCESS_ARGUMENT → process_argument_binding
  → MATCHES_ARGV_DECODER_CANDIDATE → cpp_argv_decoder_binding
  → BINDS_ARGV_DECODER_CANDIDATE → string_key_decoder
  → DECODED_VALUE_TARGET_CANDIDATE → 接收截取值的函数
```

匹配依据是模板中已知的字面前缀、相应字符串检索键，以及 argv 来源/准备步骤。参数名、文件名、程序名及键均来自已有事实。每条记录保留所选部署、提供目标、配置、编译单元归属、源码条件和有效负载缺口。多个适用解析器分别保存为条件候选；序列未展开、字面前缀未知、来源/准备不完整和目标范围缺失都有具体诊断。

`prepared_value_relation=argument_word_may_contribute_to_decoded_input` 表示启动词可能进入该解码输入。C++ 的条件拼接和取元素选择继续保留；`payload_equivalence=not_established` 将准备后值是否相等留给后续求值或运行验证。已知键而 payload 来源尚未展开时，接口候选保留，并同时记录必需缺口。运行身份仍为 not_observed。

默认 builder 已接入该阶段。15 项机制检查覆盖 Command/调用/配置隔离、另一入口、同名键、原生链接范围、头文件归属、构建前置依赖、未知准备、部分 payload、歧义、重复事实和预算；生产夹具从普通 Cargo、CMake、Python 打包和跨语言源码恢复参数到 C++ 解码函数的正反向路径。首轮修正了测试事实缺少 status 字段，原始失败日志保留在仓库外。690 项完整回归通过，1 项按平台跳过。

```text
python -m unittest tests.test_process_argument_bindings tests.test_project_snapshot.FullSnapshotTests.test_default_rust_current_exe_chain_reaches_cmake_backend_entry -v
python -m unittest discover -s tests -v
```

固定源码控制复用已记录版本的启动、Rust 参数和 C++ argv 事实，重新执行当前配对与索引；复用阶段及其版本单独保存。

```text
python experiments/2026-10-25-w1/run_process_argument_control.py --source SOURCE --revision REVISION --startup-trial STARTUP_TRIAL --rust-argument-trial RUST_TRIAL --cpp-argv-trial CPP_TRIAL --output NEW_OUTSIDE_DIRECTORY
python experiments/2026-10-25-w1/score_process_argument_control.py --trial NEW_OUTSIDE_DIRECTORY --output NEW_SCORE.json
```

下一项核对具体启动词的准备分支、数字转换及选项/监听对象身份，并继续其余冻结边界和模式。G03/G04 按完整账本验收。
