# A2：全仓连接扩展

状态：**A2 已完成**，见[完成报告](completion.md)。2,310 个自动输入生成 271,737 个节点、386,100 条边；三条链在同一全仓图上回归，独立重建内容一致。承接 [A1](../2026-10-24-a1/completion.md) 的自动范围，使用固定源码版本和现有提取器建立同版本的调用、协议、字段和资源关系。历史验证候选继续按[样本划分](../../datasets/msinsight-regressions/split.md)保留；本阶段使用常规全仓分析、既有三条链和自编机制正反例。

## 执行次序

1. 在 A1 自动范围执行未经本阶段修改的完整构图器，保存首次结果、日志和资源预算。
2. 根据执行证据改进规模成本和缺失机制，复用既有 TypeScript、Tree-sitter、规范化关系和查询实现。
3. 从同一全仓快照验收既有协议/字段链、资源反查和代表性的不同写法。
4. 在独立自编源码副本改名、改命令/注册、删除提供方，核对失配、歧义与跨作用域隔离。
5. 记录版本、输入、输出、诊断、存储方式和未展开能力，完成独立重建及回归。

## 本阶段门槛

| 检查 | 验收内容 |
|---|---|
| C01 全仓输入 | 沿用自动发现策略；每个纳入路径有覆盖状态；构图不读取人工参考答案 |
| C02 语言内关系 | TS 静态声明、绑定与导入，C++ 声明/定义、类型和调用候选有来源；同名、遮蔽及缺上下文不升级为确定目标 |
| C03 协议两端 | 提供方、消费方、模块/服务/命令独立提取；匹配结果保留条件、歧义、动态值与失配 |
| C04 字段关系 | 保留调用位置、参数/返回字段、序列化与状态消费的来源；三条链按各自既有验收范围在全仓快照回归 |
| C05 资源关系 | 读写按声明/对象与键条件关联；不同作用域、实例、常量键保持隔离，运行别名未知可查 |
| C06 变更维护 | 源码改名、命令改值和删除注册后自动重算，旧关系失效；正反例同时验收 |
| C07 可重复与成本 | 固定规则和源码，新目录重建；比较有意义的事实与诊断，记录时间/内存/截断；不核验文件哈希 |
| C08 完整回归 | 既有测试及新增通用机制用例通过；保留首次失败与未支持项 |

“连接”按源码关系、静态声明目标、有条件候选分别记录。缺编译/部署上下文、未解析动态目标、字段约束及运行实例仍需明确表达；运行行为不由静态连通性推定。

## 已建立的机制对照

[自编源码变更实验](run_connection_controls.py)建立两个独立前端包和两个服务端，使用相同命令、模块键及工厂方法名。通过现有刷新器逐次提交源码变更，检查单侧改名、命令改值、删除注册、动态值、重复注册、不同模块、文件改名/删除和缺部署绑定；另用共享资源的相同/不同常量键与不同成员声明检查反向连接。它读取提取结果评分，预期名称不进入提取器。

首轮 14 项中有 1 项失败，见[首次结果](evidence/controls-first.json)：单侧修改协议作用域字段后，另一服务也受到影响。原因是工厂组件按 getter 方法拼写关联。修复改用调用目标 ID，经声明/定义和虚函数候选到达组件 getter；目标未知时保留 `factory_target_unresolved`。单元测试覆盖同名 getter、未知接收者和基类虚函数入口。

全仓 TS 的不同包还具有独立的全局声明；测试可能覆盖全局调用函数。把全部源码作为单一编译器程序的根会混合这些环境。[该次执行](evidence/context-failure.json)保留了既有消费者缺失及编译诊断，发现问题后由协调者停止。新实现按最近的包清单和源码角色自动划分根文件，所有纳入文件仍可作为 import 依赖；包/角色是分析假设，实际构建变体和每个测试的运行环境仍需对应构建信息。

划分后还需跨单元组合消息。[首次组合缺口](evidence/cross-unit-first.json)中，126 个消息都停在 `postMessage`。实现现分别在发送方和接收方自己的编译器上下文中求值，再把符号消息模板送入已发现的注册回调，保留消息过滤、接收者源码与部署条件。自编正反例检查三个包之间的发送、转发、socket 以及不匹配事件和删除注册。

恢复工厂身份还需要标准容器的元素类型。[既有链回归](evidence/factory-range-first.json)发现结构化 range-for 没有为工厂接收者提供类型，并在返回图阶段遇到跨单元生成 ID 冲突。现复用 ValueTypes 的容器/模板模型推导循环元素及智能指针类型；被重新赋值的绑定保持未知。符号化执行记录按分析单元区分 ID，AST 身份与消息字面值保持原义。

