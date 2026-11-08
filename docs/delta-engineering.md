# 三角洲工程版使用说明

## 2026-11-02 当前同源潮汐产品

最新离线产品为 `.scratch/delta-tides-bars-20261102/tidal-segmented-v6`，另有 `tidal-segmented-calm-v6` 与 `tidal-segmented-wave-v6` 对照。真实 TD 派生床面上，100 段解析河槽与 300 m 海岸网格共同推进 30 天水沙、M2/S2 潮汐、有限海床冲淤和可选波浪搬运。原生保存床面 30 m；原地质三角洲为初态，不是本轮增长量。

```python
from terrain_pipeline.large_delta_tidal_product_v4 import read_product

saved = read_product('.scratch/delta-tides-bars-20261102/tidal-segmented-v6')
bed = saved['native']['bed_m']
depth = saved['native']['water_depth_m']
coverage = saved['native']['coverage']
water_class = saved['native']['water_class']
```

读取不会生成或推进世界。数组仍为 `[z,x]`，首像元中心与格距在 `origin_xz_m`、`spacing_m` 中。`coverage=False` 处水状态未知；覆盖内 `water_class` 为 0 干、1 连海湿区、2 其他湿区。沿河取 `river_stage_m`；`water_stage_m` 为面积加权等效水面。低/高潮各自保存床面、水深、时刻和湿区分类。

v6 对纯海岸像元做有限保守水面重建，减轻粗网格造成的矩形条纹；河槽混合像元、DEM、泥沙、水动力检查点和河口时序保留。该重建允许跨粗单元局部重新分配水量，不是新增物理时间或 30 m 水动力计算。局部网格痕迹仍存在，波浪情景尤其明显。

准备、模拟、保存和恢复入口为 `terrain_pipeline.large_delta_tidal_product_v4`（保留模块名，当前输出 schema 为 v6），默认实际验收步长 15 s。命令及来源见[水动力与续算说明](../.scratch/delta-tides-bars-20261102/tidal-v5-review.md)、[v6 表示与冷读](../.scratch/delta-tides-bars-20261102/tidal-v6-review.md)、[主端验收](../.scratch/delta-tides-bars-20261102/main-review.md)。恢复只能使用剩余已提供驱动；满 30 天后不能重复花费原输入。外部流域水沙仍未知，默认世界或游戏接线尚未发布。

## 2026-10-31 历史构造版

当前版本：2026-10-31，`complete-coast-and-tidal-island-construction-v2`。主要分汊继承原主河方向向海展开，附属潮道依据可淹潮坪储量构造，取消同岸大U形切岛。入口保存真实床面并计算有限年度水沙；潮汐水盐交换单独执行。[本轮实测与图片](../.scratch/delta-process-natural-20261031/acceptance.md) · [文献依据与独立形态比较](../.scratch/delta-process-natural-20261031/research.md)。

## 读取已完成产品

```python
from terrain_pipeline.complete_delta import load_run

saved = load_run('.scratch/delta-process-natural-20261031/run-v1')
bed = saved['arrays']['final_bed_m']
water_depth = saved['arrays']['water_depth_m']
```

完整潮沟几何与掩码保存在 `scene.npz` 的 `tidal_*` 字段；读取这些字段使用 `numpy.load(..., allow_pickle=False)`。通用旧场景加载器只提取已知字段，不能用它读取完整潮沟数据。`result.npz` 保存年度床面、水体、泥沙及逐子步状态；`state.json` 支持续算；`outlet-packets.json` 是本次新产生的出口交接包。

坐标以米为单位：`origin_xz_m` 为第0行第0列像元中心，列沿+x、行沿+z增长。当前样本为16 km范围、20 m保存间距，继承并重采样旧TD；不是新增20 m原生推理。

## 新建、潮汐验证与绘图

从工程根目录执行，输出目录须使用新目录：

```powershell
runtime/venv/Scripts/python.exe -B tools/run_complete_delta.py --output .scratch/my-delta/run
runtime/venv/Scripts/python.exe -B tools/verify_delta_tides.py --run .scratch/my-delta/run --output .scratch/my-delta/tides
runtime/venv/Scripts/python.exe -B tools/render_tidal_delta.py --run .scratch/my-delta/run --tides .scratch/my-delta/tides --output .scratch/my-delta/images
```

默认源场景和年度边界分别来自 `.scratch/hydrological-planning-domain/stylized-mouth-16km-20261017-09/scene.npz` 和 `verification/fluvial-delta/adaptive-tree-16km-20261018-02/result.npz`，不是在此重新生成TD或上游汇流。源场景应保留已有主河/海岸场景字段，不能直接把任意DEM当作完整场景传入。

