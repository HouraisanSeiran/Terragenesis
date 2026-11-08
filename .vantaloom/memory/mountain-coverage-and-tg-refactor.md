---
name: mountain-coverage-and-tg-refactor
description: 山地占陆地20–30%；Terragenesis 重构后再查河网算法复用
scope: project
type: spec
---
用户 2026-11-05：①整片山地（含丘陵/山间盆地/高原）占陆地 20–30%，主造山带 150–400 km 宽，次级 40–120 km；>1500 m 占比只报不作目标。②Terragenesis 正在代码重构，重构完成后再检查复用其已有河网算法；期间织梦用现有非规则图汇流（irregular_drainage 等），不复制 Terragenesis 代码。织梦 import 的 Terragenesis 文件（irregular_drainage、irregular_grid、skeleton_mountains、procedural_mountain_erosion、tectonic_evolution/product、diffusion/plate_td_*）重构后可能移动，需按 manifest 里的路径+SHA 重新核对。写入 docs/terrain-generation-rules.md 第6节。
