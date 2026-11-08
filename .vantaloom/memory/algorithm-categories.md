---
name: algorithm-categories
description: Terragenesis 算法大类划分（用户 2026-11-05 定）：A 山脉与基础地形 / B 河网（B1 三角洲、B2 泥沙）/ C 三维地形 / D 地理环境 / 公共底层；只做逻辑分类不搬文件
scope: project
type: spec
---
用户 2026-11-05 决定算法分大类，落地为**逻辑分类（不移动文件、不改 import）**：
- **A 山脉与基础地形**：TD 扩散（diffusion/、geography*、plate_td_*）、tectonic_*、*_mountains、world_mountain_belts、fictional_world_overview、world_terrain_*、new_world_terrain，以及海岸底图产品线（coastal_terrain/archipelago/detail）。
- **B 河网**：drainage_kernels、irregular_*、new_world_*（地形外）、hydrology_*、surface_rivers/、lake_*、single_domain_shallow_water*、rainfall_runoff；子类 **B1 三角洲**（delta_network_*、coastal_delta_*、large_delta_*、complete_delta、metric_*delta*）、**B2 泥沙沉积**（metric_sediment、coastal_marine_*、coastal_river_connector）。
- **C 三维地形**：hybrid_*、special_terrain_*、metric_vdm*、underground_*、vdm_diffusion/。
- **D 地理环境**（单列）：environment_*、雪冰冻土、气候、岩性、风化、PET 等。
- **公共底层**：common_infra、world_seed、artifacts/、mountain_source_adapter。
做法：模块声明 CATEGORY；被 pin 文件不改，由 docs/architecture/algorithm-categories.json 登记；模块表/台账按大类分节，--check 要求每个活跃算法模块有大类；每大类一张实现总表。规范见 .scratch/algorithm-refactor-20261105/r4/coding-standard-draft.md §11。
