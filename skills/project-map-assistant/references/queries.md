# 查询指南

以下省略共同前缀 `python SKILL/scripts/project_map.py --workspace WORKSPACE`。stdout 是 UTF-8 JSON，错误及构建进度写 stderr；失败退出码 2。

| 需求 | 命令 |
|---|---|
| 模块及覆盖 | `query overview --limit 20` |
| 跨模块关系分组 | `query links --module MODULE` |
| 模块文件及处理状态 | `query files --module MODULE` |
| 按名称找节点 | `query search --text NAME --kind KIND` |
| 协议入口、提供方 | `query entries --name NAME`、`query providers --text COMMAND` |
| 邻接及条件 | `query neighbors --start NODE_ID --direction out` |
| 正向关系 | `query trace --start NODE_ID --depth 6` |
| 反向影响 | `query impact --start NODE_ID --depth 6` |
| 两点路径 | `query path --start NODE_ID --target OTHER_ID --depth 12` |
| 节点解析状态 | `query status --start NODE_ID` |
| 源码解析诊断 | `query diagnostics --path RELATIVE_PATH` |
| 展开完整依据 | `query detail --entity node --id NODE_ID --pointer /evidence` |
| 固定版本源码 | `query source --start NODE_ID --context 8` |
| 字段的组合说明 | `explain ENTRY --field FIELD --seconds 30` |

`detail` 的 entity 支持 node/edge/provider/entry/diagnostic；使用查询返回的 detail 地址及 pointer，避免自行猜测 ID。`source` 也支持 `--path RELATIVE_PATH --line LINE`，读取 Git blob。

`explain` 用重复 `--field` 表示字段路径，例如 `--field body --field items`。它复用既有组合查询器，单独进程加载原图；大图会消耗较多内存，时间预算到期返回截断状态。一般导航使用 SQLite 索引，不需要完整加载原图。

## 分页和预算

分页复用相同查询参数、`--cursor RETURNED_CURSOR` 和 `--snapshot RETURNED_SNAPSHOT`。游标绑定查询、快照及导航版本，刷新后的游标需要重新开始。跨多步分析固定返回的 snapshot；如被版本检查拒绝，先重新读取 status。

普通查询默认时间 3 秒、节点 200、边 500、输出 128 KiB。按需设置 `--seconds`、`--nodes`、`--edges`、`--output-bytes`、`--limit`；当前最大值分别为 30 秒、5000、10000、1 MiB、200。trace/path/impact 的 `--kinds TYPE1,TYPE2` 可缩小遍历关系。

`impact` 是静态关联的反向遍历，须结合边类型和条件判断影响。空结果、歧义、未知类型、动态 SQL、未配置的部署边界，以及遍历预算耗尽都需要明确处理；源码证据决定已知部分，运行场景补充实际发生的部分。
