# 前端返回值、字段消费与状态更新

在 Insight 的两个 `getUnitFlows` 调用入口中，已自动提取返回字段到 `session.singleLinkLine` 的依赖，并单独记录请求完成后的四处状态更新。查询可以从 API 返回字段找消费者，也可以从一个有作用域的状态位置反查请求。**D02 继续连接响应传输、回调匹配、前端解包与本次 API 返回值边界；D03、D05 随整链验收。**

## 输入、方法和证据

- 输入：Insight 提交 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`，[148 文件清单](response-manifest.json)，基础图为 [响应对象与路由增量](response-routing.md) 的 `p3-data-v5`。
- 工具：TypeScript **5.9.3**、已有 P1 编译器事实提取和 P2 协议图；新增 `typescript_data_flow/0.1.0`、前端关系导入及查询。规则提交 `090f31bbe477850ec0dd5633243f8dae72fab527`。
- API 起点由协议图中已匹配消息的 `EMITS_MESSAGE` 关系提供。编译器解析直接调用这些 API 的函数，再沿局部变量、对象/数组构造、实参、源码辅助函数和回调展开。业务名称用于本报告和验收脚本；提取器按语法、符号和数据来源工作。
- 执行证据：[frontend-consumers.json](evidence/frontend-consumers.json)。这是执行源码提取、查询和数据库存储的结果；Insight 产品没有在该实验中运行。
- 编译选项沿用固定分析预设，读取清单内的路径别名。外部依赖和清单外源码保持未知。API 的 Promise 成功值在这一增量中作为输入边界。

## 实测关系

| 入口 | 源码状态赋值位置 | 返回字段影响状态值 | 请求完成后执行的其他赋值 |
|---|---|---|---|
| `getSingleFlow` | `modules/timeline/src/components/FilterLinkLine.tsx:448–449` | `session.singleLinkLine = newLines` | `session.renderTrigger` |
| `onClick` | `modules/timeline/src/insight/units/AscendUnit.tsx:800–803` | `session.singleLinkLine = newLines` | `session.drawLineMode`、`session.linkLines`、`session.renderTrigger` |

两个入口都经过源码中的 `buildSingleLinkLines`。返回数组遍历后构造类别字典和连线对象，提取到六种来源路径：

```text
unitAllFlows[*].cat
unitAllFlows[*].flows[*].cat
unitAllFlows[*].flows[*].from
unitAllFlows[*].flows[*].from.dbPath
unitAllFlows[*].flows[*].to
unitAllFlows[*].flows[*].to.dbPath
```

`from`、`to` 是对象来源，`dbPath` 是辅助函数按条件选取的字段。对象展开、字段覆盖、循环和调用位置随证据保存。路径指向返回值中的来源，不能据此认为赋值前后的整个对象完全相同。

图使用 `VALUE_MAY_REACH_STATE_WRITE` 表示字段对状态值的候选影响，使用 `FULFILLMENT_PRECEDES_STATE_WRITE` 表示请求完成后的执行关系。因此查询 `unitAllFlows` 字段返回两处 `singleLinkLine` 赋值；仅查询 API 时，同时显示四处完成后执行的其他赋值。刷新表达式从当前状态取值，其值依赖与请求完成关系分别表达。

同一个 API 的两次调用各有请求上下文；状态位置按入口、参数根对象和属性路径区分。辅助函数内的读取保留调用链，`runInAction` 回调附带外部函数实际调用回调的条件。已知源码函数只按其函数体展开；未调用的闭包不会自动产生状态更新。

## 验证结果与范围

完整图为 **23,725 个节点、34,474 条关系**。本次分析覆盖三个直接 API 调用入口，提取三次调用、25 条字段读取和六条状态赋值；其中两个入口属于本例，另一个入口用于检查不同 API 的隔离。

**158 项 Python 测试、36 项 TypeScript 测试通过。** 新增测试验证请求上下文、改名、字段赋值、辅助函数参数、未等待 Promise、分支条件、未知调用和受限查询。完整图保存到原生 CGC/Kuzu 副本后，JSON 数据读回一致，前端查询及原有四条后端响应查询一致，790 条原生函数记录保持一致。

查询明确保存以下缺口：

- API 成功值与后端 JSON 字段之间的传输、回调表匹配和拆包尚待连接。
- `getFlowPointIdentity` 等清单外调用、部分集合方法和接收对象尚未展开；传入返回数据的未知调用附带可能改写对象的诊断，后续字段关系保留此缺口。
- 状态根目前取直接 API 调用入口的参数。跨入口捕获状态、框架 setter、跨分支调用者别名效应和异常路径需要继续扩展。
- 数组按一个符号元素分析；分支、循环、外部回调及未知对象选择保留条件。查询结果描述静态候选，实际执行由 P5 验证。

## 复现

在研究仓库根目录执行。`SOURCE` 指向上述 Insight checkout，`TS` 指向 TypeScript 5.9.3 的 `lib/typescript.js`，`BASE` 指向 `p3-data-v5` 图，`OUT` 和 `STORE` 使用新的仓库外目录。Windows 的原生 Kuzu DLL 配置沿用 [P1 复现](../2026-10-23-p1-completion/reproduce.md)。

```sh
python scripts/build_frontend_graph.py --source "$SOURCE" --manifest experiments/2026-10-23-p3/response-manifest.json --base "$BASE" --typescript "$TS" --output "$OUT"
python scripts/query_data_graph.py "$OUT/graph.json" --frontend-api getUnitFlows
python scripts/query_data_graph.py "$OUT/graph.json" --frontend-api getUnitFlows --field-path '["unitAllFlows"]'
python scripts/query_data_graph.py "$OUT/graph.json" --frontend-state '<state_node returned by the query>'
python -m unittest discover -s tests -v > "$OUT/python-tests.txt" 2>&1
npm test > "$OUT/typescript-tests.txt" 2>&1
python experiments/2026-10-23-p3/run_frontend_consumers.py --graph "$OUT/graph.json" --cgc-db "$CGC_DB" --output "$STORE" --python-log "$OUT/python-tests.txt" --typescript-log "$OUT/typescript-tests.txt"
python scripts/check_p3_frontend_consumers.py
```

评分器的预期字段与入口用于核对提取结果。图生成与查询不读取评分器或人工参考答案。版本检查读取 Git 提交，不重新核验文件哈希。
