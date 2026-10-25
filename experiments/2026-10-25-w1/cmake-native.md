# CMake 原生构建产物接口实测

日期：2026-10-25。性质：W2 产物连接的组件预备实验；[62 项检查通过](evidence/cmake-native-probe.json)。使用未修改的 CMake `3.31.6`，尚未配置 Insight，也未生成生产图的进程对端连接。

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

Insight 的源码检查显示三段来源：CMake 定义后端产物，Python 构建脚本先统一输出目录再复制到发行目录，Rust 用路径片段拼接子进程程序。后续要连接这些来源，并核查平台和实例条件，才能形成进程到后端入口的关系。该检查属于源码阅读，尚非自动提取结果。

```text
python experiments/2026-10-25-w1/run_cmake_probe.py --cmake CMAKE --make MINGW_MAKE --cxx CXX --output NEW_OUTPUT
```

本实验采用 MinGW Makefiles 及已安装的 MinGW 编译器。输出必须是仓库外新目录，夹具由脚本独立创建；原始 Insight checkout 未修改。G02/G03 保持未通过。
