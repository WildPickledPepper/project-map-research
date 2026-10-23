# 复现 code-map 原版切片试验

需要 Git、Node.js 20+、npm、Python 3.11+。已执行环境版本与文件哈希见 `environment.json`。不需要 C++/.NET 构建工具，不运行目标应用。把源码、npm cache、结果目录放在研究 Git 仓库之外；以下 PowerShell 变量均为示例相对路径。

```powershell
$cmTool = '../external/code-map'
$cmSource = '../external/msinsight'
$cmResults = '../external/codemap-unitflows-run'
git clone https://github.com/abbaing/code-map $cmTool
git -C $cmTool checkout --detach d57c92bda4c3b1f62be8d2e75c9a45dddd430bb4
git clone https://gitcode.com/Ascend/msinsight $cmSource
git -C $cmSource checkout --detach d4e8d1cf9f90208bcbe5371c127088f6fd66c688
npm ci --prefix $cmTool --omit=dev --ignore-scripts --cache ../external/code-map-npm-cache --no-audit --no-fund
python experiments/2026-10-23-unit-flows/code-map/run_experiment.py --source $cmSource --tool $cmTool --reference cases/unit-flows/reference.json --output-dir $cmResults
```

runner 路径与 reference 路径按实际保存位置调整。`--output-dir` 下不得已有 `fixtures/insight`，避免混入旧配置；重跑请选择新的结果目录。runner 核对两个 checkout 的 HEAD 后复制真实切片，不会修改产品 checkout。它会生成合成 React/.NET fixture，执行 7 次 scan-only 扫描、一次子图导出、一次 inspect 和一次预期缺失种子查询。缺失种子原生退出码 3 是验收负例，runner 已断言；任何非预期退出或单进程超过 120 秒均使 runner 停止并保留日志。

可直接复核的核心 CLI（从结果中相应 fixture 根目录运行；`<tool>` 替换为固定 checkout 的路径）：

```text
node <tool>/cli.mjs --scan
node <tool>/cli.mjs --scan --config explicit.project-map.json
node <tool>/cli.mjs submap create unit-flows-imports --graph .code-map/graph.json --node file:modules/timeline/src/api/request.ts --direction both --depth 3 --output .code-map/unit-flows.submap.json --non-interactive
node <tool>/cli.mjs submap inspect .code-map/unit-flows.submap.json --json
node <tool>/cli.mjs submap create missing-handler --graph .code-map/graph.json --node file:server/src/modules/timeline/handler/QueryFlowsBySliceInfoHandler.cpp --stdout --json-errors --non-interactive
```

默认扫描在写配置之前执行。显式 Insight 配置的核心是：

```json
{
  "schemaVersion": 1,
  "project": {
    "name": "Insight real slice explicit React roots",
    "graphOutput": ".code-map/graph.json"
  },
  "sourceRoots": {"frontend": "modules", "backend": "server"},
  "imports": {"aliases": [
    {"prefix": "@insight/lib", "path": "modules/lib"},
    {"prefix": "@/", "path": "modules/framework/src"}
  ]}
}
```

该配置不声明 `runtimeLinks`、插件或人工业务连接，沿用原版默认 templates。alias 是显式的全局解析辅助，不代表已验证整个多包仓库的每个独立 tsconfig。

完整输出含第三方切片/原始图，仅留本机。提交时选择报告、紧凑 JSON、hash manifests、环境指纹、runner 和此文档；不要提交整个结果目录。各次时间戳/耗时可以变化，语义断言和期望节点/边应一致。
