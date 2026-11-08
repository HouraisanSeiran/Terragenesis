# 板块驱动的海洋岛屿与岛链

> 当前岛屿TD默认面积严格>25km²，峰海拔300–3000m、±10%波动；普通世界生成已接线。见[当前规则](island-mountains-current.md)。旧100/2000km²资格门槛属于历史记录。

算法代码由 Terragenesis 维护。织梦等调用方负责选择来源、配置和调度，导入本工程公开接口或读取冻结产品，不复制岛屿生成内核。
当前实现面向**有限、已冻结的板块来源**；采用绝对米制坐标和稳定要素清册。完整无限板块的按需准备、局部 TD 模型响应及外部应用接线分别验收。

2026-11-07：织梦实际v3世界层和TD.raw条件接线已通过来源/全部最终场SHA/保护格/潟湖与负床核查，见[主端审查](../.scratch/ocean-islands-20261106/review.md)。该历史审查中2000km²资格计划为空；后续已放宽至25km²并接入普通世界任务，见[当前山系规则与验收边界](island-mountains-current.md)。完整无限上游与真实整岛TD峰高仍未验。

当前新生成算法为 `ocean-islands-volcanic-edifices-v5`。根据用户对v4圆盘体量与放射沟槽的反馈，特殊岛改为水下基座、低缓熔岩裙坡和偏心紧凑上锥，并加入平滑扭曲Voronoi熔岩堆积几何。普通小岛不强制刻沟槽：按固定单要素露海估计，等效直径≤20km或露海高差≤600m时关闭；直径20–40km、高差600–1500m分别平滑渐开。该门槛服务于游戏形态取舍，不表示小岛在自然界不会侵蚀。
尺度估计使用实际源底面、沿岸权重和固定48角×96径向采样，独立于查询窗口、格距和海底支持半径；结果在 `product.valley_domains` 与manifest中保留。
`valley_strength=0` 可完全关闭；大岛启用时使用非等角、弯曲分叉的有限谷线，最终水下地形不刻谷。
`valley_paths(feature)` 返回潜在路径，不能据此认定该岛已启用谷切。旧v1/v2/v3/v4产品仍以旧形态只读复现，拒绝重新保存；升级须显式准备新产品。v4火山几何单独冻结于`island_volcanoes_v4.py`。

v3将统一角度模板改为固定用途子种子、绝对米制连续噪波：20/8/3km控制轮廓，700/240/80m补露海起伏。细节强度受局部正高差限制，海面与环礁不加细噪波；`detail_strength=0`可关闭。不同分辨率直接采样同一连续场，2km图本身不能解析80m细节。

岛间海底采用一次多元有界平滑最大值，替代重叠底座的尖锐max折缝；`seabed_join_softness_m=0`关闭，默认320m（支持范围0–320m）。全部要素累计额外抬升最多160m，接近海面及环礁连续退零；不以无约束累加填海，也不对整张图高斯模糊。

岛屿山系按[当前TD规则](island-mountains-current.md)固定分析真实露海连通体，默认面积严格>25km²，无默认腹地宽度门槛，再显式调度已有TD链。空计划不启动GPU；这与轻量岛体谷切门槛是两项不同控制。[首版TD计划](island-mountains.md)中的2000km²及宽度门槛仅供历史追溯。

## 模块与流程

| 入口 | 职责 |
| --- | --- |
| `terrain_pipeline/ocean_islands.py` | 来源校验、板块条件生成、连续地貌采样、不可变清册、冻结保存和冷读 |
| `terrain_pipeline/ocean_island_consumers.py` | 世界栅格化、已有地表合成、小岛/潟湖保护及局部 TD 条件采样 |
| `tools/prepare_ocean_islands.py` | 显式 CPU 准备、数据导出、来源绑定和实际结果图片 |

