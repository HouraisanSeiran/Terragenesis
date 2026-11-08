# 一、二阶段遥感式验收图集

本目录是 2026-10-31 的 13 张成果图副本。完整 TD 来源、SHA-256、单位、空间范围、采样间距、时间情景、参与算法和覆盖状态见 [manifest.json](manifest.json) 与 [report.md](report.md)。图像是模型结果的遥感式合成可视化，不是卫星观测。大部分图只读重绘已保存结果；G4 降水另做了原驱动下的一小时 CPU 对照计算。

[中文验收记录与逐组说明](../../.scratch/project-remote-acceptance-20261031/acceptance.md)

详见 [图集报告](report.md)。本目录包含 42 km 同源 TD/宏观/组合高程、现行不规则河网和模型湖泊、派生床与未知边界；G3 月际温度、G4 实算降水与地形支持、G7 雪季情景、G5/G11 水库存；G2/G6/G9/G15 土壤与覆盖消费、G12/G13/G14/G16/G20 有限机制专题；以及最新三角洲床面/实际湿区和潮汐水位对照。

河网只按图注中的 Q 阈值显示，细流的贡献仍保留在保存网络；`pending_basin_mask` 与 `upstream_unknown_mask` 分开显示。季节图和 3 小时环境图不是长期气候变化证明，三角洲图是固定工程情景，不是自然多年演化或真实遥感观测。

第 13 图在同一个 G6 产品、同一地形窗口和 7200 秒时刻联合检验 TD 派生地形、土壤分配、根区水与生物量；没有混用季节样例的状态。地下量和小量变化保持专题色标，不通过美术配色伪造可见地貌。

原始可重复输出仍保存在 [.scratch/project-remote-acceptance-20261031/atlas6](../../.scratch/project-remote-acceptance-20261031/atlas6)，入口为 [tools/render_project_acceptance.py](../../tools/render_project_acceptance.py)。
