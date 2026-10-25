# W1：多语言接入

2026-10-25，**W1 执行中，G02 尚未通过**。JavaScript、Python 和 Rust 均已接入生产图、自动刷新与独立安装查询，并完成[同一默认全仓快照复验](repository-recheck.md)。接下来按 W0 账本逐模块核对事实与缺口，继续补全跨进程对端；skill 整理与打包留到最后。

## 原生组件基线

[实测结果](evidence/native-summary.json)来自原版 CGC `0.6.13` / `93c9685bff9151f50a3121e9913e5ba2d27c1191`，源码为 Insight `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`。全部目标语言文件从 Git blobs 导出到独立目录；上游实现和原始 checkout 均未修改，未重新核验文件哈希。

| 原生语言组件 | 文件 | functions 记录 | 调用记录 | import 记录 |
|---|---:|---:|---:|---:|
| JavaScript | 53 | 102 | 1,057 | 99 |
| Python | 119 | 1,586 | 9,214 | 884 |
| Rust | 13 | 146 | 873 | 170 |

185 个文件均返回结果，未报解析错误；范围含产品、测试、构建和文档脚本，角色逐文件保留。这些是上游原生记录数，跨文件身份/调用正确性尚待独立检查。

原始输出保存在仓库外的 `raw-parser`。该原生基线未执行 CGC 跨文件解析器；后续 JS 接入使用既有 TypeScript 编译器，Python 使用 AST/Jedi，Rust 使用 Tree-sitter/Cargo/rust-analyzer。三者均已生成统一图并通过安装后查询。

三种语言的基础事实、调用/值来源、条件及首条接口已保存独立证据；Python/Rust 到后端的实际对端继续按 W2 的产物和实例身份展开。三种语言均按 G02 和首条 G03 实际连接验收。

[Rust 基础事实与平台接口](rust.md)已进入生产图：12 项组件检查、80 项原生入口检查、41 项 Rust 生产图检查和 22 项独立安装/模块更新检查通过。两份 Cargo 清单的 24 组上下文分别保留；统一导航能查到进程启动、WebView 加载及资源协议回调。

同一默认全仓快照包含 2,496 个源码与清单输入；Rust 41 项、Python 137 项、JS 链 14 项和 JS 范围 1,218 项检查均通过。详细版本、实际范围、首次磁盘失败及恢复见[全仓复验记录](repository-recheck.md)。后端对端配对与全模块覆盖继续验收。

[129 个必需组件的逐项事实对照](module-fact-audit.md)已生成，明确列出 Shell、声明/常量、C++ 解析及跨组件连接的审查队列；账目检查与语义门槛分别记录。

[CMake 原生产物接口预备实验](cmake-native.md)通过 62 项检查，确认可复用目标、产物路径、源文件、配置及声明回溯。此项为 W2 组件验证，尚未配置 Insight 或连接生产进程对端。

复现使用既有 CGC 环境，以下路径均由调用方提供，输出需为仓库外新目录：

```text
python experiments/2026-10-25-w1/run_native_languages.py --source SOURCE --revision d4e8d1cf9f90208bcbe5371c127088f6fd66c688 --cgc CGC --parser-cache CACHE --dll-dir DLL --output OUTPUT
```
