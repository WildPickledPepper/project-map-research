# P5 运行材料盘点

日期：2026-10-24。证据类型：固定源码检查与本地文件/命令发现。P5 运行和场景验收尚未执行。

源码版本沿用 `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`。已有材料足以开始准备本地构建与场景，后续先复用项目自带的测试框架。

| 材料 | 已观察内容 | 下一步 |
|---|---|---|
| `e2e/package.json` | 固定 `@playwright/test` 1.57.0，已有全量与冒烟入口 | 安装锁定依赖并选择最小用例 |
| `e2e/playwright.config.ts` | headless；前端 localhost:5174；后端 wsHost=127.0.0.1、wsPort=9000；Windows 使用 MinGW 产物 | 验证前后端构建并以隔离配置启动 |
| `test/data/pytorch/db/level0/rank0_ascend_pt/ASCEND_PROFILER_OUTPUT/ascend_pytorch_profiler_0.db` | 本地文件存在，679,936 字节 | 检查 schema、flow 数据和最小场景适用性 |
| `test/data/pytorch/text/level0/rank0_ascend_pt/ASCEND_PROFILER_OUTPUT/trace_view.json` | 本地文件存在，1,805,798 字节 | 检查数据与 DB/Text 分支的关系 |
| `test/st/README.md` | 记录 Qwen3-0.6B、四卡训练及采集配置，说明部分 rank 删除了非必要文件 | 选定场景数据后按其采集范围解释覆盖 |
| Windows 当前 PATH | 发现 node、wsl；未发现 cmake、ninja、clang++、g++、cl、msbuild、docker、rustc、cargo | 检查已安装但未进 PATH 的编译工具与 WSL 环境 |

现有 Playwright 配置为 `retries: 0`、`trace: 'on-first-retry'`。P5 需要明确启用本次场景的 trace，另加跨语言请求关联、后端执行记录、最终状态断言和迟到响应自检。已有测试框架的存在不等于这些采集与断言已接入。

开发环境文档提供后端第三方依赖下载/预处理、前端 pnpm 安装及各平台编译说明。GUI 测试 README 还指向独立演示数据仓库；本轮尚未下载该数据仓库，先检查当前已有样例。

源码依据：[环境搭建](https://gitcode.com/Ascend/msinsight/blob/d4e8d1cf9f90208bcbe5371c127088f6fd66c688/docs/zh/development_guide/environment_setup.md)、[GUI 测试说明](https://gitcode.com/Ascend/msinsight/blob/d4e8d1cf9f90208bcbe5371c127088f6fd66c688/e2e/README.md)、[Playwright 配置](https://gitcode.com/Ascend/msinsight/blob/d4e8d1cf9f90208bcbe5371c127088f6fd66c688/e2e/playwright.config.ts)、[测试依赖](https://gitcode.com/Ascend/msinsight/blob/d4e8d1cf9f90208bcbe5371c127088f6fd66c688/e2e/package.json)、[ST 数据采集说明](https://gitcode.com/Ascend/msinsight/blob/d4e8d1cf9f90208bcbe5371c127088f6fd66c688/test/st/README.md)。

继续按 [P5 计划](../../plans/implementation-plan.md)验证正常查询、查询中切换项目、故障注入；正常和切换场景各重复三次。文件大小只用于定位材料，本轮没有核验文件哈希。
