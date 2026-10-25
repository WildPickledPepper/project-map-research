# W1：JavaScript 接入与真实混合模块连接

2026-10-25。已执行生产构图、导航和独立安装检查。**W1 仍在执行，G02 未通过**；Python/Rust 语义接入和首条实际边界仍待完成。skill 的整理与打包留到工具能力和验收稳定后进行。

源码固定为 Insight `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`，构图规则为本仓 `7fbd29bd03dcc7f19c524d90e15612ac74757a55`；TypeScript `5.9.3`、Node `22.23.3`、Python `3.11.9`、Tree-sitter `0.25.2`、language-pack `1.20.0`、Kuzu `0.11.3`。原始 checkout 未修改，未重新核验文件哈希。

## 接入内容

复用既有 TypeScript 编译器流水线，启用 `allowJs`，统一处理 JS/JSX/MJS/CJS 与 TS/TSX/MTS/CTS。模块路径解析使用编译器的 module resolver；工作区包以只读虚拟 `node_modules` 视图提供给它，保留 `import`/`require` 条件，不另写一套包导出解析器。不同模块同名符号按声明身份区分。

统一图新增文件模块、导入/重导出/require/动态 import 的引用位置与模块依赖边，已有函数调用和源码导航同时接入 JS。类型导入保留标记；动态模块表达式、被遮蔽的 require 和重复工作区包名保留具体诊断。多候选方法使用 `STATIC_CALL_CANDIDATE`，不会把联合类型中的第一个签名认作唯一调用目标。

这些关系进入既有自动发现、刷新、JSON 快照、SQLite 导航和 CLI；本次没有引入 LLM 推断或历史资产。编译器仍采用当前分析配置，并未完整重放产品构建条件；模块依赖表示源码关系，实际执行需由运行证据验证。

## 实测结果

| 检查 | 输入与结果 | 能说明什么 |
|---|---|---|
| 新增语言回归 | 11 项 JS/TS fixture 全通过；首批 8 项在旧实现上全部失败 | 混合调用、ESM/CJS、重导出、条件 exports、同名负例、类型导入、动态候选和模块增删改名 |
| 既有回归 | 121 项 Node 检查、375 项 Python 检查通过 | 当前既有功能回归；Python 检查数不代表支持 Python 源码分析 |
| 首条真实连接 | [受控链证据](evidence/javascript-chain.json)，14 项通过 | UI 到 JS 依赖的定义、调用、导入、正反查询及固定版本源码导航 |
| 全仓生产构图 | 4,855 跟踪路径、2,363 输入、289,504 节点、422,496 边 | 同一全仓图已成功发布；29 个结构分组仍是旧导航分组，不是 W0 的逻辑模块分母 |
| 全仓同链复验 | [14 项通过](evidence/javascript-repository-chain.json) | 连接在自动全仓输入下成立，未依赖受控输入过滤 |
| 全仓 JS 范围核对 | [53 个文件均有输入记录、parsed 状态和文件模块](evidence/javascript-repository-scope.json)；1,218 项记录检查通过 | 提取与未知记录入图；不表示全部调用已解析 |
| 独立安装与更新 | [22 项检查通过](evidence/javascript-installed.json) | 新环境安装 wheel 后直接使用 CLI；新增、改名、删除模块自动更新，旧版本查询被拒绝，原源码未被工具修改 |

真实连接由源码独立审计形成 [reference](javascript-reference.json)，仅由后置评分器读取。构图程序不读取参考答案。链从 `CodeTextSearch.tsx` 创建并调用 `mark.js`，再连接 `DOMIterator` 和 `RegExpTool`；`serachInCode` 到 `RegExpTool.createRegExp` 的正向与反向路径均可查。`this[searchFunctionName]` 保留 `wrapMatches` / `wrapMatchesAcrossElements` 两个候选，没有唯一目标边。

全仓 JS 的 1,063 个调用点中，182 个定位到静态声明，1 个保留联合类型歧义，880 个保留 `no_input_callable_or_runtime_binding`。该原因尚未细分外部 API、动态绑定和其他未解析来源，后续需结合边界与参数来源分析继续展开。99 个模块引用中 33 个连到源码模块、66 个未连接；列表含 Node 内建模块、外部构建依赖及 `plugins/jupyterlab/style/index.js` 的 CSS 引用，样式连接归入后续资源适配。跨文件且至少一端为 JS 的唯一静态调用目标边为 34，模块依赖边为 34；这两个数字不能换算为全项目关系正确率。

独立安装 fixture 使用不同包名与目录，连接 TS → JS → CJS，并放置不应连接的同名函数。新增模块后能查到新路径；改名后身份和路径更新；删除提供方、保留消费者后旧定义消失，缺失模块产生诊断。C++ 符号仍可查询。fixture 代码只参与静态分析，未执行产品运行场景。

## 失败及修正记录

首批 8 个 JS fixture 在旧实现上 0/8 通过。新接入初次构图还暴露 SourceFile 名称处理的空 parent，已修正。新增动态方法负例时，编译器返回的单个签名造成错误唯一目标，先保留失败，再改为检查 callable union 并输出候选；当前 11 项通过。

首次 wheel 构建使用缺少 `bdist_wheel` 的全局 Python，随后改用已有构建环境成功。安装后检查首次因驱动在切换工作目录后传入相对 TypeScript 路径失败；驱动改用绝对路径后 22 项通过。原始失败日志、完整构图和 CLI 命令日志保留在仓库外。

## 复现

先按工具说明安装依赖并提供 TypeScript 与 parser 环境，输出使用仓库外新目录：

```text
node --test tests/javascript_facts.test.cjs
python experiments/2026-10-25-w1/run_javascript_trial.py --source SOURCE --revision d4e8d1cf9f90208bcbe5371c127088f6fd66c688 --typescript TYPESCRIPT --scope repository --output TRIAL
python experiments/2026-10-25-w1/score_javascript_trial.py --trial TRIAL --output SCORE.json
python experiments/2026-10-25-w1/assess_javascript_scope.py --trial TRIAL --output SCOPE.json
python experiments/2026-10-25-w1/smoke_installed_javascript.py --python INSTALLED_PYTHON --typescript TYPESCRIPT --parser-cache CACHE --dll-dir DLL --output SMOKE
```

`--scope chain` 只用于首条连接的受控实验；生产全仓结果使用 `--scope repository`。独立安装脚本使用隔离 Python 模式调用安装包，不从研究仓库导入工具实现。公开证据由 `publish_javascript_evidence.py` 投影原始结果，去掉本机 workspace 路径及重复全仓明细。
