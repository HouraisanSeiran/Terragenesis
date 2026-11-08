---
name: refactor-merge-decisions-20261105
description: 功能→唯一模块合并的用户决定（2026-11-05 20:21）
scope: project
type: spec
---
依据 .scratch/algorithm-refactor-20261105/pin-retirement/function-module-map.md（50 项功能、目标净减 447 模块）及其 §8 主代理修正。用户决定：
1. metric_contracts 并入 common_infra。
2. 允许 D 依赖 B（environment_regional_hydraulics、environment_climate_driver 调 B 水力内核），登记在实现总表。
3. new_world_* 20 个模块拆进各功能内核（洪泛→drainage_kernels、断面→channel_geometry_kernel 等），不建 new_world_kernel。
4. §5 其余按建议：surface_kernel 归属按报告；world_acceptance_processes 语义归 D；mountain_source_adapter 不留别名，并入 common_infra。
执行规则见 .scratch/algorithm-refactor-20261105/merge/rules.md：不留 shim；函数体搬进目标模块→调用方直接改 import→np.array_equal 差分→旧文件移入 legacy-code/refactor-merge-20261105/<批>/；合并批次不改任何数值（种子迁移、平局键等在数值修订轨道另做）；三角洲族不动；织梦闭包三模块公开名与签名不改。
工作区有大量未提交/未跟踪文件，git worktree 从 HEAD 建会缺这些文件，不能用 worktree 并行；并行批次只能按互不重叠的文件集划分。
