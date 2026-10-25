# C++ 条件成员声明

日期：2026-10-26。证据类型：独立机制检查与默认建图检查。所属范围：W1/W2，G02/G03/G04 继续按完整账本验收。

原成员提取器只读取类体的直接子节点，会漏掉 `#ifdef` 内的字段。现在[成员声明提取器](../../adapters/cpp_member_declarations.py)遍历类体，按最近的所属类归档成员，保存条件分支中的每一处声明、声明类型、指针/引用形态、初始化表达式和源码位置。同一类中的同名声明组成一个逻辑成员，声明之间保留“任选其一”的关系。

条件路径包含 `#if/#ifdef/#ifndef/#elif/#else` 及嵌套分支的正反条件，遵循 [C++ 条件包含规则](https://eel.is/c++draft/cpp.cond)的分支结构。当前保存源码条件，未执行预处理器来选择构建配置。两分支的类型相同可共用该声明类型；类型或指针形态不同时，类型保持配置依赖并报告必需缺口。初始化表达式分别保存。条件 const bool 不再取第一条声明的值。

类定义身份和当前翻译单元的可见声明共同限定成员查找；不同翻译单元中的同名类保持分离。方法声明从数据成员中排除，函数指针成员保留。匿名类/union 的成员展开暂未实现，其位置进入必需缺口。

统一图现在包含所有已识别成员及物理声明，类经 `DECLARES_SOURCE_MEMBER` 到成员，再经 `HAS_MEMBER_DECLARATION` 到各声明。已有读写效果引用同一成员并保留声明条件，未发生读写的字段也能查询。默认建图、正反向路径和固定版本源码导航已有独立夹具验证。

13 项机制检查通过；完整回归运行 709 项，通过，1 项按平台跳过。最后的投影重构后，33 项成员/类型/数据检查和 6 项默认生产建图检查通过。真实 Insight 的全 C++ 输入控制待执行，运行实例、活动构建配置及监听端配对继续单独验证。

```text
python -m unittest tests.test_cpp_member_declarations tests.test_cpp_nested_members tests.test_cpp_data -v
python -m unittest tests.test_project_snapshot -v
python -m unittest discover -s tests -v
```

全 C++ 控制使用仓库外新目录，提取规则中没有业务成员名。评分器在提取结束后检查 Insight 的条件声明及导航：

```text
python experiments/2026-10-25-w1/run_cpp_string_decoder_control.py --member-declarations --source SOURCE --revision d4e8d1cf9f90208bcbe5371c127088f6fd66c688 --parser-cache CACHE --output OUTPUT
python experiments/2026-10-25-w1/score_cpp_member_control.py --trial OUTPUT --output SCORE.json
```
