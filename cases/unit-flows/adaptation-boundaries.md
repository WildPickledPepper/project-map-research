# unit/flows：适配需要读取哪些机制

状态：协调者对固定源码的补充审计；不是任一工具自动提取的成果，也没有进行动态验证。输入仍是 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`。以下定位用于解释实验缺口，不替代工具实际输出。

## 请求身份跨过多层封装

1. `modules/timeline/src/api/request.ts:175` 指定 `timeline` 与 `unit/flows`。
2. `modules/timeline/src/bootstrap.tsx:89` 将 `window.requestData` 绑定到 `createRequest(connector)`。
3. `modules/lib/src/utils/Request.ts:38` 将 command/params/module 交给 connector；`:43` 解出响应的 body。
4. `modules/framework/src/connection/index.ts:60` 注册接收模块请求的回调，再调用 `requestModule`。
5. `modules/framework/src/centralServer/server.ts:243` 调用选中 Connection 的 fetch。
6. `modules/framework/src/centralServer/websocket/connection.ts:45` 将 module 转成传输字段 `moduleName`；`:186` 构造请求头，后续序列化发送。

适配需求：追踪函数值绑定、回调注册和字段映射；不能因名字含 request 就当 HTTP。整个查询需保留目标服务/连接、module、command，不能扩散到所有公共发送函数的所有消费者。

## 提供方包括协议反序列化与模块注册

- `server/src/modules/defs/ProtocolDefs.h:88` 定义命令常量的字符串值。
- `server/src/modules/timeline/TimelinePlugin.h` 将 Timeline 模块名绑定到 TimelineModule 与 TimelineProtocol。
- `server/src/modules/timeline/protocol/TimelineProtocol.cpp:74` 注册命令到 `ToUnitFlowsRequest`，`:112` 注册响应序列化。
- `server/src/modules/timeline/TimelineModule.cpp:87` 将命令注册到 QueryFlowsBySliceInfoHandler。
- `server/src/modules/ModuleManager.cpp:63` 按 moduleName 选择模块；`server/msinsight/src/base/BaseModule.cpp:36` 按 command 选择处理器。

适配需求：独立提取消费接口、提供接口、解码器、注册项与处理器；按作用域内的协议身份关联。代码中 `emplace` 的调用边不等于恢复了注册语义。

## 数据库实现取决于建立的连接池与状态

`server/src/modules/timeline/core/database/DataBaseManager.cpp:45` 起的 `CreateTraceConnectionPool` 在连接池尚不存在时读取数据类型，并选择 DB 或 Text 构造路径；`:104` 起查表获取已有池的连接。

Handler `QueryFlowsBySliceInfoHandler.cpp:41` 起还会按 dbPath 是否为空选择 rankId/fileId 查找路径，`:57` 调用抽象接口。不能只靠 `QueryUnitFlows` 名字选择某个具体实现。

适配需求：方法声明与实现的统一身份、虚接口候选、工厂和池的构造/返回关系、选择条件。静态模型保留候选，特定执行选中了谁需要运行证据或更强的状态分析。本次没有恢复数据类型状态的全部写入来源。

## 返回消费者确实改变前端状态

- `server/src/modules/timeline/protocol/TimelineProtocolUtil.cpp:353` 写出 JSON 字段 `unitAllFlows`。
- `modules/lib/src/connection/index.ts:200` 通过 Promise resolve 返回消息；`:250` 起还存在服务端 connector 的回调与回复逻辑。
- `modules/timeline/src/components/FilterLinkLine.tsx:434` 等待 getUnitFlows；`:445` 读取 `raw.unitAllFlows`；`:448` 更新 singleLinkLine；`:449` 翻转 renderTrigger。

适配需求：请求/响应关联、解包层次、字段生产消费与状态赋值。找到调用者符号只能覆盖其中一部分，不代表已经建立了跨协议返回数据流。

前端 websocket 层另有旧项目响应过滤，因此仅凭后端成功并不能判定结果一定被上述消费者采用。状态与动态方案仍见 [动态行为与审查](../../docs/03-runtime-and-review.md)。

## 最小适配边界

先验证现有底座能否接受具有来源和条件的自定义节点/关系。建议只补：

1. TS 请求封装和身份提取器。
2. C++ 常量、协议/模块/handler 注册提取器。
3. 带作用域、方向与歧义的协议关联器。
4. C++ 方法/接口/工厂关系的可靠解析路径。
5. 返回字段与已知前端消费者的可查询关联。

逐条从源码重新提取，不手填每条接口对应答案。不在本轮顺带实现完整的新解析器、图数据库或运行追踪平台。
