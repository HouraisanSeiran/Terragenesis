# 工程生成数据整理（2026-11-07）

2026-11-08 文档整理（与二进制清理分开）：根目录过时评估/对话/旧实现状态迁入 [docs/archive/historical-reports/](../../archive/historical-reports/)；现行入口见 [docs/README.md](../../README.md)。另删除 `.scratch` 内重构合并备份中的重复 docs 树与 markmap `node_modules` 文档噪音（约 245 MiB），未动 `verification/` 与任务证据二进制。

已完成首轮清理：删除 **14 个可再生缓存/临时输出目录、714 个文件，释放 28,133,118 字节（约26.83 MiB）**。分类文档先完成，随后执行清理；没有删除原始地形输入、模型权重、有效产品、来源依赖、冻结源码、任务文档或验收证据。

用户随后明确授权删除已确认不再使用的旧实验数据，第二批已完成：删除 **64 个旧实验重复派生数组，释放2,879,146,276字节（约2.681 GiB）**。每个删除文件均有SHA256完全相同的保留副本，删除后45个保留文件已重新核验；未删除唯一数值成果或原始输入。两批合计删除778个文件，释放2,907,279,394字节（约2.708 GiB）。[第二批逐项报告](../../../.scratch/world-system-classification-20261107/obsolete-cleanup/report.md) · [旧路径及保留副本映射](../../../.scratch/world-system-classification-20261107/obsolete-cleanup/deleted-files.jsonl)。

## 已清理

| 范围 | 处理 |
| --- | --- |
| 重构交接M1/M4/M5的pytest临时、Numba和字节码缓存 | 按精确目录删除，保留before/target、SHA、报告与冻结源码 |
| `.scratch/refactor-followup-20261106/numba-cache`、`pytest-temp` | 删除已结束回归的可再生输出，保留测试日志和v1兼容fixture |
| `cache/matplotlib` | 删除字体/渲染缓存 |
| `build/classes`、`build/test-classes`、`build/tmp` | 删除可重建编译/临时文件，保留JAR和分发文件 |

每个目标先确认绝对路径在本工程下、所有路径组件和子项均非junction/reparse point、无Git跟踪文件，并比较清理前后文件数与容量。已删除目录均确认不存在。精确路径、大小、理由见[逐目录执行结果](../../../.scratch/world-system-classification-20261107/cleanup-result.json)；清理计划与盘点表保留在同目录。

## 活跃工作与保留项

盘点发现另一项海岛工作正在运行pytest，并新增/更新海岛模块和测试。根`.pytest_cache`已发生变化，第一次清理在写入前停止；随后主动从清理名单移除根pytest和活跃源码旁字节码缓存，避免干扰其他工作。本轮不停止其他测试，不删除其输出。

| 目录 | 本次盘点容量 | 保留原因 |
| --- | ---: | --- |
| `verification` | 约61.97 GiB | 历史实验、有效结果、冻结证据和来源混合；不能整目录删除 |
| `.scratch` | 约33.04 GiB | 任务、实现暂存、复验记录、旧/新产品混合；本次只删已结束任务的缓存 |
| `preview` | 约228.79 MiB | 预览产品与潜在来源引用，未逐项判定失效 |
| `temp_probe` | 约138.94 MiB | 同时包含脚本、记录与`flood.npz`等数据，名称不构成删除依据 |
| `data`、`cache/diffusion`、`artifacts` | 见完整盘点 | 存在地形源、原始TD缓存或交付产品，保留 |
| `build/libs`、`build/candidates`、`dist`与游戏运行目录 | 见完整盘点 | 交付JAR、安装/兼容材料和测试世界，保留 |
| `runtime`、`models`、`vendor`、`third_party`与外部DEM | 未扫描容量 | 环境/外部原始输入或第三方实现，不属本轮清理目标 |

容量来自一次有界stat-only盘点，跳过87个链接/运行环境等目录，不代表全盘占用或可释放容量。未读取大数组或遍历junction。最大的旧实验候选与保留依据见[数据盘点](../../../.scratch/world-system-classification-20261107/data-review.md)、[机器容量表](../../../.scratch/world-system-classification-20261107/data-inventory.json)。

## 后续持久数据清理边界

用户已选择“删除已确认不再使用的旧实验数据”，第二批按此授权执行，无需重复申请同范围许可。旧清单约36GiB尚存文件只是线索，不等于都可删除；本轮核对代码/测试/任务/正式文档引用，并用完全相同字节的保留副本确立可删重复输出。最终第37批成果、固定测试输入、原始source、唯一结果和用途不明文件继续保留，不按扩展名或目录名称批删。

旧批次在原路径执行完整冷读可能提示缺少已删除数组；各受影响目录新增`NUMERIC-DUPLICATES-REMOVED-20261107.md`列出旧路径、保留副本及SHA，历史报告/JSON和身份pin保持原样。引用扫描跳过18个大于4MB的文本及运行环境/快照，不宣称已排除全仓所有间接依赖；本批因此只删除仍保留完全相同字节的重复文件。后续唯一旧成果须另有明确的停用依据才能清理。

本次无算法数值测试、GPU推理或游戏操作。文档覆盖与源码摘要核对见[静态核对结果](../../../.scratch/world-system-classification-20261107/verification.json)。
