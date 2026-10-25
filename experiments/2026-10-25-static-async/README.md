# 异步返回与分页字段传播

五项指定连接已在完整新快照中贯通，A5 环境准备完成。完整验收与成本见[报告](completion.md)。

目标：补齐 A4 登记的防抖 Promise 返回、分页累积到 Worker 调用边界两类静态断点。

沿用 TypeScript 编译器与现有符号解释器，按标准 Promise、Map、定时器和数组语义扩展。业务名称只用于检查源码参考，不进入提取规则。原始 Insight checkout 保持不变。

验收范围：

1. 保存的 resolve 经过 Map/对象/队列及定时回调后，返回字段可追溯到实际传输边界；reject、替换回调和取消定时器不能证明成功返回。
2. 分页循环的数组累积保留字段来源与路径条件，直到实际 Worker 包装器调用；零次迭代、删除累积和不可达代码不产生相应关系。
3. 循环、回调、调用深度与值大小均有预算；运行次数、调度、缓存及 Worker 内部执行另由运行证据验证。
4. 六条已有开发链及原 P7 链继续回归。以上源码已经用于定位缺口，结果按开发回归登记；历史验证样本不用于调整规则。

先保存新增机制检查的首次结果，再修改规则。大图、原始日志和实验源码保存在研究 Git 外。A5 同步检查独立运行副本、构建产物、浏览器及公开输入是否可复用。

## 复现

按仓库根目录安装固定版本依赖。使用 [A4 的实验副本生成器](../2026-10-24-a4/prepare_update.py)准备源代码及配置，读取生成的 `preparation.json` 中的最终提交。所有输出指向研究 Git 外的新目录。

```sh
python experiments/2026-10-24-a4/prepare_update.py --source <original-checkout> --output <experiment>
python experiments/2026-10-24-a2/probe_full_build.py --source <experiment>/source --revision <final-revision> --config <experiment>/config.json --typescript <typescript.js> --output <results>/static-async-full-02 --seconds 1800
python experiments/2026-10-25-static-async/evaluate.py --graph <results>/static-async-full-02/build/graph.json --output <results>/connections.json
python experiments/2026-10-24-a4-repair/retest.py --graph <results>/static-async-full-02/build/graph.json --output <results>/a4-replay
python experiments/2026-10-24-a4-repair/run_direct_updates.py --typescript <typescript.js> --output <results>/updates
```

导航与 P7 回归继续使用 [A4 的复验入口](../2026-10-24-a4-repair/README.md)，需要对应历史索引和 P5 运行记录库。`run_checks.py` 按本次已归档的外置目录布局串行执行全部检查；`compare_frontend.py` 对两份前端阶段结果执行完整解析 JSON 比较。它覆盖前端阶段的重复提取。

原防抖实现和运行环境可分别检查：

```sh
node experiments/2026-10-25-static-async/probe_source.cjs <original-checkout> <new-probe-output>
python experiments/2026-10-25-static-async/prepare_runtime.py --source <runtime-checkout> --output <new-preparation> --build cluster --build leaks
node experiments/2026-10-25-static-async/probe_browser.cjs <runtime-checkout> <browser-result.json>
python experiments/2026-10-25-static-async/inspect_fixture.py --source <runtime-checkout> --output <fixture-result.json>
```

运行副本需先按 [P5 准备步骤](../2026-10-24-p5/README.md)建立并禁用推送。`prepare_runtime.py` 通过环境变量指定构建参数，源码与锁文件不变；源代码是否干净随结果登记。`probe_browser.cjs` 仅检查 headless 启动与 about:blank 能力，产品行为由 [A5 场景](../../plans/a5-runtime-validation.md)验证。

`diagnose_iframe.py`、`diagnose_graph.py` 用于定位共享连接问题；`evaluate.py --callback-facts` 仅作未发布组件替换诊断。本轮正式结果来自修复后的完整重建。首次构建、组合查询失败及分析预算停止均保留在证据中。

```sh
python experiments/2026-10-25-static-async/check_completion.py
python scripts/check_research.py
```
