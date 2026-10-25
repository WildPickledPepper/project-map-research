# W0：项目无关发现与独立范围核对

日期：2026-10-25。状态：**执行中，G01 尚未通过**。本轮已实现通用发现器、生成正式账本并执行独立范围检查；职责/资源归属、各类接口参考和完整模式组合继续审计。

源码固定为 Insight `d4e8d1cf9f90208bcbe5371c127088f6fd66c688`；正式生成规则为 `011164d0a2edc8caa90bee6edb26c490e94e172e`。原始源码仓库保持只读，历史资产关闭，未重新核验文件哈希。

## 结果

| 项目 | 实际结果与含义 |
|---|---|
| 跟踪文件 | 4,855，全部有归属与扫描状态 |
| 自动发现组件 | 166，含嵌套包、公开模块、Worker、支持及测试范围 |
| 必需运行组件审查 | 126 个候选组件，尚未作为确认后的产品模块总数 |
| 构建/部署支持审查 | 4 个组件，与运行候选可有重合 |
| 文本扫描 | 2,695；另有 2,148 个资源、4 个外部/生成项、8 个超预算输入 |
| 边界来源信号 | 8,136，保留位置与方向候选；两端尚待语义提取 |
| 机制 | 18 类，逐组件展开；无信号保持未知 |
| 独立范围检查 | 46 项通过，涵盖工作区包、后端模块、数据工具、插件与入口/配置来源 |
| 独立模式义务 | 13 项来源核对，尚未执行；构建组合和数据工具场景继续展开 |
| 后续组件验收义务 | 903 项，按必需运行/支持组件展开 G02–G08 |
| 评测器故障控制 | 7 项均成功检出预设错误 |
| 回归 | 370 项 Python、110 项 TypeScript 检查通过 |

8 个超预算输入均为测试数据中的大型 `trace_view.json`，保留归属和状态。166 是自动结构分解结果；边界信号不是最终语义边，也不是独立召回率分母。各类接口参考继续单独建立。

普通环境首次运行 `npm test` 因缺少 TypeScript 模块失败。使用既有固定依赖环境后 110 项通过；未修改测试断言。

## 项目无关性与新增模块

[发现器](../../adapters/project_inventory.py)读取固定提交的 Git blobs；根据清单、入口、语言包、公开导出和 Worker 等证据形成层次归属。生产实现不读取人工参考，未包含 Insight 业务模块或接口白名单。

[11 项发现测试](../../tests/test_project_inventory.py)覆盖两种不同布局、任意目录中的入口/导出、模块新增/改名/删除、未支持语言、工作副本隔离、Worker、构建/部署支持，以及字符串内嵌示例造成的伪入口。新增模块的语义连接与刷新将在 G02/G03/G07 分别验收。

独立[参考](scope-reference.json)从源码入口、工作区声明、构建和安装方式记录已知范围；[评测器](verify_scope.py)重新枚举跟踪路径并核对来源。它们均位于研究目录，不作为生产发现输入。

[故障控制](run_controls.py)仅修改临时账本副本，分别删除文件、删代理模块、伪造连接、隐藏 Rust 缺口、把未知机制标为不适用、改变版本和误报整体通过。所有错误均被独立检查拒绝，源码未变动。

## 当前产物与下一步

完整的五份账本及评测输出保存在仓库外。公开仓库保存[紧凑结果](evidence/scope-review.json)和[故障控制结果](evidence/controls.json)。运行模式表保留人工审计来源，执行状态均为未执行。

下一步完成模块职责/角色和资源归属审计，补齐各边界家族的独立正常/负例及运行验证方式，展开构建条件和数据工具场景，再冻结 G01。随后按计划接入 JS、Python、Rust 语义事实与真实连接。

## 复现

在研究仓库内使用 Python 3.11+，`SOURCE` 指向固定提交可读的 Insight checkout，所有输出选择仓库外的新目录：

```text
python scripts/build_project_inventory.py --source SOURCE --revision d4e8d1cf9f90208bcbe5371c127088f6fd66c688 --output INVENTORY
python experiments/2026-10-25-w0/verify_scope.py --source SOURCE --inventory INVENTORY --output REVIEW
python experiments/2026-10-25-w0/run_controls.py --source SOURCE --inventory INVENTORY --output CONTROLS_JSON
python -m unittest tests.test_project_inventory tests.test_repository_discovery tests.test_snapshot_inputs
python scripts/check_research.py
```

正式账本记录生成时已提交的规则版本；`--development` 仅用于开发检查。完整回归使用 `requirements-store.txt` 和固定 TypeScript 依赖。
