---
name: terrain-generation-rules
description: 织梦地形生成基本规则：TD为主、世界层约1km、30m仅特殊地形/大城镇、边界方案C
scope: project
type: spec
---
用户2026-11-04确认，详见 织梦/docs/terrain-generation-rules.md。
- 地貌以 Terrain Diffusion 为主（板块骨架作条件）；噪声+侵蚀只作对照。复用 Terragenesis TD 代码只 import 不改文件，产物写织梦 artifacts/。
- 世界层约 1 km：约 400 km 见方及更大区域一律按约 1 km 网格采样。当前实现取 TD latent 第五通道低频高程（~240 m）做 4×4 平均得 960 m，不经 30 m 解码；manifest 写明格距与来源。
- 30 m 仅限特殊地形或大型城镇附近，须登记中心/范围/原因；局部层继承世界层海岸、主河、湖面、出口。
- 有限骨架边缘的 TD 条件用方案 C：越出部分按骨架双向周期从对边取；成品仍为有限域，边缘连续性单独检查。
- 河湖在世界层上复用汇流算法粗算即可。先验证再接游戏。
- 美术：山脉范围用底图色彩表现，山峰符号只标每片山脉最高点。
