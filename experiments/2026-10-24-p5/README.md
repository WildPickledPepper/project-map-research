# P5 真实运行验证

日期：2026-10-24。R01–R05 已通过：独立实验 checkout 完成前后端构建和公开数据导入，正常 `unit/flows` 场景重复三次，跨层采集及最终状态断言通过。R06 继续实施。按当前工作目标，P5 完成后暂停，P6–P7 暂不展开。

## 输入与隔离

产品基准为 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`。从原下载副本创建独立本地 clone，禁用该 clone 的 push URL；所有构建、后续采集改动和故障注入只进入实验副本。GitCode 远端与原下载副本保持不动。运行时再将公开样例复制到独立输出目录，解析生成的数据库、项目记录和日志也写入该目录。

构建工具实际发现并调用：MinGW GCC 11.5.0（x86_64、msvcrt、posix、seh）、CMake 3.30.1、pnpm 9.15.9、Node 22.23.3、Python 3.11.9。CMake 配置已成功；产品文档写的 CMake 3.16–3.20 是文档范围，本轮使用 3.30.1 的结果单独记录。

后端沿用项目的依赖版本：libuv v1.44.2、uSockets v0.8.6、uWebSockets v20.48.0、SQLite 3.46.1；rapidjson 的 master 按本次实际提交固定。四个 Git 依赖的精确提交见 [输入盘点](evidence/inputs.json)。只构建 `profiler_server`，不运行桌面打包、集群分析 Python 集成或单元测试目标。

前端用仓库 `pnpm-lock.yaml` 冻结安装，GUI 测试用 `e2e/package-lock.json` 安装 Playwright 1.57.0，并准备 Chromium 143.0.7499.4 / build 1200。首链首先使用 Framework 和 Timeline 两个模块。

## 可复现准备步骤

以下命令在独立产品副本执行，编译器、CMake、Ninja、Node、pnpm 应在本次进程的 PATH 中：

```sh
git clone --no-hardlinks --config core.autocrlf=false --no-checkout ORIGINAL_CHECKOUT msinsight-p5-runtime
git -C msinsight-p5-runtime checkout --detach d4e8d1cf9f90208bcbe5371c127088f6fd66c688
git -C msinsight-p5-runtime remote set-url --push origin disabled://p5-local-experiment
```

按产品 `server/build/download_third_party.py` 中的地址，将上述四个依赖下载到实验副本 `server/third_party/` 并切换到输入盘点中的提交。然后在 `server/build` 执行 `python preprocess_third_party.py`，复用其 Windows SQLite 下载和整理流程。

产品副本根目录：

```sh
cmake -S server -B server/build/p5-win -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DCMAKE_SHARED_LINKER_FLAGS=-Wl,--exclude-libs,libssp.a
cmake --build server/build/p5-win --target profiler_server -j 4
```

本次配置和后续重建固定 `SOURCE_DATE_EPOCH=1792773720`，时区为 Asia/Shanghai（UTC+08:00），对应产品宏 `DATABASE_VERSION=2026102400`。产品用 `string(TIMESTAMP)` 生成该宏；固定时间使后续插桩构建使用相同数据库版本，避免跨小时重新配置导致全量重编译。此环境变量由 [CMake 3.30 官方文档](https://cmake.org/cmake/help/v3.30/command/string.html#timestamp)定义。

首次链接失败于 `__stack_chk_fail` 重复定义。上述共享库链接参数排除 `libssp.a` 符号的自动导出，保留原有栈保护编译参数；重建后链接成功，真实启动与导入通过。参数语义见 [GNU ld 文档](https://sourceware.org/binutils/docs/ld/Options.html)。

在 `modules` 执行 `pnpm install --frozen-lockfile --ignore-scripts`。分别在 `modules/timeline` 和 `modules/framework` 运行 `craco build`，设置 `NODE_OPTIONS=--max-old-space-size=4096 --openssl-legacy-provider`、`GENERATE_SOURCEMAP=false`、`DISABLE_ESLINT_PLUGIN=true`、`CI=false`。这与原构建入口使用相同编译工具；直接指定 Node 参数，避开 Timeline package script 中参数前的 `==`。在 `e2e` 执行 `npm ci --ignore-scripts --no-audit --no-fund` 和 `npx --no-install playwright install chromium`。

## 数据与启动检查

[inspect_inputs.py](inspect_inputs.py)以只读 SQLite 连接检查公开 DB，读取 Text trace 的事件类型；未重新计算或核验文件哈希。现有 DB 包含 550 条 TASK、713 条 CANN_API、2,460 条 PYTORCH_API；Text trace 包含 8,375 个事件，其中 s/f flow 起止事件分别为 606/611 条。数据内容和实际运行行为分别验证。

[run_boot_probe.py](run_boot_probe.py)与 [boot_probe.cjs](boot_probe.cjs)已执行：把两个前端产物放到输出目录，以 loopback 地址启动真实后端及静态站点。脚本从产品参数解析源码读取允许的 9000–9100 端口范围，选择空闲后端端口；站点使用系统分配端口。浏览器等待 Timeline 界面就绪，再从 UI 导入复制的 trace，等待解析完成事件并检查实际泳道文本。保存 Playwright trace、WebSocket 消息、页面截图和结果，结束后关闭本次启动的进程。

成功运行 `p5-boot-03` 捕获 70 条 WebSocket 消息，无页面脚本异常；看到 `parse/success`、`allPagesSuccess` 和五个 `unit/threadTracesSummary` 请求。[紧凑证据](evidence/boot.json)保存构建参数、全部启动尝试和成功结果。原始日志与截图位于外置 `results/p5-runtime-01/`、`results/p5-boot-01/` 至 `p5-boot-03/`。

前两次失败也保留：第一次选择了产品范围外的端口，原生参数解析拒绝启动；第二次过早导入，后端解析完成时 Timeline 尚未准备好，泳道断言失败。第三次在导入前等待 Timeline 就绪后通过。未构建的 Memory/Operator 页面有两个 404，本次验收范围为 Framework、Timeline 与 Text 数据。后端还记录未提供的可选 RL 配置；本轮样例未启用 RL。

```sh
python experiments/2026-10-24-p5/run_boot_probe.py \
  --source ../work/repo-map-research/msinsight-p5-runtime \
  --output ../work/repo-map-research/results/p5-boot
