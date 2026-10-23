# P1 完成版复现

从研究仓库根目录运行。需要 Python 3.11、Node 22，以及 Insight 的固定提交 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`。生成目录使用尚不存在的仓库外目录。无需 AI 模型或 API Key。

```sh
python -m pip install -r requirements-store.txt
npm ci --ignore-scripts --no-audit --no-fund
python -m unittest discover -s tests -v
npm test
```

Windows Kuzu 若需要独立 VC 运行库目录，设置 `PROJECT_MAP_DLL_DIR`；已有语言包缓存可设置 `PROJECT_MAP_PARSER_CACHE`。Linux CI 使用相同 Python/Node 依赖。第三方工具版本与原生索引复现见[前一轮说明](../2026-10-23-p1/reproduce.md)。

## 从源码生成图

```sh
python scripts/build_fact_graph.py --source /path/to/msinsight --output /outside/new-facts
python experiments/2026-10-23-p1-completion/run_fixtures.py --output /outside/new-fixtures
```

默认 manifest 是前一轮的 65 文件清单；默认 TypeScript 来自本仓库 npm 安装。也可用 `--typescript /path/to/typescript/lib/typescript.js` 指向已安装的 5.9.3。构图入口检查 Git 提交和输入路径，不重新核验文件哈希。生产 `cpp.json`、`typescript.json`、`graph.json`；无参考图输入参数。

```sh
python scripts/query_fact_graph.py --graph /outside/new-facts/graph.json --start getUnitFlows --target ClientConnector.send --kinds OBSERVES_CALL,USES_BINDING,BINDS_CALLABLE,STATIC_CALL_TARGET,STATIC_DECLARATION_TARGET,PASSES_CALLBACK
python scripts/query_fact_graph.py --graph /outside/new-facts/graph.json --start ClientConnector.send --target getUnitFlows --reverse --kinds OBSERVES_CALL,USES_BINDING,BINDS_CALLABLE,STATIC_CALL_TARGET,STATIC_DECLARATION_TARGET,PASSES_CALLBACK
```

同名实体必须使用精确节点 ID。输出保留节点位置、条件、边类型和候选状态，深度上限通过 `--max-depth` 设置，触及限制会标注。未找到路径不代表没有依赖。它返回结构关系路径；实际调用顺序由后续运行证据提供。

## 验证真实存储

准备前一轮已关闭的 CGC 原生运行目录（含 `cgc.kuzu`）和 CodeGraph 原生运行目录（含 `cache/*/graph.db`），执行：

```sh
python experiments/2026-10-23-p1-completion/run_completion.py --graph /outside/new-facts/graph.json --cgc-run /outside/native-cgc --codegraph-run /outside/native-codegraph --output /outside/new-stores
```

此命令只写新目录中的数据库副本。对两种库执行相同 graph 的往返、替换、删除、恢复、另一快照保留与真实链路评分；检查相关原生记录原值，并以 SQL/Cypher 直接查询同一候选边的正反方向。

本次成功输出位于工作区相对路径：

- `work/repo-map-research/results/p1-completion-04/`：真实源码生成图。
- `work/repo-map-research/results/p1-completion-fixtures-02/`：共用 3 个合成样例结果。
- `work/repo-map-research/results/p1-completion-stores-04/`：两种原生库副本与最终验收证据。
- `work/repo-map-research/results/p1-codegraph-storage/final-run/`：独立 CodeGraph SQL CLI 试验；发生于用户要求停止文件哈希核验之前，历史记录保留。

调试期间的失败包括：第一次路径评分发现缺少“传入回调”边，已增加类型化关系并回归；收紧输入读取时暴露 Windows 标准库路径分隔符问题，已统一路径；共用 fixture 的定义配对断言由误写的 3 组纠正为源码中的 2 组。最终成功运行使用上述目录。

日常检查：

```sh
python scripts/check_research.py
python scripts/check_trial_evidence.py
python scripts/check_p1_evidence.py
python scripts/check_p1_completion.py
```

这些检查验证公开材料、版本、关系证据和门槛记录，不重跑产品、原生索引或重新核验文件哈希。CI 另行执行 Python/TS 自动测试；真实源码及原生数据库复现按上面的命令执行。
