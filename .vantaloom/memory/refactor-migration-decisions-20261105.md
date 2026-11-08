---
name: refactor-migration-decisions-20261105
description: 用户对算法重构迁移方案 §7.1/§7.3/§7.5 的决定（2026-11-05 19:11）
scope: project
type: spec
---
用户 2026-11-05 19:11 对 .scratch/algorithm-refactor-20261105/migration-plan.md §7 的决定：
1. §7.1 选丙：迁移执行先停下，先做「证据 pin 退役」评估（哪些被 pin 文件对应的证据已不需要原路径复现、能否把源文件连同字节一起归档而证据仍可校验），评估后再定归档范围。60 个薄封装也等评估结果一起排批。
2. §7.5 选乙：20261020 → 20260903 全部改，含旧产物生成器；接受旧产物需重新生成。归入数值修订轨道单独立项，不与无数值变化的重构批次混做。
3. §7.3 选乙：薄封装后统一抛 ValueError，删掉 OverviewError/LayoutError/LithologyError 等专用异常，同步改 except 子句和测试断言。风险：fictional_world_overview 在织梦依赖闭包里，织梦侧若 except OverviewError 会受影响（织梦目录不在本工作区，需织梦侧核对）。
