# 河网系统模块登记

状态日期：2026-10-10。

## Canonical

| 领域 | 运行路径 | 状态 |
| --- | --- | --- |
| 统一米制契约和来源 | `terrain_pipeline/surface_rivers/metric_contracts.py`、`metric_source.py`、`metric_large_source.py` | 主线 |
| 排水和路由策略 | `terrain_pipeline/surface_rivers/metric_drainage.py`、`metric_routing_comparison.py` | 主线 |
| 降雨和本地产流 | `terrain_pipeline/surface_rivers/metric_forcing.py`、`metric_runoff.py`、`metric_large_runoff.py` | 主线 |
| 河道库存和水量 | `terrain_pipeline/surface_rivers/metric_channel_state.py`、`metric_channel_solver.py`、`metric_channel_product.py` | 有界主线 |
| 湖泊和边界 | `terrain_pipeline/surface_rivers/metric_lake_storage.py`、`metric_boundary_coupling.py`、`metric_natural_lakes.py`、`metric_lake_channel_coupling.py` | 有界主线 |
| 河床和网络几何 | `terrain_pipeline/surface_rivers/metric_channel_geometry.py`、`metric_network_geometry.py`、`metric_valley_*`、`metric_monotone_union.py` | 主线 |
| 泥沙和床变 | `terrain_pipeline/surface_rivers/metric_sediment.py`、`metric_bed_update.py`、`metric_morphology_coupling.py` | 有界主线 |
| 形态事件 | `terrain_pipeline/surface_rivers/metric_morphology_events.py`、`metric_morphology_topology.py` | 主线契约 |

## Morphology

| 功能 | 运行路径 | 当前能力 |
| --- | --- | --- |
| 三角洲 | `terrain_pipeline/surface_rivers/metric_delta.py`、`metric_delta_product.py` | 真实TD局部候选和独立冷审 |
| 截弯取直 | `terrain_pipeline/surface_rivers/metric_cutoff.py` | 河颈、捷径、牛轭湖候选 |
| 河岸/点坝/辫状 | `terrain_pipeline/surface_rivers/metric_bank_braiding.py` | 有界冲刷、点坝和有限分汊候选 |
| 冲积扇/洪泛平原 | `terrain_pipeline/surface_rivers/metric_fan_floodplain.py` | 有界沉积扇和洪泛带候选 |

真实TD候选包：`verification/td-morphology-candidates/td256-20261010-01/`。独立冷审：`verification/td-morphology-candidates/td256-20261010-01-audit-05/audit.json`。

## Hybrid and underground

| 功能 | 运行路径 | 当前边界 |
| --- | --- | --- |
| 混合地表/地下图 | `terrain_pipeline/hybrid_river_graph.py` | 独立早期水系图 |
| 地下洞道几何 | `terrain_pipeline/underground_river_v1.py` | 固定山地窗口的有界几何 |
| 洞道布尔和VDM | `terrain_pipeline/hybrid_cave_geometry.py`、`terrain_pipeline/metric_vdm*.py` | 几何审查，不代表地下水力 |

## Legacy and adapters

- 旧排水/河槽：`terrain_pipeline/surface_rivers/drainage.py`、`channel.py`、`branches.py`、`delta.py`、`transport.py`。
- 旧产流/路由：`terrain_pipeline/rainfall_runoff.py`、`real_dem_rainfall_routing.py`、`mountain_lake_coupling.py`。
- 外部参考：`terrain_pipeline/surface_rivers/metric_reference_routing.py`、`tools/prepare_td_reference_routing.py`。
- 前端审查：`web-preview/`，真实TD形态入口为 `?workspace=morphology`。
- Minecraft消费：`src/`、`minecraft-mod/`，当前不迁移、不扩展。

## Validation

- 生成后审计：`tools/audit_td_*`、`tools/audit_hybrid_*`。
- 生成和验证入口：`tools/prepare_td_*`、`tools/verify_td_*`。
- Python测试：`tests/test_metric_*`、`tests/test_td_*`。
- 保存证据：`verification/`，禁止覆盖已有包。
