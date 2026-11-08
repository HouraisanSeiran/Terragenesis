# 三角洲连续演化工程初版

2026-11-03：45×45 km，同源TD30 m、计算100 m；5等效年形成后启用新汊，再连续推进两次25 h潮浪事件。工程闭环通过，**自然形态仍有明显栅格直角，多级分汊与百公里案例尚未完成**。本目录是已有结果的冻结交付，没有重跑TD或演化。

- [主端验收、参数、限制与续算接口](工程验收与接口.md)
- [全域同源对照](figures/01-full-window.png)
- [局部同源对照及实际床变](figures/01b-local-comparison.png)
- [最终实际河口水路](figures/02-mouth.png)
- [床变及实际水面剖面](figures/03-change-profile.png)
- [独立水沙与连通核查](evidence/main-full-evolution-accept.json)
- [新汊年度续算核查](evidence/main-full-active-continuation-probe.json)
- [各阶段低滩出露量](evidence/land-stability.json)
- [文件摘要与发布大小](manifest.json)

![同源初末与实际床变](figures/01b-local-comparison.png)

图为地形配色及实算水体，不是卫星观测。紫色代表原海洋分类未知，并非DEM无效；青色河水为保存的正流量/正水深结果，显示宽度有注明的增强，不是100 m整格都被挖成河床。

形成阶段新增10.25 km²平均海位以上陆地（仅统计初始连通海域）；含历史库存再搬运，不能全归为本轮新河沙。最终两路总流量16.819 m³/s，150 m³/s为供给情景，其余水沙保留待交付。未宣称模型能完全接收150 m³/s。

`data/`保存初态、形成后、事件1、事件2的NPZ+JSON，可以加载续算；`source/`保存100 m来源、状态和初始河床；逐图TD页来源仍可追溯至`figures/manifest.json`。`snapshot/`只冻结本轮相关实现与测试，不是独立可安装运行包；运行需本工程及其Python依赖。

本次流程为5年形成→修订helper启用一条新汊→50 h事件。最终代码的每个形态步已接平均海位候选评估，从初态重跑可能更早启用新汊；`evidence/full-final-case.py`等仅为实际过程记录，依赖工作区历史短例，不是本目录自包含的一键重算脚本。使用上文接口从已保存状态继续即可。

历史原始存档和图集均保留；不包含大TD页、日志、旧低沉降诊断或新百公里输出。
