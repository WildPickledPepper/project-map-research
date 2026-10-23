# P2 复现

在研究仓库根目录运行。依赖 Python 3.11、Node 22、TypeScript 5.9.3 和 `requirements-store.txt`。Insight checkout 使用提交 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`。原生 CGC 数据库沿用 [P1 复现](../2026-10-23-p1-completion/reproduce.md)。

```sh
python -m pip install -r requirements-store.txt
npm ci --ignore-scripts --no-audit --no-fund
python scripts/build_protocol_graph.py --source /path/to/msinsight --output /outside/new-p2-graph
```

生成 `typescript.json`、`cpp.json`、`graph.json`。输入来自 [manifest](input-manifest.json)；额外的插件头文件为包含上下文，提供常量可见性证据。`--typescript` 可指向已有 `typescript/lib/typescript.js`。源码构图不读取预期端点，服务目录归属来自 [deployment.json](deployment.json)，通过 `--deployment` 更换。

```sh
python scripts/query_protocol_graph.py /outside/new-p2-graph/graph.json --from getUnitFlows --to Dic::Module::Timeline::QueryFlowsBySliceInfoHandler::HandleRequest
python scripts/query_protocol_graph.py /outside/new-p2-graph/graph.json --from Dic::Module::Timeline::QueryFlowsBySliceInfoHandler::HandleRequest --to getUnitFlows --reverse
python scripts/query_protocol_graph.py /outside/new-p2-graph/graph.json --explain queryTimelineOffset
```

查询返回有类型的路径、源码位置、条件和缺口。`--explain` 查看匹配状态；同名定义歧义时使用节点 ID。默认深度 12，可用 `--depth` 修改。图中的源码证据可展开到每次参数传递和字段赋值。

```sh
python experiments/2026-10-23-p2/run_completion.py --graph /outside/new-p2-graph/graph.json --cgc-db /outside/native-cgc/cgc.kuzu --output /outside/new-p2-store
```

该命令在构图完成后评分三条真实接口，执行 Python/TS 正反例，并在新目录的 CGC 副本中写入、查询、替换、删除和恢复图。输出 `completion.json`、测试日志和数据库副本。关闭原生数据库后再复制。Windows 可用 `PROJECT_MAP_DLL_DIR` 指定 VC 运行库目录，已有语言解析器缓存可用 `PROJECT_MAP_PARSER_CACHE`；TypeScript 测试可通过 `NODE_PATH` 使用已有 npm 目录。

成功运行的工作区相对位置：

- `work/repo-map-research/results/p2-completion-02/`：规则冻结后的真实源码图。
- `work/repo-map-research/results/p2-stores-01/`：最终评分、测试日志和存储试验。

开发期间修正了简写对象属性取值、C++ 包含上下文、析构函数被当作入口、未知值覆盖后保留旧值、空集合回调以及条件返回合并。相应行为已加入最终测试。所有运行均使用源码副本/新输出目录，保留产品源码。

```sh
python scripts/check_research.py
python scripts/check_trial_evidence.py
python scripts/check_p1_evidence.py
python scripts/check_p1_completion.py
python scripts/check_p2_completion.py
```

这些命令检查公开证据与引用；CI 还执行适配器测试。CI 不下载 Insight 源码或重跑原生索引，真实图复现使用上述命令。全过程按 Git 版本和行为结果追踪，不重新核验文件哈希。