[返回字段首次回归](evidence/return-first.json)通过 16/19 项，三个请求处理器均已恢复，两条返回字段链仍缺失。原因是回调 setter 定义于被导入的类中。返回分析现检查该程序实际加载的依赖类方法，注册调用仍来自自身根文件；自编跨包回复包装测试覆盖这一写法。后续验收继续使用原来的字段到状态门槛。

[成本定位](evidence/cost-first.json)保留全仓回调阶段的慢执行和一次 1.5 秒 CPU 采样。该采样主要落在分支 union 合并与垃圾回收；源码检查确认候选数组没有宽度上限。合并现按默认 64 个候选限制宽度，超限返回未知值并生成包含入口位置的 `alternative_budget_exceeded`；步数与深度限制继续记录。预算截断对应未展开能力，不能解释为没有依赖。

[完整提取后的校验失败](evidence/schema-first.json)来自两个未解析序列化注册键：键值为 null，同时被用作节点名称，违反图模式。节点现使用源码键表达式显示，键及 `key_resolution=unresolved` 保持未知，不参与确定身份匹配。新增 fixture 经真实提取和图校验覆盖未知键；错误定位附带节点 ID、类型与源位置。完整构建还保留返回阶段的未校验 checkpoint，失败产物不发布为完整快照。

JSON 模式使用结构与 JSON 域校验，避免为一次校验生成整套数据库导入行和编码副本。节点身份、边端点、字段类型及无损 JSON 约束继续检查；数据库导入保留原准备路径。反例覆盖非字符串键、tuple、非有限数、set、循环引用和悬空端点。

## 复现入口

依赖沿用 requirements-store.txt、Node 22 和 TypeScript 5.9.3。`$SOURCE` 指独立 Insight clone，`$TS` 是固定 TypeScript 模块，`$OUT` 和 `$CONTROLS` 是新的仓库外目录；Windows 使用已有 parser cache、运行库及 c++filt 环境。

```powershell
python experiments/2026-10-24-a2/probe_full_build.py --source "$SOURCE" --revision d4e8d1cf9f90208bcbe5371c127088f6fd66c688 --config experiments/2026-10-24-a1/evidence/auto-config.json --typescript "$TS" --output "$OUT" --seconds 1800
python experiments/2026-10-24-a2/run_connection_controls.py --output "$CONTROLS" --typescript "$TS"
python experiments/2026-10-24-a2/audit_graph.py --graph "$OUT/build/graph.json" --output "$OUT/audit.json"
```

每次完整构建冻结源码提交和已提交的规则版本。probe 记录时间、Windows 进程树采样工作集、Node heap 与退出结果；最终全仓执行上限分别为 1,800 秒、6 GiB 和 3,072 MiB，前序执行保留各自的原预算。工作集相加可能重复计算共享页，不能当作机器实际独占内存。

[原规则首次运行](evidence/first-pass.json)达到 300 秒时间预算；其旧监测只覆盖 venv 启动器，明确不作为进程树内存结果。[后续规模失败](evidence/scale-failure.json)在读取约 694 MB 中间图时超过 Node 字符串上限；阶段输入现已改为从同一图派生的接口和返回边界 ID，完整关系保留在 Python 图中。原始图、日志、源码导出与实验 Git 仓库保留在 Git 外。

## 重建、查询和证据检查

在另一新目录 `$SECOND` 再执行相同 probe，以下 `$RUNTIME_STORE` 为 P5 的运行记录存储，按 [P5 复现说明](../2026-10-24-p5/README.md)准备。P7 清单用于历史基准评分，构图输入仍由自动发现决定。

```powershell
python experiments/2026-10-24-a2/audit_graph.py --graph "$OUT/build/graph.json" --rebuild "$SECOND/build/graph.json" --output "$OUT/comparison.json"
python experiments/2026-10-24-p7/coverage_catalog.py --source "$SOURCE" --graph "$OUT/build/graph.json" --output "$OUT/catalog.json"
$env:PYTHONPATH=(Get-Location).Path
python experiments/2026-10-24-p7/run_acceptance.py --graph "$OUT/build/graph.json" --inventory experiments/2026-10-24-p7/evidence/inventory.json --catalog "$OUT/catalog.json" --runtime-store "$RUNTIME_STORE" --output "$OUT/acceptance"
python experiments/2026-10-24-p7/query.py --graph "$OUT/build/graph.json" trace getUnitFlows --field '["unitAllFlows"]'
python experiments/2026-10-24-p7/query.py --graph "$OUT/build/graph.json" resource CurveContainer
python experiments/2026-10-24-a2/check_completion.py
```

最后一条检查本仓库保存的紧凑证据，不读取产品源码、不核验哈希。`package_evidence.py --help` 列出从成功的外部实验产物打包证据的参数。
