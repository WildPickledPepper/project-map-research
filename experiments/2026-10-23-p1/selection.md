# P1 候选决策与编译索引准备

日期：2026-10-23。状态：工作路线选择，最终底座未定。执行结果见[本轮报告](README.md)。

## 按组件评估

| 候选 | 当前角色与依据 | 剩余成本与重新选择条件 |
|---|---|---|
| CGC | 事实集成的工作路线；原生保留关键 C++ 定义；扩展存储实测通过 | 原生声明/类型缺口需补齐；全仓性能和稳定更新待验收 |
| CodeGraph | 同等资格的事实层备选；TS 归属正确，有 raw call 与查询接口 | C++ 头文件、限定方法、声明需修复或由外部事实补充；外部事实接入成本待测 |
| CBM | 导航、原生查询和更新对照 | 重载实体合并和同名错连需解决，未核实调用不能进入确定事实层 |
| code-map | 接口身份、方向和子图组织的参考组件 | Insight C++ 提取尚未接入；多服务身份需修正；沿用上一轮实测 |
| CoderMind | 项目职责组织候选 | 先绑定可靠事实，后验证功能地图、摘要版本与语义更新；完整 AI 路径尚未执行 |
| RepoGraph / Code-Craft | 定义/引用检索与论文机制参考 | RepoGraph 下载版存在已审计问题；Code-Craft 尚无可核实执行的官方实现 |

“同时推进两个主要改造候选”是工作量安排。本轮原版对照实际包含三个工具；后续按必要能力与改造成本调整。没有根据节点总数、单次耗时或不同输入切片宣布综合优胜者。

补充提取器不引用 CGC 的对象模型；其 JSON 可作为其他底座的输入。当前 CGC 集成成功说明这条路径可行，CodeGraph 是否有更低成本需实测其扩展与维护接口。

## CodeGraph 缺口的源码定位

固定提交 `7bac941c1916d34fae0e93dd0ffeaef360d741fb`：

- [扩展名映射](https://github.com/sina-parsania/CodeGraph/blob/7bac941c1916d34fae0e93dd0ffeaef360d741fb/crates/codegraph-parse/src/lib.rs#L129) 将 `.h` 交给 C 解析器。
- [C/C++ 名称提取](https://github.com/sina-parsania/CodeGraph/blob/7bac941c1916d34fae0e93dd0ffeaef360d741fb/crates/codegraph-parse/src/lib.rs#L2064) 沿 declarator 链取名；该分支未接受 `qualified_identifier`。最小 fixture 及真实类外定义都发生遗漏。
- 修好名称与文件分类后，仍需验证声明、类型、重载身份和解析关系。当前未修改上游 Rust 源码，也未把预估修复当作已通过能力。

此前接口方向、服务身份和更新差异的修复范围见[上一轮适配审计](../../cases/unit-flows/adaptation-boundaries.md)。外部补充方案与修复上游方案应分别记录成本。

## SCIP 是两者的共同待测路径

CGC 固定源码中，[C/C++ 命令生成](https://github.com/CodeGraphContext/CodeGraphContext/blob/93c9685bff9151f50a3121e9913e5ba2d27c1191/src/codegraphcontext/tools/scip_indexer.py#L439) 会寻找真实 `compile_commands.json`，用 `scip-clang` 生成索引。缺少编译数据库时回退到 Tree-sitter。

CodeGraph 固定版本的 [scip 自动检测](https://github.com/sina-parsania/CodeGraph/blob/7bac941c1916d34fae0e93dd0ffeaef360d741fb/crates/codegraph-cli/src/scipcmd.rs#L20) 包含 TS、Rust、Python、Java、Go，没有自动选择 C++ 的分支；CLI 提供 `index --scip` 导入入口。C++ 路线需外部生成索引，并验证导入能否补齐缺失实体及调用。

2026-10-23 核对的 [scip-clang v0.4.1 发布包](https://github.com/sourcegraph/scip-clang/releases/tag/v0.4.1) 提供 Linux x86_64 与 macOS arm64 文件，无 Windows 发布二进制。本机 PATH 未发现 cmake、ninja、C/C++ 编译器、docker 或 scip-clang，目标 tracked 文件也没有编译数据库。两工具的真实 C++ SCIP 路径均未执行，记录为环境依赖，不能计作任何一方的已验证优势。

## 获取真实构建上下文

Insight 固定版本的[开发指南](https://gitcode.com/Ascend/msinsight/blob/d4e8d1cf9f90208bcbe5371c127088f6fd66c688/docs/zh/development_guide/develop_guide.md) 和 [server/build/build.py](https://gitcode.com/Ascend/msinsight/blob/d4e8d1cf9f90208bcbe5371c127088f6fd66c688/server/build/build.py) 给出了实际入口：

1. 在独立产品副本准备官方 CMake/Ninja/编译器依赖。
2. 在 `server/build` 执行 `download_third_party.py`、`preprocess_third_party.py`。
3. 使用官方构建脚本的 Release/Ninja 配置，增加 `-DCMAKE_EXPORT_COMPILE_COMMANDS=ON`；保留平台、宏、include、依赖版本和配置日志。
4. 确认真实 handler 与两个数据库实现都在编译数据库中；用 scip-clang 对实际配置生成索引。
5. 分别导入 CGC 和 CodeGraph，再检查本轮声明、重载、作用域和智能指针反例。

以上是待执行步骤。源码审计确认官方脚本使用 CMake/Ninja；编译、索引生成及导入尚未验证。运行阶段还需真实可共享数据及正常/切项目场景，准备方法与 P5 分开登记。
