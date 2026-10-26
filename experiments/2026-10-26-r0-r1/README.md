# R0 组件准入与 R1 全仓事实接入

2026-10-26。执行范围为[复用优先计划](../../plans/reuse-first-execution-plan.md)的 R0/R1。沿用已有证据，产品实现已按用户指令恢复；历史资产关闭，原始 Insight checkout 保持只读。新增工具、环境、缓存、临时文件及原始实验数据均放在 D 盘，Git 只保存实现与紧凑报告。

当前：[R0 准入决定](../../research/r0-provider-admission-2026-10-26.md)已固定；正式统一快照已发布，[129 组件事实账](module-facts.md)核对完成。[450 项声明/查询样本](evidence/source-contract-review.json)全部通过，剩余接入项与编译诊断继续处理，R1/G02 尚未通过。

## 已交付：CBM 隔离启动恢复

执行发布包 `codebase-memory-mcp 0.12.1`，使用此前的四文件 Python/Shell/Docker/Compose 夹具。[结果](evidence/cbm-startup.json)保存原生输出投影和逐项检查。二进制与先前试验相同，没有重算文件哈希。

启动原因与修正：

1. 原实验缓存路径的祖先目录允许不受信任的写入，CBM 在读取设置前拒绝启动。独立的私有缓存目录通过了这一步；未放宽 CBM 检查，也未修改现有公共目录权限。
2. 显式指定的运行协调父目录尚不存在，随后报 `secure CLI coordination could not be created (endpoint)`。CBM 的 Windows endpoint 在构造前要求父目录可规范化且已经存在。
3. 创建运行父目录后，原生索引成功：4 文件、33 节点、38 边，原生报告未索引/跳过/部分解析/不可用文件均为零。

对应源码审计为 CBM `10ab613` 的 `src/cli/runtime_settings.c::canonical_cache_path`、`src/daemon/bootstrap.c::bootstrap_runtime_parent_override` 与 `src/daemon/ipc.c::cbm_daemon_ipc_endpoint_new`。该源码提交与发布包 tag 提交不同；成功与具体关系由发布包实际输出确认，不以源码存在代替试验。

已观察到 Docker CMD → Python 模块、Python `Popen` → 进程、Docker/Compose 环境设置 → 对应读取函数。Shell 的 `dirname` 包装启动未恢复为 SPAWNS，保留该范围缺口。源码/发布包版本、此前失败及其它组件限制见[组件审计](../2026-10-26-reuse-audit/README.md)。

复现：缓存与运行父目录需位于符合上游目录权限要求的本地路径；Windows 上先创建用户私有父目录。实验输出与缓存/运行路径通过参数传入：

```text
python experiments/2026-10-26-reuse-audit/probe_cbm_boundaries.py --binary CBM_EXE --output NEW_OUTPUT --cache-dir PRIVATE_CACHE --runtime-dir PRIVATE_RUNTIME
```

本节为启动恢复时的收据。后续边界身份、C++ 语义与正式接入结果见下文；数据流替代失败由 R0 准入决定持续记录。

## 已交付：C++ 原生语义提供方

[clangd 提供方](../../adapters/clangd_provider.py)复用固定版本的 multilspy 客户端和 clangd 23.1.0，导入原生文档符号、AST 和定义跳转；初始化时开启 LSP 的层级文档符号能力。引用/接收对象的节点按原生范围区分，编译配置进入身份，未解析目标及预算残余保留。

[准入结果](evidence/clang-provider.json)记录两个通用布局、feature 开/关各 8 项检查：继承方法、模板调用、类型别名、活动/非活动预处理分支、两个命名空间同名字段、成员和接收对象的引用身份。首次运行因客户端未声明层级符号能力，导致适配器漏导入声明；该首轮失败保留，修正能力声明后通过。此前 getter 值/引用/指针及重载检查直接继承原审计，不重复执行。

真实 Insight 编译数据库包含 497 项原生编译记录。静态成员文件 `OperatorGroupConverter.cpp` 通过 clangd 原生检查；include-only 文件 `TextTraceDatabaseStatistics.cpp` 保留一项 `__rdtsc` 本征函数定义兼容诊断。两项结果不代表整个 C++ 范围通过；原生符号/定义身份也不等于运行实例或通用别名分析。

后续已定位并修正该兼容问题：query-driver 导入的 GCC builtin 头文件先于 clangd 自带头文件被找到。[编译数据库适配](../../adapters/compilation_database.py)使用 Windows 原生参数解析函数（其它平台使用标准 shlex），生成 arguments 数组并优先加入同版 clangd 自带的 builtin headers；不执行 command 字符串、不改产品源码或原始 CMake 数据库。[原生复验](evidence/clang-header-precedence.json)中该文件由 1 错误变为 0 错误，3 项互操作检查通过。

