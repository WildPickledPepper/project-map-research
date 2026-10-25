# C++ 嵌套接收对象的成员类型

日期：2026-10-26。证据类型：独立机制与源码探针。W2 继续从参数解码展开到选项字段及监听对象。

`options.endpoint = value` 的成员写入原先使用基础词法推断接收对象的类型，`options` 是类成员时会漏掉最终 endpoint 字段。最小反例只有 Options、Reader 和一次嵌套赋值；修正前提取到外层 options 的读取，未提取 endpoint 的写入。

[类型修正](../../adapters/cpp_data.py)复用已有 ValueTypes 推断接收对象，再按其声明的类查找成员。多层嵌套、继承、getter 返回的对象，以及 -> 上的标准智能指针解引用使用同一路径。局部遮蔽和不同类的同名字段按声明类型区分，未知接收对象保持未解析状态。

六项独立机制检查及既有数据/字段回归通过，35 项相关检查全部通过。实例身份继续保留为 unresolved，后续沿调用、getter 返回的引用和子对象路径绑定。该修正提供选项赋值的成员类型和写入位置。

完整回归运行 696 项，通过，1 项按平台跳过。

对 ParamsParser.cpp/.h 的两文件开发探针已识别 `option.wsPort = port`、`option.strictMode = false` 及 host/logSize/logLevel/eventDir/scanPort 等字段写入。该探针用于检查本机制，固定版本的全项目构图和实例配对继续独立验证。探针还暴露 logPath 在条件编译的成员声明中，后续需保留其声明及适用条件。

```text
python -m unittest tests.test_cpp_nested_members tests.test_cpp_data tests.test_p7_origins tests.test_cpp_field_flow -v
python -m unittest discover -s tests -v
```
