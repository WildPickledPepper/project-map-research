# P5 真实运行验证

日期：2026-10-24。当前为运行环境准备：独立实验 checkout 与依赖已就绪，Timeline 和 Framework 前端编译成功，后端编译进行中。R01–R06 尚未通过。按当前工作目标，P5 完成后暂停，P6–P7 暂不展开。

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
cmake -S server -B server/build/p5-win -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cmake --build server/build/p5-win --target profiler_server -j 4
```

在 `modules` 执行 `pnpm install --frozen-lockfile --ignore-scripts`。分别在 `modules/timeline` 和 `modules/framework` 运行 `craco build`，设置 `NODE_OPTIONS=--max-old-space-size=4096 --openssl-legacy-provider`、`GENERATE_SOURCEMAP=false`、`DISABLE_ESLINT_PLUGIN=true`、`CI=false`。这与原构建入口使用相同编译工具；直接指定 Node 参数，避开 Timeline package script 中参数前的 `==`。在 `e2e` 执行 `npm ci --ignore-scripts --no-audit --no-fund` 和 `npx --no-install playwright install chromium`。

## 数据与启动检查

[inspect_inputs.py](inspect_inputs.py)以只读 SQLite 连接检查公开 DB，读取 Text trace 的事件类型；未重新计算或核验文件哈希。现有 DB 包含 550 条 TASK、713 条 CANN_API、2,460 条 PYTORCH_API；Text trace 包含 8,375 个事件，其中 s/f flow 起止事件分别为 606/611 条。数据内容和实际运行行为分别验证。

[run_boot_probe.py](run_boot_probe.py)与 [boot_probe.cjs](boot_probe.cjs)已准备：把两个前端产物放到输出目录，以 localhost 临时端口启动真实后端及静态站点；无界面浏览器从 UI 导入复制的 trace，等待服务端解析事件和 Timeline 泳道。保存 Playwright trace、WebSocket 消息、页面截图和结果，结束后关闭本次启动的进程。该启动检查完成后再验收 `unit/flows` 正常与迟到响应场景。

```sh
python experiments/2026-10-24-p5/run_boot_probe.py \
  --source ../work/repo-map-research/msinsight-p5-runtime \
  --output ../work/repo-map-research/results/p5-boot
```

## 待完成的运行验收

1. R01：真实构建、启动、导入和数据/配置清单。
2. R02：通过 UI 触发 `unit/flows`，关联实际数据库实现、返回及最终状态；正常场景重复三次。
3. R03：控制 A 的响应晚于切换 B，验证 B 状态不受污染并找到丢弃/拒绝位置；重复三次。
4. R04：并行请求和异步边界的身份不混合；人为缺少一个采集点时明确保留缺口。
5. R05：独立副本注入迟到错误更新，确认状态断言会失败。
6. R06：运行记录绑定实际源码/构建/配置，映射同版本静态图，跨版本及未映射事件有明确状态。

独立预期以请求所属项目、选定公开数据中的 flow 和最终前端状态为准；采集轨迹用于解释过程。真实场景和故障自检结果全部保留，不能以启动成功替代运行验收。
