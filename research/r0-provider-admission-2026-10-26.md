# R0 提供方准入决定

2026-10-26。组件选择与接口核实已完成；准入结果为部分通过。已准入组件进入 R1，数据流替代能力的失败项继续阻止相应门槛通过。全项目验收分母与 G01–G09 保持不变。

## 固定选择与真实入口

| 需求 | 复用入口与接合位置 | 决定与实测依据 |
|---|---|---|
| 地图、存储、查询、版本与发布 | 现有 `projectmap/`、`adapters/project_map.py`、SQLite；保留 CGC 的事实/存储互操作 | 继承既有 P/A/W 结果；本轮原生提供方进入相同发布和查询流程 |
| TS/JS 定义、类型、引用与调用 | TypeScript 5.9.3 Program/TypeChecker → `adapters/typescript_facts.cjs` | 沿用；补原生声明/三斜线引用，21 个既有零事实文件均有对应记录；124 项 Node 检查通过 |
| Python 包、符号与调用候选 | Python AST/Jedi → 既有 Python 适配 | 沿用已有全仓与隔离结果；动态目标保留候选与缺口 |
| Rust 语言与配置事实 | rust-analyzer definition、Cargo metadata/JSON → 既有 Rust 适配 | 沿用；Joern 未取得可替代 Rust 语义输出 |
| C++ 声明、引用、原生目标及编译条件 | clangd 23.1.0，经 multilspy `LanguageServer.create`/定义/AST 请求 → `adapters/clangd_provider.py` | 准入；继承 11 项原生检查，新增两个布局/条件配置各 8 项通过。497 项真实编译记录下执行全仓提取；有诊断上下文保留候选 |
| C++ 编译参数互操作 | CMake File API、Windows CommandLineToArgvW/POSIX shlex → `adapters/compilation_database.py` | 准入；保留参数，优先同版 Clang builtin headers，真实文件由 1 项编译错误降为 0；原始数据库不变 |
| Shell、容器、环境及进程候选 | CBM 0.12.1 CLI/原生 SQLite → `adapters/cbm_provider.py` | 准入到原生实际输出范围；私有 cache/runtime 修复启动；7 项启动检查、8 项范围/身份检查通过。Shell 包装表达式残余保留 |
| Shell 命令位置和参数语法 | 已有 tree-sitter-language-pack 1.20.0 的 Bash grammar → `adapters/shell_facts.py` | 限定语法准入；补 CBM 未输出的顶层命令位置，保留展开/进程目标未求值。8 个真实脚本 parsed，340 个命令位置；注释/heredoc 负例与 11 项接入检查通过 |
| CMake/Cargo 目标和产物 | 已有原生收据；同提交 CMake capture → `adapters/cmake_project.py` | 沿用并增加 capture 接入；拒绝错误提交，实际配置收据复用通过 |
| SQL AST 与 SELECT 血缘 | SQLGlot 30.24.0 `parse_one`/`lineage` | 限定准入，5 项检查通过；产品宿主参数/数据库实例接合属于 R3 |
| C++ 数据依赖 | Joern 4.0.665 CPGQL/`reachableByFlows` | 仅准入候选路径；6 项语义题匹配 5 项，直接 const-reference 别名漏报。独立编译执行确认预期；不能替代必需别名能力 |
| Rust 数据依赖新引擎 | 同版 Joern rust2cpg/CPGQL | 不准入；目录输入成功退出但方法数为 0。继续用 RA 语言事实，通用 Rust 数据流能力保持缺项 |
| 运行上下文与应用事件 | OTel Python SDK 1.45.1 TracerProvider/context/events | 限定准入，4 项检查通过；产品与其它语言接入属于 R4 |
| 浏览器与交互证据 | 既有 Playwright 驱动与场景 | 沿用；对应产品场景按 R4 运行义务验收 |

版本、许可证、上游源码入口及原生输出来源见[源码契约](reuse-source-contracts-2026-10-26.md)、[原始组件审计](../experiments/2026-10-26-reuse-audit/README.md)和[本轮执行记录](../experiments/2026-10-26-r0-r1/README.md)。同版本已通过结果直接继承，没有重跑完整选型，也没有重新核验文件哈希。

## 已调查仓库的去向

CGC 的 SCIP 读取、CodeGraph 的 SCIP 导入/存储保留互操作价值。人工 SCIP 对照发现两者调用投影各有精度问题，当前 C++ 主路线采用原生 clangd。code-map 保留适用标准 HTTP extractor；其路径策略和服务身份尚需适配。CBM 使用 CLI 输出，不复制其解析/传播代码。RepoGraph 保留检索组织参考，RPG/CoderMind 的职责摘要后置。Code-Craft 论文引出的 multilspy 已实际复用；论文完整实现仍未核实。具体旧结果见[已有工具复用账](reuse-assessment-2026-10-26.md#0-已有工具的组件复用账)。

## 剩余能力与阶段判定

| 缺项 | 本轮出口 | 影响 |
|---|---|---|
| Joern C++ 引用别名遗漏 | 固定为替代准入失败；保留既有有限模型及其限制，停止扩展自有求解器。后续高精度备选仅保留已调查的 SVF 路线，需 LLVM IR 与源码位置映射后独立准入 | R0 必需数据流替代能力未全部通过；R3/G05 不可继承通过 |
| Joern Rust 零方法 | 结束该版本/配置候选试验；RA 继续承担语言事实，已有有限边界模板保留 | Rust 通用数据流未解决，R3/G05 保持缺口 |
| CBM 不支持的包装启动/自定义协议 | 保留原始位置与候选；R2 消费语言原生事实及有限机制模型，不重写 Shell 引擎 | 对应连接需 R2 逐项验收 |
| 部分 C++ 文件具有原生编译诊断 | 保留诊断、原始 AST、上下文及候选精度；由 R1 逐组件报告实际影响 | 未核清的必需语义保持 G02 未通过 |

本轮交付的是可执行的复用选择、接入和明确失败出口。R0 的“组件取舍”工作已闭合，严格准入状态为 **partial**；R1 同版本全仓接入、129 组件事实账及后置查询复核已交付，详见[最终报告](../experiments/2026-10-26-r0-r1/completion.md)。候选失败没有从必需能力分母删除。后续工具、缓存、临时文件与原始实验数据统一放 D 盘；原始 Insight checkout 保持只读，历史资产关闭，skill 在 R5 整理。
