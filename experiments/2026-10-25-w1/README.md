# W1：多语言接入

2026-10-25，**W1/W2 执行中，G02/G03 尚未通过**。JavaScript、Python 和 Rust 均已接入生产图、自动刷新与独立安装查询，并在规则 5f8079d 完成[同一默认全仓快照复验](repository-recheck.md)。[CMake 生产接入](cmake-native.md)在规则 07dcab6 的 C++/CMake 控制范围通过 32 项检查。继续补全路径/进程对端及各模块机制，随后复验当前规则全仓；skill 整理与打包留到最后。

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

[CMake 原生产物接口与生产接入](cmake-native.md)通过独立夹具 62 项、Insight 真实后端配置 24 项及生产快照 32 项检查。目标、完整产物路径、编译输入、C++ 入口及依赖已进入统一导航；首次清单遗漏和修正保留。进程对端继续按[路径值传播](path-values.md)展开。

[Rust 启动路径](path-values.md)已接入生产适配：Windows 单 Cargo 配置下 33 项真实源码/统一索引检查通过，程序路径连到可执行文件目录、完整相对路径、常量及调用位置。下一项是 Python 打包复制，再连接 CMake 产物与启动消费点。

复现使用既有 CGC 环境，以下路径均由调用方提供，输出需为仓库外新目录：

```text
python experiments/2026-10-25-w1/run_native_languages.py --source SOURCE --revision d4e8d1cf9f90208bcbe5371c127088f6fd66c688 --cgc CGC --parser-cache CACHE --dll-dir DLL --output OUTPUT
```
