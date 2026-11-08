---
name: td-coarse-gpu-later
description: TD 粗模型世界尺度运行放显卡上，当前只做 1600 km/小窗口验证
scope: project
type: spec
---
用户 2026-11-05：TD 粗模型山脉走向场（织梦 app/world_gen/td_coarse.py、tools/td_coarse_ridges.py）的 5000 km / 万公里正式运行留到独立显卡上跑；现在只验证思路，CPU 运行限 1600 km 全图或 ≤500 km 窗口，不在 CPU 上硬跑万公里。规范：织梦/docs/td-coarse-ridges-spec.md。数值相关改动须与 world1600-v4-shaped/td-coarse-ridges（6d5d2c4e…）比：主脊方向中位偏差变化 ≤2°、1000 m 山地 IoU 降 ≤0.03。显卡耗时由 --plan-only 块数 × --benchmark 每块耗时估算，写 estimate.json 并标推算/实测。
