# C++ 条件成员声明

日期：2026-10-26。证据类型：独立机制检查与默认建图检查。所属范围：W1/W2，G02/G03/G04 继续按完整账本验收。

原成员提取器只读取类体的直接子节点，会漏掉 `#ifdef` 内的字段。现在[成员声明提取器](../../adapters/cpp_member_declarations.py)遍历类体，按最近的所属类归档成员，保存条件分支中的每一处声明、声明类型、指针/引用形态、初始化表达式和源码位置。同一类中的同名声明组成一个逻辑成员，声明之间保留“任选其一”的关系。

条件路径包含 `#if/#ifdef/#ifndef/#elif/#else` 及嵌套分支的正反条件，遵循 [C++ 条件包含规则](https://eel.is/c++draft/cpp.cond)的分支结构。当前保存源码条件，未执行预处理器来选择构建配置。两分支的类型相同可共用该声明类型；类型或指针形态不同时，类型保持配置依赖并报告必需缺口。初始化表达式分别保存。条件 const bool 不再取第一条声明的值。

类定义身份和当前翻译单元的可见声明共同限定成员查找；不同翻译单元中的同名类保持分离。方法声明从数据成员中排除，函数指针成员保留。匿名类/union 的成员展开暂未实现，其位置进入必需缺口。

统一图现在包含所有已识别成员及物理声明，类经 `DECLARES_SOURCE_MEMBER` 到成员，再经 `HAS_MEMBER_DECLARATION` 到各声明。已有读写效果引用同一成员并保留声明条件，未发生读写的字段也能查询。默认建图、正反向路径和固定版本源码导航已有独立夹具验证。

13 项机制检查通过；完整回归运行 709 项，通过，1 项按平台跳过。最后的投影重构后，33 项成员/类型/数据检查和 6 项默认生产建图检查通过。运行实例、活动构建配置及监听端配对继续单独验证。

## Insight 全 C++ 输入控制

固定源码 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`，提取规则 `66f3a2fd3ff074f8d323cdd8c80da100b096846b`，Tree-sitter 0.25.2、language-pack 1.20.0。全部 1,323 个 C++/头文件重新提取并建立导航索引，得到 4,967 个逻辑成员、4,969 处物理声明。4,449 个成员带预处理条件，其中包含头文件的 include guard；该数量不表示平台分支数。

[24 项检查通过](evidence/cpp-member-control.json)：logPath 在 ParamsParser.h 的第 35/37 行保留 `""` 与 `"./"` 初始表达式，以及共同的头文件 guard、相反的 `_WIN32` 条件。四项正反路径及两项版本化源码查询通过。未选择构建配置，也未运行产品。

[首轮结果](evidence/cpp-member-control-first-score.json)保留 23/24 通过：评分参考遗漏头文件 guard。修正参考后对同一提取产物重新评分，未改提取结果。

本次全量提取另报 51 项 `member_declarator_not_expanded`。源码检查表明这些位置都是返回引用的方法声明，如 `static ParamsParser &Instance()` 和 `const ParamsOption &GetOption()`，属于成员目录的错误缺口分类，后续需在声明分类中修正。目标字段导航通过与这一错误分别记录，G02/G03/G04 保持未通过。其余解码器的 strlen 表达式缺口继续保留。

## 引用返回方法的声明分类修正

提取器 0.1.1 沿声明符向内检查函数声明，处理方法返回指针、左值引用及右值引用时的外层声明符。方法不再进入数据成员的未解析分支；函数指针、函数引用，以及返回指针的函数指针字段仍保留为数据成员。判断依据是语法结构，不匹配方法名。

新增独立反例和原成员/类型/数据机制共 34 项检查通过；完整回归运行 710 项，通过，1 项按平台跳过。全 C++ 控制复验待执行。原规则的 51 项错误记录保留在上述证据中。

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
