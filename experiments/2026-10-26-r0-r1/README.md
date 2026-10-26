# R0 组件准入与 R1 全仓事实接入

2026-10-26。执行范围为[复用优先计划](../../plans/reuse-first-execution-plan.md)的 R0/R1。沿用已有证据，产品实现已按用户指令恢复；历史资产关闭，原始 Insight checkout 保持只读。新增工具、环境、缓存、临时文件及原始实验数据均放在 D 盘，Git 只保存实现与紧凑报告。

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

R0 剩余：边界身份负例、C++ 语义补充准入与数据流精度路线。R1 的真实仓库接入和逐组件核验待执行；本项不改变 G02–G08 状态。

## 已交付：C++ 原生语义提供方

[clangd 提供方](../../adapters/clangd_provider.py)复用固定版本的 multilspy 客户端和 clangd 23.1.0，导入原生文档符号、AST 和定义跳转；初始化时开启 LSP 的层级文档符号能力。引用/接收对象的节点按原生范围区分，编译配置进入身份，未解析目标及预算残余保留。

[准入结果](evidence/clang-provider.json)记录两个通用布局、feature 开/关各 8 项检查：继承方法、模板调用、类型别名、活动/非活动预处理分支、两个命名空间同名字段、成员和接收对象的引用身份。首次运行因客户端未声明层级符号能力，导致适配器漏导入声明；该首轮失败保留，修正能力声明后通过。此前 getter 值/引用/指针及重载检查直接继承原审计，不重复执行。

真实 Insight 编译数据库包含 497 项原生编译记录。静态成员文件 `OperatorGroupConverter.cpp` 通过 clangd 原生检查；include-only 文件 `TextTraceDatabaseStatistics.cpp` 保留一项 `__rdtsc` 本征函数定义兼容诊断。两项结果不代表整个 C++ 范围通过；原生符号/定义身份也不等于运行实例或通用别名分析。

```text
python experiments/2026-10-26-r0-r1/probe_clang_provider.py --binary CLANGD --output NEW_OUTPUT
python experiments/2026-10-26-r0-r1/probe_clang_provider.py --binary CLANGD --output OTHER_OUTPUT --feature-mode 0 --layout alternate
```
