# W1：多语言原生输出基线

2026-10-25，**W1 执行中，G02 尚未通过**。先保存已选上游的原生事实，再接入统一身份、语义连接和查询。

[实测结果](evidence/native-summary.json)来自原版 CGC `0.6.13` / `93c9685bff9151f50a3121e9913e5ba2d27c1191`，源码为 Insight `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`。全部目标语言文件从 Git blobs 导出到独立目录；上游实现和原始 checkout 均未修改，未重新核验文件哈希。

| 原生语言组件 | 文件 | functions 记录 | 调用记录 | import 记录 |
|---|---:|---:|---:|---:|
| JavaScript | 53 | 102 | 1,057 | 99 |
| Python | 119 | 1,586 | 9,214 | 884 |
| Rust | 13 | 146 | 873 | 170 |

185 个文件均返回结果，未报解析错误；范围含产品、测试、构建和文档脚本，角色逐文件保留。这些是上游原生记录数，跨文件身份/调用正确性尚待独立检查。

原始输出保存在仓库外的 `raw-parser`。本轮没有执行 CGC 跨文件解析器，也没有生成归一化图，安装后的工具尚未因此获得这些语言的查询能力。

接下来先检验 TypeScript 编译器对 JS/TS 混合、ESM/CommonJS 的解析，接入真实 TS↔JS 运行组件；Python/Rust 对照原生结构补充作用域、包/module 和配置条件，再验证代理和后端启动连接。三种语言均按 G02 和首条 G03 实际连接验收。

复现使用既有 CGC 环境，以下路径均由调用方提供，输出需为仓库外新目录：

```text
python experiments/2026-10-25-w1/run_native_languages.py --source SOURCE --revision d4e8d1cf9f90208bcbe5371c127088f6fd66c688 --cgc CGC --parser-cache CACHE --dll-dir DLL --output OUTPUT
```
