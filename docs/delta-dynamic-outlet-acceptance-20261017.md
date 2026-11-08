# 三角洲动态供沙与出口分配验收

2026-10-17：修复独立对照器的输沙方向和空间路由问题，并用已保存河流的全年实际供沙完成空间反馈验收。DeepSeek 编写实现与返工，主协调审查、修正集成、补充验收并检查实际图。原 v10 生成器和场景09保持不变。

## 本轮实现

- 非空间预算修正为低于运输目标的泥沙继续输送，超额部分沉积；零来水时泥沙保留为未输送余量，不凭空外排。移除按分支编号施加的偏置，显式初始阻力才可造成非对称。
- 空间对照器复用一次完整 `simulate_fluvial_delta`，保留各时间窗之间的床面和库存，不再自行搜索三条固定路径或沿路径均匀填沙。
- 分配比例来自实际海侧出口水量。出口必须完整覆盖声明的海洋外排格；入口、无效格、超过水头的阻挡和强迫入口不一致均有检查。
- 固体转床面使用孔隙率及格面积；总沉积、再侵蚀、净库存、海洋外排和未输送量分别记录，不把反复沉积算成净增长。
- 新增保存案例验收工具，保存逐窗床面、库存、流量通过体积、出口水沙和对照数据；重新打开后逐项精确重放，拒绝数组、预算、汇总指标或来源变更。

实现：[`metric_river_dominant_delta.py`](../terrain_pipeline/surface_rivers/metric_river_dominant_delta.py)。案例入口：[`verify_river_dominant_saved_source.py`](../tools/verify_river_dominant_saved_source.py)。没有修改底层水沙内核或 v10 静态生成器。

## 同源案例

新产物位于 [`river-dominant-saved-source-20261017-01`](../verification/fluvial-delta/river-dominant-saved-source-20261017-01/summary.json)。输入为此前保存的 96×96、30m 栅格河口，范围2.88km×2.88km；12个时间窗沿用365日的实际供水、供沙汇总。上游来自84个控制体、8.224km河段的有限岩土、硬度和逐日流量计算，未增加或放大来沙。

| 项目 | 结果 |
| --- | --- |
| 输入固体 | 67,932.416003m³ |
| 总沉积 / 再侵蚀 | 72,398.722399 / 4,559.617892m³固体 |
| 期末净库存 / 海洋外排 | 67,839.104507 / 93.311496m³固体 |
| 未输送固体 | 0m³ |
| 固体收支残差 | 2.21×10⁻¹¹m³ |
| 实际来水收支残差 | 0m³ |
| 原陆地净库存 / 沉积面积 | 146.054384m³固体 / 4,500m² |
| 最大净床面抬升 | 0.405545m |
| 单个海侧出口比例最大变化 | 0.059104754，即5.91个百分点 |
| 同水量零来沙对照的比例漂移 | 4.16×10⁻¹⁷ |
| 原海洋标签范围内新增高于海平面面积 | 0m² |

这里统计224个声明的边界外排格，不把它们称为224条分汊。零来沙对照水量残差为-2.38×10⁻⁷m³，相对约19.72亿m³来水属于浮点误差，按规模容差通过，并保留原数值。

旧案例报告的11,700m²“出露”使用所有初始床面≤0的格子；这些格子均在原海洋标签之外。它与本表“原海洋范围新增出露为0”口径不同，不能据此声称海岸向海长出新陆地。

![同源床面与沉积对照](../verification/fluvial-delta/river-dominant-saved-source-20261017-01/overview.png)

![实际出口与清水对照](../verification/fluvial-delta/river-dominant-saved-source-20261017-01/outlet-history.png)

四份保存来源在运行前后哈希一致。实际最终床面、库存和总沉积与旧案例逐项精确一致，本轮新增的是修正后的对照接口、出口反馈证据和可冷读验收，不是另一年的新演化或新的供沙量。主协调已查看两张实际结果图。

## 验证与复现

相关回归：**80 passed, 11 subtests passed in 8.16s**。包含零来水、低含沙、超额沉积、空间非对称反馈、清水对照、无效格和高水头阻挡、真实出口水沙闭合、孔隙率、再侵蚀、确定性、存档及篡改拒绝。

独立进程冷读通过，见 [`cold-audit.json`](../verification/fluvial-delta/river-dominant-saved-source-20261017-01/cold-audit.json)。重放检查每个保存数组，包括逐窗库存和JSON元数据，同时重新计算全部汇总字段。v10的三个实现文件及场景09存档四份已登记SHA256全部保持一致。

```powershell
.scratch/hydrological-planning-domain/pydeltarcm-venv/Scripts/python.exe -B tools/verify_river_dominant_saved_source.py --output verification/fluvial-delta/新的目录
.scratch/hydrological-planning-domain/pydeltarcm-venv/Scripts/python.exe -B tools/verify_river_dominant_saved_source.py --audit verification/fluvial-delta/river-dominant-saved-source-20261017-01
```

计算使用单进程、两核、BelowNormal及数值线程1；本轮进程已结束。输出不覆盖旧目录。

## 当前边界

本轮完成有限河流主导模型的预算修复、空间反馈及同源数据验收。路由仍是床面阻力与显式水头上界近似，不求解自由水面；图中是时间窗水量通过体积，不是流速、流量或水深。

16km v10仍是风格化构造地形，与这个2.88km供沙案例分开。统一16km地形、实际供沙、动态水面与陆侧持续扩展仍未完成，不能将本轮局部反馈验收标成完整水动力三角洲。`hydraulic_ready=false`、`publishable=false`；潮汐、波浪、袭夺及跨水文域交换未加入。本轮未修改前端、默认世界、游戏或JAR，未提交推送。
