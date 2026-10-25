# 使用项目地图工具

**当前 0.2.1 已有 TS/JS、C++、Python 的基础关系和部分接口适配，Rust 已接入生产构图并通过独立混合夹具，真实全仓复验继续执行。** 完整范围见[全项目计划](../plans/project-wide-completion-plan.md)及[整体验收矩阵](../plans/project-wide-acceptance.md)。安装包同时记录具体规则提交；可用 `status` 核对。

## 直接使用 CLI

需要 Git、Python 3.11 或更新版本、Node.js 22。安装已构建 wheel 的 `extract` 依赖，创建源码仓库之外的地图目录：

```text
python -m pip install "WHEEL[extract]"
project-map --workspace WORKSPACE init --source SOURCE
project-map --workspace WORKSPACE setup
project-map --workspace WORKSPACE doctor --probe-parser
project-map --workspace WORKSPACE build
project-map --workspace WORKSPACE query overview
```

`setup` 将固定版本 TypeScript 安装到地图目录；已有安装可在 `init` 时传入 `--typescript TYPESCRIPT_MODULE`。语法包缓存和 Windows 原生依赖可在 `init` 时指定 `--parser-cache CACHE`、`--dll-dir DLL`。使用指定提交时加 `--revision COMMIT`；默认跟随 HEAD，提交新代码后执行 `update`。

先搜索模块、函数或边界，再用节点 ID 展开，避免同名误选：

```text
project-map --workspace WORKSPACE query search --kind callable --text NAME
project-map --workspace WORKSPACE query search --kind code_module --text PATH
project-map --workspace WORKSPACE query search --kind python_boundary
project-map --workspace WORKSPACE query search --kind rust_boundary
project-map --workspace WORKSPACE query path --start NODE_ID --target TARGET_ID --depth 16
project-map --workspace WORKSPACE query impact --start NODE_ID --depth 8
project-map --workspace WORKSPACE query status --start NODE_ID
project-map --workspace WORKSPACE query detail --entity node --id NODE_ID
project-map --workspace WORKSPACE query source --start NODE_ID
```

`python_boundary` 保留监听、路由、连接和进程接口的 API、参数来源、应用归属及待匹配状态。`entries` / `providers` 当前展示已有协议适配结果；Python 边界通过 `search` / `detail` 查询。JS/TS 的模块导入使用 `module_reference`、`CONTAINS_IMPORT` 和 `IMPORTS_MODULE`；Python 参数与值来源使用 `CALL_ARGUMENT`、`BINDS_ARGUMENT`、`READS_BINDING`、`VALUE_SOURCE` 等边。可用 `--kinds TYPE1,TYPE2` 限定遍历关系。

Python 的 `python_file_operation` 表示经导入绑定确认的 shutil 复制/移动或 os 改名操作；FILE_SOURCE、FILE_DESTINATION 连接两端参数，PATH_VALUE_CANDIDATE、PATH_COMPONENT_SOURCE 展开路径及常量来源。文件精确目标、目录复制根、可能已存在的目标目录分别记录，复制选项保留原参数。每个候选标明 Windows/Posix 路径解释及源码条件。FILE_OPERATION_CONTEXT、CONTEXT_PATH_VALUE 将同一调用位置的源、目标配对；PATH_CALL_CONTEXT 和 PATH_GUARD_SOURCE 连接调用点与条件谓词。用 `search --kind file_operation_context` 找到上下文后展开，保留 `operation_context` 和路径风格筛选关联结果。目录枚举及完整映射状态见 [Python 打包适配](../experiments/2026-10-25-w1/python-packaging.md)。

`path_value.value.resolution=pattern` 表示含目录项变量的路径，`display_path` 用于展示；`segments` 中的变量带枚举目录和独立身份。PATH_ITERATION_SOURCE 可查到 `path_iteration`，再沿 ITERATION_DIRECTORY 查看目录来源。模式匹配按完整路径和目录成员约束进行，过滤及复制契约的应用状态继续在文件映射中单列。