全仓收集器使用同版本、成功配置的 CMake 导出，多个独立语言服务分片处理；跨分片定义查找仍以全部选定 C++ 输入为范围。第一次全仓批次在确认共享头文件问题后停止，653 项已处理记录保留；修正后使用新输出目录重新执行，未将首轮部分结果当作全仓通过。

```text
python experiments/2026-10-26-r0-r1/probe_clang_provider.py --binary CLANGD --output NEW_OUTPUT
python experiments/2026-10-26-r0-r1/probe_clang_provider.py --binary CLANGD --output OTHER_OUTPUT --feature-mode 0 --layout alternate
```

## 已交付：CBM 原生事实导入与范围/身份控制

[提供方](../../adapters/cbm_provider.py)直接调用 CBM CLI，再用 SQLite 的只读连接与 backup API 保存一致的原生数据库，导入节点、关系、原生 ID/属性和覆盖记录。原生推断边保留 candidate；不把高 confidence 当作编译器精确身份或运行证据。[6 项互操作检查](../../tests/test_cbm_provider.py)验证同名身份、跨项目/范围过滤、无源资源、错误路径和原生解析/排除状态。

Insight 全部 4,855 个跟踪输入的首轮原生索引耗时约 509 秒，输出 41,987 节点、149,605 边；按输入范围过滤后导入 41,355 节点、143,954 边。[首轮覆盖记录](evidence/cbm-repository-first.json)保留 1,921 项文件排除、36 项部分解析、10 项不可用解析及 6 个目录排除；这些包含非产品源码，不能直接当作产品缺失数。原生忽略目录影响了第一方脚本，因此首轮不能作为完整事实覆盖通过。

适配采用 CBM 现成的 `.cbmignore` 否定规则，在提供方的独立输入副本中按已选择路径生成范围策略；不修改原始 checkout 或调用方的固定源码导出。[原生隔离检查](evidence/cbm-isolation.json)8 项通过：`build` 目录内脚本进入索引、Shell 启动连到脚本、两个容器同环境键分别连到自身程序、同名读者不合并，原输入不变。该策略须在真实仓库后续重建中核查，不以夹具通过代替全仓结果。

```text
python experiments/2026-10-26-r0-r1/probe_cbm_isolation.py --binary CBM_EXE --output NEW_OUTPUT --cache-dir PRIVATE_CACHE --runtime-dir PRIVATE_RUNTIME
python experiments/2026-10-26-r0-r1/run_cbm_repository.py --source INSIGHT --revision COMMIT --output NEW_OUTPUT --binary CBM_EXE --cache-dir PRIVATE_CACHE --runtime-dir PRIVATE_RUNTIME
```

## 已交付：TypeScript 声明与类型依赖

继续使用 TypeScript 5.9.3 Compiler API，补充其原生枚举/成员常量值、类型别名、ambient module、变量/属性/参数声明，以及三斜线类型/路径/lib 引用。命名空间与枚举成员的限定名保持区分；未加载的外部类型依赖明确记录为 `recorded_not_loaded`。

[真实提取结果](evidence/typescript-declarations.json)：986 个 TS/JS 文件生成 106,571 节点、106,103 边；W0 后置审查列出的 21 个 TypeScript 零基础事实文件全部具有声明或依赖记录。124 项既有与新增 TS/JS/前后端机制检查通过。此结果解决该审查队列，不以非零事实判定所有组件的语义正确性或 G02 通过。

## 已接入正式建图流程

新增 Shell、Dockerfile 和 YAML 输入自动发现；原生提供方默认从环境取得可执行文件，或通过 `build.providers.captures` 导入同源码提交、同编译上下文的固定结果。错误提交、错误编译上下文、范围外事实和重复身份均拒绝。Cpp include-only 文件复用现有 Tree-sitter include 记录生成依赖声明，目标尚未解析时保持 `recorded_not_resolved`。

正式 Workspace 夹具验证 Shell → 脚本启动关系、Docker/环境事实与 TS 枚举进入同一生产图，并成功发布快照。首轮发现 CBM 短暂子进程占用 staging 工作目录，导致 Windows 原子发布失败；将 CLI 工作目录设为持久缓存后复验通过。原生解析/排除状态保留；有编译诊断的 clangd 关系保持候选，不升级为精确关系。

CMake 同样复用已有 File API：`build.cmake.captures` 绑定固定源码与成功的原生配置，避免重复执行配置和生成时间相关宏。已在通用夹具和实际 Insight 497 项编译记录的捕获上复验；错误源码提交被拒绝。原 CMake 数据库、原始源码均未改动。

