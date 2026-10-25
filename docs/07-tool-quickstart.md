# 使用项目地图 skill

最终入口为 [project-map-assistant](../skills/project-map-assistant/SKILL.md)。它携带查询规则和执行脚本，工具生成的项目地图与研究材料分开保存。

完整分发包解压后将 `project-map-assistant` 放到 AI 客户端的 skills 目录。按 skill 的 [安装说明](../skills/project-map-assistant/references/setup.md)执行 bootstrap、init、setup、doctor 和 build，然后可用：

```text
$project-map-assistant 请说明当前项目的主要模块，以及这次修改涉及哪些接口和消费者。
```

skill 使用 CLI 查询；支持 MCP 的客户端也可以选用四个只读工具。源码不被工具修改，地图只反映选定 Git 提交。历史资产当前关闭，运行记录需要相应项目的采集与上下文。

## 从源码构建分发包

在干净、已提交的工具版本上，使用具备 setuptools/wheel 的 Python：

```text
python -m pip wheel --no-deps --no-build-isolation --wheel-dir OUTSIDE_REPO/wheels .
python scripts/package_skill.py --wheel OUTSIDE_REPO/wheels/project_map_tool-0.2.0-py3-none-any.whl --output OUTSIDE_REPO/project-map-assistant.zip
```

需要时增加 `--install-to NEW_SKILL_DIRECTORY`；目标必须不存在，脚本保留已有 skill。打包器检查 wheel 内容白名单及规则 Git 提交。二进制、依赖、图和原始日志不入研究仓库。

独立安装后的真实提取检查：

```text
python scripts/smoke_installed_tool.py --python VENV_PYTHON --output NEW_OUTSIDE_DIRECTORY
```

该检查创建独立 TS/C++ 小仓库，调用安装后的工具建图、改名更新、反向查询和读取固定版本源码；它不加载历史问题测试材料。后续 AI 对照实验安排见 [交付计划](../plans/tool-and-skill.md)。
