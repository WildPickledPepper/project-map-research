# W1：Python 基础事实与代理接口连接

2026-10-25。Python 基础事实已进入生产构图、自动更新和统一查询，第一条代理内部连接通过独立检查。**W1 继续执行，G02 未通过**；Rust 仍待接入，跨进程对端、完整数据与运行验证按 W2–W4 继续推进。skill 留到最后整理。

源码固定为 Insight `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`，构图规则为本仓 `81e97f21d37b0fe70a0a3739859c0bea68590ccf`。Python `3.11.9`、Jedi `0.19.2`、Parso `0.8.5`，其余组件版本随公开证据记录。原始 GitCode checkout 未修改；未重新核验文件哈希。

## 复用与实现

先对原版 CGC `0.6.13` / `93c9685bff9151f50a3121e9913e5ba2d27c1191` 的 Python parser 做同输入检查。它提供函数、导入和调用结构；这次 fixture 的原生调用记录缺少列位置，`inferred_obj_type` 为空。该比较没有执行 CGC 跨文件解析器，因此不据此比较跨文件解析正确率。[七项组件实测](evidence/python-resolver-probe.json)保留原生记录和 Jedi 推断结果。

接入采用 Python 标准 AST 提取精确位置、定义、参数、值表达式和条件，复用 Jedi 的公开 `infer` / `goto` API 处理作用域、导入、别名、重导出和实例方法。Jedi 的项目入口支持指定搜索路径；本实现把搜索根与源码入口关联，外部库边界另按导入身份识别。[Jedi 0.19.2 API 文档](https://jedi.readthedocs.io/en/v0.19.2/docs/api.html)是能力依据，实际效果由本次实验检查。

新增文件模块、类型、函数、绑定、导入引用、调用点和值节点；关系包括调用目标/候选、参数绑定、返回值、默认值、回调、装饰器、继承和异步等待。身份使用文件与源码位置，同名对象分开。源码只做分析，未被导入执行。唯一推断目标标为 `inferred`，多个目标或上下文未决时保留候选；未解析调用保留具体原因。

Python 边界补充按实际导入的库 API 和参数来源工作，覆盖本次需要的 aiohttp Application、AppRunner、TCPSite、路由、ClientSession/WebSocket 和 subprocess 启动/释放。监听与路由通过同一个 Application 的源码值来源连接；本地同名包、同名参数和其他 Application 不应误连。进程释放关系目前是符号句柄候选，尚非实际进程实例证明。

## 实测结果

| 检查 | 结果与范围 |
|---|---|
| 独立组件探针 | 7 项通过；含相对导入、继承、同名负例、分支候选、同一行调用和遮蔽 |
| 新增 Python 事实/边界单元检查 | 17 项事实与 7 项边界检查通过；含无执行哨兵、命名空间入口上下文和多上下文歧义 |
| 既有回归 | Windows 全量 401 项 Python 测试通过；[Linux CI](https://github.com/WildPickledPepper/project-map-research/actions/runs/40184874514) 的 401 项 Python、121 项 Node 检查通过 |
| 首条实际连接 | [代理范围 41 项通过](evidence/python-proxy.json)：23 个 Python 文件进入生产图，5 项独立调用目标、监听/路由/客户端/进程边界、URL 来源、释放、正反路径和版本源码导航通过 |
| 自动全仓构图 | 4,855 跟踪路径、2,482 输入、365,906 节点、528,475 边，快照成功发布 |
| 全仓 Python 复验 | [137 项通过](evidence/python-repository.json)：119 个第一方 Python 文件全部有 parsed 输入与文件模块，代理同链在全仓自动输入下仍成立 |
| 独立安装与更新 | [23 项通过](evidence/python-installed.json)：隔离环境安装 wheel，CLI 查询、TS/JS/C++ 保留、新增/改名/删除 Python 模块、过期拒绝、命名空间同名负例通过 |

独立源码参考保存在 [python-reference.json](python-reference.json)，只有后置评分器读取。生产发现与连接不使用业务名称白名单。代理范围过滤只用于对照；全仓实验由生产发现器决定输入。

真实可查路径为 `start_proxy` → `MultiplexAIOProxyServer.start` → `TCPSite` → 同 Application 的路由 → `default_request_handler` → `session.ws_connect`。反向查询也通过；WebSocket URL 能追到所选 server 的 host/port 表达式。这里建立的是源码上的接口和条件分派关系。远端 C++ 服务仍需要启动产物、所选服务实例和部署上下文来配对，归入 W2，未把同端口或同名可执行文件直接当作对端。

全仓 9,418 个 Python 调用点中，2,105 个有唯一推断目标，4 个保留候选，7,309 个未解析：6,252 个为外部/内建调用、981 个无输入内目标或动态绑定、2 个输入声明未索引或解析问题、74 个在候选上下文中没有输入内可调用目标。这些是实际提取状态，不是正确率。50 个边界节点包含 39 个启动、5 个释放、2 个监听、1 个路由和 3 个客户端；数量也不代表全部边界机制已覆盖。

当前导航的 29 个结构分组来自旧构建清单归属，不能代替 W0 冻结的 129 个必需逻辑组件。Python 接口节点已可通过 `search --kind python_boundary`、详情和路径查询使用；统一接口列表、逻辑模块视图与逐模块门槛继续在 W5 收口。完整配置选择、动态导入/绑定、复杂解包/对象变更、其他插件注册、跨语言对端和实际运行仍需按既定工作包验证，整体验收保持未通过。

## 失败与修正

首次完整回归发现旧测试仍把 Python 排除在输入之外，更新预期后通过；Rust 继续保留明确缺项。Jedi `fast_parser=False` 在固定版本的磁盘推断路径触发缓存错误，改为串行消费每个 Script，立即转存公开结果，并恢复调用方设置。

命名空间 fixture 揭示另一个实际误连：入口导入 `tools.helper`，helper 再导入 `common`，相邻目录存在同名诱饵。旧实现选择了相邻文件。修正为传播导入入口的搜索上下文；两个入口各有不同提供方时保留两个候选，某个入口未解析时也不会输出唯一目标。旧 wheel 在新增安装负例上失败，修正后的 wheel 23 项通过。该修正也进入第二次全仓重建；本文全部生产证据来自修正后的规则。原始失败与两次构图日志保留在仓库外。

## 复现

先按[工具说明](../../docs/07-tool-quickstart.md)安装提取依赖，提供 TypeScript/parser 环境，输出使用仓库外新目录：

```text
python -m unittest tests.test_python_facts tests.test_python_boundaries -v
python experiments/2026-10-25-w1/run_python_trial.py --source SOURCE --revision d4e8d1cf9f90208bcbe5371c127088f6fd66c688 --typescript TYPESCRIPT --scope repository --output TRIAL
python experiments/2026-10-25-w1/score_python_trial.py --trial TRIAL --output SCORE.json
python experiments/2026-10-25-w1/smoke_installed_python.py --python INSTALLED_PYTHON --typescript TYPESCRIPT --parser-cache CACHE --dll-dir DLL --output SMOKE
python experiments/2026-10-25-w1/check_evidence.py
```

安装检查通过 `-I -m projectmap` 从研究仓库外调用安装包，清除源码导入环境变量。公开 JSON 不包含本机工作路径、源码导出或原始图；发布脚本可按 `--only resolver proxy repository installed` 分项保存，已有证据不覆盖。
