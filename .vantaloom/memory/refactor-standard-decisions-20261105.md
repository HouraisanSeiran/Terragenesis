---
name: refactor-standard-decisions-20261105
description: 算法重构规范的用户决定：种子20260903、不采用五层包、其余按建议、算法分三大类
scope: project
type: spec
---
用户 2026-11-05 对《算法模块重构与编码规范》草稿（.scratch/algorithm-refactor-20261105/r4/coding-standard-draft.md）的决定：
1. 种子统一 20260903；代码残留的 20261020 默认值迁移；复验旧冻结产物沿用产物记录的种子（common_infra.WORLD_SEED_LEGACY_20261020 仅复验用）。
2. 不采用五层包。
3. 附录第 3–14 条按草稿建议执行（算法身份+PROFILES 不建 _vN；network v5 已归档；山体线只归档织梦依赖闭包外的；temp_* 出库；四项改数值整理进独立数值修订轨道；冻结清单+守卫测试作前置；功能族净模块数不得增加 等）。
4. 新增：算法分大类。A 山脉与基础地形（含 Terrain Diffusion 扩散算法）；B 河网（下属 B1 三角洲、B2 泥沙沉积等）；C 三维地形单独一类。成员初分见草稿 §11。待定：地理环境是否单列 D、海岸底图产品线归属、落地方式（甲=逻辑分类不移文件 / 乙=物理分子包）。
