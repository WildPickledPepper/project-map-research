# iframe 返回、API 解包与前端状态

已将框架层 Promise 的交付值，经返回包装、iframe 消息、按编号查找回调和 API 解包，接到前端字段消费与状态赋值。`unit/flows` 的 `unitAllFlows` 查询覆盖四个后端响应出口和两处连线状态赋值；从两处状态分别反查，均回到同一 API、提供方及四个响应出口。

## 输入与实现

输入为 Insight 提交 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688` 的 [154 文件](server-channels-manifest.json)，基础图为 [服务端来源](server-channels.md)的 `p3-data-v11`。实现提交 `6040ab9`，使用 TypeScript 5.9.3。[返回提取入口](../../adapters/typescript_return_flow.cjs)复用已有语法、绑定和有界值传播器；[组合查询](../../adapters/return_bridge_queries.py)复用协议、回调编号、socket、响应对象和前端消费事实。

提取入口来自已有图中的 API、回调注册和交付函数，应用类名、方法名、成员名和字段名均读取源码。浏览器模型依据 2026-10-23 查阅的 WHATWG [postMessage](https://html.spec.whatwg.org/multipage/web-messaging.html#dom-window-postmessage-options-dev) 与 [Window frames](https://html.spec.whatwg.org/multipage/nav-history-apis.html#dom-frames-dev) 语义；实际父子窗口部署、origin 和处理函数生命周期保留为条件。

## 自动关联

| 阶段 | 自动恢复的来源关系 |
|---|---|
| 框架返回 | 已注册的处理函数 await 请求结果，包装到返回对象 |
| 回复构造 | 服务端连接器调用该回调，复制请求编号与发送方字段，展开返回对象 |
| 消息发送 | 按请求发送方选择目标窗口，序列化并调用 postMessage |
| 客户端分发 | window.onmessage 解析 JSON，按事件字段选择处理函数 |
| 回调交付 | 响应编号查到原请求回调；错误对象进入拒绝分支 |
| API 返回 | createRequest 解包 body，getUnitFlows 返回该值 |
| 前端状态 | 字段投影与既有消费表达式匹配，关联两处 singleLinkLine 赋值 |

提取器记录源对象初始化、回调成员绑定、继承方法、Window 消息参数、动态窗口选择和字段投影。全局请求函数必须有唯一源码绑定；未知尾部对象展开会使可能被覆盖的字段失效。消息编号、事件、目标窗口选择或 API 投影失配时，返回关联断开。

`unitAllFlows` 查询得到 **1 个 iframe 返回关系、4 条响应出口关系、2 处字段状态赋值**。正常和异常发送出口带有此前生产的字段来源；两个提前返回出口保留序列化字段与消费关系，但没有后续数据库写入来源。查询保留分支条件，不能把这些候选当作同一次运行路径。

不限定字段时得到 8 个条件组合，包含请求完成后触发的更新。返回字段依赖和完成后更新分别标记。socket 错误对象会转发到 iframe，但客户端拒绝该 Promise；组合查询根据源码条件过滤其成功赋值关系。

## 验证

执行证据见 [return-bridge.json](evidence/return-bridge.json)。图为 **24,985 节点、35,440 条关系**，快照 `p3-data-v12`。

**223 项 Python、76 项 TypeScript 测试通过。** 新增检查覆盖应用标识改名、全局绑定替换、回调覆盖、未知对象修改、监听器清除、预算截断、尾部展开覆盖和 API 返回字段覆盖。真实图的六组受控变化分别修改编号、事件、目的窗口、API 投影、监听器和回调注册，返回关系全部断开，上游四个 socket 关系保留。

完整图写入 CGC/Kuzu 副本后读回一致；字段查询、两处状态反查和六组负例重新执行通过，790 条原生函数记录保持一致。该实验验证源码提取与存储查询；实际运行场景由 P5 验收。

## P3 收尾

返回字段与前端状态已连接，D02、D03、D05 等待合并验收。合并报告需要统一呈现数据库候选、字段生产、跨语言传输、返回消费、反向查询，以及编码和队列的残余缺口。路径约束保留但尚未做完整可满足性求解；调用预算截断、未知对象修改和运行条件均随结果输出。

## 复现

从研究仓库根目录运行；环境配置见 [P1 复现](../2026-10-23-p1-completion/reproduce.md)。`BASE` 为 v11 图，`TYPESCRIPT` 指向 TypeScript 5.9.3 的 `typescript.js`，`OUT`、`STORE` 为新的仓库外目录，`CGC_DB` 为已关闭的原生数据库。

```sh
python scripts/build_return_bridge_graph.py --source "$SOURCE" --base "$BASE" --typescript "$TYPESCRIPT" --output "$OUT"
python scripts/query_data_graph.py "$OUT/graph.json" --return-provider 'provider:registry:cdb1a04ef30726dc964f3a66:registry:8cc84bafd0ccae7c02b7357d' --field-path '["unitAllFlows"]'
# 对返回结果中的 state_node 增加 --frontend-state 参数，可按状态反查。
python -m unittest discover -s tests -v > "$OUT/python-tests.txt" 2>&1
npm test > "$OUT/typescript-tests.txt" 2>&1
python experiments/2026-10-23-p3/run_return_bridge.py --graph "$OUT/graph.json" --cgc-db "$CGC_DB" --output "$STORE" --python-log "$OUT/python-tests.txt" --typescript-log "$OUT/typescript-tests.txt"
python scripts/check_p3_return_bridge.py
```

提供方与状态 ID 来自生成图。提取器不读取人工参考或评分器，不重新核验文件哈希。
