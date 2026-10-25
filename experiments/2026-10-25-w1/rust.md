# W1：Rust 接入记录

2026-10-25。当前完成组件对照，生产统一图与平台接口接入继续执行。W1/G02 尚未通过。源码范围沿用 W0 与 [119/53/13 文件基线](README.md)，未介入历史资产，skill 留到最后整理。

## 已执行：原版组件对照

下载并运行 rust-analyzer `0.3.3089-standalone (5ec20d044d 2026-10-18)`，对应官方 [2026-10-19 发布](https://github.com/rust-lang/rust-analyzer/releases/tag/2026-10-19)。二进制、压缩包、原始 LSP 响应和日志均在仓库外；没有安装系统 Rust 工具链或修改系统 PATH。

对照 CGC `0.6.13` / `93c9685bff9151f50a3121e9913e5ba2d27c1191` 的原生 Rust parser，在相同独立源码上执行 12 项检查，全部通过。[公开证据](evidence/rust-resolver-probe.json)保存两者的原生输出投影：

| 机制 | 实测结果 |
|---|---|
| module/use、别名与重导出 | `api::invoke` 定位到实际文件内的 `run`；另一个同名函数未被选中 |
| 内联模块、super、glob | 定位到正确模块定义 |
| impl 接收者 | `a.run()` 定位到 A 的实现，同名 B 实现未被选中 |
| trait 对象 | 定义导航指向 trait 方法声明；implementation API 列出两个实现。它们仍需按分派条件作为候选 |
| 闭包绑定 | `callback()` 指向局部绑定，需要适配器继续连接绑定和值来源，不能把变量位置当作函数定义 |
| cfg 与 path | 分别给定 windows/unix 上下文时，同一 module 声明选择相应文件；显式路径覆盖也成立 |
| 参数遮蔽 | 指向函数参数，没有误连全局同名函数 |
| 声明宏 | 定义导航同时返回宏内生成定义的位置及宏调用位置，需要保留展开来源 |
| Unicode 位置 | 调用前存在非 BMP 字符时，UTF-16 请求仍定位正确 |

每个 fixture 的 `rust-project.json` 是明确的实验上下文，由测试驱动提供。此处未测自动 Cargo 项目发现，也没有把人工上下文计为自动提取。rust-analyzer 支持 JSON 项目描述和内联 `linkedProjects`，这是此次未安装 Cargo 仍能运行探针的基础；生产接入仍需自动提供 crate、依赖和配置上下文。[官方项目描述文档](https://rust-analyzer.github.io/book/non_cargo_based_projects.html)

本次禁用 Cargo 构建脚本、proc-macro 和保存时检查，没有执行被分析源码；声明宏由分析器展开。所有会话都收到 quiescent/ok 状态。LSP 使用初始化配置和状态通知等待加载；其接口依据见[官方 LSP 扩展](https://rust-analyzer.github.io/book/contributing/lsp-extensions.html)。

CGC 原生记录保留了结构与调用拼写；本批调用记录没有列坐标，实例方法接收者类型为空，闭包未单列为函数，trait 的签名声明也未列入 functions。这些是本批原生 parser 的观察，未运行 CGC 的全量跨文件解析器，不据此给两套系统计算正确率。

首轮探针有两个手写列位置错误；宏导航还返回两处来源，原参考只写了一处。核对 fixture 后修正参考，第二轮 12 项通过。原始失败保留在仓库外。这次验证支持优先复用 rust-analyzer 处理解析与定义导航；统一身份、闭包值来源、候选、配置条件和接口图仍由接入工作检验。

## 下一项

先验证自动 crate/构建上下文和真实平台源码上的定义查询，再把语法事实与语义导航接入统一图。缺失依赖、未选配置、宏展开来源和输入外目标应各自可查。平台启动后端及 WebView/资源加载至少打通第一条实际接口连接；完整跨进程配对继续按 W2 的产物和实例身份完成。

## 复现

```text
python experiments/2026-10-25-w1/probe_rust_resolvers.py --cgc CGC --parser-cache CACHE --dll-dir DLL --rust-analyzer RUST_ANALYZER --output NEW_OUTPUT
```

固定原版 CGC 提交和官方 rust-analyzer 版本，输出使用仓库外新目录。脚本复用现成解析器和 LSP API，实验过程不生成生产关系图。
