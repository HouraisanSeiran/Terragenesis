---
name: fixed-world-seed-policy
description: 世界种子约定：当前权威在 CONTRIBUTING.md:39-41，WORLD_SEED=20260903；20261020 为历史基准
scope: project
type: spec
---
种子约定以 CONTRIBUTING.md:39-41 为唯一权威（2026-11-05 主代理核对）：
- 当前共用 `WORLD_SEED = 20260903`（`terrain_pipeline/world_seed.py:5` 一致）。新正式世界、山体实验、连续测试统一用它。
- `20261020` 是**历史基准**：复验已有冻结地形、来源绑定、保存续算时沿用产物实际记录的种子（如 terrain-v3、native-*、delta_network v1–v4 用的是 20261020）。
- 各用途以稳定用途名确定性派生独立子种子，记录派生方式/实际值；禁止时间、系统熵、内置 hash。绝对世界坐标 + 明确物理时间索引采样，不受查询/加载顺序影响。
- 代码里仍有旧默认值 20261020 的入口，迁移未完成；新正式运行前须显式传入共用种子。
- 是否在重构中统一迁移旧默认值，属规范草稿 §10 待用户拍板项。
