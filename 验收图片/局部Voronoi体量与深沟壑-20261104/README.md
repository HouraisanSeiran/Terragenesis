# 局部 Voronoi 体量与深沟壑：试验图库

世界种子 20260903；主窗 0–24 km，401 × 401、60 m 间距，行 Z 向南、列 X 向东。数据源为独立山体算法，详细参数、来源摘要、子种子、量化和性能记录见 [manifest.json](manifest.json)。

- [组合高程原图（16 位）](main_combined_height_m.png) · [8 位预览](main_combined_height_m_preview.png)
- [对照高程原图（16 位）](main_control_height_m.png) · [8 位预览](main_control_height_m_preview.png)
- [四组高程对照](main_comparison.png) · [阴影及裸山](main_comparison_terrain.png)
- [实际高程差分](main_comparison_differences.png) · [固定 9–15 km 局部与剖面](main_comparison_local_profiles.png) · [深度增益剖面差值](main_comparison_depth_profile.png)
- [负坐标窗口](negative_comparison.png) · [负窗口阴影及裸山](negative_comparison_terrain.png)
- [图形学地形生成方法筛选](../../research/图形学地形生成方法筛选-20261104.md)

高程原图为无阴影、无坐标轴的 16 位单通道灰度，预览为 8 位；统一固定映射 −500 至 6000 米，黑低白高，与上一轮图使用的 −500 至 4500 米映射不同。NPZ 保存 float64 原始场与中间场。新 control 包含坡度淡入，不是上一轮未淡入的旧结果。

P=0 的局部体量区外严格不变仅指宏观高度；Advanced 使用至多 600 米邻域，最终高度在区外边缘仍可能改变。负增量放大是外观雕刻，不是水沙过程。深沟壑和局部抬升可见；整体仍偏宽缓，局部尖锐以及沿脊细线没有全部消除，当前为实验候选，不能宣称自然度验收通过，也未接入默认世界。

512²、60 m 规则网格采样：近坐标 11.46 秒，远坐标 11.69 秒；采样进程 RSS 峰值分别约 138 MiB 和 163 MiB。采样可能漏掉瞬时峰值。生成、保存、绘图计时分列于 manifest。图库文件从 run-20261104-02 逐文件 SHA-256 核对复制。
