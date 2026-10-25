# C++ 字符串键到解析函数

日期：2026-10-26。证据类型：独立机制及默认生产建图检查。W2 继续从后端启动参数展开到解码、选项和监听端。

[解码提取器](../../adapters/cpp_string_decoders.py)复用现有 C++ Tree-sitter、类型候选、常量解析和目标函数分析，提取源码中的 `find(key)` → `!= npos` 分支 → `substr(position + key.length()/size())` → 目标函数参数。键名、输入字符串、分支位置、接收函数及参数序号均从源码取得。标准字符串操作语义参考 C++ 标准草案的 [find](https://eel.is/c++draft/string.find) 和 [substr](https://eel.is/c++draft/string.substr)。

提取按类型和局部绑定工作：接收对象及 npos 所属类型须能解析到 std::string/string_view；检索和截取使用同一个输入存储；偏移来自对应检索结果与同一个常量键的长度。顺序复用同一个 position 变量时，选择到达当前分支的局部赋值；条件赋值、输入/偏移修改和其他长度表达式保留具体缺口或未展开状态。类成员键保留默认初始化适用条件，已发现构造函数覆盖时退出该默认候选。同名自定义类型、被参数遮蔽的全局键、另一输入字符串或另一键的长度分别隔离。

```text
原解析函数 → DECLARES_STRING_DECODER → string_key_decoder
  ├─ STRING_DECODER_SEARCH / SLICE / FORWARD → 原调用位置
  └─ DECODED_VALUE_TARGET_CANDIDATE → 接收截取值的函数
```

默认 builder 在现有 C++ 数据提取之后接入该结果，可按 `string_key_decoder` 搜索，沿 `DECODED_VALUE_TARGET_CANDIDATE` 正查和反查。每个结果保留搜索/截取/转交源码、文字键、参数序号、类型与路径条件及目标候选；`argv_origin=not_bound`。接下来结合所选可执行文件、argv 来源和对象/字段传播，才能连接 Rust 参数到后端解析及监听实例。静态候选和实际运行身份分别记录。

11 项独立机制检查及六项完整 builder 检查通过。生产夹具使用另一项目布局和 `--socket-renamed=`，验证 CMake 入口、解码节点、目标函数正反查及索引保留。首轮修正了 qualified_identifier 的嵌套结构；遮蔽负例随后发现变量列表需要采用现有解析器排序后的最近绑定，构造覆盖负例补齐了内联构造函数的类作用域。原始失败日志保留在仓库外。

完整回归运行 660 项，通过，1 项按平台跳过；最后统一了搜索后变更的诊断名称，11 项专项检查再次通过。

```text
python -m unittest tests.test_cpp_string_decoders tests.test_project_snapshot -v
python -m unittest discover -s tests -v
```

固定源码的后置控制由通用 C++ 文件策略重新发现全部输入，再独立评分解析操作。规则执行要求干净的研究提交，图和原始日志输出到被分析仓库之外。

```text
python experiments/2026-10-25-w1/run_cpp_string_decoder_control.py --source SOURCE --revision REVISION --parser-cache CACHE --output NEW_OUTSIDE_DIRECTORY
python experiments/2026-10-25-w1/score_cpp_string_decoder_control.py --trial NEW_OUTSIDE_DIRECTORY --output NEW_SCORE.json
```

该步骤覆盖标准字符串检索/截取这一种解码机制；字面量相等开关、argv 集合与循环、数字转换、选项实例和监听接收对象沿后续规则及值/对象关系展开。
