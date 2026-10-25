# C++ argv 到参数解码

日期：2026-10-26。证据类型：独立机制及默认 builder 检查。W2 继续连接程序身份、参数准备、解码和监听。

[argv 来源提取器](../../adapters/cpp_argv_origins.py)复用现有 C++ 作用域、类型、常量和目标函数候选，按调用位置展开字符串解码输入。它从全局 main 的窄字符 argv 声明出发，追踪数组选择、std::string 构造、std::vector<string> 的 push_back/emplace_back、at/下标选择、函数参数、局部别名和唯一返回值。变量、函数、类及模块名均来自源码。标准入口、数组和容器含义分别参考 C++ 草案的 [main](https://eel.is/c++draft/basic.start.main)、[字符串构造](https://eel.is/c++draft/string.cons)及 [vector 修改操作](https://eel.is/c++draft/vector.modifiers)。

字符串 append 的原始输入、追加操作数、分支和循环条件分别保留；通过函数传递的数组和参数保留原调用帧。集合构建和取元素时的索引是带源码位置的表达式，运行时选择仍待记录。`origin_complete` 表示当前来源和准备操作数已展开；拼接后的具体参数值、所选循环迭代及运行端口由相应求值或运行证据确定。

```text
C++ main → CPP_ENTRY_ARGV → cpp_entry_argv
  → ARGV_FLOW_CANDIDATE → cpp_argv_decoder_binding
  → BINDS_ARGV_DECODER_CANDIDATE → string_key_decoder
  → DECODED_VALUE_TARGET_CANDIDATE → 接收截取值的函数
```

默认 builder 已接入该图，支持上述整段路径及反查。每条绑定保留入口、调用帧、argv/数组选择来源、准备步骤和具体缺口。选中构建目标、源调用/循环可达、数组元素存在及未展开别名效果均有独立条件；`runtime_execution=not_observed`。

源参数或集合有未知修改、非 argv 元素、循环携带的写入、介入调用或预算限制时，绑定保留必需缺口。源文件中已可见的同签名定义优先于不可见的另一文件实现；只有头文件声明、缺少本单元可见定义时，其他实现继续保留为链接候选。不同 main、同一函数的不同调用和局部同名变量分别隔离。

13 项 argv 机制、两项可见定义隔离及六项默认 builder 检查覆盖直接 argv、数组/循环、别名、拼接、同名负例、两种布局和未知修改。生产夹具使用另一参数名/业务键，验证 main→解码→接收函数的正反向索引查询。首轮补齐了只读 substr 的分类，并由跨文件同名负例修正可见定义选择；原始日志保留在仓库外。

完整回归运行 675 项，通过，1 项按平台跳过。源码控制与原生语义事实仍按各自提交保存，下一节的控制命令用于固定规则后的真实输入复验。

```text
python -m unittest tests.test_cpp_argv_origins tests.test_cpp_data tests.test_project_snapshot -v
python -m unittest discover -s tests -v
```

真实源码控制重新发现全部 C++/头文件，提取与答案核对分开执行：

```text
python experiments/2026-10-25-w1/run_cpp_string_decoder_control.py --argv-origins --source SOURCE --revision REVISION --parser-cache CACHE --output NEW_OUTSIDE_DIRECTORY
python experiments/2026-10-25-w1/score_cpp_argv_control.py --trial NEW_OUTSIDE_DIRECTORY --output NEW_SCORE.json
```

下一项沿已确认的构建/部署程序身份连接 Rust 启动词与 C++ argv 解码，继续核对准备分支对该词的影响；随后展开数字转换、选项对象/字段与监听接收对象。来源关系与数值相等分别验证。

## Insight 全 C++ 输入控制

规则 edd48dc 在源码 d4e8d1c 的 1,323 个 C++/头文件输入上通过 [63 项后置检查](evidence/cpp-argv-control.json)。提取重新执行，新增索引含 93,647 节点、115,599 边。七个解码操作各恢复一条来源绑定，均来自 `server/src/entry/server/bin/main.cpp` 的 main/argv，argv 来源阶段没有必需缺口。

工具恢复的来源路径为：

```text
main 的 argv[i]
  → std::string → args.emplace_back
  → ParamsParser::Parse(args) → args.at(i)
  → 条件性的 data.append("=").append(args.at(++i))
  → ParamsParser::ParseField(data) → 对应键的截取与解析函数
```

每条绑定保留两个源调用帧、argv 装入数组和取数组元素的两层选择，以及两次 append 的操作数和分支条件。原始词和可能追加的下一词分别保留来源；实际 i 与 ++i 的运行数值仍是选择表达式。main→端口解码节点为 3 条边，main→ParseWsPort 为 4 条边，四个正反查及四处同版本源码导航通过。

原有另一模块的一项 strlen 长度缺口保留。该控制确认 argv 来源与准备操作，后续用构建/部署身份把 Rust 的具体启动词接到相应绑定，并核对准备分支和数值转换。运行 PID、端口和监听实例在相应场景中采集；原始 checkout 未修改，未重新核验文件哈希，G03 保持未通过。
