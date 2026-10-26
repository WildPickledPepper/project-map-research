# 三项原生组件补齐

2026-10-26。沿用原 R0/R1 分母与验收要求，继续补齐头文件引用、C++ 别名和值流、Rust 数据流。新工具与原始数据存放 D 盘；SVF/RAPx 的 Linux 原生试验在研究仓库 CI 执行，输出下载到 D 盘。原始 Insight checkout 保持只读，历史资产关闭。

| 项目 | 当前结果 | 后置验收 |
|---|---|---|
| Clang 头文件语义 | 原生提取与逐头文件查询通过，提供方已接入 | 三项集成后统一快照复验 |
| SVF C++ 别名和值流 | 六项固定语义题全部通过；真实全程序分析超过 13 GiB 进程预算 | 保留原生输入与资源收据，真实全仓值流未完成 |
| RAPx + 编译器/SVF Rust 数据流 | RAPx 提供 MIR 与借用摘要；SVF 补字段值流，六项固定题通过 | 已接入五种 MIR 配置、四种 LLVM 配置；统一快照复核中 |

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

## C++：准入通过，全程序资源阻塞

复用 PySVF `1.0.0.50` 的 Andersen 与完整 SVFG。适配器只导出原生节点、边、调用位置、函数及上下文；[六项固定题](evidence/svf-cpp-six-cases.json)全部通过，包括此前 Joern 漏掉的 const-reference 别名，以及独立对象、先复制后修改的隔离负例。LLVM 原生优化后的同六项题也通过，预期保持不变。

真实源码按 CMake File API 的目标依赖收集第一方编译单元，全部所选单元生成 LLVM 输入。首次全程序求解在 900 秒上限退出；去除非行号调试信息后一次 runner 提前关闭。随后复用已有 bitcode，使用 LLVM 原生 O1 预处理和进程资源监控：8 GiB、13 GiB 两次预算均触发停止，后者实际观察到 `13,734,240 KiB` RSS，运行 `91.256` 秒。该分析没有生成完整真实后端值流图，不能计为 R1/G02 通过。已完成的源码编译、固定用例和失败记录分别保留。

Python 分发包的 points-to 方法未暴露，CLI 输出和 Python 图来自不同原生进程。其节点身份尚未独立校验，因此保留 CLI 原始结果，统一图不生成这部分 `SVF_POINTS_TO` 边。六项值流查询使用同一进程构造的原生 SVFG，不依赖跨进程编号配对。

## Rust：复用两种现成分析能力

RAPx 固定 `974eb8e7f91e186720daffdfdf1125c3daf6c8cb`，使用其要求的 `nightly-2026-07-21`。新增 Rust 代码是在现有分析完成后序列化 MIR 图、调用及 MFP 借用摘要，没有修改上游传递规则。[首次独立检查](evidence/rapx-independent-first.json)为 6/8：成员字段写入后读取、借用修改后读取两项漏边，原始预期保留。两项返回借用摘要通过。

字段值流改用 Rust 编译器输出 LLVM bitcode，再交给同一个 SVF 分析；[六项原始配置检查](evidence/rust-svf-six-cases.json)及[优化配置复验](evidence/rust-svf-optimized.json)均通过。包含跨函数传递、字段写读，以及独立对象、复制、忽略参数三种负例。独立 Rust 执行还核对 16 项值/指针身份断言。

真实源码已采集 HTTP、Linux 桌面 Release/Debug、Windows 桌面 Release/Debug 五种 RAPx 配置；SVF 已采集其中 HTTP、Linux Release、Windows Release/Debug 四种。Linux Debug 当前保留 RAPx 原生基本图及其字段能力限制，未据此宣称全配置字段数据流完整。[37 项逐文件查询](evidence/rust-native-query-checks.json)通过固定提交源码、搜索与正反查复核；它验证导入和查询，数据流精度由独立题另行检验。

发现并保留了三类配置失败：

