# P4 记录版本与资产锚点

日期：2026-10-24。证据类型：已执行的合成记录测试和真实提取器改名测试，完整 Python 套件 274 项通过。真实 Insight 快照上的记录试验由 [run_record_trial.py](run_record_trial.py)执行；记录内容明确标为 synthetic。P5 的产品运行与 P6 的真实资产接入分别验收。

## 保存与查询

[snapshot_records.py](../../adapters/snapshot_records.py)保存四类不可变记录：运行 trace、职责摘要、验证结果和资产锚点。生产者先取得已发布快照的 `basis`，在生成记录后原样提交；basis 包含快照 ID、源码提交、完整建图配置与工具版本。写入时核对已发布收据，拒绝缺失或不一致的版本。每条记录保存生产者名称/版本、来源引用、证据类别及原始 payload。

记录按独立 UUID 目录原子发布，没有更新旧记录的接口；未写完的目录不会被查询采用。记录可以晚于新图提交，仍属于生产者指定的旧快照。写记录不修改图、Kuzu 数据库或刷新状态。

查询同时返回原始 basis 和请求的 basis。相同快照可以直接叠加；不同源码、配置、工具或快照 ID 都显示版本差异并关闭直接叠加。查询旧版本仍可看到旧结果，当前刷新失败时会同时显示旧图的新鲜度。`eligible_for_direct_overlay` 只表示版本允许映射；记录中的测试结论仍是带来源的生产者声明。

CLI [snapshot_records.py](../../scripts/snapshot_records.py)：

```sh
python scripts/snapshot_records.py --store ../work/repo-map-research/results/insight-snapshots basis
python scripts/snapshot_records.py --store ../work/repo-map-research/results/insight-snapshots append --input submission.json
python scripts/snapshot_records.py --store ../work/repo-map-research/results/insight-snapshots query --kind trace
python scripts/snapshot_records.py --store ../work/repo-map-research/results/insight-snapshots query --id RECORD_ID --snapshot SNAPSHOT_ID
```

提交对象包含 `kind`、`basis`、`provenance`、`payload`、`anchors`。每个 anchor 有记录内唯一的 `label` 和原图 `node_id`；无法定位的事件带 `reason` 保存。运行构建、测试数据、场景与断言内容由生产者放在 payload，P5 将提供真实采集与场景校验。

## 改名、同名与失效

首次关联从原图保存类型、路径、名字、参数签名及存在的接口作用域/命令等选择器。跨快照只做这些字段的精确匹配：单个匹配为候选，多个为歧义，无匹配为悬空；行号和哈希不参与重定位。候选只供进一步核实，契约适用性单独显示尚未评估。所有查询明确返回 `verification_carried_forward: false`。

相同节点 ID 不足以继承历史记录。记录原本未映射的事件继续显示缺口；后来出现同 ID 节点也不会自动补齐历史映射。文件/符号改名后，需要新的明确关联依据，原记录继续保留原位置和版本。

## 已执行检查

[记录测试](../../tests/test_snapshot_records.py)覆盖四类记录跨版本保存、同源码下配置/工具变化、延迟提交、刷新失败时旧图状态、错误生产者版本、改名/删除、复用 ID 但接口改义、多候选、未映射事件、并发追加、写入失败恢复以及正式 CLI。

[自动监听测试](../../tests/test_snapshot_watch.py)使用真实 TS/C++ 提取器：在旧处理器上挂 synthetic 资产锚点，随后修改处理器名称与文件路径，并增加其他作用域的同名方法。自动刷新后旧锚点悬空，原快照仍可定位，旧验证不会迁移。

回归中发现 Windows 读状态文件可能短暂阻止替换，已为原子写入增加最多 0.95 秒的有限重试；持续失败仍保留旧文件并报错。两项故障测试分别验证短暂占用恢复和持续失败。

## 验收归属

已在 Insight 两份已发布图上执行四类记录的版本试验：旧记录完整保留，新图中的旧注册锚点悬空，未变客户端仅为候选，全部关闭跨版本直接叠加与验证继承。见 [公开结果](evidence/record-trial.json)和 [完成报告](completion.md)。

以上检查补足 U03 的历史锚点失效和 U06 的非图记录版本隔离。U01、U02、U04 的证据见 [自动刷新报告](automatic-refresh.md)。首版只读取已提交源码，未提交工作区不纳入；增量关闭，U05 不适用。真实运行关联及资产业务适用性仍按后续阶段验收。
