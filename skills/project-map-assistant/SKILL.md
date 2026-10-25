---
name: project-map-assistant
description: Query a versioned project map to understand unfamiliar code, trace cross-module interfaces and data flow, and inspect the impact of a proposed change. Use for repository exploration, end-to-end chain analysis, and checking applicable runtime evidence through the bundled project-map tool.
---

# 项目地图助手

用可查询的项目地图辅助理解源码。工具自动发现模块和支持的源码，提取接口、注册、调用、数据及状态关系；结果带源码位置、条件、版本和覆盖缺口。当前提取器重点支持 TypeScript/TSX 与 C++，其他语言保留文件清单与未展开状态。

## 工具入口

以本 skill 的目录为 `SKILL`。首次使用或环境尚未建立时读 [安装与建图](references/setup.md)。命令中的 `WORKSPACE` 是源码仓库之外的地图状态目录；工具只从指定 Git 提交建图，不改源码仓库。

```text
python SKILL/scripts/project_map.py --workspace WORKSPACE status
python SKILL/scripts/project_map.py --workspace WORKSPACE query overview --limit 20
```

已有环境可用 `--environment VENV` 指定，默认使用用户目录下 `.cache/project-map-assistant/venv`。所有参数原样传给已安装的工具；命令及查询参数见 [查询指南](references/queries.md)。普通命令行即可使用，MCP 是可选入口。

## 按任务查询

1. 先用 `status` 读取源码提交、快照、工作区改动及建图版本。地图过期时执行 `update`；研究旧版本时明确固定版本。未提交改动需要另读当前 diff，它们没有进入图。
2. 陌生项目从 `query overview`、`links`、`files` 找模块；定位任务相关函数或资源用 `search`、`entries`、`providers`。使用返回的节点 ID，避免重名误选。
3. 正向用 `trace` 或 `path` 追连接，反向用 `impact` 查消费者及共享资源。需要解释响应字段的生产和消费时用 `explain`。按需展开 `detail` 的 JSON pointer，再用 `source` 读取同一提交的源码。
4. 保留边的解析状态、条件和源码依据。路径中出现候选、多实现或部署作用域未知时，查相应注册、配置和源码，给出适用条件；图中缺边表示未知。检查 `stop_reason`、`page_complete`、`next_cursor` 和诊断，按任务需要续查，不能将截断结果当作全部影响。
5. 判断实际执行、顺序、缓存或故障时查询 `runtime`。只有源码、构建、配置、数据和场景上下文匹配的记录才可叠加；未覆盖的场景继续标为未知。采集接入和适用性见 [运行证据](references/runtime.md)。

回答围绕用户的问题组织：关键链路与影响、对应源码位置、影响结论所需的条件，以及仍需验证的具体断点。按任务选择查询，不必每次遍历全仓。

## 评测边界

此版本不接入历史问题资产。工具分发包只含 skill 和执行代码，不含研究测试题、归因、修复答案和预制项目图。对照实验由评测方提供任务、版本和允许的输入，skill 不读取研究仓库的案例或数据集目录。
