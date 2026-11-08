# Voronoi 山体与沟槽保护（2026-11-03）

独立程序山体功能候选，来源为 Advanced 底座及 Voronoi 结构，不是 Terrain Diffusion、真实地形或真实河流。世界种子 20260903；主窗 0–24 km，负窗 -24–0 km；每组 401×401、间距 60 m。固定中心 9–15 km，剖面 Z=12 km，未挑选景观。

建议先看 [主窗脊网局部与剖面](main_ridge_network_central.png)，再看三组同尺度对照：[块状](main_cellular_massif.png)、[脊网](main_ridge_network.png)、[混合](main_mixed.png)；负窗：[块状](negative_cellular_massif.png)、[脊网](negative_ridge_network.png)、[混合](negative_mixed.png)。每组另有 1:1 比例图；主图注明垂直夸张。

视觉审查认为过渡较旧版平滑，但地形仍粗碎，**自然度未通过**。保护作用于估算的外观沟槽；加宽过渡会削弱塑形，并仍可能改变分水岭和路由，不能宣称真实河道或河网得到保护。主窗 65×65 诊断（375 m，未知边界）核心高程误差为零；块状、脊网、混合的核心接收方向变化分别为 2.40%、12.59%、6.26%，终点变化分别为 2.66%、20.65%、11.06%。

512²、60 m 混合形态近/远坐标采样为 21.31/20.29 秒，采样进程 RSS 峰值 292.6/300.1 MB；绘图计时独立。内存为整个进程 10 ms 采样，可能漏峰并包含先前分配。完整参数、数据、诊断、哈希和测试记录见[原始运行](../../.scratch/mountain-voronoi/run-20261103-04/manifest.json)。旧候选 run02 保留窄过渡反例。

主端已独立核对六组高程、源码摘要、共同坐标、沟槽核心和路由收支：[冷读审计](../../.scratch/mountain-voronoi/main-saved-audit.json) · [评价与剩余问题](../../.scratch/mountain-voronoi/review.md)。