```

## 待完成的运行验收

采集实现：[instrument_runtime.py](instrument_runtime.py)已在独立副本应用十个文件的采集改动。[C++ 辅助代码](ProjectMapProbe.h)记录解码、实际 handler、数据库虚调用和系统线程身份；[浏览器采集](browser_probe.cjs)记录 UI 动作、API、响应处置和状态赋值。实验提交 `f76b3db12717c6e5ab33764a9f49d9ff8b89be7d` 完成前后端重建；后续 `ccd0d88080861b0c7185bcca70a85bd61f823168` 将 C++ 线程编号改为 `GetCurrentThreadId` 并重建后端，前端源码保持相同。最终三次运行使用后一个提交。上述提交仅存在于禁用 push 的本地产品副本。

关联使用运行/连接范围内的请求编号，并为首链添加命名空间隔离的 `params.__projectMapTrace` 元数据，将 iframe API 调用与实际 WebSocket 请求绑定。C++ 参数解码按已知字段取值；三次正常运行均接受追踪元数据，响应端点与独立输入预期一致。时钟只用于展示，不作为请求因果的唯一依据。源码钩子必须在禁用 push 的实验副本上应用，应用后提交本地源码并重建；运行证据使用该实验提交。

### R02 正常场景结果

[flow_scenario.cjs](flow_scenario.cjs)从公开 trace 独立读取第一个 `Enqueue` 及其 s/f flow 两端，通过真实搜索界面定位算子，再点击画布触发查询。输入 flow 为 `8234 / async_task_queue`，来源线程 `3016828`、目标线程 `3020403`。后端当前 Text 路径返回的 flow `id` 为空，因此断言按类别、两端进程/线程和绝对时间验证，保留原始输入 ID 作参考。

三次最终运行 `p5-normal-final-01` 至 `03` 均通过：响应返回一条预期 flow，最终状态包含一条对应连线，选中算子和 rank 与请求相同。[关联检查器](verify_capture.py)连接 UI、API、WebSocket 请求、解码、handler、数据库调用/返回、WebSocket 响应、前端分类/采用、API 返回和状态赋值；检查 API 解包结果与线上响应 body 相同，实际数据库类型为 `TextTraceDatabase`。[紧凑证据](evidence/normal.json)保存每次结果、阶段、线程和全部试验目录。

初版采集在 DLL 和 executable 中观察到不同的 `std::thread::id` 值。改用 Windows 系统线程 ID 后，同一次 handler 与数据库调用记录为相同线程，解码在另一线程；请求编号跨该边界保持一致。关联本身使用显式身份，不用线程编号或时间接近代替请求身份。

[采集负例](check_capture_controls.py)从真实运行证据派生三个变体：删除数据库返回记录、替换解码追踪标识、重复请求编号。三者均被拒绝为完整链；缺失记录保留“由当前采集无法确定是否执行”。这些检查验证采集器与关联器，产品错误注入和并发运行分别在 R05、R04 验收。

复现正常场景：

```sh
python experiments/2026-10-24-p5/instrument_runtime.py --source EXPERIMENTAL_CHECKOUT
# 在实验副本提交脚本列出的文件，按上文固定时间与参数重新构建。
python experiments/2026-10-24-p5/run_boot_probe.py --source EXPERIMENTAL_CHECKOUT --output NEW_EXTERNAL_RUN --scenario normal
python experiments/2026-10-24-p5/verify_capture.py --run NEW_EXTERNAL_RUN
python experiments/2026-10-24-p5/check_capture_controls.py --run NEW_EXTERNAL_RUN --output NEW_EXTERNAL_CONTROLS
```

采集器对单次运行限定一条 WebSocket 连接；重连需要补充服务端连接代际标识后再扩大关联范围。原始页面、日志和截图含本机路径，均保存在仓库外。

### R03 查询中切换项目

[late_scenario.cjs](late_scenario.cjs)先通过 UI 导入 A、B 两份独立的公开数据，再从项目树切回 A，搜索并点击目标算子。[ws_gate.cjs](ws_gate.cjs)使用安装版本 Playwright 1.57 的 `routeWebSocket` / `connectToServer` 暂存真实 `unit/flows` 响应。切换到 B、确认其选中项与连线为空后，发送原响应字节；其余通信持续正常转发。

`p5-late-01`、`02`、`03` 三次全部通过。实际 `response.classified` 显示请求属于 A、当前项目为 B，随后出现 `response.discarded`；该追踪标识没有 API 返回或状态采用记录。独立读取的 B 最终状态与放行前相同，连线、选中项和绘制模式均未被 A 覆盖。[结果与顺序证据](evidence/late.json)包含三次完整摘要和两次驱动调试失败；正常场景回归及三个采集负例也通过。

```sh
python experiments/2026-10-24-p5/run_boot_probe.py --source EXPERIMENTAL_CHECKOUT --output NEW_EXTERNAL_RUN --scenario late
python experiments/2026-10-24-p5/verify_capture.py --run NEW_EXTERNAL_RUN
```

1. R01（通过）：真实构建、启动、导入和数据/配置清单。
2. R02（通过）：通过 UI 触发 `unit/flows`，关联实际数据库实现、返回及最终状态；正常场景重复三次。
3. R03（通过）：控制 A 的响应晚于切换 B，验证 B 状态不受污染并找到丢弃/拒绝位置；重复三次。
4. R04（通过）：并行请求和异步边界的身份不混合；人为缺少一个采集点时明确保留缺口。
5. R05（通过）：独立副本注入迟到错误更新，确认状态断言会失败。
6. R06：运行记录绑定实际源码/构建/配置，映射同版本静态图，跨版本及未映射事件有明确状态。

独立预期以请求所属项目、选定公开数据中的 flow 和最终前端状态为准；采集轨迹用于解释过程。真实场景和故障自检结果全部保留，不能以启动成功替代运行验收。

### R05 状态断言自检

[inject_late_fault.py](inject_late_fault.py)在禁用推送的本地副本中给旧响应守卫增加显式测试开关，实验提交为 `7f851c66b12a833ebeb2e3b12bf527a1cf0aea7a`。重新构建 Framework 后，用同一构建、同一公开样例和同一项目切换脚本运行对照：

- `p5-fault-control-01`：测试开关关闭，旧响应丢弃，B 状态断言通过。
- `p5-fault-01`：测试开关开启，旧响应进入真实回调、API 和状态赋值；B 仍是当前项目，其连线出现 A 的 rank 数据。`Late A response must not change B flow lines` 断言失败，场景退出 1。
- `p5-fault-restored-01`：恢复正常采集提交 `ccd0d88080861b0c7185bcca70a85bd61f823168` 并重建 Framework，迟到场景及关联检查再次通过。

[check_fault_result.py](check_fault_result.py)确认失败发生在目标状态断言，核对真实采用记录、B 中的 A 数据和同版本正常对照。[紧凑证据](evidence/fault.json)将“故障场景失败”与“断言自检通过”分别保存。

```sh
python experiments/2026-10-24-p5/inject_late_fault.py --source EXPERIMENTAL_CHECKOUT
# 本地提交该脚本报告的文件并重建 Framework。
python experiments/2026-10-24-p5/run_boot_probe.py --source EXPERIMENTAL_CHECKOUT --output NEW_CONTROL_RUN --scenario late
python experiments/2026-10-24-p5/run_boot_probe.py --source EXPERIMENTAL_CHECKOUT --output NEW_FAULT_RUN --scenario late --allow-stale-response
# 上一条命令预期退出 1；下一条验证是否命中了预定的状态违例。
python experiments/2026-10-24-p5/check_fault_result.py --control NEW_CONTROL_RUN --fault NEW_FAULT_RUN
```

### R04 两个待返回请求与采集缺口

[parallel_scenario.cjs](parallel_scenario.cjs)通过真实搜索和画布点击选择两个不同的 Enqueue。两条真实响应均暂存在传输门，确认两个请求同时处于等待状态后按请求顺序放行。`p5-r04-parallel-01` 通过：算子 861、862 对应不同 flow，API 结果和各自状态赋值分别与其线上响应一致，最终选中项与连线属于第二条请求。解码及 handler/数据库线程均记录为原生系统线程，跨异步边界通过显式身份连接。

四项派生采集负例全部通过：删除一条请求的数据库返回只使该链出现“执行未知”，另一条仍完整；替换解码追踪标识、重复请求编号、交换两个 API 结果均被识别。正常查询和切换项目场景使用当前驱动回归通过。[紧凑证据](evidence/parallel.json)保存请求、线程、顺序及负例结果。

本项验证两个 UI 请求同时未完成时的身份关联；响应按请求顺序放行，数据库执行的时间重叠不在本项断言范围。

```sh
python experiments/2026-10-24-p5/run_boot_probe.py --source EXPERIMENTAL_CHECKOUT --output NEW_EXTERNAL_RUN --scenario parallel
python experiments/2026-10-24-p5/verify_capture.py --run NEW_EXTERNAL_RUN
python experiments/2026-10-24-p5/check_capture_controls.py --run NEW_EXTERNAL_RUN --output NEW_EXTERNAL_CONTROLS
```
