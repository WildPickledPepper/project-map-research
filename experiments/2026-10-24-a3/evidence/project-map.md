# 自动生成的项目地图

来源：已执行的 A3 查询；模块按最近受版本控制构建清单归属。

源码提交：`d4e8d1cf9f90208bcbe5371c127088f6fd66c688`。快照：`d4e8d1cf9f90208bcbe5371c127088f6fd66c688:full:db2898b7ae2d485d899b2775fe68eb31`。

图中连线汇总跨模块的源码关系与条件候选；箭头沿事实边方向，数量包含不同关系类型和平行边。

```mermaid
flowchart LR
  m0[".<br/>4 个分析输入"]
  m1["e2e<br/>50 个分析输入"]
  m2["modules<br/>6 个分析输入"]
  m3["modules/cluster<br/>69 个分析输入"]
  m4["modules/compute<br/>66 个分析输入"]
  m5["modules/framework<br/>62 个分析输入"]
  m6["modules/leaks<br/>128 个分析输入"]
  m7["modules/lib<br/>75 个分析输入"]
  m8["modules/memory<br/>55 个分析输入"]
  m9["modules/memory-on-chip<br/>24 个分析输入"]
  m10["modules/numa<br/>45 个分析输入"]
  m11["modules/operator<br/>25 个分析输入"]
  m12["modules/reinforcement-learning<br/>28 个分析输入"]
  m13["modules/statistic<br/>29 个分析输入"]
  m14["modules/timeline<br/>287 个分析输入"]
  m15["platform<br/>1 个分析输入"]
  m16["platform/linux<br/>1 个分析输入"]
  m17["plugins/jupyterlab<br/>19 个分析输入"]
  m18["pre-commit<br/>1 个分析输入"]
  m19["server<br/>4 个分析输入"]
  m20["server/msinsight<br/>53 个分析输入"]
  m21["server/src<br/>918 个分析输入"]
  m22["server/src/entry<br/>1 个分析输入"]
  m23["server/src/entry/server<br/>1 个分析输入"]
  m24["server/src/entry/server/bin<br/>2 个分析输入"]
  m25["server/src/test<br/>345 个分析输入"]
  m26["server/src/test/fuzz<br/>11 个分析输入"]
  m27["server/third_party<br/>0 个分析输入"]
  m28["server/third_party/sqlite<br/>0 个分析输入"]
  m3 -->|33| m5
  m3 -->|116| m7
  m4 -->|3| m2
  m4 -->|14| m5
  m4 -->|61| m7
  m5 -->|40| m3
  m5 -->|22| m4
  m5 -->|108| m7
  m5 -->|18| m8
  m5 -->|12| m11
  m5 -->|6| m13
  m5 -->|68| m14
  m5 -->|98| m21
  m6 -->|14| m5
  m6 -->|27| m7
  m7 -->|60| m3
  m7 -->|55| m4
  m7 -->|45| m8
  m7 -->|18| m11
  m7 -->|15| m13
  m7 -->|137| m14
  m8 -->|12| m2
  m8 -->|10| m5
  m8 -->|53| m7
  m9 -->|11| m7
  m10 -->|10| m2
  m10 -->|9| m7
  m11 -->|6| m5
  m11 -->|44| m7
  m12 -->|14| m7
  m13 -->|3| m5
  m13 -->|30| m7
  m14 -->|46| m5
  m14 -->|166| m7
  m20 -->|173| m21
  m20 -->|308| m25
  m21 -->|19349| m20
  m21 -->|1| m24
  m21 -->|12269| m25
  m24 -->|22| m20
  m24 -->|4| m21
  m25 -->|5175| m20
  m25 -->|13210| m21
  m26 -->|9| m20
  m26 -->|8| m21
```

| 模块 | 受版本控制文件 | 分析输入 | 源码实体 |
|---|---:|---:|---:|
| `.` | 1930 | 4 | 0 |
| `e2e` | 288 | 50 | 5273 |
| `modules` | 27 | 6 | 23 |
| `modules/cluster` | 73 | 69 | 5149 |
| `modules/compute` | 77 | 66 | 2769 |
| `modules/framework` | 69 | 62 | 2960 |
| `modules/leaks` | 145 | 128 | 13277 |
| `modules/lib` | 159 | 75 | 4555 |
| `modules/memory` | 59 | 55 | 3829 |
| `modules/memory-on-chip` | 28 | 24 | 262 |
| `modules/numa` | 53 | 45 | 937 |
| `modules/operator` | 30 | 25 | 679 |
| `modules/reinforcement-learning` | 32 | 28 | 209 |
| `modules/statistic` | 33 | 29 | 536 |
| `modules/timeline` | 375 | 287 | 18077 |
| `platform` | 23 | 1 | 0 |
| `platform/linux` | 1 | 1 | 0 |
| `plugins/jupyterlab` | 33 | 19 | 521 |
| `pre-commit` | 3 | 1 | 0 |
| `server` | 10 | 4 | 0 |
| `server/msinsight` | 53 | 53 | 4867 |
| `server/src` | 919 | 918 | 109058 |
| `server/src/entry` | 1 | 1 | 0 |
| `server/src/entry/server` | 1 | 1 | 0 |
| `server/src/entry/server/bin` | 2 | 2 | 71 |
| `server/src/test` | 415 | 345 | 98357 |
| `server/src/test/fuzz` | 12 | 11 | 328 |
| `server/third_party` | 1 | 0 | 0 |
| `server/third_party/sqlite` | 3 | 0 | 0 |

逐层查询命令见 [A3 使用说明](../README.md)。无分析输入的模块仍保留在地图中，具体排除理由由 files 查询给出。
