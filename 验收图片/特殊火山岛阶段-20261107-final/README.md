# 特殊火山岛阶段图集

验收日期：2026-11-08；目录沿用2026-11-07任务起始日期。[完整验收](../../.scratch/volcanic-islands-20261107/review.md) · [来源与样本SHA绑定](image_binding.json)。

![四种静态阶段的同址实际几何对照](volcano_stages.png)

从左到右：幼年单锥与小顶口、成熟复合锥与侧锥、塌陷宽火山口、侵蚀残锥与不规则沟谷。上排为直接采样的地形高程配色与阴影，下排为同源东西向高程剖面，海面为0m。配色不表示真实植被或卫星观测。

这是同一已保存板块来源、同一要素位置的四个显式静态参数情景，不是默认世界自然选出的四座岛，也不是喷发历史。`world_seed=20260903`，中心模型坐标约`(-47.762km, -387.403km)`，格距约99.77m；产品与全部数值样本保存在[stage-comparison-final](../../.scratch/volcanic-islands-20261107/stage-comparison-final/)。算法为`ocean-islands-volcanic-stages-v4`，本轮没有TD推理。

![默认参数实际世界图](default_world.png)

默认实际世界覆盖1600×1600km，800×800格、2km格距。候选选择参数`volcanic_fraction=0.2`；此来源实际生成2个young、1个mature特殊要素，形成3个受保护露海连通组件，另有21个普通TD合格组件。本图不代表所有默认世界必有四阶段。

原板块来源：`D:/codexwork/织梦/artifacts/worlds/world1600-archipelago-v4/skeleton.npz`，身份`78e2a5fc5ba6e3f6c0cd53d29d99f508d9fb03bfe6c7078c33c61d413459d0bb`。实际新产品身份`b13e7d77aa1a792ef9583e4333b58b8c4487ab0fbe74194d12eebfae477daa9e`。图片、产品、代码和样本SHA逐项见绑定文件；两图均从保存的算法产物查询，未使用生成式图片。
