# 河网参考样本冻结：2026-10-11

本参考包用于阶段0–2条件化审查，不认证TD自然河网。入口是 `tools/prepare_river_reference_baseline.py --output <新工作区目录>`；本轮最终包为 `verification/td-natural-river-stages/reference-baseline-02/`。自然度指标计算与比较由单独的基线工具负责。

## 实测宽深

原始数据来自 [USGS channel-measurements API](https://api.waterdata.usgs.gov/ogcapi/v1/collections/channel-measurements/items?monitoring_location_id=USGS-06719505&limit=100&f=json) 和其 [字段字典](https://api.waterdata.usgs.gov/ogcapi/v1/collections/channel-measurements/queryables?f=json)。本仓于2026-10-02保存响应，measurements SHA256 为 `cb68bbdddac7c55e80dafe4cc62c088d28d0d486811be934e8139cdfe64c82b7`；字典 SHA256 为 `1e2c19a3fe2d0986562e24539fd93696370e26ec774729dc457f941a1e8b62a2`。无需再次联网即可从原始记录重放明确英制至SI换算。

100条记录来自USGS-06719505，位置(-105.234722,39.753056)，按原channel_name分8组：Imported Channel 1=77、Main - wading=4、Main=10、1=4、Main - Pulley=1、Imported Channel 0=2、Main - DS Bridge=1、main=1。它们是同站点重复观测，不能作为全球独立河流总体。平均深度为实测断面积/实测宽度，不是最大水深、bankfull深度或测量床面。原流量、日期、材料和河道组保留，气候/地形类别无证据时记unknown；没有实测纵坡、曲率、粗糙度或断面点云。

## 地形与线段

DEM来自本地CIAT-CSI SRTM v4.1保存候选，[产品来源](https://srtm.csi.cgiar.org/)。90m格网、EPSG:32651，X=easting、Z=-northing，左上中心(328905,-3282165)，642×460。保存包SHA256为 `d081ff6439a4d8bd57add2e6316096009a57b197f27e4ad7a93608f1bcd605b3`。原栅格SHA、recipe、数组身份、valid/unknown/core/footprint均保留。源高程米制是假定，垂直datum和自然海口未验证，许可仅本地研究，不随技术对照推断可再分发。

[HydroRIVERS](https://www.hydrosheds.org/products/hydrorivers)原选中线段包SHA256为 `9c466ecb5cad277229c620df0b79ce92bfcf2f723f64a44950443493ebb0080e`，上游归档SHA为 `29780b0a75f90024f22e7e2029e5e3045f7325cda0528db65c5cc4c864b98525`。这些15角秒DEM派生中心线可用于粗尺度几何/河阶对照，非独立河道测绘；WaterGAP长期平均流量非同期实测流量。保留原完整选中线段与米制投影，不用SRTM推造精细床面，不将NEXT_DOWN=0解释为认证海口。

## 比较约定

固定DEM窗口为row0:96、col0:96，沿用已保存90m目标格网，本轮不再采样；原SRTM是地理坐标栅格，经exact_inverse_target_pixel_center_source_affine_floor重投影采样，不能把90m目标格网称为源原生格网。原始source resolution与transform保留，最终包逐项通过原TIF SHA256、header、window和投影采样重放。渠道面积阈值100000m²。分位概率为[.05,.25,.5,.75,.95]，线性计算，数值重现容差1e-9。参考区间q05..q95用于审查，不能代表所有地形和气候的统一成功阈值；单条记录组没有统计覆盖能力。原始高度、粗线几何和实测宽深分别比较。TD的30m模型样本与90m DEM的分辨率、来源和类别不相同，报告必须显示条件不匹配。

固定TD来源清单包含20260930/20260931同origin以及20260931另一region，保存metadata/generation_config/native_resolution与SHA及原生成报告hash核对。`diffusion/backend.py`返回WorldPipeline原output elev，`benchmark_height_budget_v5.py`在process_region前直接保存该数组；未施加后续加工或游戏datum+126m。模型高程基准未测绘认证。它们是虚构模型地形，不是实测DEM。冻结参考包先于读取这些TD样本的自然度评分。

SRTM与HydroRIVERS网页链接为产品主页；旧本地archive没有原下载URL记录，本轮不伪造retrieved时间或下载身份。原archive字节hash、本地路径和已有来源审核元信息保留。USGS则有实际已保存HTTP响应URL/日期/字节hash。