处理顺序：冻结板块与基础洋底 → 基础洋底平滑及大陆山系 → 岛体/海山合成 → 更新海陆与海洋状态 → 下游消费。
后续平滑及清除小陆斑须读取保护信息，不得把登记岛屿或潟湖删掉；海洋连通要在最终地表上重新计算。

| 地貌 | 第一版方法 |
| --- | --- |
| 热点岛链 | 绝对候选单元产生热点；旧火山沿板块运动方向排列，按离线阶段降低和破碎；遇异板块或来源边界终止 |
| 海山 | 保留未露海的尾链和海底坡面，高程仍可查询 |
| 岛弧 | 洋—洋汇聚边界的有界局部方向估计，上盘侧偏移布置火山体；上盘极性采用已记录的组成/板块编号近似 |
| 洋中脊岛 | 洋—洋张裂边界上的稀疏海底脊台，少数高地露海 |
| 环礁 | 可选暖水游戏情景，将旧阶段底座塑为低平环缘和水下潟湖，默认关闭 |

岛体具有海底底座、偏心主次喷发中心、塌陷口与谷切。先合成连续海底山体，再按海平面 0 m 决定露海部分。
速度单位为 m/offline-step，阶段尚未标定为地质年；没有模拟熔体、岩石物质收支或珊瑚生态过程。

## 特殊火山岛

`OceanIslandConfig(volcanic_fraction=0.2)`默认对可露海热点/岛弧要素按固定种子和feature key抽取少量特殊火山形态。0关闭，1用于显式全候选情景；该值是候选要素的选择比例，不保证有限来源恰有20%的连通岛为火山岛。CLI为`--volcanic-fraction`。

| `feature.volcano_stage` | 地形形态 |
| --- | --- |
| `young` | 完整单锥、小型顶口 |
| `mature` | 较高的复合锥、侧锥与裙坡 |
| `caldera` | 截顶、宽塌陷火山口和环壁 |
| `eroded` | 较低残锥、局部宽凹坡与单侧破口；不向裙坡和海底刻放射槽 |

普通要素为`none`。热点按现有离线stage顺序映射；岛弧没有已模拟喷发史，其静态阶段由用途子种子决定。四种形态是游戏地貌情景，不表示所有真实火山按单一顺序演化，也不模拟喷发、岩浆或火山灰。

`volcanic_lava_strength`控制v5的平滑Voronoi熔岩堆积几何，范围0–2，默认1；0用于关闭对照，CLI为`--volcanic-lava-strength`。采用确定性子种子、连续坐标域扭曲和有界邻域，实际改变裙坡/堆积厚薄，不能把该参数理解为已运行岩浆流体过程或新增表面材质。它与普通`detail_strength`相互独立；胞元边界不直接刻成裂缝，海床与关键顶口保留。

新查询字段`volcano_weight`为连续0..1保护权重；原大陆、海水与潟湖处为0。特殊锥体在有界内支持区保留火山口，登记环礁潟湖优先。包含特殊锥的露海连通岛在普通TD山系计划中记`special-volcanic-morphology`并跳过，避免火山口被随机山脊覆盖；普通岛仍按>25km²规则。特殊锥沿用岛要素自身峰高及阶段形态，不套用普通TD整岛300–3000m归一化。

`volcanic_fraction=0`的新产品保留v3同坐标几何；加载旧v1/v2/v3时火山配置为0、阶段为none，查询仍保留旧字段集合。[v4历史验收与图集](../.scratch/volcanic-islands-20261107/review.md)记录其真实默认世界和同址四阶段控制对照；用户指出的形态问题在[v5修正任务](../.scratch/volcanic-islands-refinement-20261108/spec.md)追踪，历史测试通过不代表自然度通过。

## Python 调用

