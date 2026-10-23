# C++ JSON 结果、延迟回调与 socket 发送

已将 `unit/flows` 的四个响应出口接到 **JSON 字符串生成 → 编码包装 → lambda 捕获 → 事件循环回调 → socket 发送参数**。查询得到 12 条带条件的来源路径：四个出口各对应三个能够恢复来源的编码分支。P3、D02 继续实施，下一步连接 socket 两端、iframe 返回包装和业务 API 解包。

## 输入与实现

输入为 Insight 提交 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688` 的 [150 文件清单](transmission-manifest.json)。在上一批 148 文件上增加 `ServerDefs.h` 和 `StringUtil.h`，分别提供 socket 类型别名和编码包装函数；`WsSessionImpl.h` 已在原清单中。

实现提交 `5764a6e`，执行证据见 [transmission.json](evidence/transmission.json)。[提取器](../../adapters/cpp_transmission.py)复用已有 C++ AST、类型候选、可见性和库类型别名解析，新增值来源、源函数实参、显式按值捕获和延迟调用的传播。[查询](../../adapters/transmission_queries.py)按调用位置、调用者和被选中的 JSON 返回函数接到已有响应对象路由。业务函数、变量、捕获项和类型别名均从源码读取，名称预期只存在于评分器和报告。

外部库模型使用 RapidJSON 的 `Accept(Writer)`、`StringBuffer.GetString`，依据见 [RapidJSON 官方流文档](https://rapidjson.org/md_doc_stream.html)。uWS 模型按类型识别 `Loop::defer` 和 `WebSocket::send`；回调入队与发送接口核对了上游提交 `045bbc11ef4f3ec933c112579d3e8922302a798b` 的 [Loop.h](https://github.com/uNetworking/uWebSockets/blob/045bbc11ef4f3ec933c112579d3e8922302a798b/src/Loop.h) 和 [WebSocket.h](https://github.com/uNetworking/uWebSockets/blob/045bbc11ef4f3ec933c112579d3e8922302a798b/src/WebSocket.h)。该提交用于库模型依据，Insight 所用库二进制版本未在本次实验验证。

## 自动恢复的路径

| 阶段 | 固定源码位置 | 提取结果 |
|---|---|---|
| JSON 返回值 | `WsSessionImpl.cpp:169` | 现有响应对象路由选择的 `ProtocolManager::ToJson` 调用结果 |
| JSON 字符串 | `JsonUtil.h:140–144` | Writer 绑定输出缓冲区，Accept 将 JSON 写入该缓冲区，再读取字符串 |
| 编码包装 | `WsSessionImpl.cpp:176`、`StringUtil.h:175–188` | 按源函数实参和返回分支传播；保留条件编译和编码判断 |
| 参数与捕获 | `WsSessionImpl.cpp:177–183` | 字符串进入重载函数，再按值捕获；后续局部赋值不修改已捕获的来源 |
| 延迟回调 | `WsSessionImpl.cpp:183–192` | 根据 `uWS::Loop` 类型展开回调，保留弱引用锁定和会话状态检查 |
| 发送实参 | `WsSessionImpl.cpp:153–159` | 根据 `WsChannel` 的源码别名识别 `uWS::WebSocket`，字符串进入 TEXT 帧发送参数 |

查询同时保留 JSON 有值、弱引用锁定成功、会话未关闭、channel 非空和事件循环执行回调等条件。三个有来源的编码分支为：非 Windows、Windows 已是 UTF-8、Windows 非 UTF-8 且代码页非 GBK。Windows GBK 转换涉及 Win32 输出缓冲区，本次未恢复该分支的返回数据来源，查询明确返回缺口。编码检测函数内部循环也保留未展开诊断，分支判断值由运行时决定。

同一提取器还恢复了一条事件发送路径。它与响应路径共享底层发送方法，但拥有独立 JSON 来源和调用上下文，未混入 `unit/flows` 的四个响应出口。

## 实测与验证

完整图为 **24,185 节点、34,713 条关系**，快照为 `p3-data-v9`。本批在 86 个候选入口中提取 85 个 JSON 来源、2 个带来源的发送上下文。数量描述所选源码和当前支持机制；实际发送次数与接收结果由 P5 验证。

**190 项 Python、53 项 TypeScript 测试通过。** 新增检查覆盖源变量改名、初始化捕获、弱引用接收对象、捕获前后覆盖、引用捕获缺口、同名假 socket/调度器、可变实参、条件内修改、局部遮蔽、不同 JSON 对象、未建模缓冲区修改、预算截断、图存储与查询隔离。真实图中移除选定 JSON 返回函数的候选身份后，12 条提供方发送路径全部断开。

完整图写入 CGC/Kuzu 副本后读回一致；响应发送查询与上一批编号关联查询保持一致，790 条原生函数记录保持一致。执行了源码提取、查询和持久化实验，尚未运行 Insight 产品场景。

## 下一步

1. 连接服务端 socket 和前端接收端，保存服务/连接对应条件。
2. 将前端 Promise 结果经过框架包装、iframe 转发和业务 API 解包，接到已有状态消费者。
3. 补充条件队列与编码转换的来源缺口，按 D02 的必要范围验收；随后完成 D03 反向查询和 D05 整链说明。

当前提取器支持显式按值捕获。引用捕获、默认捕获、未知可变实参和未建模控制流保留缺口；条件分支保留为源码候选，不判断其运行时可行性。

## 复现

从研究仓库根目录运行。`SOURCE` 为固定 Insight checkout，`BASE` 为上一批 `p3-data-v8` 图，`OUT`、`STORE` 为新的仓库外目录；`CGC_DB` 为已关闭的原生 CGC 数据库。解析器缓存和 Windows DLL 配置沿用 [P1 复现](../2026-10-23-p1-completion/reproduce.md)。

```sh
python scripts/build_transmission_graph.py --source "$SOURCE" --base "$BASE" --manifest experiments/2026-10-23-p3/transmission-manifest.json --output "$OUT"
python scripts/query_data_graph.py "$OUT/graph.json" --transmission-provider 'provider:registry:cdb1a04ef30726dc964f3a66:registry:8cc84bafd0ccae7c02b7357d'
python -m unittest discover -s tests -v > "$OUT/python-tests.txt" 2>&1
npm test > "$OUT/typescript-tests.txt" 2>&1
python experiments/2026-10-23-p3/run_transmission.py --graph "$OUT/graph.json" --cgc-db "$CGC_DB" --output "$STORE" --python-log "$OUT/python-tests.txt" --typescript-log "$OUT/typescript-tests.txt"
python scripts/check_p3_transmission.py
```

其他源码版本从生成图选取提供方或入口 ID。提取与查询不读取人工参考或评分器，不重新核验文件哈希。
