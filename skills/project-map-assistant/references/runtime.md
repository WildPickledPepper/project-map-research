# 运行证据

运行记录从既有采集流程导入，不会因建图而自动产生。首次接入新项目需要设置边界采集点、执行可复现场景及断言，然后使用版本记录 API 保存事件和映射。当前随工具保留 `adapters.snapshot_records` 和 `adapters.runtime_records`；MindStudio 实验的业务插桩没有被复制进分发包。

已有记录可在 `attach --graph GRAPH --runtime-store STORE` 关联；两者必须属于同一快照。`runtime` 列出场景、结果和阶段计数。列表中的 `same_snapshot` 只确认静态版本，不能单独证明环境适用。

查询单条映射：

```text
python SKILL/scripts/project_map.py --workspace WORKSPACE runtime --id RECORD_ID --context CONTEXT.json --limit 20
```

CONTEXT 包含五个键：`source_commit`、`build`、`runtime_config`、`data`、`scenario`。后四项是采集流程实际记录的非空对象，应由当前构建和复现流程提供，不能从旧记录复制后当作新的验证。

检查 `eligible_for_direct_overlay`、`version_differences`、`runtime_context_differences`。任一不匹配时保留记录供对照，不能把其中节点标记为当前场景已执行。一次采集只覆盖实际经过的场景与采集点；未映射阶段保留诊断。
