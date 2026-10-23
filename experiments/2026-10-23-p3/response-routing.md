# 响应对象到序列化回调：按参数与注册上下文连接

已将处理器中的响应对象，沿发送函数、会话方法、模块选择和命令选择，连接到对应的序列化回调。`unit/flows` 的 **4 个发送位置分别形成 6 段路径**，共享辅助函数保留各次调用的参数上下文。正常发送和异常处理发送分别关联到 7 处业务字段写入；两处提前返回的错误发送不关联后续数据库写入。

这轮补上了 [字段生产](output-fields.md) 与 [序列化映射](serialization.md) 之间的对象关系。**P3、D02 继续实施：下一步连接 JSON 字符串传输、前端解包、字段消费及状态更新。**

证据类型：实际执行源码提取、上下文查询、自动测试与 Kuzu 读回。Insight 提交为 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`；提取规则为 `49725f5`，查询规则为 `cd71800`。输入从 141 文件扩展到 [148 文件](response-manifest.json)，加入发送封装、会话类型和协议常量定义。结果见 [response-routing.json](evidence/response-routing.json)，验收脚本见 [run_response_routing.py](run_response_routing.py)。

## 自动恢复的路径

```text
QueryFlowsBySliceInfoHandler::HandleRequest 中的 responsePtr
  → Dic::SendResponse 的智能指针参数
  → WsSessionImpl::OnResponse 的智能指针参数
  → WsSessionImpl::SendResponse 的响应引用
  → ProtocolManager::ToJson 的响应引用
  → 按响应模块字段选中的 ProtocolUtil::ToJson
  → 按响应命令字段选中的 ToUnitFlowsResponseJson
```

提取器沿 `std::move`、智能指针解引用和引用别名追踪对象，并记录调用位置、实参、形参及分支条件。继承的未限定方法调用和可见声明中的默认参数补入已有候选解析。类型关系排除已知不兼容的响应/事件重载。

模块和命令值从字段复制恢复：解码函数将传输字段写入请求对象，基类辅助函数把请求字段复制到响应对象。模块表查找携带响应字段来源，并与 P2 的插件工厂作用域对应；最终回调按注册容器、所选协议类和命令值共同匹配。项目中的字段、类、方法和注册名均来自源码。

查询逐个调用位置传递对象及字段值。源代码中后续的键改写会改变选择；未知值、条件改写及未建模的复合运算保留未知。序列化回调内的参数路径投影回原响应对象后，再与该对象的生产位置连接。当前按源码位置排除发送之后的写入，结果仍保留控制流与别名条件。

## 实测结果

| 处理器发送行 | 源码场景 | 业务写入候选 | 业务写入到 JSON 路径的关系 |
|---|---|---:|---:|
| 38 | 参数检查失败后返回 | 0 | 0 |
| 47 | 数据库为空后返回 | 0 | 0 |
| 61 | 数据库异常处理 | 7 | 182 |
| 65 | 查询后的正常发送 | 7 | 182 |

每条路径均到达 Timeline 的已注册回调，恢复 34 个字段或集合路径。其中 26 个业务路径由集合字段派生，因此 7 处集合写入各关联到这 26 个路径。异常路径表示发生异常前可能已有部分写入；实际写入量由运行证据确认。公共响应字段的生产关系另保存在结果中。

图包含 23,660 个节点、34,363 条关系。查询访问 44 个状态，未截断。154 项 Python 测试通过，覆盖字段改名、不同模块的同名命令、不同响应对象、发送前后顺序、封装内改写、未知键、无关解码器、展开预算和未展开的对象传递。完整图保存后读回一致，读回查询重新通过同样断言，790 条原生函数记录保持一致。

## 保留的条件与后续工作

关系描述源码候选：所选会话及协议实例、虚方法目标、分支执行、未建模的中间修改和写入是否到达发送位置，均保留条件。查询按协议作用域和对象上下文组合关系，公共形参没有被全局连到所有调用者。

队列的 `operator<<` 作为未展开对象传递记录，附 `useResponseQueue` 条件。源码检查显示本版 `WsSessionImpl.h` 将该成员初始化为 `false`；提取器保留了分支，尚未执行队列生产/消费模型。后面的 JSON 字符串转换与 `loop->defer` 发送也属于后续传输工作。当前没有据此宣称消息已送达前端。

下一步从已恢复的序列化结果继续追踪传输与前端解包，再连接 `unitAllFlows` 的消费和状态赋值，完成 D02。D03 返回字段反向影响与 D05 全链说明随后验收。

## 复现

依赖及 P2 基础图见 [P2 复现](../2026-10-23-p2/reproduce.md)。输出使用新的仓库外目录，原生 CGC 数据库须先关闭：

```sh
python scripts/build_data_graph.py --source /path/to/msinsight --base /outside/p2/graph.json --manifest experiments/2026-10-23-p3/response-manifest.json --output /outside/new-response-routing
python experiments/2026-10-23-p3/run_response_routing.py --graph /outside/new-response-routing/graph.json --cgc-db /outside/p1/cgc.kuzu --output /outside/new-response-store
python scripts/query_data_graph.py /outside/new-response-routing/graph.json --response-provider provider:registry:cdb1a04ef30726dc964f3a66:registry:8cc84bafd0ccae7c02b7357d
python scripts/check_p3_response_routing.py
```

查询 ID 对应该版本输入；其他项目使用提取出的 provider ID。成功运行位于工作区相对目录 `work/repo-map-research/results/p3-response-routing-01/` 和 `work/repo-map-research/results/p3-response-routing-store-01/`。证据文件将重复来源放在 `source_evidence` 中，通过 `evidence_refs` 引用；重复条件、映射和生产关系放在 `shared_records` 中，通过对应的 `_ref` 字段引用。打包与展开已检查一致。未重新核验文件哈希。
