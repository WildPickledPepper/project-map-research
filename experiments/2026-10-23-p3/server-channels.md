# 服务端接受连接、会话保存与响应发送

已从源码连接 **uWS 注册 → 接受连接参数 → 会话构造 → channel 成员 → 管理器保存/读取 → 响应发送**。`unit/flows` 的四个响应出口均可查询到同一个服务端通道来源，并与已有前端 socket 接收关系组合。

## 输入与实现

输入为 Insight 提交 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688` 的 [154 文件](server-channels-manifest.json)。在上一批 150 文件上增加服务端实现、声明、基类声明和日志声明：最后一项用于从源码判断可变参数按值传递，避免把传入日志的通道指针误判为被重新赋值。

实现提交 `8a44521`，提取器 [cpp_socket_origin.py](../../adapters/cpp_socket_origin.py) 复用既有 C++ 语法、类型、实例提取器和有界值传播器。应用方法名、成员名、构造参数和静态实例均来自源码。解析器为 tree-sitter 0.25.2、tree-sitter-language-pack 1.20.0；基础图为 [socket 接收绑定](socket-receivers.md)的 `p3-data-v10`。

外部语义模型使用 uWebSockets 固定提交 `045bbc11ef4f3ec933c112579d3e8922302a798b` 的 [App.h](https://github.com/uNetworking/uWebSockets/blob/045bbc11ef4f3ec933c112579d3e8922302a798b/src/App.h#L272)：`open` 的首个参数为接受的 WebSocket，`ws` 接受行为对象并转移处理函数。该提交用于模型依据，Insight 产品二进制实际链接版本尚未核实。

## 自动提取与连接

| 阶段 | 自动恢复的关系 | 查询保留的条件 |
|---|---|---|
| 服务端注册 | `WsServer.cpp:66` 的路径、行为对象及 `:93` 的 open 绑定 | std::bind 的目标、接收对象和占位参数类型匹配 |
| 监听配置 | `WsServer.cpp:68` 与注册使用同一 app 来源 | host、port 保留为成员来源；实际配置值由运行环境决定 |
| 接受连接 | open 事件首个实参传入 `OnOpenCb` | 非空、URL、现有会话等源码分支条件 |
| 会话构造 | `WsServer.cpp:133` 的分配将通道传到 `WsSessionImpl.cpp:29` 的 channel 初始化 | 构造完成后的字段仍保留原来源 |
| 共享存储 | 分配的会话写入管理器成员，经同一静态实例的 getter 取回 | 同一进程/链接映像，取回前未替换、移除 |
| 响应发送 | 取回会话的调用位置匹配已解析的响应路由，channel 成员匹配 socket.send 的接收字段 | 选择该虚调用候选，会话与通道仍有效 |

一次提取得到 1 个原生服务端注册、1 个监听、3 个对象分配、1 个接受通道初始化、2 个对象保存位置、27 个成员返回位置和 5 个成员接收调用位置。对象分配与保存数量包括会话内部的消息缓冲区；`unit/flows` 查询按分配身份、成员身份、管理器实例、调用位置和响应对象选择出 **1 个服务端来源关系、4 个响应出口、12 条带编码条件的发送路径**。

[服务端查询](../../adapters/server_channel_queries.py)和[前后端组合查询](../../adapters/socket_queries.py)共用上述事实。组合查询返回服务端来源、前端接收绑定及三种 Promise 交付候选。网络两端仍通过逻辑服务配置组合；实际地址、代理和某次连接的对应属于 P5 运行证据。

## 验证

证据见 [server-channels.json](evidence/server-channels.json)。完整图为 **24,450 节点、34,801 条关系**，快照为 `p3-data-v11`。

**217 项 Python、67 项 TypeScript 测试通过。** 新增检查覆盖应用标识改名、错误占位参数、通道重赋值、构造器成员覆盖、参数遮蔽、回调覆盖、行为对象复制、未展开的可变参数、按值传递的参数包、不同管理器实例、不同 app、相反分支及预算截断。

真实图分别移除通道初始化、会话保存、成员 getter 后，服务端来源查询均断开。前端接收关系和已有的 12 条发送路径保留，组合查询重新显示服务端来源缺口。完整图在 CGC/Kuzu 副本中读回一致，服务端查询和前后端组合查询结果一致，790 条原生函数记录保持一致。

本批执行的是源码提取、正反例和存储查询。源码条件、对象生命周期和实际执行状态分开保存。

## P3 剩余验收

服务端来源已补齐。接下来将前端 Promise 交付经过框架返回包装、iframe 转发和业务 API 解包，接到现有字段消费与状态赋值关系；处理首链必要的编码/队列来源缺口，然后验收 D02、D03 和 D05。D01、D04 的已通过状态保持。

当前 open 回调模型支持显式 std::bind 成员绑定；其他回调形式保留缺口。静态管理器身份提供源码层关联，保存、取回之间的替换和生命周期以条件呈现。

## 复现

从研究仓库根目录运行。`SOURCE` 为固定 Insight checkout，`BASE` 为 `p3-data-v10` 图，`OUT`、`STORE` 为新的仓库外目录；`CGC_DB` 为已关闭的原生 CGC 数据库。环境配置见 [P1 复现](../2026-10-23-p1-completion/reproduce.md)。

```sh
python scripts/build_server_channel_graph.py --source "$SOURCE" --base "$BASE" --output "$OUT"
python scripts/query_data_graph.py "$OUT/graph.json" --server-channel-provider 'provider:registry:cdb1a04ef30726dc964f3a66:registry:8cc84bafd0ccae7c02b7357d'
python scripts/query_data_graph.py "$OUT/graph.json" --socket-provider 'provider:registry:cdb1a04ef30726dc964f3a66:registry:8cc84bafd0ccae7c02b7357d'
python -m unittest discover -s tests -v > "$OUT/python-tests.txt" 2>&1
npm test > "$OUT/typescript-tests.txt" 2>&1
python experiments/2026-10-23-p3/run_server_channels.py --graph "$OUT/graph.json" --cgc-db "$CGC_DB" --output "$STORE" --python-log "$OUT/python-tests.txt" --typescript-log "$OUT/typescript-tests.txt"
python scripts/check_p3_server_channels.py
```

提供方 ID 来自生成图。提取器不读取评分器或人工参考，不重新核验文件哈希。
