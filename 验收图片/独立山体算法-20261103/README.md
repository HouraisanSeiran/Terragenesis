# 独立山体算法：首轮候选图集

优先查看裸山几何及生成阶段：

- [固定光照裸山多视角](oblique.png)：图中标明垂直夸张倍数。
- [物理 1:1 比例视图](physical_aspect.png)。
- [四阶段实际采样对照](stages.png)。
- [俯视地形总览](overview.png)。
- [关闭细节的地形与剖面](sections.png)。
- [有限过程诊断](processes.png)。

本图集来自独立程序化高度场，不是 Terrain Diffusion 地形，也不对应真实命名山峰。世界种子为 20260903，原点为 (0, 0) 米，采样网格为 401×401，间距 60 米。阶段图使用实际采样字段，并非补画。

这是首轮可运行候选，尚未证明参考山形态的自然度：层状台阶过于规则，花岗岩平台偏大，角峰仍有长弧墙。有限过程图展示未知边界路由、有限材料扩散与九单元、240 米冰川流线诊断，不代表完整山体冰川或耦合地形结果。

[原始运行目录](../../.scratch/mountain-morphology/run-20261103-04/)包含高度场、过程数据、完整基准与来源记录。本目录的图像和 manifest 是原运行的逐字节副本。[主端冷读审计](../../.scratch/mountain-morphology/main-saved-audit.json)与[实现审查](../../.scratch/mountain-morphology/implementation-review.md)记录了独立核验和剩余问题。
