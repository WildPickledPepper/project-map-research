# 安装与建图

需要 Python 3.11+、Git、Node.js 22。完整分发包在 `assets/` 带一个工具 wheel。`bootstrap.py` 创建独立虚拟环境，安装该 wheel 和提取依赖；依赖首次安装及 C++ parser 首次下载需要网络。

```text
python SKILL/scripts/bootstrap.py
python SKILL/scripts/project_map.py --workspace WORKSPACE init --source REPOSITORY
python SKILL/scripts/project_map.py --workspace WORKSPACE setup
python SKILL/scripts/project_map.py --workspace WORKSPACE doctor --probe-parser
python SKILL/scripts/project_map.py --workspace WORKSPACE build
```

`setup` 只在地图目录安装 TypeScript 5.9.3。已有编译器模块可在 `init` 提供 `--typescript PATH/TO/typescript.js`。独立环境路径用 `bootstrap.py --environment VENV` 和入口的同名参数设置，也可统一设置 `PROJECT_MAP_ENV`。

源码版 skill 没有二进制附件：先从工具仓库构建 wheel，执行 `bootstrap.py --wheel PATH.whl`；仓库的 `scripts/package_skill.py` 可生成带 wheel 的完整包。

Windows 的 C++ parser/native 依赖可能需要 Microsoft VC++ 运行库。自有 parser 缓存及 DLL 目录可在 `init` 提供 `--parser-cache DIR`、`--dll-dir DIR`；`doctor --probe-parser` 会实际检查 parser，错误保留在输出中。

## 更新与已有产物

```text
python SKILL/scripts/project_map.py --workspace WORKSPACE update
python SKILL/scripts/project_map.py --workspace WORKSPACE update --watch
python SKILL/scripts/project_map.py --workspace WORKSPACE attach --graph GRAPH.json
```

更新采用完整重建，成功后发布新的导航索引；失败保留上一成功版本。watch 跟踪 Git 提交及分析配置，失败后等待输入变化或重启再试。它不包含未提交改动。`init --revision COMMIT_OR_BRANCH` 可固定其他提交；更换规则版本后执行 `update`。

`attach` 导入原有版本化图，仍需本地源码仓库含该提交。默认不假设同仓各模块部署在同一服务中，未确认的跨服务匹配保留候选和作用域缺口。有实际部署清单时在 `init --analysis FILE.json` 提供已有分析配置；不通过填写业务函数清单来手工接链。

## 可选 MCP

bootstrap 默认安装包含 MCP 的依赖。客户端注册一个 stdio 服务：command 为虚拟环境的 Python，args 为 `-I -X utf8 -m projectmap --workspace WORKSPACE serve`。无 HTTP 端口或图形界面。

服务提供 `map_status`、`map_query`、`map_field_chain`、`map_runtime` 四个只读工具；建图和更新通过上述 CLI 完成。所有查询与 CLI 共用活动快照及适用性检查。
