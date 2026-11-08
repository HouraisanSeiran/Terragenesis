# 大范围三角洲与活动河网初版

[50 km 总图](overview.png) · [25 km 局部](delta-detail.png) · [5 km 分汊](junction-detail.png) · [清单](manifest.json)

地形采用 [terrain-product-v2](../../.scratch/large-delta-20261101/terrain-product-v2/manifest.json)，河网采用 [active-network-v12](../../.scratch/large-delta-20261101/active-network-v12/metrics.json)。清单中的相对路径指向权威 30 m 地形、河网和事件输入文件。图中线宽经过增强；解析宽度约 17.6–37.0 m，不能把整格湿像元当作真实断面宽度。

124.1595 km² 连通新生陆地属于有限供沙的生成式地质初始化，并非物理年数或 30 天沉积。约 25 km 地质复合体可包含本次不活动的部分。已知本地入口流量 27.657844 m³/s 的 30 天事件使用三个活动入海口；外部水沙未知且未计入，不代表总量为零。

弯曲是受地形约束的算法初始化，不宣称是演化形成的曲流。分流、固定水头及有限库容平流与沉降是游戏级运动学近似，并非潮汐、回水或完整水动力求解。原床最大新增切深约 1.94 m；施工挖出物单独记账，与事件供沙分开。形成期与事件期的水沙账见清单及河网指标。

主端已完成保存数据与图片验收，见[主端报告](../../.scratch/large-delta-20261101/main-review.md)和[独立检查](../../.scratch/large-delta-20261101/main-final-checks.json)。本成果为游戏用途的显式派生初版，不自动接入默认世界；形态供用户继续复核。完整潮沟、周期潮位和沙洲持续演化仍是后续范围。
