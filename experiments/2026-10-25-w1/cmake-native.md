# CMake 原生构建产物接口实测

日期：2026-10-25。[独立夹具 62 项](evidence/cmake-native-probe.json)及 [Insight 实际配置 24 项](evidence/cmake-native-repository.json)检查通过。使用未修改的 CMake `3.31.6`，已实现生产快照接入；真实快照的首次遗漏与修正见下文，进程对端配对继续实施。

## 已执行的检查

独立夹具采用两种目录布局及目标名称，每种分别配置功能开关关闭和开启的 Release 构建。只执行配置与生成及其编译器探测，没有编译或运行产品。原生 File API 返回 codemodel、cache、cmakeFiles 和 toolchains；原始回复和日志保存在仓库外。

| 检查 | 实测结果 |
|---|---|
| 同名输出 | 两个可执行目标均输出 worker，分属 service 与 decoy 目录；原生产物路径和目标 ID 分离 |
| 异名连接 | 目标名 launch_unit/backend_alpha 与产物名不同，仍可关联到各自 startup.cpp |
| 目标依赖 | 可执行目标依赖静态库，依赖使用原生 target ID；无关可执行目标未进入该依赖 |
| 配置选择 | 开关开启时才包含 extra.cpp 与 EXTRA_ENABLED=1；缓存保留选项和 Release 配置 |
| 源码依据 | 目标和源文件保留声明回溯，含 add_executable 及包装函数 register_program 的文件/行号 |
| 安装位置 | 原生 install destination 为 package/bin，可作为另一类产物放置依据 |
| 失败控制 | 缺少必需依赖时配置失败，没有成功 File API index；不得把失败解析为没有目标 |