`--scene` 可指定兼容场景；`--forcing` 可指定JSON，必须包含同长度的 `record_ids`、`month_seconds`、`monthly_water_m3`、`monthly_solid_m3`。记录ID唯一，时长为正，水量/固体体积非负。默认世界种子20261020，各用途独立派生；`natural` 是构造形态模式名称。

## 保存后继续

```powershell
runtime/venv/Scripts/python.exe -B tools/run_complete_delta.py --resume .scratch/my-delta/run/state.json --forcing additional-forcing.json --output .scratch/my-delta/continued
```

追加文件只提供新时段及新记录ID。恢复复用保存的构造床面并重放已有历史，然后追加计算；旧出口包不再发送。当前恢复不是恒定时间的增量快照恢复，大量历史会增加重放成本。

## 算法与预算

`terrain_pipeline/surface_rivers/metric_tidal_creek_construction.py` 的 `enrich_tidal_coast(arrays, metadata, world_seed=...)` 接收已有海岸构造结果，返回 `arrays`、`metadata`、`audit`；`metric_tidal_island_geometry.py` 负责平台、路径及服务储量。平台起伏使用固定用途种子与绝对坐标的连续场，路径在本有限场景内确定性生成，不承诺任意裁块独立生成相同拓扑。

较大贯穿潮道的主河方向投影严格递增，盲支从口门向内生成时方向相反，不能把数组编码方向当实际水流方向。高低潮水深差在高水位可连海的非重叠服务区积分，子树累积、双口潮道按两口均分，得到几何交换储量P。用理想正弦Q峰值=πP/T、选定速度0.25m/s和未限幅宽深比70估计断面；梯形面积系数0.725。它是几何设计代理，不是沿沟流量求解。

原主河和海床受保护；当前20 m样本保留30 m河岸缓冲，外侧220 m连续过渡。最小可解析沟宽50 m，不可解析支沟省略后重分服务区。潮沟宽上限为入流河宽的60%（本样本120 m），深度可补偿至3.8 m；受限断面保存容量缺口和隐含峰速，不能宣称所有断面均满足选定速度。湾侵入尺度80–260 m是适配本域洲体厚度的初始几何参数。

`complete_delta.py` 负责同一入口的初始构造、年度水沙、保存与恢复。河流水力使用连续中心线和分汊树，不要求八邻格路径。栅格D4仅用于海水连通检查。初始含孔隙挖填体积、年度固体泥沙与潮汐水盐分别记账。

`delta_tidal_validation.py` 从场景元数据读取 `design_low_stage_m`、`design_high_stage_m`、`design_period_s`，复用连通水体棱柱模块，在真实床面上计算两个周期。新版为周期44,712 s、±1.5 m的理想对称边界：3 m完整潮差参考Hale et al. (2019)报告的GBM海岸Hiron Point春潮3–3.5 m，不是现场标定。旧无设计字段的场景沿用±0.65 m默认值；部分声明或非对称边界拒绝，避免混用设计和验证潮位。验证保存真实水量和静态可达范围；不解二维动量、不改变床面，年度河流和海侧潮汐分别验证。

本版支持有限边界下的初始构造三角洲。形态评估记录方向、曲折度、交角和岛体分布；这些描述指标及账本守恒不是统一“科学自然度”认证。自发长期演化、高沙挑战及真实DEM标定另列研究，默认世界和游戏发布不包含在本交付内。

## 2026-11-02 多尺度沿岸案例待验收

实际生成并冻结约 45、114、255 km 连通沉积地貌及分汊 DEM，分别为 541.32、1,231.92、3,762.72 km²；源 TD 间距分别 120、600、600 m，入口流量为声明情景 600、4,000、18,000 m³/s。它们是受陡峭海岸限制的细长沿岸复合地貌；较大两例的 1,000 m 盆地容纳上限是显式假设。河宽由解析断面保存，粗栅格不具备对应高精度。原目标 40/120/300 km 目录名保留作历史标识，实际标题用 45/114/255 km。[中文对比与产品](../验收图片/多尺度三角洲-20261102/README.md) · [测量及复现](../.scratch/delta-scale-suite-20261102/suite-review.md)。

真实地理潮汐适配已有小型早期几何及 114 km 早期几何各 25 小时证据；早期与最终中型源数组完全一致，但产品身份不同。255 km 事件正在校准；数值敏感性和同源边界须主端审查。地形图不声称全域动力学或长期自然演化完成。[地理潮汐审查](../.scratch/delta-scale-suite-20261102/tidal-review.md)。


### 多尺度初版最终验收（2026-11-02）
约45/114/255km的真实TD派生DEM与初始河网已交付；三例25小时地理潮汐均有保存证据。大型局部高水头和步长敏感性未通过，不宣称动态三角洲完成。来源、实际尺度、有限盆地填积假设与未通过项见[主端验收](../.scratch/delta-scale-suite-20261102/main-review.md)。
