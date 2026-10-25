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

查询结果带版本、预算和停止原因。静态候选与源码依赖用于查找可能的关系；实际执行由相同版本与场景的运行记录验证。未解析的调用和导入保留在节点的 `resolution` / `reason` 中，可用 `status` / `detail` 检查；`diagnostics` 汇总解析与其他诊断。源码工作区的未提交修改需要另读 diff。

Rust 原生语义需要 Cargo、rustc、rust-src 和 rust-analyzer；当前验证组合为 Rust 1.94.0 与 rust-analyzer 2026-10-19 发布版。可通过 PATH 或 `PROJECT_MAP_CARGO`、`PROJECT_MAP_RUSTC`、`PROJECT_MAP_RUST_ANALYZER` 指定可执行文件。`doctor` 单列这些检查。分析器使用导出副本与离线 Cargo metadata，禁用构建脚本和 proc-macro；外部依赖须已存在于调用方的 Cargo 缓存。缺少工具或上下文时保留语法事实及必需缺项，不记为完整 Rust 语义覆盖。

`rust_boundary` 保留进程、网络、WebView 的声明身份、参数及待匹配状态；`analysis_contexts` 指出适用的 Cargo 清单、目标和 feature/debug 条件。唯一推断、条件候选和运行证据分别保留。跨配置路径需要核对上下文相容性，完整部署/实例配对继续按 W2 验证。

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
