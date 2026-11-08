---
name: fast-world-layer-decision
description: 世界层改用快速程序化 2 km，TD 只做局部 30 m；山脉走向须与 TD 相似；粗细河道偏差接受
scope: project
type: spec
---
用户 2026-11-05：①世界层不跑 TD，织梦内快速程序化算法从板块骨架生成，格距 2 km，CPU；TD 只用于局部 30 m。②两者同一骨架为条件，地形可不同但山脉走向必须相似（对比 td-world/world-960m-v6 的山地 IoU、主脊方向）。③局部 30 m 河道/海岸与世界层对不上时接受偏差；粗河网用 Terragenesis 非规则图汇流，可抽出优化为粗尺度版，禁止 D8。④骨架阶段可加强山脉，复用 Terragenesis 地形算法（skeleton_mountains、fictional_world_overview 山带、procedural_mountain_erosion 等，只 import 不改）。规则见 织梦/docs/terrain-generation-rules.md 第 6 节。
