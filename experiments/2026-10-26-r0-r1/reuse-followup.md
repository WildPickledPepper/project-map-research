# 三项原生组件补齐

2026-10-26。沿用原 R0/R1 分母与验收要求，继续补齐头文件引用、C++ 别名和值流、Rust 数据流。新工具与原始数据存放 D 盘；SVF/RAPx 的 Linux 原生试验在研究仓库 CI 执行，输出下载到 D 盘。原始 Insight checkout 保持只读，历史资产关闭。

| 项目 | 当前结果 | 后置验收 |
|---|---|---|
| Clang 头文件语义 | 原生提取与逐头文件查询通过，提供方已接入 | 三项集成后统一快照复验 |
| SVF C++ 别名和值流 | 固定 PySVF 1.0.0.50，原生工具已运行，正在导出与准入 | 原六项语义题、不同布局与对象负例、真实源码、统一查询 |
| RAPx Rust 数据流 | 固定上游 `974eb8e`，nightly-2026-07-21 下已编译，正在接原生图导出 | 值传递、借用/复制/字段、跨函数与隔离负例、真实源码、统一查询 |

## 头文件引用恢复：原生提取与查询通过

复用 `libclang 18.1.1` 的 Python CIndex 接口，按原 CMake 编译数据库解析 `.cpp` 编译单元，直接读取 Clang 返回的声明、引用、目标、USR、类型和包含关系。编译单元选择消费现有 CBM 导入候选；覆盖结论由 Clang 的实际包含与诊断决定。适配代码负责接口调用、上下文选择与结果归一化。

[实测收据](evidence/libclang-header-recovery.json)绑定产品提交 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`、`server/Release` 配置。14 个编译单元全部零错误，覆盖 37 个原先带独立打开诊断的头文件；产出 44,728 个节点、65,930 条关系，耗时 321.407 秒。37 个头文件逐项通过统一索引的搜索、固定提交源码定位、引用目标正查和反查；14 项相关 Python 检查通过。

标准库等范围外目标保留为原生外部声明，使用 USR 和头文件身份，不导入其源码。原有独立头文件诊断保留，新状态绑定观察到的实际编译单元。不同布局、条件编译与配置身份分别验证。

`CollectionUtil.h` 的泛型函数体中仍有 35 个原生未返回目标的位置，收据逐项保留原生种类、类型及源码位置，查询继续显示未解析。不同编译配置和模板实例的语义保持独立；该结果的编译配置为上述 `server/Release`。

实现入口为 [libclang 提供方](../../adapters/libclang_provider.py)及[正式提供方接入](../../adapters/native_provider_graph.py)。`requirements-native.txt` 和安装包 `native` extra 增加固定 libclang 版本；`PROJECT_MAP_CLANG_BUILTIN_HEADERS` 指定匹配版本内置头文件。已配置的 `CC`/`CXX` 提供原生 target 和系统 include 路径。捕获导入仍验证源码版本、编译配置及输入范围。

实际调用及公开查询分别由以下脚本复现，输出指定为新目录：

```text
python experiments/2026-10-26-r0-r1/run_header_recovery.py --repository INSIGHT --revision COMMIT --cmake-capture CMAKE_CAPTURE --clang-capture CLANGD_CAPTURE --baseline-workspace OLD_WORKSPACE --output NEW_CAPTURE --builtin-headers CLANG18_HEADERS --query-driver CONFIGURED_CXX
python experiments/2026-10-26-r0-r1/verify_header_queries.py --capture NEW_CAPTURE --repository INSIGHT --output NEW_REVIEW
```

正式全仓建图支持 `--header-capture NEW_CAPTURE`。实时模式从编译诊断自动选择需恢复的非测试头文件；固定捕获模式复用同源码/配置结果。三项接入完成后发布一个最终统一快照，独立检查 R0/R1，当前保持未通过。

原生 API 与编译数据库的行为见 [Clang CIndex](https://clang.llvm.org/docs/LibClang.html)、[Clang 编译数据库](https://clang.llvm.org/docs/JSONCompilationDatabase.html)和 [clangd 头文件编译命令](https://clangd.llvm.org/design/compile-commands)。
