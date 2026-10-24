# A4 通用机制修复与复验

**本轮验收通过**，结果、版本、成本与剩余覆盖项见[完成报告](completion.md)。事实提取版本 `573330f`，最终查询/校验版本 `3537a62`；两次事实构建一致，后续组件变化由[版本差异检查](evidence/component-versions.json)记录。

本轮从 `106a251` 的失败结果继续，保留[首轮成绩](../2026-10-24-a4/report.md)。六条链已经用于定位缺口，后续结果按开发回归记录。

修复复用现有 TypeScript 编译器解释器、C++ 类型候选、RapidJSON 序列化分析和地图查询。

- R1：直接平台传输成为入口；导出工厂回调保留源身份与导出名称。
- R2：剩余/展开参数、局部 Map 保存、定时回调传参；共享连接表保留此前运行状态未知。
- R3：显式模板注册保留类型实参与依赖静态调用；智能指针工厂保留具体类型。
- R4：数组投影保留元素字段；helper 返回、外部参数转交分别登记；虚函数序列化保留具体响应类型并按对象类型过滤。

复验门槛：六条请求正确连接且无额外错误提供方、两个指定状态连接、直接发送入口可见、原有 19 项链回归通过、更新/删除/失败恢复通过、两次完整构建内容一致。构建对象沿用隔离实验副本 `8b2d4deaf2c995fac11efb280e9ec3b7a1610be9`，原始 Insight 仓库保持不变。

每条路径仍携带源码条件与未知项。定时器模型产生“回调未被取消且实际触发”的候选，不作为运行观测。Worker 转交止于已恢复的调用边界，内部执行另行检查。

原始构建、诊断、图数据库保存在研究仓库外；复验后补入便携结果与成本。`diagnose_protocol.cjs` 通过内存插桩观察转发失败事件，不修改提取规则文件，不作为验收构建器。

## 复现入口

安装仓库根目录列出的 Python/Node 依赖，输出目录使用研究 Git 与源码 checkout 之外的新目录。先用已下载的 Insight checkout 生成独立副本：

```sh
python experiments/2026-10-24-a4/prepare_update.py --source <Insight-checkout> --output <experiment>
```

读取 `<experiment>/preparation.json` 的 `final_revision`，两次调用已有全仓构建器，分别使用新输出目录。复现记录中的提取规则时使用 `573330f`；当前版本也可直接构建，并记录当前工具版本。

```sh
python scripts/build_project_snapshot.py --source <experiment>/source --revision <final_revision> --config <experiment>/config.json --typescript <typescript.js> --output <build-1>
python scripts/build_project_snapshot.py --source <experiment>/source --revision <final_revision> --config <experiment>/config.json --typescript <typescript.js> --output <build-2>
python experiments/2026-10-24-a4/compare_graphs.py --first <build-1>/graph.json --second <build-2>/graph.json --output <comparison.json>
```

使用最终查询代码复验，保留事实图自己的构建版本：

```sh
python experiments/2026-10-24-a4-repair/retest.py --graph <build-1>/graph.json --output <scoring>
python experiments/2026-10-24-a4-repair/run_direct_updates.py --typescript <typescript.js> --output <updates>
python experiments/2026-10-24-a4-repair/verify_navigation.py --graph <build-1>/graph.json --source <experiment>/source --old-index <A3-map.sqlite> --output <navigation>
python experiments/2026-10-24-a4/run_regression.py --source <experiment>/source --build <build-1> --runtime-store <P5-store> --output <known>
python experiments/2026-10-24-a4/probe_publication.py --build <build-1> --source <experiment>/source --output <publication>
```

`probe_serialization.py` 可按源码 include 闭包快速定位一个序列化函数，输出单函数摘要；其结果不替代完整构建。`run_final_checks.py` 保留首次组合验收的目录布局和预算，最终查询/校验修正后的单项复验分别存档。

检查公开结果：

```sh
python experiments/2026-10-24-a4-repair/check_completion.py
python scripts/check_research.py
```
