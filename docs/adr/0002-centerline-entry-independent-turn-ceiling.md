# 中心线搜索以「入口无关的转角上限」取代自指回归门

Status: accepted

日期：2026-10-18。用户拍板取消「以参考路径为上限」的自指接受规则（A-P0），并认可旧 v6 证书标 superseded 而非删除。

## 背景

`shape_centerline` 的接受约束原本写成「候选的 ordinary/junction 的 max 与 p95 四个转角数，不得超过参考路径自身对应值」（`baseline_turn`），而参考路径正是搜索起点（传了 `reference_points` 时直接用该路径，否则用八遍初始化）。后果（实测，见 `docs/centerline-naturalness-audit-20261018.md`）：

1. **自指**：上限即基线自身，基线质量直接决定搜索空间，把「把 90° 台阶摊成两组 45°」这类真实改善判为回归（余量仅 1e-7）。
2. **入口决定结果**：同算法同参数，只改传不传 `reference_points`，转角能量差 27 倍（1.000 一动不动 vs 降至 0.037）。
3. **四数全局互斥**：移动节点 i 可抬升节点 j 的相对转角，于是整批候选被否。
4. 全仓 139 份台账口径下，该纪律占拒绝总量 36.4%（6403/17583），且一经触发即不可协商。

## 决定

1. 声明固定解析上限 `ANALYTIC_TURN_BOUND_DEGREES = {ordinary: 90°, junction: 90°}`，它是**严格程度的上限封顶**而非一次性硬墙。有效上限 `turn_ceiling(baseline) = max(声明上限, 基线自身 movable 转角最大值)`：既不看 `reference_points`（入口无关），又保证脏基线仍有单调下降余量（实测一次性硬墙会让整批搜索被否、接受 0 步）。
2. 上限只作用于**可移动节点**（`~_anchors`）。源/汇流/终点锚点不可移动，其宽转角属不可变原始栅格，改记到 `anchor_turn_exemption` 诊断字段。
3. 取消 max/p95 四数互斥：p95 ≤ maximum（同一节点集），约束 maximum 即约束 p95。
4. 起点归一：无论是否传 `reference_points`，搜索起点一律为确定性八遍六米初始化；`reference_points` 只写 `reference_turns` / `reference_turn_regression` 诊断字段，不再拒绝候选。
5. 三处副本同源化（见下），身份升 v7。

## 落点

| 位置 | 作用 |
|---|---|
| `terrain_pipeline/surface_rivers/metric_terrain_centerline.py` | 搜索期主门；新增 `node_turns` / `movable_turn_maxima` / `turn_ceiling` / `enforce_turn_ceiling` / `anchor_turn_exemption` |
| `terrain_pipeline/surface_rivers/metric_td_generated_rivers.py` | 横向切深预算修复阶段的第二道门，改用 `policy["effective_turn_ceiling_degrees"]` |
| `tools/diagnose_td_river_bottom_budget.py` | 诊断工具副本，改用 `turn_ceiling(legacy, receiver)` |

## 算法身份

| 项 | 值 |
|---|---|
| 新身份 | `anchored-staged-terrain-branch-certified-ordinary-sweep-analytic-turn-bound-v7` |
| 被替代 | `anchored-staged-terrain-branch-certified-ordinary-sweep-v6` |

按 `CONTRIBUTING.md:31,37`：算法身份变更与存储格式变更分别记录；旧证书不得继承，失败证据不删除。v6 证据一律标 superseded，清单与处置见 `verification/td-terrain-generated-rivers/CENTERLINE-V6-SUPERSEDED.md`。

## 后果与未认证项

- 会改变已冻结的穴面几何，既有 v6 验收不得继续引用；受影响模块与结果须重跑后另行声明。
- 90° 是**未标定的工程设定**，不是物理定律；policy 里以 `coefficient_status` / `turn_bound_policy` 显式标注。
- 本次未做：静默拒绝补账（A-P1）、走廊三类拆分（A-P3）、抬升预算数值标定。
