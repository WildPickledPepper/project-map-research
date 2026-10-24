# 历史遗留分类中的改动回归候选

日期：2026-10-24。证据类型：原始问题记录与源码检查；本轮未运行复现。

[下载候选表（Excel）](historical-change-regression-candidates.xlsx)。工作簿包含 7 条候选的详细归因、限制和证据，以及原表 33 条“历史遗留问题”的筛查登记。原表行号用于回溯内部问题记录。

对这 7 条核对了相关引入提交、父版本与后续修复差异，发现过去改动影响旧模块的候选关系。它们尚未分配开发或验证集合；原 [24 条样本划分](split.md)保持不变，不能据此计为 31 条已验证测试样本。

## 源码核对结果

下表提交链接固定相关引入改动，修复 PR 提供后续处理线索；完整版本与来源见工作簿。

| 原表行号 | 相关改动 | 对旧模块的影响 | 后续修复 |
|---|---|---|---|
| 5 | [!905](https://gitcode.com/Ascend/msinsight/pull/905)，[6247674](https://gitcode.com/Ascend/msinsight/commit/6247674f23d1c3d4dfaa3bcebf9c32bd5d295be5) | OPFS 增量绘制将 blocks、allocations 请求并行化，增大旧 WebSocket 通道的大响应与背压负担 | [!1022](https://gitcode.com/Ascend/msinsight/pull/1022)，master |
| 18 | [!1101](https://gitcode.com/Ascend/msinsight/pull/1101)，[4e1ca2b](https://gitcode.com/Ascend/msinsight/commit/4e1ca2b38e0de90e68a0d410ff1054f638729fe6) | 快照分窗后数据库就绪状态按切片变化，旧泄漏统计和详情消费者缺少切片就绪判断 | [!1129](https://gitcode.com/Ascend/msinsight/pull/1129)，master |
| 71 | [!659](https://gitcode.com/Ascend/msinsight/pull/659)，[49791d6](https://gitcode.com/Ascend/msinsight/commit/49791d672fc384eafe94f429fe0d622b5a66ee6b) | 联合导入校验新增目录遍历，绕开已有 FileUtil 的 Windows 长路径支持 | [!872](https://gitcode.com/Ascend/msinsight/pull/872)，master |
| 69 | [8f87bd8](https://gitcode.com/Ascend/msinsight/commit/8f87bd8410418b7038c66ae38b0b2fc5d7ef1617) | 屏蔽混合数据对比时，按记录数量拒绝并移除选中路径过滤，误拒同类型多记录 | [!1208](https://gitcode.com/Ascend/msinsight/pull/1208)，master |
| 63 | [e562eb0](https://gitcode.com/Ascend/msinsight/commit/e562eb010654a713bc2c9452b209e53b887cb259) | 范围锁定加入连线请求参数，却未加入刷新依赖，锁定变化后不能立即重查 | [!1197](https://gitcode.com/Ascend/msinsight/pull/1197)，26.2.0 |
| 27 | [935ec78](https://gitcode.com/Ascend/msinsight/commit/935ec78901b235f18e48e27073a573bff5772380) | 连线性能改动引入每次绘制复制整棵 units 树，新增复制和垃圾回收成本 | [!912](https://gitcode.com/Ascend/msinsight/pull/912)，master |
| 29 | [df5c3e5](https://gitcode.com/Ascend/msinsight/commit/df5c3e57123fc021af85d0df9967908fe9465ea9) | 目录搜索修复同时将固定高度从 310px 增至 500px，放大旧弹窗的小屏溢出问题 | [!1179](https://gitcode.com/Ascend/msinsight/pull/1179)，master |

## 复现与集合限制

- 第 5 行与既有开发样本 1、5 同属 OPFS 家族；同一 Issue #499 的 !1036、!1056、!1066 是后续并发或消息大小处理，未计为独立新增回归。
- 第 18 行与开发样本 8、关联回归 7、验证候选 4/6 的分窗家族有关。第 27、63 行涉及已研究的 unit/flows 链，不能仅因未在原 24 条内就视为独立验证。
- 第 69、71、29 行尚未在原 24 条中登记，当前同样保持集合未分配。
- 第 27 行证明新增复制成本；整体现象与首次性能失败阈值需测量。第 29 行证明高度增加 190px；首个失败版本需固定窗口尺寸复现。
- 第 71 行应以短根路径、深层超长子路径隔离新增遍历的影响。第 18 行仍需实际时序复现数据库就绪问题。
- 部分历史提交来自迁移前历史，提交对象可定位不等于已证明其与当前分支的精确祖先关系；坏版本、修复版本和触发条件在执行前分别固定。
