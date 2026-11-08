---
name: no-d8-routing
description: 用户 2026-11-05：禁止新代码使用 D8 河网流向，改用 Terragenesis 非规则图汇流
scope: project
type: spec
---
用户 2026-11-05 决定：织梦今后任何新的河网/汇流/侵蚀代码**不得使用 D8**（每格只流向 8 邻格之一，会产生 45° 直线、梳齿、平行束）。改用 Terragenesis `terrain_pipeline/surface_rivers/drainage.py:route`（非规则图汇流，底层 irregular_drainage.py / irregular_grid.py），河线平滑用 channel_centerline.py；需 numba（用 Terragenesis runtime/venv）。现有 D8 代码（app/world_relief/drainage.py、erosion.py、product.py、td_flats.py、td_freeze*.py、td_hydro.breach）保留只为复现 v1–v5 冻结产品，不得在新任务中 import/复制/扩展。派河网相关任务时必须在 prompt 写明并引用 docs/river-routing-d8-deprecated.md。