```python
from terrain_pipeline.ocean_islands import (
    PlateOceanSource, OceanIslandConfig, prepare_ocean_islands,
    save_product, load_product,
)
from terrain_pipeline.ocean_island_consumers import (
    rasterize, compose_surface, sample_td_condition,
)

source = PlateOceanSource.from_npz(
    "source.npz", expected_identity="<来源的64位SHA身份>"
)
config = OceanIslandConfig(world_seed=20260903, world_type="archipelago", volcanic_fraction=0.2)
product = prepare_ocean_islands(source, config)
save_product(product, "new-island-product.npz")  # 不覆盖已有文件

frozen = load_product("new-island-product.npz", expected_identity=product.identity)
world = rasterize(frozen, spacing_m=2000, land_supersamples=2)
height_m = world.fields["elevation_m"]
feature_inventory = frozen.features
```

`from_npz` 支持本工程冻结板块产品与织梦 `dream-world-skeleton-plate-v1` 来源。
原始来源保留实际 `world_seed`，生成配置的种子另记；项目共用种子权威见 [CONTRIBUTING.md](../CONTRIBUTING.md#共用世界种子用户更新2026-11-03)。
旧产物的种子不能改标为共用新种子。

`frozen.query(x_m, z_m)` 接收可广播 NumPy 坐标，返回基底/最终高程、地貌增量、海陆、保护和潟湖字段。
坐标约定为 X 向东、Z 向南，单位米；来源有效域为半开区间，域外查询拒绝。
点查询不隐式准备、不启动模型、不写文件。

调用方已有独立地表时，用 `compose_surface(frozen, x_m, z_m, base_elevation_m=base)` 在连续支持域内合成。
该分支的 `base_elevation_m/relief_m/elevation_m` 按消费基底保持数值一致，原冻结基底与增量另存为 `frozen_base_elevation_m/frozen_relief_m`。
局部 TD 通过 `sample_td_condition` 读取同一份要素；这是条件采样接口，模型能否保留小岛及环缘需要实跑验证。
显式 `periodic=True` 仅重复有限产品，不能据此推断世界边缘已经无缝。

密度可用 `none/low/medium/high`；`world_type` 调整候选密度。
`hotspot_count` 是有限来源中的数量上限，海洋条件不足时不保证补足；不会换种子补挑。
`arcs`、`ridge` 分别控制岛弧与洋中脊；开启环礁须同时明确 `atolls=True, warm_water_scenario=True`。
固定海平面；新增陆地及海洋比例偏差应回报调用方，算法不会按请求窗口重调海平面。

## 尺度、预算与产物

矢量清册中的 `feature_id/chain_id` 是地貌身份，临时栅格连通分量不是地貌身份。
小于粗格距的岛仍保留清册与空间范围；面积采用有限采样近似，窄环缘/小岛可能未解析，不能把它们夸大成整格陆地。
`rasterize(..., area_refinement=8)` 默认对潜在露海内支持域采用8×8面积细分；CLI局部细图显式使用2×2，并在元数据记录实际精度。
细分最多8,000,000采样点，超限拒绝；这项面积近似与格心的真实高程采样分别记录。
直接查询同一冻结几何时公共坐标一致；对不同 DEM 做插值不具有这一承诺。

源硬上限 262,144 格，候选、阶段、要素及查询工作内存另有限额，超限拒绝。
可在允许范围内调整配置，调用方对大查询分批。
具体依赖范围、局部支持数量和有限来源约束保存在冻结产品的 `preparation` 中。
显式热点数量需要全有限来源排序，不是无限模式的局部热点准备算法。

CLI 必须提供 `--source`、`--expected-identity` 和新的 `--out`；默认 2 km 输出。
`--gallery` 可指定图片副本目录；`--atolls --warm-water-scenario` 为明示暖水情景。
导出包含自含冻结产品、浮点高程及字段、16/8 位灰度高度图、原底与结果图、局部和剖面，以及来源/源码摘要和实测资源记录。
灰度固定映射 -8000…8000 m，浮点产品为权威；超范围裁剪数量另记。
颜色表示高程，未推断实际植被或生态覆盖。

规格及独立验收见 [任务规格](../.scratch/ocean-islands-20261106/spec.md) 与 [主端审查](../.scratch/ocean-islands-20261106/review.md)。
