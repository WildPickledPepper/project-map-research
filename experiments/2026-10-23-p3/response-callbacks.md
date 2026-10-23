# 响应回调表、Promise 与交付字段

已从源码提取两张响应回调表及 **五条候选交付路径**：WebSocket 回调的三个返回分支，以及 iframe 连接器的成功与失败分支。每条路径连接注册位置、查找键、所选回调、Promise 和交付值，保留注册有效性及响应筛选条件。**P3、D02 继续实施：下一步连接请求编号传播、发送/接收边界和 Promise 返回值到业务 API 的转换。**

## 输入与实现

输入是 Insight 提交 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688` 的 [148 文件清单](response-manifest.json)，基础图沿用 [前端消费增量](frontend-consumers.md) 的 `p3-data-v6`。规则提交为 `7253fdb`，TypeScript 编译器固定 **5.9.3**。执行证据在 [response-callbacks.json](evidence/response-callbacks.json)。

本次扩展已有 `typescript_data_flow` 的值传播器。第一遍分析源码中的标准 Promise 构造，跟踪传入执行函数的 `resolve/reject`、捕获它们的闭包和 Map 登记；第二遍分析标准 Map 查找，将响应参数代入候选回调，提取其交付值。辅助函数、变量别名、对象字段及解构复用现有规则。

Promise、Map 和 JSON 的规则要求编译器解析到标准库声明，项目自己定义的同名类不会获得这些语义。业务成员、函数和字段名称全部来自输入源码。回调表按声明和接收对象类型区分，查找和闭包调用保留入口及调用位置，防止不同入口共享一次参数绑定。

## 实测结果

| 回调表及登记方法 | 查找键来源 | 交付分支 | 交付给 Promise 的数据 |
|---|---|---|---|
| `Connection._responseHandlers` / `Connection.fetch` | `JSON.parse(ev.data).requestId` | `command` 为 `import/action` | 完整解析后的响应 |
| 同上 | 同上 | 成功且 `body` 存在 | 响应的 `body` |
| 同上 | 同上 | 错误分支 | 构造的 `{ error: { code, message } }` |
| `ClientConnector._msgSequence` / `ClientConnector.fetch` | `res.data.id` | `body.error` 存在 | `reject(res.data.body.error)` |
| 同上 | 同上 | 成功分支 | `resolve(res.data)` |

WebSocket 三条路径都保留 `!isImport && isOldRequest` 为假的条件：项目已切换且旧请求不适用时，源码删除回调并提前返回。还保留响应类型筛选、找得到回调、连接可用和各返回分支的条件。`JSON.parse` 作为转换步骤保存，因此可以区分事件参数路径 `data.body` 与解析后的 JSON 路径 `body`。

iframe 的回调表保存的是包含两个 Promise 结算函数的对象；WebSocket 的表保存的是另一个源码函数返回的闭包。查询沿对象属性或闭包捕获的 Promise 来源展开。先查出回调、再从表中删除、最后调用的源码顺序仍可表达：删除表项后，局部变量保留此前查出的值。

图为 **23,789 个节点、34,589 条关系**。本次分析 18 个函数/阶段组合，记录 9 个 Promise 来源、2 个包含结算函数的登记、11 个 Map 查找和 26 个静态结算候选；其中 **5 个候选通过上述两张回调表关联**。其余记录包括连接初始化和清单内其他函数，不计入本例返回链。

## 验证和当前边界

**162 项 Python、48 项 TypeScript 测试通过。** 新增用例覆盖闭包返回、对象解构、成功/失败分离、不同表与类型、不同常量键、回调被覆盖、项目同名标准类型、改名、未知调用改写，以及同一查找函数由不同入口调用。

完整图保存到原生 CGC/Kuzu 副本后，数据读回一致；五条回调路径、已有前端消费查询和后端响应路由查询保持一致；790 条原生函数记录保持一致。本实验执行静态提取和查询，产品运行观察留给 P5。

候选选择需要满足：登记与查找使用同一个运行时实例、两个键相等、登记在查找前仍有效、捕获的回调字段在调用前未被改写。不同已知常量键直接排除；运行时编号保留来源及相等条件。源码中的计数器、请求消息字段和后端回填字段尚待联合验证。

其他待接通部分是 C++ 序列化结果到实际发送、WebSocket/iframe 端点对应、框架返回值重新包装、`createRequest` 解包到业务 API，以及条件队列分支。清单外调用、未展开的控制流和异常路径在查询中保留诊断。D02、跨传输的 D03 和整链说明 D05 继续按原计划验收。

## 复现

在研究仓库根目录运行。`SOURCE` 为固定 Insight checkout，`TS` 为 TypeScript 5.9.3 的 `lib/typescript.js`，`BASE` 为 `p3-data-v6` 图；`OUT`、`STORE` 使用新的仓库外目录，`CGC_DB` 为已关闭的原生 CGC 数据库。Windows DLL 配置沿用 [P1 复现](../2026-10-23-p1-completion/reproduce.md)。

```sh
python scripts/build_callback_graph.py --source "$SOURCE" --manifest experiments/2026-10-23-p3/response-manifest.json --base "$BASE" --typescript "$TS" --output "$OUT"
python scripts/query_data_graph.py "$OUT/graph.json" --response-requester Connection.fetch
python scripts/query_data_graph.py "$OUT/graph.json" --response-requester ClientConnector.fetch
python scripts/query_data_graph.py "$OUT/graph.json" --response-receiver '<receiver callable ID from the first query>'
python -m unittest discover -s tests -v > "$OUT/python-tests.txt" 2>&1
npm test > "$OUT/typescript-tests.txt" 2>&1
python experiments/2026-10-23-p3/run_response_callbacks.py --graph "$OUT/graph.json" --cgc-db "$CGC_DB" --output "$STORE" --python-log "$OUT/python-tests.txt" --typescript-log "$OUT/typescript-tests.txt"
python scripts/check_p3_response_callbacks.py
```

提取器和查询不读取本例名称或人工参考答案。评分器使用这些名称检验结果。版本检查读取 Git 提交，不重新核验文件哈希。