Python 路径条件中的 `predicate_expressions` 保存可计算谓词及源码依据，`predicate_complete` 表示求值上下文是否齐全；复制选项在 `option_expressions` 中保存。谓词需要显式的宿主、目录变量和文件事实，求值结果分别列出排除、已知条件与残留条件。详见[文件过滤谓词](../experiments/2026-10-25-w1/python-packaging.md#2026-10-26文件过滤谓词)。

可用 `query search --kind copied_artifact` 查复制后的产物，沿 COPIES_ARTIFACT_TO 正向查看后续打包，或反向追溯原生构建产物。COPY_OPERATION、COPY_SOURCE_PATH、COPY_DESTINATION_PATH 提供复制位置及两端路径依据。候选保留构建、调用、过滤、操作顺序和物化条件，执行状态单列；当前范围见[原生产物传播](../experiments/2026-10-25-w1/python-packaging.md#原生产物的生产图传播)。

可用 `query search --kind python_process_invocation` 查 Python 外部程序调用。PROCESS_ARGUMENT_SOURCE/COMPONENT、PROCESS_WORKING_DIRECTORY、PROCESS_SETTING_SOURCE 和 PROCESS_CALL_STACK 展开参数、cwd、选项与调用帧；PROCESS_ENVIRONMENT_EFFECT 指向同一根调用内较早或顺序未定的环境操作。字符串/数组、继承/替换环境及运行采用条件分别保留，详见[进程调用与环境来源](../experiments/2026-10-25-w1/python-processes.md)。

查询结果带版本、预算和停止原因。静态候选与源码依赖用于查找可能的关系；实际执行由相同版本与场景的运行记录验证。未解析的调用和导入保留在节点的 `resolution` / `reason` 中，可用 `status` / `detail` 检查；`diagnostics` 汇总解析与其他诊断。源码工作区的未提交修改需要另读 diff。

`query path` / `trace` / `impact` 的深度可指定为 0–64，用于跨多层包装、进程和提供方的链。节点、边、耗时及输出预算同时生效；深度边界、预算耗尽和未找到路径分别报告。长链可配合 `--kinds` 限定关系家族，并用 `--nodes`、`--edges`、`--seconds` 设置本次查询范围。

Rust 原生语义需要 Cargo、rustc、rust-src 和 rust-analyzer；当前验证组合为 Rust 1.94.0 与 rust-analyzer 2026-10-19 发布版。可通过 PATH 或 `PROJECT_MAP_CARGO`、`PROJECT_MAP_RUSTC`、`PROJECT_MAP_RUST_ANALYZER` 指定可执行文件。`doctor` 单列这些检查。分析器使用导出副本与离线 Cargo metadata，禁用构建脚本和 proc-macro；外部依赖须已存在于调用方的 Cargo 缓存。缺少工具或上下文时保留语法事实及必需缺项，不记为完整 Rust 语义覆盖。

`rust_boundary` 保留进程、网络、WebView 的声明身份、参数及待匹配状态；`analysis_contexts` 指出适用的 Cargo 清单、目标和 feature/debug 条件。唯一推断、条件候选和运行证据分别保留。跨配置路径需要核对上下文相容性，完整部署/实例配对继续按 W2 验证。

Rust 的 `path_value` 可从程序或文件参数展开，保留相对基址、路径片段、调用上下文、分支和未解析原因。使用 `query search --kind path_value` 查找，再通过 PATH_VALUE_CANDIDATE、PATH_COMPONENT_SOURCE、PATH_CALL_CONTEXT 检查消费点与来源。常量/符号路径是源码候选，实际产物放置和进程实例由打包及运行证据连接；详情见[路径适配范围](../experiments/2026-10-25-w1/path-values.md)。

`executable_deployment` 保存 Cargo 程序的构建/发行位置；`deployed_path_candidate` 保存与之相符的 Rust current_exe 路径计算。沿 PATH_DEPLOYMENT_BINDING、MATCHES_DEPLOYED_ARTIFACT_CANDIDATE 和 RESOLVES_EXECUTABLE_TARGET_CANDIDATE 可查到完整文件位置、生产目标及其入口。`match_status` 区分单个条件生产方、多个条件生产方和未匹配，源码归属、配置、物化及 OS loader 条件分别保留。详见[可执行文件与后端产物](../experiments/2026-10-25-w1/executable-deployment.md)。

CMake 项目自动按顶层 CMakeLists.txt 发现根目录。具备 CMake/Ninja 时，工具在独立配置副本执行配置与编译器探测，导入原生目标、产物、编译输入和库依赖；未编译或启动产品。当前验证版本为 CMake 3.31.6、Ninja Python 分发包 1.11.1.4。通过 PATH 或 `PROJECT_MAP_CMAKE`、`PROJECT_MAP_NINJA` 指定工具，`doctor` 单列检查。缺工具、依赖或配置失败保留具体必需缺口。

`build_configuration.target_system` 保存原生目标、宿主和交叉编译信息，`host_path_style` 与 `target_path_style` 分别用于构建/打包和目标运行的路径解释。`declared_processor` 保留 CMake 的声明值；实际编译器架构尚未由该字段证明。缺少生成的系统记录时，构建目标继续保留，平台连接有独立必需诊断。

默认 build_tool 范围包含 vendor/third_party 目录内跟踪的 CMake 构建清单，记录其构建依赖用途；目录角色与第三方源码范围分别保留。显式 exclude 仍会排除相应清单，并在配置失败时报告缺口。

```text
project-map --workspace WORKSPACE query search --kind build_configuration
project-map --workspace WORKSPACE query search --kind build_target
project-map --workspace WORKSPACE query search --kind build_artifact
project-map --workspace WORKSPACE query search --kind build_source
```

`PRODUCES_ARTIFACT` 区分主产物和附属产物，`COMPILES_SOURCE` 记录实际构建输入，`LINKS_BUILD_TARGET` 使用原生目标身份。全局 C++ main 的 `EXECUTABLE_ENTRY_CANDIDATE` 保留预处理和链接选择条件；它与进程实际启动的配对继续通过产物/打包/运行证据验证。

构建环境可在 `init --analysis ANALYSIS.json` 中通过可选 `build` 字段配置；省略时默认启用发现、Ninja、Release。该字段与原有 version/scope/deployment/storage 并存，例如：

```json
{
  "build": {
    "version": 1,
    "cmake": {
      "configurations": ["Release"],
      "generator": "Ninja",
      "arguments": [],
      "dependencies": []
    }
  }
}
```

`arguments` 接受原生 `-DNAME=VALUE` 配置值。外部依赖可声明为 `kind: git`，提供 destination、repository、40 位固定 revision；准备好的生成源码可声明为 `kind: file`，提供 destination、path、version、origin。工具将依赖导出/复制到配置副本，保留版本来源，并拒绝覆盖选中源码。配置输入提供环境和依赖来源，目标、产物、入口及新增模块由原生分析发现。

### Cargo 原生构建记录

默认建图会从源码 Cargo build 调用、离线 metadata 和 rustc 文件名查询生成主要可执行文件的输出计划，并连接已有 Python 打包操作。该阶段只运行原生查询；`build_configuration.state=declared_output_plan`、`build_artifact.materialization=expected_output_not_built`，条件随复制路径保留。可直接搜索 `cargo_build_request`、`build_target`、`build_artifact`、`copied_artifact` 查询。未支持的上下文与产物类型在 diagnostics 中列出，见[默认输出计划](../experiments/2026-10-25-w1/cargo-native.md#默认源码建图的-cargo-输出计划)。

可选的 `build.cargo.captures` 将成功 Cargo 编译流接入同一图，查询构建目标、实际产物、Rust 根文件及后续 Python 复制关系。默认源码分析保留原有模式；原生捕获通过 Python 接口显式执行，构建脚本/proc macros 会运行，产品可执行文件不启动。详见[捕获接口及验证范围](../experiments/2026-10-25-w1/cargo-native.md)。

从选定 Git 提交导出输入，再捕获到仓库外的新目录：

```python
from pathlib import Path
from adapters.snapshot_inputs import select_inputs, export_inputs
from adapters.cargo_native import capture

selection = select_inputs(Path("SOURCE"), "COMMIT", analysis)
export_inputs(Path("SOURCE"), selection, Path("NEW_EXPORT"))
facts, receipt = capture(
    Path("NEW_EXPORT"), [f["path"] for f in selection["files"]],
    output=Path("NEW_CAPTURE"),
    source_commit=selection["source_commit"],
    expected_commit=selection["source_commit"],
    context_key="release-host", cwd=".", manifest="Cargo.toml",
    profile="release", target_directory="target",
)
```

`analysis` 为上述 version/scope/deployment/storage 分析配置。外部依赖须满足离线构建条件；捕获使用独立 Cargo home，可在输入中准备 vendor/config。存在 `build.target` 配置时须明确传入 `target`。捕获保留 rustup 工具链选择，隔离继承的 Cargo/Rust 编译设置；额外构建环境通过 `environment` 显式提供并进入收据。

在完整分析配置中加入：

```json
{
  "build": {
    "version": 1,
    "cargo": {
      "captures": [{
        "directory": "ABSOLUTE_CAPTURE_DIRECTORY",
        "source_commit": "FIXED_40_CHARACTER_COMMIT",
        "context_key": "release-host"
      }]
    }
  }
}
```

使用 `init --analysis ANALYSIS.json` 后运行 `build`。捕获必须对应本次选定源码版本，捕获输入必须包含在分析输入范围内；旧版本、失败或损坏记录使本次构建失败，上一份成功地图继续保留。捕获目录作为不可变输入管理，变更后创建新目录并更新配置。用 `build_target`、`build_artifact`、`copied_artifact` 搜索及 PRODUCES_ARTIFACT、CARGO_TARGET_SOURCE、COPIES_ARTIFACT_TO 遍历；图中分别保留原生构建报告、源码候选和运行状态。

同时存在 Python Cargo build 调用时，建图会从已提取参数、cwd 和环境效果生成 `cargo_build_request`，核对原生捕获或默认输出计划，沿 SOURCE_BUILD_REQUEST、REQUESTS_BUILD_CONTEXT_CANDIDATE 接入上述产物链。搜索该节点后可检查 `request` 中的源码值、条件和缺项。继承 cwd、未知选项及不相符配置会保留具体原因；候选边保留环境、工具链和外部配置与所选上下文一致的前提。

## skill 入口

skill 的统一整理与打包安排在工具能力和验收稳定之后；以下保留已有分发入口的用法。

最终入口为 [project-map-assistant](../skills/project-map-assistant/SKILL.md)。它携带查询规则和执行脚本，工具生成的项目地图与研究材料分开保存。

完整分发包解压后将 `project-map-assistant` 放到 AI 客户端的 skills 目录。按 skill 的 [安装说明](../skills/project-map-assistant/references/setup.md)执行 bootstrap、init、setup、doctor 和 build，然后可用：

```text
$project-map-assistant 请说明当前项目的主要模块，以及这次修改涉及哪些接口和消费者。
```

skill 使用 CLI 查询；支持 MCP 的客户端也可以选用四个只读工具。源码不被工具修改，地图只反映选定 Git 提交。历史资产当前关闭，运行记录需要相应项目的采集与上下文。

## 从源码构建分发包

在干净、已提交的工具版本上，使用具备 setuptools/wheel 的 Python：

```text
python -m pip wheel --no-deps --no-build-isolation --wheel-dir OUTSIDE_REPO/wheels .
python scripts/package_skill.py --wheel OUTSIDE_REPO/wheels/project_map_tool-0.2.1-py3-none-any.whl --output OUTSIDE_REPO/project-map-assistant.zip
```

需要时增加 `--install-to NEW_SKILL_DIRECTORY`；目标必须不存在，脚本保留已有 skill。打包器检查 wheel 内容白名单及规则 Git 提交。二进制、依赖、图和原始日志不入研究仓库。

独立安装后的真实提取检查：

```text
python scripts/smoke_installed_tool.py --python VENV_PYTHON --output NEW_OUTSIDE_DIRECTORY
```

该检查创建独立 TS/C++ 小仓库，调用安装后的工具建图、改名更新、反向查询和读取固定版本源码；它不加载历史问题测试材料。后续 AI 对照实验安排见 [交付计划](../plans/tool-and-skill.md)。
