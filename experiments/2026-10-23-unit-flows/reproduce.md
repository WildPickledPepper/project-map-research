# 复现两个原版工具

从研究仓库根目录执行。需要 Python 3.11+、Git、rg；code-map 还需要 Node 20+、npm。CodeGraph 本轮使用官方 Windows x64 v1.39.0，未验证其他平台的同等结果。

第三方 checkout、下载包、npm cache、图和原始日志放到研究仓库之外。下面的 `../external` 是示例目录，可替换成其他外部工作目录。

## 固定输入

```powershell
git clone https://gitcode.com/Ascend/msinsight ../external/msinsight
git -C ../external/msinsight checkout --detach d4e8d1cf9f90208bcbe5371c127088f6fd66c688

git clone https://github.com/sina-parsania/CodeGraph ../external/CodeGraph
git -C ../external/CodeGraph checkout --detach 7bac941c1916d34fae0e93dd0ffeaef360d741fb

git clone https://github.com/abbaing/code-map ../external/code-map
git -C ../external/code-map checkout --detach d57c92bda4c3b1f62be8d2e75c9a45dddd430bb4
```

在 [CodeGraph v1.39.0 release](https://github.com/sina-parsania/CodeGraph/releases/tag/v1.39.0) 下载 `codegraph-windows-x64.exe` 与官方 `sha256sums.txt`，保存到外部目录，按清单校验。此轮执行文件 SHA256：

```text
54156dd1f6481b4d7658f1435b97939a606ff7447caca196bb4b89499773df22
```

code-map 安装到自己的 checkout，不执行目标项目的安装或构建：

```powershell
npm ci --prefix ../external/code-map --omit=dev --ignore-scripts --cache ../external/npm-cache --no-audit --no-fund
```

## 实际扫描、查询与对照

下面两个 output 目录必须不存在。runner 会复制真实源码片段，所有修改只针对 fixture，不修改输入 checkout。

```powershell
python experiments/2026-10-23-unit-flows/codegraph/run_experiment.py --source-repo ../external/msinsight --tool-repo ../external/CodeGraph --reference cases/unit-flows/reference.json --binary ../external/codegraph-windows-x64.exe --output ../external/codegraph-unitflows-run --phase all

python experiments/2026-10-23-unit-flows/code-map/run_experiment.py --source ../external/msinsight --tool ../external/code-map --reference cases/unit-flows/reference.json --output-dir ../external/codemap-unitflows-run
```

CodeGraph runner 执行官方原版 CLI、只读原生 SQL、HTTP 与 C++ 控制 fixture、查询触发更新和 full rebuild 对照。code-map runner 执行默认/显式配置扫描、子图查询、HTTP 控制和显式重扫；缺失 C++ 种子的退出码 3 是预期负例。

公开静态证据中的耗时来自独立试验；[协调者重跑](coordinator-reproduction.json) 排除了耗时后比较关键原生输出。CodeGraph 主输出记录全量重建约 0.2603 秒、协调者约 0.2218 秒，均不是全仓性能。code-map runner 最终打印的 slice_files 是删除 handler 后的副本文件数，初始输入仍以 manifest 的 46 个文件为准。

runner 生成的 manifest 是原生选片记录。公开版本还添加了协调者验证的 repository 元信息和 `sha256_lf_utf8`；byte-level SHA256 保留。若只想检查/复制输入文件，可使用：

```powershell
python scripts/prepare_source_slice.py --repo ../external/msinsight --manifest experiments/2026-10-23-unit-flows/codegraph/slice-manifest.json --out ../external/codegraph-input-only
python scripts/prepare_source_slice.py --repo ../external/msinsight --manifest experiments/2026-10-23-unit-flows/code-map/manifest.json --out ../external/codemap-input-only
```

这两条只按固定清单验证/复制源码，不建图；不要把复制成功视为语义结果复现。

## 核对输出

- CodeGraph：`compact-evidence.json`、`update-comparison.json`、`update-delta.json` 和 `commands.json`。
- code-map：`evidence.compact.json`、`evidence.json`、manifest 和 raw 子目录。
- 重点检查：真实切片是否缺业务接口、HTTP 两端边的方向、同路径服务是否合并、更新与重建是否相同。

不应期待两个原版恢复 Insight 全链；本实验就是记录其缺口。CI 只检查公开研究材料的一致性，不联网安装工具或替代上述实际实验。原始日志可能包含本机路径，分享前需选择性脱敏；不要直接提交整个输出目录。
