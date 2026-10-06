# 移动雨团空间只读回放 v1

入口：`verification/mountain-storm-review/run-20261001T072059959238Z/review.html`。高精度JSON：同目录 `weather-water-consumer.json`。源为冻结071520天气/湖河配对与无雨基线；源文件SHA前后核查一致，不覆盖或修改旧结果。独立工具 `tools/verify_mountain_storm_review.py` 只读保存NPZ并静态校验，不生成天气、不推进水文，不修改Sonnet或coupling，不使用GPU推理。

## 页面

共享状态滑块k=0..288，物理时间0..72h。雨图、干格receiver Q与四池储水同步。状态k显示前一时段k−1的平均雨/Q；k=0没有时段量。雨图绘制保存的15 HRU雨强，绝对300m分区叠加实际30m贡献格；不是加载时求天气函数。湖footprint用青色框突出，最大混合HRU局地湖雨误差5.16334110mm/h始终显示。河图为离散干格receiver传播，不把全部连线称可见河道，不提供未求解水面。

过程线同轴显示东向蓝、西向红、同初始湿土无雨灰，分别绘制外边界Q和四池总储水。雨图色标固定0–24mm/h，Q色标采用三方向共同上限；地图绝对东/南坐标以km显示，内部JSON仍米制。

## JSON接入

- `geometry`：`grid_shape`、`origin_m_xz`、`cell_flat`、`east_m`、`south_m`、`HRU`、`node`、`receiver_flat`、`lake_footprint`、`lake_nodes`、节点种类/下游及HRU面积/绝对300m格索引。格与节点顺序由保存索引定义，不在网页重建。
- `cases.eastward/westward/no_rain`：`rain_mm_h[T,HRU]`、`node_q_m3_s[T,node]`、`node_storage_m3[T+1,node]`、`outlet_q_m3_s[T]`、`lake_storage_m3[T+1]`、每湖stage[T+1]与土壤/快慢库总量[T+1]。保留Python JSON双精度往返精度；原始NPZ为来源证据。
- `state_time_hours[T+1]`与`interval_start_hours[T]`分别表示状态和时段起点；Q为时段平均。metadata绑定source/geometry/selection身份以及每案例coupling/weather SHA。`no_rain`天气数组为零，仍来自同初始状态保存的水文基线。

Edge禁GPU绘制验收东/西/无雨三案例，各检查k=0/24/48/56/96/288（0/6/12/14/24/72h），雨时段/状态对齐通过，零pageerror；截图与 `browser-review.json` 保存在同目录。
