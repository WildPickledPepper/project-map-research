# 原生 socket、接收绑定与响应回调表

已把前端请求使用的 socket 接到 `onmessage` 绑定，再沿事件参数进入 JSON 解析、响应编号查找和 Promise 交付。结合上一批 C++ 发送证据，`unit/flows` 的 **四个响应出口**均可查询到这条前端接收路径。跨网络组合沿用已配置的逻辑服务关系；服务端接受连接到会话 socket 的来源、实际 host/port/proxy 对应仍待补充。

## 输入与实现

输入保持 Insight 提交 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688` 的 [150 文件](transmission-manifest.json)，基础图为 [C++ 发送增量](transmission.md)的 `p3-data-v9`。TypeScript 编译器版本为 **5.9.3**，实现提交 `6c006b9`，执行证据见 [socket-receivers.json](evidence/socket-receivers.json)。

[socket 提取入口](../../adapters/typescript_socket_flow.cjs)复用已有 TypeScript 值传播器，增加专用分析入口。它根据标准库声明识别 WebSocket，以字段声明、实参来源和分配上下文标识通道，并提取创建、赋值、发送和接收绑定。业务类、字段、方法、URL 参数名均来自源码。

[接收查询](../../adapters/socket_queries.py)要求请求发送与监听绑定指向同一来源通道、回调拥有正确的 `this` 语义，且回调查找键确实来自该处理函数的事件参数。平台模型使用 `message` 事件的 `MessageEvent.data`；依据见 [WHATWG WebSockets 标准](https://websockets.spec.whatwg.org/#feedback-from-the-protocol)（2026-10-23 查阅）。

## 自动提取结果

| 源码段 | 结果 | 保留的条件 |
|---|---|---|
| `connection.ts:95、103、114` | 三处原生 WebSocket 创建，赋给同一个类字段 | JupyterLab 代理、普通路径和代理路径的分支选择 |
| `connection.ts:82` | VS Code 包装通道赋值 | 来源未展开，与原生创建分别记录 |
| `connection.ts:284` | 请求发送使用该字段 | socket 已定义，实际实例属于原生分支 |
| `connection.ts:151` | 建连阶段的接收回调 | 该回调仅完成建连 Promise，没有被接到业务响应表 |
| `connection.ts:182` | 请求阶段安装业务接收回调 | 原处理函数非空且 `_fetchFlag` 为真；安装后持续有效 |
| `connection.ts:219、226、248` | 回调事件参数 → JSON 解析 → 编号查表 | 消息类型、解析成功及已有响应筛选条件 |
| `connection.ts:204` 起 | 三种 Promise 交付候选 | 完整响应、响应 body 或错误对象，各自保留条件 |

三个 URL 都保存表达式树和来源，包括初始化端口、页面地址、字符串组合与路径替换。动态值保持符号形式；地址是否指向当前后端需结合服务端来源和运行配置核实。

查询按请求上下文组合：一个前端接收关系，三个创建候选，一个未展开的通道赋值，三种 Promise 交付候选，以及四个后端响应出口。每个出口保留上一批的三个编码分支发送路径，总计仍为 12 条 C++ 来源路径。

## 验证

完整图为 **24,198 节点、34,740 条关系**，快照为 `p3-data-v10`。本批提取四个分析入口、三个创建、四个通道赋值、两个监听绑定和两个发送上下文。

**195 项 Python、67 项 TypeScript 测试通过。** 新增检查覆盖改名、socket 别名、不同字段、不同接收对象、同步覆盖、条件清除、`await` 后清除、箭头函数与显式 `bind`、未绑定方法、同名自定义 WebSocket、联合类型分支、类字段初始化、不同分配、动态 URL 来源与预算截断。

同步安装后立即清除会使原绑定在该入口失效；跨过 `await` 的后续清除保留为生命周期条件，因为等待期间可能收到响应。真实图中移除业务接收函数绑定后，四条后端到接收端的组合全部消失，原有 12 条 C++ 发送路径仍然保留。

完整图在 CGC/Kuzu 副本中读回一致，提供方接收查询、独立接收查询和 C++ 发送查询一致，790 条原生函数记录保持一致。本批执行源码提取与存储查询，产品运行证据属于 P5。

## 剩余工作

P3、D02 继续实施。接下来补服务端接受连接、创建会话和保存 channel 的来源，再连接框架返回包装、iframe 转发和业务 API 解包。Windows GBK 转换与条件队列仍有来源缺口，D03 跨返回链反查和 D05 整链说明随后验收。

同一类字段的记录描述同一运行时实例这一条件下的关系；动态 URL、代理连接、监听寿命和原生/包装通道的实际选择均未被当作已观测结果。本批支持直接 `onmessage` 赋值；其他监听机制和处理函数包装形式按明确缺口继续扩展。

## 复现

从研究仓库根目录运行。`SOURCE` 为固定 Insight checkout，`BASE` 为 `p3-data-v9` 图，`TS` 指向 TypeScript 5.9.3 的 `lib/typescript.js`；`OUT`、`STORE` 是新的仓库外目录，`CGC_DB` 为已关闭的原生 CGC 数据库。环境设置见 [P1 复现](../2026-10-23-p1-completion/reproduce.md)。

```sh
python scripts/build_socket_graph.py --source "$SOURCE" --base "$BASE" --typescript "$TS" --output "$OUT"
python scripts/query_data_graph.py "$OUT/graph.json" --socket-provider 'provider:registry:cdb1a04ef30726dc964f3a66:registry:8cc84bafd0ccae7c02b7357d'
python -m unittest discover -s tests -v > "$OUT/python-tests.txt" 2>&1
npm test > "$OUT/typescript-tests.txt" 2>&1
python experiments/2026-10-23-p3/run_socket_receivers.py --graph "$OUT/graph.json" --cgc-db "$CGC_DB" --output "$STORE" --python-log "$OUT/python-tests.txt" --typescript-log "$OUT/typescript-tests.txt"
python scripts/check_p3_socket_receivers.py
```

提供方 ID 来自当前输入的生成图。提取器不读取人工参考或评分器，不重新核验文件哈希。
