# P4：版本化重建与自动刷新

P4 让图随代码提交更新：固定输入版本，重新提取关系，检查通过后发布；构建失败时保留上一成功图，并恢复到最新目标。首版采用全量重建，增量更新保持关闭。

## 首个增量：统一构建入口

已实现 [提交输入导出](../../adapters/snapshot_inputs.py)与[完整建图入口](../../scripts/build_project_snapshot.py)。一次构建依次执行已有协议、数据库与字段、前端消费、回调、传输、连接来源、返回桥接和常量条件提取，输出完整图、输入清单、配置、源码与工具版本。Kuzu 模式写入新的数据库，关闭前验证读回内容与生成图一致。

Git 输入通过 `ls-tree` 和 `cat-file --batch` 读取指定提交的普通文件；不会读入工作区未提交内容。构建期间出现新提交，也不会改变本次输入。源码使用 Git 提交标识，配置保存完整规范化内容，工具记录提交与实际依赖版本；不重新核验文件哈希。

输入规则使用相对 POSIX 路径上的区分大小写 `fnmatch`，`*` 可以跨目录。被排除的文件、符号链接和子模块均写入 `selection.json` 的遗漏记录；符号链接不会被跟随。`.gitattributes` 的 archive 排除和替换不会改变导出的源码。

[所选范围配置](selected-scope.json)沿用 P3 的 154 个路径，用于比较重构前后的首链。这个配置的路径清单固定，新文件须扩大配置范围才能纳入。需要自动接纳新增文件时，使用目录/扩展名模式配置；全仓解析覆盖仍需独立验收。

## 已执行检查

证据类型：执行的合成机制测试。新增 8 项，完整 Python 套件 245 项通过。

- 固定提交导出不受后续提交及脏工作区影响，文件字节保持原样。
- 新增、删除、重命名后的输入选择变化；排除和大小写规则生效。
- archive 属性不会删除或替换输入；符号链接明确跳过，路径越界拒绝。
- 已有导出目录不能覆盖，配置保存独立副本并拒绝未知字段。
- 使用真实 TS/C++ 提取器连续执行两次完整构建：只修改后端协议常量，前端保持不变；第二版不再保留旧匹配，第一版结果仍保留。

测试见 [输入测试](../../tests/test_snapshot_inputs.py)和[完整构建测试](../../tests/test_project_snapshot.py)。后者是测试显式调用两次构建，自动提交检测与发布机制在下一增量实现。CI 在安装 TypeScript 后运行 Python 套件，保证完整构建测试参与执行。

## Insight 整链回归

证据类型：执行的真实源码重建、Kuzu 读回与既有案例断言。公开摘要见 [full-build.json](evidence/full-build.json)，评分程序见 [verify_full_build.py](verify_full_build.py)。评分沿用 P3 独立参考，业务名称不会传入提取器。

固定源码提交 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`，从 Git 导出 154 文件后一次完成全流程：25,355 节点、36,605 关系，Kuzu 全部内容读回一致，P3 的 D01–D05 均通过。首链仍为 373 条关系、589 条源码证据；两处前端状态、四个后端响应出口、数据库候选及反查维持既有验收结果。

旧 P3 图由逐步扩大的输入构建，本次所有提取阶段统一使用最终 154 文件。整图增加 366 个节点，类型为工厂分配、对象绑定、对象路径和字段写入，集中在 `StringUtil.h`、`WsServer.cpp`、`ServerLog.h`、`BaseServer.h`。旧节点 ID 均保留。案例关系通过原断言，整图节点与关系数量不要求等于分阶段产物；节点增量的分类计数保存在公开摘要。

## 复现

安装仓库固定依赖并配置本地解析器缓存后，在研究仓库执行：

```sh
python scripts/build_project_snapshot.py \
  --source ../work/repo-map-research/msinsight-full \
  --revision d4e8d1cf9f90208bcbe5371c127088f6fd66c688 \
  --config experiments/2026-10-23-p4/selected-scope.json \
  --typescript ../work/repo-map-research/code-map-new/node_modules/typescript/lib/typescript.js \
  --output ../work/repo-map-research/results/p4-full-build
```

输出目录必须是新目录，并位于研究仓库和被分析仓库之外。CLI 要求建图实现已提交，以记录可定位的工具版本。输出包括 `source/`、`selection.json`、`request.json`、各提取阶段 JSON、`graph.json`、`graph.kuzu`、`result.json` 与 `build.log`。数据库包含本次构建的 `PMGraph*` 表，不复制旧 CGC 原生索引。

对生成的图执行原案例断言，并记录与 P3 分阶段产物的计数差异：

```sh
python experiments/2026-10-23-p4/verify_full_build.py \
  --build ../work/repo-map-research/results/p4-full-build \
  --python-log ../work/repo-map-research/results/p4-input-tests-01/python-tests.txt \
  --baseline ../work/repo-map-research/results/p3-closure-01/graph.json \
  --output ../work/repo-map-research/results/p4-full-build/verification.json
```

后续增量：[自动刷新、发布与恢复](automatic-refresh.md)已实现提交/配置检测、完整快照发布、`last_success`、锁与进程中断恢复、连续提交追赶。15 项新增测试及完整 Python 套件 260 项通过。旧非图证据、摘要和资产锚点的跨版本处理待完成，P4 保持进行中；增量关闭，U05 不适用。真实运行仍由 P5 验收。
