# 请求编号、发送字段与响应查找键

已在 `unit/flows` 上自动恢复 **发送 JSON 的 `id` → C++ 请求字段 → 响应字段 → JSON `requestId` → 前端回调查找键** 的来源关系。四个后端响应出口均可查询，提前返回的错误响应也携带这条编号复制关系。**P3、D02 继续实施：C++ 响应实际发送、端点对应、iframe 返回包装和业务 API 解包仍需连接。**

## 输入与规则

输入是 Insight 提交 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688` 的 [148 文件清单](response-manifest.json)。沿用 [前端消费](frontend-consumers.md) 的 `p3-data-v6` 基础图，使用 TypeScript **5.9.3** 和 `typescript_response_flow/0.2.0` 重新提取响应回调、请求发送与计数器来源，再组合已有 P2 协议证据和 P3 C++ 字段证据。

实现提交 `41f003a`，解码候选键修正提交 `e4fc2bc`。执行证据见 [request-correlation.json](evidence/request-correlation.json)。新增逻辑在 [TypeScript 值传播器](../../adapters/typescript_data_flow.cjs)与 [编号关联查询](../../adapters/correlation_queries.py)中，业务名称只用于本报告和评分器。

## 自动提取的连接

| 段落 | 来源关系 | 检查依据 |
|---|---|---|
| WebSocket 请求 | 递增前的 `_msgId` 同时进入消息 `id` 和回调表键 | 局部变量、数值型后缀递增、源码辅助函数和同一次 Promise 构造 |
| iframe 请求 | `_curFetchSequenceID` 先写入 `params.id`，再以递增前的值登记回调 | 参数对象字段赋值、别名及发送时 JSON 快照 |
| C++ 请求解码 | JSON `id` 进入请求对象的 `id` | 当前提供方的解码调用可达范围及接收对象类型 |
| C++ 响应构造 | `response.requestId = request.id` | 实参与形参映射、请求参数根对象、响应对象根及写入位置 |
| 响应序列化 | 响应字段进入 JSON `requestId` | 当前响应路由和注册的序列化回调 |
| 前端回调选择 | `JSON.parse(ev.data).requestId` 用于回调表查找 | 与登记相同的回调表、接收对象类型和五条交付候选中的对应查找 |

三条请求字段绑定分别来自一个 WebSocket 发送候选和两个 iframe 发送分支；两个 iframe 候选来自同一源码发送位置的不同数组/分支展开。它们分别关联自己的 Promise 和回调登记，不跨请求共享编号来源。

跨语言组合要求 P2 已匹配到当前提供方，发送位置与协议路径一致，并且路径确实经过对应的请求函数。C++ 一侧要求当前解码器可达、类型兼容、来源是处理函数的请求参数，并存在字段复制和响应序列化证据。已知后续覆盖会阻断原复制关系；多个候选解码键保持歧义，不解释成嵌套路径。

## 实测和验证

完整图为 **23,813 个节点、34,616 条关系**。本次提取 11 个发送候选、10 个计数器更新、3 条请求字段绑定；其中 WebSocket 编号关系与 `unit/flows` 的 **4 个后端响应出口**组合成功。计数描述所选源码中的候选事实，不代表运行次数。

**170 项 Python、53 项 TypeScript 测试通过。** 用例覆盖递增前后值、发送后改写、同名自定义 socket、未知数值转换、不同请求、矛盾条件、字段被覆盖、错误提供方、不同类型、不可达解码器及歧义字段。实测中移除请求解码来源后，四条编号关联均消失，后续同名字段不会补出连接。

完整图在 CGC/Kuzu 副本中读回一致，编号、回调和前端消费查询一致，790 条原生函数记录保持一致。初次存储验证对应 169 项 Python 测试；补充解码键歧义用例后，执行 170 项测试并只读查询已保存数据库，结果保持一致。此实验执行静态提取和查询，产品运行证据仍由 P5 补充。

## 当前条件与下一步

编号关系描述同一次请求中的值来源。运行时实例、序列化保持键值、登记仍有效、数据未被未知调用改写，以及请求与响应属于同一交换过程，仍是候选条件。计数器初值没有被当作每次调用的编号，键的全局唯一性和运行时生命周期尚未证明。WebSocket 联合类型中的实际实现也保留为运行时选择。

下一步沿 C++ 序列化结果补字符串构造和实际发送，再连接响应接收端、框架的返回包装、iframe 解包与业务 API 返回值。条件队列路径继续保留缺口。之后完成 D03 的跨传输反查及 D05 整链验收。

## 复现

在研究仓库根目录运行。`SOURCE` 指向固定 Insight checkout，`TS` 指向 TypeScript 5.9.3 的 `lib/typescript.js`，`BASE` 为 `p3-data-v6` 图，`OUT`、`STORE` 为新的仓库外目录。`CGC_DB` 为已关闭的原生 CGC 数据库；Windows DLL 配置沿用 [P1 复现](../2026-10-23-p1-completion/reproduce.md)。

```sh
python scripts/build_callback_graph.py --source "$SOURCE" --manifest experiments/2026-10-23-p3/response-manifest.json --base "$BASE" --typescript "$TS" --output "$OUT"
python scripts/query_data_graph.py "$OUT/graph.json" --correlation-provider 'provider:registry:cdb1a04ef30726dc964f3a66:registry:8cc84bafd0ccae7c02b7357d'
python -m unittest discover -s tests -v > "$OUT/python-tests.txt" 2>&1
npm test > "$OUT/typescript-tests.txt" 2>&1
python experiments/2026-10-23-p3/run_request_correlation.py --graph "$OUT/graph.json" --cgc-db "$CGC_DB" --output "$STORE" --python-log "$OUT/python-tests.txt" --typescript-log "$OUT/typescript-tests.txt"
python scripts/check_p3_request_correlation.py
```

其他项目或版本从生成图选取提供方 ID。图生成与查询不读取评分器或人工参考答案；不重新核验文件哈希。