1. `-Copt-level=0` 会影响默认 `debug_assertions`，曾把 Release 标签配到 Debug 模块；[首次分支对照](evidence/rust-cfg-first-failure.json)保留失败。现在先读取 Cargo 的原生 cfg，再显式保留该开关；同上下文的 RAPx/SVF 若选中冲突源码，导入拒绝。
2. Windows Release 的 O1 输入触发上游 `CallBase::getArgOperand` 断言；保持原生 Release cfg，改用 O0 后执行成功。
3. 优化后的独立库曾不生成四个可内联公共函数的 LLVM 本体，查询检查失败。启用编译器的 `-Clink-dead-code=yes` 后，六项题全部通过；没有改动 fixture 或预期。

项目图保留自有源码位置及相邻原生边界端口，范围外库的完整内部图留在原始捕获中。省略部分和位置未映射部分都有诊断，边界端口没有被推导为相互独立；全部静态关系保持候选精度，运行状态为未观察。

## 正式接入与统一发布

[导出归一化](../../adapters/native_value_flow.py)、[分组导入](../../scripts/collect_native_value_flow.py)及[提供方接入](../../adapters/native_provider_graph.py)绑定源码提交、模块与编译上下文，拒绝错版本、重复身份和配置冲突。Rust SVF 捕获不能掩盖 C++ 捕获缺失。原生采集入口为 `scripts/capture_cargo_value_flow.py`；全仓入口支持 `--value-flow-captures`。

统一图复用同产品提交、提取代码未变化的已有基础事实，追加上述原生捕获。4,042,589,813 字节的图首次发布校验遇到 `MemoryError`，旧成功快照保持完好。复用 [ijson](https://github.com/ICRAR/ijson) `3.4.0` 流式读取后，已通过现有 Workspace 接口发布；SQLite schema、校验及原子发布流程保持同源。大整数、浮点、重复 ID、缺失端点及文件变更均有对照检查。

[755 项 Python 回归](evidence/native-provider-regression.json)在该次记录的规则版本通过，含 2 项平台跳过；后续原生配置和流式读取修改另做定向检查及最终复验。没有把早期回归记录改为当前版本结果。

### 同一快照最终复核

[统一交付收据](evidence/native-unified-delivery.json)绑定产品提交 `d4e8d1c`、事实生成规则 `80007ff` 和最终读取/检查规则 `1d91f0b`，保留基础事实复用的原快照及其版本。最终快照为 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688:full:7237870b4dbb4e228adc3901f1ad9a01`，包含全部 4,855 个跟踪文件、2,516 个选定输入。1,283,596 节点和 2,884,314 关系是存储规模，不作为通过门槛。

| 复核 | 结果 | 证据 |
|---|---|---|
| 129 个组件的归属与事实账 | 6 项账本检查通过；无基础事实、未正常解析的自有程序源码均为 0 | [组件账本](evidence/native-unified-module-audit.json) |
| 独立源码与查询 | 129 组件的 450 项代表性检查通过 | [逐项结果](evidence/native-unified-source-contracts.json) |
| 头文件在统一快照中的导航 | 37/37 通过 | [头文件检查](evidence/native-unified-headers.json) |
| Rust 原生事实在统一快照中的导航 | 37 项通过 | [原生查询](evidence/native-unified-rust.json) |
| 原有全仓集成约束 | 11 项通过 | [集成结果](evidence/native-unified-integration.json) |
| 缺口、版本与精度保护 | 5 项通过；C++ 原生值流缺失仍可见，未验证的跨进程 points-to 边为 0 | [保护检查](evidence/native-unified-guards.json) |
| 最终 Python 回归 | 执行 762 项，结果通过，含 2 项平台跳过 | [回归及版本](evidence/native-unified-delivery.json) |

8 个无跨组件出边、5 个无入边的审查标记继续属于 R2；450 项代表性声明检查没有被提升为全模块数据语义召回证明。[C++ 原生资源记录](evidence/svf-real-resource.json)保存 411 个编译单元零编译失败、固定题通过及全程序停止的不同结果。后续在能承载该分析的 Linux 环境复用已有 bitcode，实际所需完整峰值尚未测出；本轮停止继续调大预算重试。

当前严格 R0/R1 总状态仍保持 partial；C++ 全程序值流及上述明确配置缺口继续阻止整体通过。R2、历史资产及 skill 整理均未启动。
