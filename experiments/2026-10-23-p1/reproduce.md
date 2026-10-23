# P1 复现

全部工具运行在独立环境中。第三方 checkout、源文件副本、数据库和原始日志放在研究仓库外；使用新的输出目录。本轮原生 CLI runner 固定 Windows 发布二进制，跨平台需要另行登记发布包与哈希；适配器测试可在 Windows/Linux 执行。

## 1. 依赖与输入

- Insight checkout：`d4e8d1cf9f90208bcbe5371c127088f6fd66c688`，tracked 文件清洁。
- CGC checkout：`93c9685bff9151f50a3121e9913e5ba2d27c1191`，安装其 0.6.13 版本到独立 Python 3.11 环境。
- CodeGraph checkout：`7bac941c1916d34fae0e93dd0ffeaef360d741fb`；v1.39.0 Windows x64 二进制及其哈希见[旧实测来源](../2026-10-23-unit-flows/codegraph/binary-provenance.json)。
- CBM：v0.12.1 Windows amd64，EXE 哈希见[本轮报告](README.md)。
- 安装 [requirements-store.txt](../../requirements-store.txt) 中固定的语法和 Kuzu 依赖。语法包首次使用会下载该版本的平台语法库。
- Windows 的 Kuzu 若需要独立 VC runtime 目录，用 `--dll-dir` 传入；无需改变全局 PATH。解析器缓存通过 `--parser-cache` 指定。

已有 CGC 本地试验的环境配置见[早期记录](../../research/experiments/2026-10-23.md)。本轮工具包版本及解析器缓存摘要保存在 [environment.json](evidence/environment.json) 和 [provenance.json](evidence/provenance.json)。缓存摘要记录 Windows 文件；Linux 测试使用同一包版本的平台文件。

以下命令从研究仓库根目录执行。`python` 表示上述独立 CGC 环境的解释器；参数中的 `/path/...` 均替换为实际目录。Windows 输出路径宜短，以满足 CBM 本地 IPC 路径限制。

## 2. 原生对照

```sh
python experiments/2026-10-23-p1/run_native.py \
  --source /path/to/msinsight \
  --cgc /path/to/CodeGraphContext \
  --cbm-binary /path/to/codebase-memory-mcp.exe \
  --parser-cache /path/to/parsers \
  --dll-dir /path/to/vclibs \
  --output /path/to/new-native-run

python experiments/2026-10-23-p1/run_codegraph.py \
  --source /path/to/msinsight \
  --tool /path/to/CodeGraph \
  --binary /path/to/codegraph.exe \
  --output /path/to/new-codegraph-run
```

两个 runner 共用文件准备函数，从之前的两个 manifest 取并集并核对源码哈希，不读取人工关系参考。代码查询在原生索引完成后筛选结果。CGC 不启用 SCIP，也未加 Query 编译缓存 shim；CodeGraph 禁用自动 SCIP；CBM 使用原生 moderate 过滤。

## 3. 补充事实与存储

```sh
python scripts/extract_syntax_facts.py \
  --source /path/to/msinsight \
  --manifest /path/to/new-native-run/input-manifest.json \
  --parser-cache /path/to/parsers \
  --output /path/to/new-native-run/syntax-facts.json

python scripts/integrate_syntax_facts.py \
  --native-run /path/to/new-native-run \
  --facts /path/to/new-native-run/syntax-facts.json \
  --dll-dir /path/to/vclibs \
  --output /path/to/new-integration
```

集成脚本核对源码提交、manifest 和文件哈希，把已关闭的原生 Kuzu 数据库复制到新目录，再导入事实。查询从数据库执行；删除验证后恢复补充事实，保留最终可查询数据库。原始 CGC 数据库不变。

## 4. 导出紧凑证据

```sh
python experiments/2026-10-23-p1/collect_evidence.py \
  --native /path/to/new-native-run \
  --codegraph /path/to/new-codegraph-run \
  --facts /path/to/new-native-run/syntax-facts.json \
  --integration /path/to/new-integration \
  --parser-cache /path/to/parsers \
  --output /path/to/new-evidence
```

导出器核对三个工具共用的 manifest，保留原生查询、过滤、关键补充事实、存储试验和实现哈希。发布时把审查过的 8 个 JSON 放入本目录 `evidence/`。JSON、fixture 和实现文件采用 LF；跨平台 Git 检出由 `.gitattributes` 固定换行。

## 5. 检查

```sh
python -m pip install -r requirements-store.txt
python -m unittest discover -s tests -v
python scripts/check_research.py
python scripts/check_trial_evidence.py
python scripts/check_p1_evidence.py
```

本地 Windows 测试可设置 `PROJECT_MAP_PARSER_CACHE` 与 `PROJECT_MAP_DLL_DIR` 指向已有隔离缓存/运行库；CI Linux 可省略。存储测试创建临时数据库，真实数据集不进入单元测试。

文档/证据检查验证引用、摘要和保存结果的一致性；重建原生结果需要执行步骤 2–4。存储边的含义与未完成项见[主报告](README.md)。
