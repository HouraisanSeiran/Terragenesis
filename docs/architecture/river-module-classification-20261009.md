# 河网模块分类与主线冻结

> 2026-10-30更新：本页下方保留旧分类基线。当前不规则河网、大世界区域与有状态环境入口见[当前入口与回归边界](../../.scratch/codebase-refactor-20261030/entrypoints.md)。已批准的根目录`irregular_*`、`world_*`、`environment_*`承担对应生产职责；“新算法一律放metric_*”是旧组织约定，不能否定这些现行入口。本轮先重构公共存储、环境职责和Java准备/采样链，再恢复二阶段接线；河流袭夺开发暂缓。

日期：2026-10-09；基准复核：2026-10-12。

## 主线定义

主线是“米制地形输入 → 可审计水文图与水量状态 → 河床/湖泊/泥沙形态事件 → 地表与地下几何产物”。所有新河网算法进入 `terrain_pipeline/surface_rivers/metric_*`，拓扑变化统一输出 `MorphologyEvent`，不直接写Minecraft或网页状态。

主线保存对象必须绑定来源、坐标、单位、边界、时间语义、父身份和算法参数。候选形态只允许标记 `candidate` 或 `bounded`；拓扑、河槽、湖泊或泥沙变化后必须声明重验范围。

## 模块登记

| 分类 | 目录/模块 | 责任 | 当前规则 |
| --- | --- | --- | --- |
| source | `metric_source.py`、`metric_large_source.py`、`metric_contracts.py` | TD/DEM来源、米制网格、unknown、边界和forcing身份 | 主线唯一来源契约 |
| routing | `metric_drainage.py`、`metric_routing_comparison.py` | 诊断receiver、DAG、donor和政策对照 | 主线政策层；通用图指标可调用 `metric_reference_routing.py` |
| forcing | `metric_forcing.py`、`metric_runoff.py`、`metric_large_runoff.py` | 空间降雨、本地产流和区间账 | 主线水文源，不重复计入河道 |
| water | `metric_channel_state.py`、`metric_channel_solver.py`、`metric_channel_product.py` | 河道库存、传播、Manning基线和保存产品 | 有界水动力主线 |
| lake | `metric_lake_storage.py`、`metric_boundary_coupling.py`、`metric_natural_lakes.py`、`metric_lake_channel_coupling.py` | 湖泊V(h)、湖河端口、边界和共同水面 | 有界湖泊主线；自然回水仍需验收 |
| geometry | `metric_channel_geometry.py`、`metric_network_geometry.py`、`metric_valley_*`、`metric_monotone_union.py` | 中心线、连续床、细床、坡度、共享端口和材料覆盖 | 主线几何；拒绝覆盖必须保留 |
| sediment | `metric_sediment.py`、`metric_bed_update.py`、`metric_morphology_coupling.py` | Exner、沉积/侵蚀、床变反馈 | 主线有界材料反馈 |
| morphology events | `metric_morphology_events.py`、`metric_delta.py`、`metric_delta_product.py`、`metric_cutoff.py`、`metric_bank_braiding.py`、`metric_fan_floodplain.py` | 三角洲、截弯、河岸/点坝、分汊、冲积扇、洪泛平原等形态事件 | 统一父身份、转移账和重验声明；候选不直接写回主图 |
| external adapter | `metric_reference_routing.py`、`tools/prepare_td_reference_routing.py` | pyflwdir等成熟库的参考计算 | 只读对照或显式适配，不直接替换TD政策 |
| legacy | `surface_rivers/*.py`（非`metric_*`）、`rainfall_runoff.py`、`real_dem_rainfall_routing.py`、`mountain_lake_coupling.py` | 历史兼容、原型和旧诊断 | 不新增功能；新主线调用需先写适配层 |
| hybrid/underground | `hybrid_river_*`、`underground_river_v1.py`、VDM模块 | 早期混合水系和固定地下几何 | 独立几何/研究线，不伪装成主线全网水力 |
| audit | `tools/audit_*`、`tools/verify_*`、`verification/` | 生成后冷读、审计、失败证据和图表 | 不承担算法状态 |
| presentation | `web-preview/` | 固定产物只读审查、导出和交互 | 不在前端推导水量/拓扑 |
| consumer | `src/`、`minecraft-mod/` | Minecraft坐标、区块和游戏消费 | 后续子项目；当前不扩展 |

## 禁止新增的重复实现

- 不在旧 `surface_rivers/drainage.py` 旁边创建第三套通用D8、priority-flood或汇水累计核心。
- 不为三角洲或截弯另建水量/泥沙账本；统一消费 `ChannelState`、`LakeStorage`和`SedimentState`。
- 不用前端样条线、线宽或颜色代替河槽几何和拓扑事件。
- 不把外部库的填洼出口直接升级为TD自然出口。
- 不把Minecraft坐标、tick或海平面写入米制物理算法。

## 新功能进入主线的门槛

每个新增形态算法必须提供：

1. 固定父图/父几何/父水沙身份。
2. 一个不可变参数对象和确定性结果。
3. 新增、退役和受影响边的明确清单。
4. 水量、泥沙、孔隙沉积和岩石材料的转移账。
5. 失败原因与未解析库存，不用截断数据伪造成功。
6. 拓扑、几何、水动力、泥沙和出口的重验声明。
7. 保存、冷读、篡改拒绝及至少一个真实TD局部案例。

当前第一批事件为 `delta_growth`、`cutoff`、`bank_migration`、`bifurcation`、`alluvial_fan` 和 `floodplain_inundation`。它们先输出有界候选，完成独立验证后再进入动态湖河和全域多精度主线。

## 当前系统基准（2026-10-12）

现有河网系统按以下职责层组织：来源与契约、水文驱动、路由与河网选择、河床与几何、河道水动力、湖泊与河湖耦合、泥沙与形态事件、水文规划域、审计/发布/消费。它们是职责边界，不表示已经由一个统一入口闭合。

当前最完整的实际链是：TD 原始来源 → 噪波降雨与诊断产流 → 汇水路由 → 河网选择 → 连续河床与唯一全局床面 → 独立保存审计 → 静态图集。2026-10-12 的六源 TD 结果接受 22569/27336 条候选边，六源独立审计通过；固定图仍显示栅格折角、窄深中心槽和部分拒绝区域。

水文规划域是已确认的后续层，不属于当前六源生成链。它负责完整干流水系的有限归属、共享分水岭、域内合法终点、有限依赖、域内编辑影响范围和生成顺序一致性。有限依赖的首选规划对象是“高山源头候选—完整分水岭—海岸入海口”闭合的源口流域；一个流域可以有多个高山源头和多个支流，但必须有明确的主干出口与有限分水岭包络。它不能被存储块、Minecraft 区块、地貌群系或简单距离缓冲替代。

河道水动力、湖泊耦合、泥沙反馈和形态事件已经有独立模块或候选产物，但尚未与水文规划域和六源全域河床形成统一的无限世界运行链。前端和 Minecraft 只消费已保存结果，不决定米制河网的水量、拓扑或流域归属。
