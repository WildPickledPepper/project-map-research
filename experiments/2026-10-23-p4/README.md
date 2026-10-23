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

当前入口完成一次构建。提交监测、临时快照原子发布、`last_success`、锁及中断恢复、连续提交追赶尚待实现；U01–U04、U06 保持待验收，U05 因增量关闭不适用。真实运行仍由 P5 验收。
