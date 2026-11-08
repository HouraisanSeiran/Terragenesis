---
name: refactor-one-function-one-module
description: 用户 2026-11-05 19:46：旧产物保留不重生成，旧代码不必能复现旧产物；重构目标是一功能一模块
scope: project
type: spec
---
用户 2026-11-05 19:46 决定（取代此前「被证据 pin 文件一字节不能改」的约束）：
1. **旧产物留着就行，不需要旧代码生成旧产物。** 已有产物、verification/ 记录、验收图全部原样保留；活跃源码不再承担复现旧产物的责任。
2. 因此证据 pin 不再阻止改动或归档源码。做法：改动或归档前，先把被 pin（含隐形 pin）的源文件原字节**复制**到 legacy-code/frozen-sources-20261105/（manifest 记原路径、SHA256、引用它的证据文件），证据仍可对冻结副本复验；然后活跃源码可自由合并、改写、归档。
3. **一功能一模块**：每项功能只有一个对应模块负责，不允许几个模块各负责同一功能的一部分。重构按「功能 → 唯一模块」目标表执行：同功能的旧模块合并进目标模块，旧文件归档（只移动不删除），调用方改为导入目标模块。
4. 种子：新代码统一 20260903；旧产物不重新生成，所以种子迁移不再需要重跑 TD/GPU。
5. 异常统一 ValueError（19:11 已定）。
仍保留的约束：三角洲族（coastal_delta_*、large_delta_*、delta_network_*、coastal_marine_*、metric_*delta*、environment_*delta 等）本轮仍不动，等 R5；织梦依赖的 skeleton_mountains、fictional_world_overview、procedural_mountain_erosion 公开接口不破坏（异常类型改动需织梦侧同步核对）；只移动不删除；每批跑测试、重建模块表。
