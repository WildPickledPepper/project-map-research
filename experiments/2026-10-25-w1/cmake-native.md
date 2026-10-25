# CMake 原生构建产物接口实测

日期：2026-10-25。性质：W2 产物连接的组件预备实验；[独立夹具 62 项](evidence/cmake-native-probe.json)及 [Insight 实际配置 24 项](evidence/cmake-native-repository.json)检查通过。使用未修改的 CMake `3.31.6`，后端构建目标和入口来源已取得原生结果，待导入生产图并连接进程对端。

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

调用方必须提供固定源码版本和实际配置退出码。版本不匹配或配置失败时返回必需缺口，不读取旧成功回复作为本次结果。适配会拒绝错导出目录、回复越界和缺失依赖 ID。该提交交付统一事实适配；生产快照的自动配置/合并与真实目标查询继续接入。

生产流水线已接入 `cmake_project`：按选中 CMakeLists.txt 的父子关系自动发现根目录，逐配置复制固定输入并执行原生配置，结果进入统一图、导航、刷新和版本记录。可选 build 配置提供工具链选项及固定依赖来源，不提供目标或入口答案；新增目标、改名和删除无需业务规则变更。配置缺失/失败保持必需诊断，disabled 也会保留未分析状态。

新增 7 项配置/项目检查及真实 Workspace 混合建图、正反向入口查询通过；完整 Windows 回归 450 项通过，1 项按平台跳过。随后调整构建路径的搜索表示并补显式 build 配置测试，相关适配、配置、快照及工具检查单独复跑。配置过程的写文件负例确认原分析输入与原始仓库保持不变。Insight 真实生产快照继续单独评分。

首次测试有两处夹具/断言修正：原生宏定义附带声明回溯，不能按只有 define 键的字典比较；configure 时 file(WRITE) 创建的文件不会自动具有 GENERATED 属性，生成输入负例改为显式声明该属性。正式测试保留原生元数据。

```text
python experiments/2026-10-25-w1/run_cmake_probe.py --cmake CMAKE --make MINGW_MAKE --cxx CXX --output NEW_OUTPUT
python experiments/2026-10-25-w1/run_cmake_repository.py --help
python experiments/2026-10-25-w1/score_cmake_repository.py --trial PRODUCT_TRIAL --output NEW_SCORE.json
python experiments/2026-10-25-w1/check_cmake_evidence.py
```

独立夹具采用 MinGW Makefiles，真实源码配置采用上游使用的 Ninja 生成器。输出必须是仓库外新目录；原始 Insight checkout 未修改，未重新核验文件哈希。G02/G03 保持未通过。
