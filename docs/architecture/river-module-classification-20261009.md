# 河网模块分类与主线冻结

日期：2026-10-09。

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
