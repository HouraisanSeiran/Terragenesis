# 山脊柔化与破缺验收图库

生成日期：2026-11-04。数据来自冻结实验 `.scratch/mountain-ridge-breakup/run-20261103-04/`，实验目录名保留 2026-11-03；本图库直接读取四组已保存 NPZ 绘图，不重新计算地形算法。世界种子为 20260903，来源为独立山体算法，并非 Terrain Diffusion 耦合结果。

主窗 X、Z 均为 0–24 km，负窗 X、Z 均为 −24–0 km；每组 401² 点，间距 60 m。`ridge_network` 是主要观察对象，`mixed` 用于泛化观察。

优先查看[主窗六阶段结构](main_ridge_network_structure.png)、[裸山双视角对照](main_ridge_network.png)、[物理比例](main_ridge_network_1to1.png)和[固定中心局部](main_ridge_network_central.png)。其他组：[主窗混合](main_mixed_structure.png)、[负窗脊网](negative_ridge_network_structure.png)、[负窗混合](negative_mixed_structure.png)。

过程依次为原始结构差值、Gaussian 柔化、坐标扰动与缺口调制、坡面细节，最后与同一 Advanced 底座及保护掩码合成。高斯 sigma 为 500 m，世界锚定辅助网格步长 300 m，实际核为 9×9，支持范围为每轴 ±1200 m。保护核心指掩码完全保护的区域，不等同真实河网；边界及路由结果属于诊断，不能证明河网保留。

每组主图包含两个视角、结构差值和俯视图；`_1to1` 使用物理比例，`_structure` 展示六个结构阶段，主窗另有 `_central` 的 9–15 km 局部及剖面。主图标注垂直夸张和曲面采样步长。六阶段图的 `cut_delta_m` 是非负的移除抬升量；旧 run04 图中的 “signed change” 标题有误，本图库已更正。

本轮自然度仍未通过验收。512² 正式生成测量为 18.04 / 17.82 秒，峰值 RSS 为 242.6 / 265.5 MB；绘图时间另计，不能与生成时间混同。各图、源 NPZ 和渲染源码的 SHA-256 见 `.scratch/mountain-ridge-breakup/gallery-publish-20261104.json`。

[主端E1–E9审查](../../.scratch/mountain-ridge-breakup/review.md) · [数据清单](../../.scratch/mountain-ridge-breakup/run-20261103-04/manifest.json) · [图库摘要清单](../../.scratch/mountain-ridge-breakup/gallery-publish-20261104.json)。
