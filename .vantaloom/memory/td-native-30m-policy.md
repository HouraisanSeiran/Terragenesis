---
name: td-native-30m-policy
description: 用户拍板：一律按TD原生30m机制、最小1m，10km基准作废；含层级划分与勿重蹈的失败路径
scope: project
type: spec
---
## 用户拍板（2026-10-23）
「往后做东西就按 terrain diffusion 的 30m 机制做，最小单位 1m，别惦记 10km 基准了，根本不适用。」

### 必须遵守
- **10 km 基准作废**，不再作为参照、回归基线或兼容目标。
- 一律按 **TD 原生 30 m 机制**；**最小空间单位 1 m**。
- 不要为兼容 10 km 而设计、妥协或加开关。

### 关键层级（别再搞错）
`diffusion/physical_config.py`：
- `native_resolution_m = 30.0` ← **TD 原生分辨率，30 m 是原生产物**
- `conditioning_spacing_m = 7680.0` = 30 × latent 8 × coarse 32
- `metric_domain_closure` 是 **7680 m 条件规划格**，**不是地形格**

### 正确的 30 m 机制
`terrain_pipeline/surface_rivers/metric_cross_region.py` 直接吃 TD 原生页：
`BORDER_BAND_CELLS = 6`（边界带拒绝，不是 margin 放大）、`assemble_pages` 全向量化且顺序无关、`resolve_point` 五词判定、`_flood` 把未解析格当不可通行而非排水口。
另有 `metric_depression_gate`（`spacing_m=30.0` 默认，61 测试）、`metric_fine_terrain`（`FINE_SPACING_M=30.0`）。

### 已记录的失败路径（勿重蹈）
曾用 `PlanningConfig.macro_span_m` 缩小去凑 30 m 粗格点，结果 `DEFAULT_MARGIN_NODES=48` 是**节点数**，30 m 下只剩 1.44 km 排水余量 ⇒ 100% `unresolved_border`。这是在错误的层上工作。
