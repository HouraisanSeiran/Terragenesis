# 连续山脊与站点体量场

这是实验候选，不代表自然度验收通过。401² 图中仍有少量沿主脊延伸的锯齿或裂线；V 边界长线显著减少但未全部消失，Advanced 外观伪影仍待处理。旧裂线候选保留在 `.scratch/mountain-product/run-20261104-03/`。

推荐先查看 [alpha=0.65 的 16 位高度图](main_alpha_0.65_height_m.png) 和 [8 位预览](main_alpha_0.65_height_m_preview.png)。高度图是纯高程灰度，无阴影或轴线。

- [alpha=0 高度图](main_alpha_0_height_m.png) / [未加 Advanced 高度图](main_alpha_0_macro_height_m.png)
- [alpha=0.65 未加 Advanced 高度图](main_alpha_0.65_macro_height_m.png)
- [alpha=1 高度图](main_alpha_1_height_m.png) / [未加 Advanced 高度图](main_alpha_1_macro_height_m.png)
- [负窗 alpha=0.65 高度图](negative_alpha_0.65_height_m.png) / [未加 Advanced 高度图](negative_alpha_0.65_macro_height_m.png)
- [主窗字段对照](main_comparison.png) / [主窗山体与阴影](main_comparison_terrain.png) / [负窗字段对照](negative_comparison.png) / [负窗山体与阴影](negative_comparison_terrain.png)

来源：`product-mountains-v2-smooth-mass`，世界种子 20260903。源代码摘要、参数、计时和量化信息见 manifest.json。

网格 401 × 401，间距 60 米；行 Z 向南，列 X 向东。主窗原点 (0, 0) 米，负窗原点 (-24000, -24000) 米。

R 为平滑连续山脊场；V 由 Voronoi 同类站点的有限支持平滑核融合而成，不是严格 F1 最近点 Voronoi 距离。主窗展示 alpha=0、0.65、1，负窗展示 0.65。

高程 PNG 是无阴影的 16 位单通道灰度，固定映射 -500 至 4500 米；`_preview.png` 为 8 位预览，NPZ 为 float64 米制高程或无量纲场。对照图单独标注 R/V，山体图仅作阴影可视化。Advanced 是外观滤波，非真实水沙侵蚀。
