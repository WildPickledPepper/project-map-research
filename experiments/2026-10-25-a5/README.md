# A5 真实运行验证

日期：2026-10-25。运行场景已执行，正在完成同版本静态映射与交付检查。研究对象为 MindStudio Insight，公开基准 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`；运行采集只进入禁用推送的独立副本。

本阶段复用 P5 的真实后端、Playwright 交付控制、运行记录及版本检查，扩展到通信防抖、snapshot 分页、MemScope、Worker 和 OPFS 缓存。静态事实仍由全仓提取器自动生成；本目录的源码钩子和选择器是明确声明的采集适配。

## 场景与独立预期

[scenarios.json](scenarios.json)在本轮产品场景前冻结验收目标。[oracle.py](oracle.py)直接读取公开输入，不调用产品解析器或读取其派生数据库：

- 通信 JSON 的 `step` 键给出迭代集合，本样例为 `2`。
- snapshot 的申请/释放事件与末态活动块组成生命周期账本。设备 0 的预期为 3,219 条，比较地址、申请事件号、释放事件号的多重集合。
- MemScope 的公开 SQLite 原始事件按设备、类型、指针配对，独立计算申请块集合。当前 PTA / device 1 为 3,267 条，比较地址和大小的多重集合。

设备切换输入从同一公开 snapshot 派生第二个设备：复制设备 0 事件和 segment，将其设备编号设为 1，地址统一平移。派生步骤和预期均在启动产品前完成，原始输入保持不动。

默认分页实际为 1,000、1,000、1,219 条。717 是快照末态 block 记录数；查询输出包含其历史生命周期，因此默认配置已经产生多页。另以显式实验配置 `page_size=128` 检验不同分片策略。

## 复现

先按 [P5 构建说明](../2026-10-24-p5/README.md)准备独立产品副本、后端依赖和前端依赖。本轮本地采集版本依次为：

| 本地产品提交 | 内容 |
|---|---|
| `ccd0d88080861b0c7185bcca70a85bd61f823168` | P5 正常采集基线 |
| `4df6d68c9f4223327b909600faeaeb93aa7c276d` | A5 原生与前端采集、默认关闭的缺块故障开关 |
| `b7a30457ce32e06172fc1dfb33e0dab75f1bfcce` | 显式结果身份和标注为直接驱动的场景入口 |

这些提交只存在于本地实验副本。采集脚本 [instrument.py](instrument.py)、[refine_capture.py](refine_capture.py)记录变更；应用后先提交该副本，再构建。新环境产生自己的实验提交，运行记录填写实际提交。

后端构建沿用 P5 固定时间与参数。Release 导入器还需要在后端 bin 下放置 `mem_snap_dump/`（来自该提交的 `scripts/MemSnapDump/`）及可用的 `python/python.exe` 与标准库。本轮使用现有 Python 3.11.9 安装的目录联接。

```sh
python experiments/2026-10-25-a5/build.py --source EXPERIMENTAL_CHECKOUT --output EXTERNAL_BUILD_LOGS
python experiments/2026-10-25-a5/run_suite.py --source EXPERIMENTAL_CHECKOUT --results EXTERNAL_RESULTS
```

[run.py](run.py)复制公开输入和前端产物，在 loopback 启动真实后端、HTTP 与 headless Chromium，结束后关闭本次进程。启动锁保证本驱动的场景串行，避免原生服务自动换端口时浏览器误连其他运行。内存原始样例在输出目录以 `.db` 名称复制，符合当前导入识别规则。

正常首链由真实 UI 导入及菜单选择触发。防抖 burst/cancel/flush、缓存重载/清理和旧页暂存属于显式标记的实验控制；设备切换使用真实下拉框。HTTP 的 COOP/COEP 设置保存在每次配置中。

[verify.py](verify.py)按连接、请求编号、追踪标识和 Worker generation 核验关联。它还对真实证据派生缺少数据库返回、错误解码标识、重复请求编号三个负例。未知消费者、未观测内部执行和未完成 Promise 均保留。

## 静态图与运行查询

[graph-config.json](graph-config.json)自动发现整个运行提交的输入。先生成该提交的全仓静态快照，再运行：

```sh
python experiments/2026-10-25-a5/map_runtime.py --source EXPERIMENTAL_CHECKOUT --archive EXTRACTED_BUILD --store EXTERNAL_STORE --results EXTERNAL_RESULTS --output EXTERNAL_MAPPING
python experiments/2026-10-24-p5/query_runtime.py --store EXTERNAL_STORE --id RECORD_ID --snapshot SNAPSHOT_ID --context EXTERNAL_MAPPING/cache-context.json
```

映射复用现有 Refresher 和 P5 运行记录。Refresher 比较源码、配置、提取器和输入路径后发布已完成提取产物，并验证完整图结构；不重算文件哈希。映射适配把观测点指向提取图中的节点，静态邻边保留静态含义。跨源码、运行配置和故障开关不继承原运行结论。

## 资源观测口径

OPFS 文件数/文件字节、Worker 逻辑指标/转交缓冲区、浏览器 JS heap、后端工作集、浏览器进程树工作集分别保存。缓存目录的一份有效上下文包含多个物理文件；发送端 ArrayBuffer 脱离不代表 Worker 或浏览器进程释放了等量内存。

本轮 heap 包含采集器保存的页面事件和响应副本；Windows 工作集采样可能重复计算共享页。资源结果解释所选场景，生产版本的内存基准另行设计。Python 导入成功有进程输出和生成结果证据，尚未采集逐函数 Python trace；Worker 内部通过消息和自身指标观察。

原始日志、数据库、截图、源码导出及完整图保存在 Git 外。仓库交付紧凑结果、可执行脚本与明确的未映射项；历史样本划分和 P6 外部契约资产保持原归属。