原生接口的结构依据见 [CMake File API 3.31 官方文档](https://cmake.org/cmake/help/v3.31/manual/cmake-file-api.7.html)。本实验只验证该版本在夹具上的实际输出；目标 ID 按不透明身份使用，不解析其字符串格式。

## 复用决定与下一步

优先导入 File API 的目标、产物、源文件、配置和回溯，无需自行解释完整 CMake 语言。配置收据必须绑定源码、工具和参数；未配置成功的仓库保留具体依赖缺口。

Insight 的源码检查显示三段来源：CMake 定义后端产物，Python 构建脚本先统一输出目录再复制到发行目录，Rust 用路径片段拼接子进程程序。后续要连接这些来源，并核查平台和实例条件，形成进程到后端入口的关系。Python/Rust 这部分仍为源码阅读，CMake 部分已有下述原生配置证据。

## Insight 真实源码配置

从固定提交 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688` 导出 server 完整子树，共 1,417 个跟踪文件。第一次未补依赖，原生 CMake 在 third_party/CMakeLists.txt:9 报缺 libuv，随后报告 uv 目标缺失，没有成功回复。该失败保留在独立 build 目录。

第二次在同一独立源码副本中准备真实依赖，再使用新 build 目录执行 Windows/Release/Ninja 配置。libuv `v1.44.2`、uSockets `v0.8.6`、uWebSockets `v20.48.0` 及 rapidjson 都从已有 Git 缓存的固定提交导出；SQLite 使用已有 `3.46.1` 源码缓存，按上游预处理脚本的目录放入四个实际源码/头文件。没有伪造依赖或替换 CMakeLists。

| 原生结果 | 实际内容 |
|---|---|
| 目标 | 1 个可执行、3 个共享库、1 个静态库；另有 28 个 CTest 工具目标 |
| 后端产物 | profiler_server → server/output/win_mingw64/bin/profiler_server.exe，另列调试符号产物 |
| 源码 | 后端目标包含 408 个源文件，含 server/src/entry/server/bin/main.cpp |
| 声明回溯 | server/src/entry/server/bin/CMakeLists.txt:13，add_executable |
| 依赖 | 原生 ID 连接 uv_a、sqlite、msinsight |
| 编译上下文 | C/CXX、Release、LIBUS_NO_SSL、LIBUS_USE_LIBUV、UWS_NO_ZLIB；DATABASE_VERSION 为配置时间生成值 |
| 可复用上下文 | File API 四类对象及 compile_commands.json 均实际生成 |

工具实际报告为 CMake 3.31.6、Ninja `1.11.1.git.kitware.jobserver-1`、MinGW g++ 11.5.0。Ninja 来自 Python 分发包 `1.11.1.4`，保留原生报告版本。上游构建命令传入的 CMAKE_POLICY_VERSION_MINIMUM=3.5 在当前 CMake 下报告未使用，其日志保留。

后置评分器单独保存目标/产物/入口的源码参考；配置器只接受仓库、版本、子树、工具与依赖路径，不含这些产品名称。24 项检查通过。只执行 CMake 配置/生成及编译器探测，产品编译和实际启动由后续构建/运行义务验收。原始源码、回复、编译命令和日志保存在仓库外。

## 统一事实适配

`adapters/cmake_file_api.py` 已实现原生回复归一化，8 项独立 CMake/Ninja 测试通过。配置、目标、产物、编译输入及库依赖进入统一节点/边格式；完整路径区分同名产物，主产物和调试符号等附属产物分别标记。编译宏、包含路径和声明回溯随编译单元保存。

源码声明只与原生目标实际列出的选中输入连接；全局 main 定义可形成入口候选，同文件命名空间下的同名函数不会混入。入口仍保留预处理和链接选择条件。生成/输入外源码及缺失上下文有具体诊断；经版本化外部依赖范围确认的第三方内部源码单独标注。

调用方必须提供固定源码版本和实际配置退出码。版本不匹配或配置失败时返回必需缺口，不读取旧成功回复作为本次结果。适配会拒绝错导出目录、回复越界和缺失依赖 ID。统一适配已接入下述生产流水线。

生产流水线已接入 `cmake_project`：按选中 CMakeLists.txt 的父子关系自动发现根目录，逐配置复制固定输入并执行原生配置，结果进入统一图、导航、刷新和版本记录。可选 build 配置提供工具链选项及固定依赖来源，不提供目标或入口答案；新增目标、改名和删除无需业务规则变更。配置缺失/失败保持必需诊断，disabled 也会保留未分析状态。

新增 7 项配置/项目检查及真实 Workspace 混合建图、正反向入口查询通过；完整 Windows 回归 450 项通过，1 项按平台跳过。随后调整构建路径的搜索表示并补显式 build 配置测试，相关适配、配置、快照及工具检查单独复跑。配置过程的写文件负例确认原分析输入与原始仓库保持不变。Insight 真实生产快照结果见后文。

## 首次生产快照的输入遗漏

规则 `868799c` 在 C++/CMake 控制范围生成可查询快照，实际输入 1,334 个；[后置评分未通过](evidence/cmake-production-first-failure.json)。原生配置报缺 server/third_party/CMakeLists.txt，构建目标事实为空，诊断仍保留。该快照的 ready 表示语言事实及索引已发布，构建边界验收仍失败。

原因是目录角色策略排除了两份跟踪的 CMake 清单。此前独立原生配置导出完整 server 子树，包含这两份清单，因此能够成功；初版混合 fixture 未覆盖嵌套 vendor 清单。新增不同布局的独立发现 fixture 和生产 Workspace fixture 均复现失败，原始日志保留。

发现规则 `/5` 将跟踪的 CMake 构建依赖纳入选中输入，并记录 inclusion_basis=tracked_cmake_build_dependency。目录角色继续保留 third_party，第三方源代码的选择策略不变；只有允许 build_tool 时适用，显式 exclude 仍生效。修正后发现、输入、模块账本及生产混合快照 37 项检查通过。Insight 默认选择数为 2,498，C++/CMake 控制选择数为 1,336，新增项正是这两份清单；真实快照复验结果见下节。

## 修正后的真实生产快照

[32 项后置检查通过](evidence/cmake-production.json)。源码仍为 d4e8d1cf9f90208bcbe5371c127088f6fd66c688，规则为 `07dcab66e14cdc5e94e4e7074320dbb7632388ee`，快照为 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688:full:af5130b88f5d476c885b98d6ffb4495e`。使用生产 Workspace.update 建图和查询；独立参考仅由后置评分器读取。

| 结果 | 已执行范围 |
|---|---|
| 控制输入 | 全部 1,323 个 C++/头文件及 13 份 CMake 清单；本次未纳入其他语言 |
| 快照 | 217,840 节点、343,093 边；其中新增原生构建/声明连接 599 节点、5,507 边 |
| 原生上下文 | 本机 Windows、Ninja、Release 配置成功；1 个 build_configuration、33 个目标 |
| 目标类型 | 1 个可执行、3 个共享库、1 个静态库、28 个 CTest 工具目标 |
| 后端输入 | profiler_server 的 408 个编译输入：396 个选中源码，12 个版本化依赖源码 |
| 产物与入口 | 完整 exe 路径、独立附属产物、CMake 声明位置及全局 main 定义分别可查 |
| 统一导航 | 目标→入口、目标→编译输入→声明、配置→产物，三类路径的正反向查询均通过；源码导航绑定原提交 |

原始仓库保持干净，未编译/启动产品，未创建运行记录。[Linux CI](https://github.com/WildPickledPepper/project-map-research/actions/runs/40199978875)也已通过当前生产规则的回归。

本次完成构建目标、产物和 C++ 入口这一段。Python 打包复制、Rust 路径值及平台/实例条件继续按[路径传播任务](path-values.md)展开，进程对端尚未配对；G02/G03 保持未通过。规则 5f8079d 的 2,496 输入多语言全仓记录保留原范围；当前规则的完整多语言重建在后续连接完成后再统一复验。

```text
python experiments/2026-10-25-w1/run_build_trial.py --source SOURCE --revision d4e8d1cf9f90208bcbe5371c127088f6fd66c688 --typescript TYPESCRIPT --analysis ANALYSIS.json --scope cmake_cpp_control --output NEW_TRIAL
python experiments/2026-10-25-w1/score_build_trial.py --trial NEW_TRIAL --output NEW_SCORE.json
```

首次测试有两处夹具/断言修正：原生宏定义附带声明回溯，不能按只有 define 键的字典比较；configure 时 file(WRITE) 创建的文件不会自动具有 GENERATED 属性，生成输入负例改为显式声明该属性。正式测试保留原生元数据。

```text
python experiments/2026-10-25-w1/run_cmake_probe.py --cmake CMAKE --make MINGW_MAKE --cxx CXX --output NEW_OUTPUT
python experiments/2026-10-25-w1/run_cmake_repository.py --help
python experiments/2026-10-25-w1/score_cmake_repository.py --trial PRODUCT_TRIAL --output NEW_SCORE.json
python experiments/2026-10-25-w1/check_cmake_evidence.py
```

独立夹具采用 MinGW Makefiles，真实源码配置采用上游使用的 Ninja 生成器。输出必须是仓库外新目录；原始 Insight checkout 未修改，未重新核验文件哈希。G02/G03 保持未通过。

## 目标系统与宿主文件系统

原生适配 `/0.2.0` 将已生成的 CMakeSystem.cmake 中的字面量系统记录并入 build_configuration 和 native_context：目标系统、声明的处理器、宿主系统/处理器、CMake 交叉编译状态，以及目标/宿主各自的路径风格。解析器只读取固定字段，不执行文件里的 CMake 语句。缺失、重复、非字面量字段和未知路径风格分别保留必需诊断。

Python 打包操作使用宿主文件系统，程序运行路径使用目标系统；两者在交叉编译时分别匹配。系统处理器字段保留 CMake 声明含义，编译器实际架构另需证据。该区别与 CMake 的 [SYSTEM_NAME](https://cmake.org/cmake/help/v3.31/variable/CMAKE_SYSTEM_NAME.html) 和 [SYSTEM_PROCESSOR](https://cmake.org/cmake/help/v3.31/variable/CMAKE_SYSTEM_PROCESSOR.html) 定义一致。

新增字段与现有原生配置、项目刷新和 Workspace 混合建图共 21 项检查通过。独立记录负例覆盖目标 Linux/宿主 Windows、未知系统、缺失/重复/动态字段和版本路径；实际 CMake/Ninja 配置验证系统字段与配置共同进入统一图。检查使用 CMake 3.31.6，产品编译/执行及后续产物传播另行验收。

原生回复重放还支持已发布快照的目录重定位：调用方从成功配置收据提供原构建根和原源码根，适配器核对 File API 中的根目录，再从当前保存位置读取回复及系统文件。两类记录根必须成对提供；缺少、错配或配置失败继续拒绝旧回复。默认原生配置流程直接使用当前根，无需重定位参数。

复制原生构建目录的独立检查先验证未绑定记录根时拒绝，再验证成对绑定后产物完整路径和系统字段保留。连同原生/项目及 Workspace 检查共 22 项通过。重复路径和声明回溯按上下文缓存计算，返回独立记录，减少同一编译组在大量源文件上的重复路径解析。

### Insight 原生系统记录重放

规则 45a9fdc 在原 d4e8d1c 的 C++/CMake 控制范围重放已成功的原生配置记录，[23 项检查通过](evidence/cmake-system-replay.json)。C++ 事实沿用 07dcab6，执行前核对语言/图组件的 Git 变更、解析器/Python 版本及 1,336 个输入选择；原生回复和系统文件由当前适配重读，源码连接重新计算，生成新索引。

目标和宿主均实际记录为 Windows、路径风格为 windows，CMake 交叉编译标志为 FALSE；声明处理器 AMD64 继续保留声明含义。系统字段可随原生配置、目标、完整产物路径及 C++ 入口一起查询。217,840 个节点、343,093 条关系保留，4 个正反向路径与同版本源码导航通过。

首次重读未绑定发布前的临时目录根，适配器拒绝了目录不匹配；原始失败保留。随后按原配置收据成对绑定目录根重放通过。驱动的字节输出解码修正和原日志也在仓库外保留。旧配置目录与原始仓库均未修改，未重新核验文件哈希。

本次未重新运行 C++ 提取、CMake 配置或产品编译/执行。生产复制边及进程对端继续按路径传播阶段验收，既有静态候选含义保持不变。

```text
python experiments/2026-10-25-w1/replay_cmake_system.py --workspace PREVIOUS_CPP_CMAKE_WORKSPACE --output NEW_OUTSIDE_DIRECTORY
python experiments/2026-10-25-w1/score_cmake_system.py --trial NEW_OUTSIDE_DIRECTORY --output NEW_SCORE_FILE
python experiments/2026-10-25-w1/check_cmake_evidence.py
```