Python 的原生客户端依赖可通过 `requirements-native.txt` 或安装包的 `native` extra 安装；CBM/clangd 二进制与编译依赖由操作者提供。`PROJECT_MAP_CBM`、`CBM_CACHE_DIR`、`CBM_RUNTIME_DIR`、`PROJECT_MAP_CLANGD`、`CC`、`CXX` 指定原生组件及私有缓存。首次运行父目录需满足上游权限规则。skill 在 R5 最后整理。

```text
python experiments/2026-10-26-r0-r1/run_repository.py --source INSIGHT --revision COMMIT --output NEW_OUTPUT --typescript TYPESCRIPT_MODULE --cmake-capture CMAKE_CAPTURE --cbm-capture CBM_NATIVE_CAPTURE --clang-capture CLANG_CAPTURE
```

## 已交付：全仓原生提供方收据

[原生全范围结果](evidence/native-repository.json)绑定同一产品提交。CBM 按生产选择范围处理 2,516 个输入，耗时 11.921 秒；原生未索引和跳过数均为零，20 项部分解析；归一化后 2,464 项有提供方事实、32 项未产出、20 项部分解析。全部 7 个非测试 Shell 文件进入原生索引，模块存在与语言语义完整性仍分别检查。

clangd 处理 1,323 个 C++ 输入，957 项 parsed、366 项带诊断；其中 970 个非测试文件为 933 项 parsed、37 项带诊断。首个修正版全仓批次约 996 秒，随后仅对 12 个预算耗尽文件复验，耗时 31.36 秒；最终预算残余与提供方失败文件均为零。37 个非测试诊断文件及原始错误摘要逐项公开，主要涉及独立头文件缺少所需包含/宏/类型上下文；相关关系保持候选。完整 AST、数据库和日志留在 D 盘。

Python 完整回归执行 745 项，首轮 1 项失败、2 项平台跳过。失败为旧测试假定多提供方下 `main` 搜索只有一个节点；改为沿原有构建/解码关系选择明确 ID 后，17 项相关回归通过。Node 124 项检查通过。文件和测试数量作为辅助证据，R1 仍需发布统一快照、逐组件结果及遗漏处置。

## 已交付：统一快照与 129 组件事实账

[正式发布收据](evidence/repository-snapshot.json)来自默认 Workspace 建图流程，复用同提交 CBM、clangd 与 CMake 原生捕获；TS/JS、Python/Jedi、Rust/RA 及既有模型重新执行。全程约 1,868 秒，原始 Insight checkout 状态未改变。全部 4,855 个跟踪文件进入地图，2,516 个选定输入进入统一图与 SQLite 查询。

沿用 W0 独立范围，124 个运行/库组件与 5 个支持组件均有逐项记录；六项归属/计数/版本核对通过。此前 41 个无基础事实文件解决 40 个，docker 组件已取得 Shell 变量和容器事实；剩余安装脚本 `build/mindstudio_insight_gui_set_environment.sh` 只有原生文件/模块记录，其命令尚未产出基础事实。

新接入的编译器对 37 个非测试头文件报告诊断，分布于 12 个必需组件。旧 13 项未正常解析队列中，12 项当前状态为 parsed、1 项仍有编译诊断；新增编译诊断单列，不将原语法分析状态覆盖丢失。完整逐文件状态与组件关系种类见[机器账本](evidence/module-fact-audit.json)和[组件表](module-facts.md)。关系计数本身不判定正确连接，R2 的边界核查继续独立。

声明样本从固定源码选取后再读取事实索引，逐项检查原名/位置、统一搜索、源代码定位及邻接查询。代表性检查与全量语义召回分别记录，不能用样本数量替代 G02。

[源码契约/查询结果](evidence/source-contract-review.json)：129 个组件共 450 项代表性检查全部通过。参考直接从固定源码及标准 AST/语法树取得，在打开事实索引前保存；没有消费生产关系解析器或历史问题答案。两个直属源码只有文档字符串的 Python 初始化包按包标记核查，实际业务声明在子组件单独检查。本结果验证代表性声明/导入和导航保真，G02 的剩余事实与编译上下文审查继续保留。

## 已补充：Shell 原生命令语法

复用已安装的 Bash grammar，将原生 `command` 节点和参数语法映射为调用位置。CBM 继续提供其函数/变量/进程/容器关系；该补充只记录语法位置及未解析状态。[实际源码结果](evidence/shell-command-syntax.json)：8 个脚本 parsed，340 个命令位置；原安装脚本的 npm、apt-get、update-alternatives、python3 六处命令全部记录。注释与 heredoc 字面内容不会产生伪命令，动态命令保持未解析，未增加展开或进程求解器。11 项语法/提供方/正式 Workspace 接入检查通过，下一版全仓快照继续复验。
