# P4 自动刷新、发布与恢复

日期：2026-10-24。状态：刷新控制器和正式 CLI 已实现；本批 15 项新增测试、完整 Python 套件 260 项通过。真实 Insight 的两次连续提交、自动追赶和配置失败恢复已执行通过，见 [公开证据](evidence/watch-trial.json)。后续已补齐记录版本和资产锚点处理，P4 总体验收见 [完成报告](completion.md)。

## 工作方式

[控制器](../../adapters/snapshot_refresh.py)观察 Git 提交、规范化配置与建图工具版本。输入身份未变化时复用上一快照；变化后从该提交导出源码，在独立目录全量建图。构建期间的新提交和配置在结束前再次读取，记录最新目标，继续构建直到追上目标或达到本轮构建次数上限。

输出先进入 `staging/<id>/`。验证图的版本、输入范围、节点/关系结构、计数及存储结果后，整体移动到 `snapshots/<id>/`，再原子替换 `state.json`。**只有状态文件登记的快照才算已发布**；移动目录后、更新入口前中断的产物不会被查询入口采用。

`last_success` 始终指向上一份完整发布的快照。失败时记录尝试 ID、错误和日志，保留旧图；下次使用新的尝试目录重建。`target` 记录最新观察的源码、配置和工具版本。每轮最多构建四次，仍有新目标则保留 `pending`，监听循环继续追赶。

写入使用操作系统锁。进程退出会释放锁，锁文件本身可以长期存在。新控制器取得锁后，将遗留的进行中尝试记为中断并重试；不会根据锁文件年龄或 PID 猜测工作是否仍在进行。每份图数据库独立，失败的数据库不会成为下一次尝试的输入。

读取使用 `read_snapshot(store, snapshot_id=None)`：默认返回最后成功图及刷新状态；指定已发布 ID 可读历史版本。`current_at_observation` 表示与最近一次观察的提交和配置一致，附观察时间；构建、失败或历史版本标为 `historical_or_pending`。输入范围始终是已提交源码，工作区未提交修改不进入图。

CLI 在启动时固定执行中的工具版本。工具代码或依赖发生变化时，本次尝试失败并要求重启监听，避免将已加载的旧 Python 代码标成新版本。普通研究文档提交不改变工具版本；工具版本取最后一次涉及实现或依赖声明的提交。

## 执行入口

[refresh_project_map.py](../../scripts/refresh_project_map.py)支持一次检查与持续监听：

```sh
python scripts/refresh_project_map.py \
  --source ../work/repo-map-research/msinsight-full \
  --config experiments/2026-10-23-p4/selected-scope.json \
  --typescript ../work/repo-map-research/code-map-new/node_modules/typescript/lib/typescript.js \
  --store ../work/repo-map-research/results/insight-snapshots \
  --watch --interval 2
```

省略 `--watch` 时检查并追赶一次；可由 CI 的提交事件调用。`--max-builds` 控制单轮构建上限；`--revision` 默认监听本地 `HEAD`。远端代码的拉取由现有 CI/仓库同步流程负责。退出码：0 已追上目标，2 构建/观察失败或还有待追赶目标，3 存储被其他刷新占用，4 执行中工具版本变化需重启，130 用户中断。

存储目录位于源码和研究仓库之外，保留快照、输入导出和失败日志。当前没有自动删除历史快照的策略。

## 已执行测试

证据类型：执行的合成控制器测试与真实提取器机制测试。测试输入为自编协议样例，区别于 Insight 产品源码试验。

| 检查 | 执行结果 |
|---|---|
| 首次发布、输入不变、脏工作区 | 发布一次；复用旧图；未提交内容不进入图 |
| 源码、范围、部署配置、工具版本变化 | 重新构建并记录新身份 |
| 构建抛错、版本错配、计数错误、悬空边 | 拒绝发布，保留上一成功入口与日志 |
| 写状态失败、目录已移动但入口未切换 | 旧入口可读，未登记目录不能作为已发布快照查询 |
| 构建中强制结束真实子进程 | 锁释放；半成品不发布；恢复后追到新目标 |
| 锁冲突 | 第二个控制器不改状态，之后可重试 |
| 构建期间连续提交两次 | 原输入保持固定，合并追赶到最后提交 |
| 达到单轮构建上限 | 目标保留为 pending，后续一轮完成 |
| 持续监听下的跨文件常量变化 | 前端文件不变，旧协议匹配自动消失 |
| 持续监听下新增/删除处理器、注册及消费者 | 新关系出现，旧定义和连接不残留 |
| 持续监听下文件/符号改名及同名干扰 | 新身份指向新处理器，同名无关方法不接入 |
| 只修改部署配置 | 源码提交不变，两端服务作用域改变后连接重算 |
| 历史图查询 | 保留原版本、原关系，显示历史状态 |

控制器故障测试见 [test_snapshot_refresh.py](../../tests/test_snapshot_refresh.py)，自动跨语言刷新见 [test_snapshot_watch.py](../../tests/test_snapshot_watch.py)。后者在后台循环监听 Git 和配置，测试线程只提交源码或写配置，不显式调用重建。

## Insight 监听试验

[run_watch_trial.py](run_watch_trial.py)创建独立 Insight checkout，启动正式 CLI，在第一次构建期间连续提交两次：先添加范围外的实验说明，再修改后端 `unit/flows` 常量为 `unit/flows/p4-probe`；前端保持不变。监听器先发布原快照，再自动追到最后提交，原消费者与新提供方失配。随后注入无效配置，旧入口保留；修复配置后恢复到最新成功状态，没有生成重复快照。

原始 154 文件图为 25,355 节点、36,605 关系，P3 的 D01–D05 原断言全部通过；变更后为 25,281 节点、36,482 关系。两份 Kuzu 数据库均完成完整内容读回验证。原图继续绑定原提交并可查询，中间提交合并到最后目标。变更是实验主动注入的协议失配，用于验证刷新，不作为 Insight 已有缺陷。

规则提交 `b19fa52b8e7bd6d4063cf7c63c8dc8840c1074c2`，完整运行版本以 [watch-trial.json](evidence/watch-trial.json)为准。原始 checkout、图、数据库、日志、状态和改动补丁保存在仓库外 `results/p4-watch-trial-01/`。

复现：

```sh
python experiments/2026-10-23-p4/run_watch_trial.py \
  --source ../work/repo-map-research/msinsight-full \
  --output ../work/repo-map-research/results/p4-watch-trial \
  --config experiments/2026-10-23-p4/selected-scope.json \
  --typescript ../work/repo-map-research/code-map-new/node_modules/typescript/lib/typescript.js \
  --python-log ../work/repo-map-research/results/p4-controller-tests-01/python-tests.txt
```

## 后续门槛

U01、U02、U04 已通过本批机制测试与所选 Insight 源码试验。U03、U06 的后续记录与锚点验收见 [记录报告](versioned-records.md)。增量关闭，U05 不适用。真实运行行为保持 P5 的验收范围。
