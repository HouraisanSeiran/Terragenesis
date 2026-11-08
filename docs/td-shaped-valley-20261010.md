# TD 原床约束下的真实谷地路径改进

成果保存在 `verification/td-shaped-valley/td1024-20261010-01/manifest.json`。本次把已有锚定中心线实际传入 `build_monotone_union`，重建稀疏三角床面与真实断面，保存改进前 `.5m` 和改进后 `.5/.25m` 床面；它们不是显示样条。原 TD、原全域产物保持原样。

| 连通组件 | 边数 | 长度 m：原→新 | 最大转角：原→新 | 新床最大切深 m | .5/.25m 切量相对误差 |
| --- | --- | --- | --- | --- | --- |
| 0 | 5 | 162.4264 → 161.1805 | 45° → 39.5761° | 0.5374 | 0.0005305% |
| 1 | 3 | 102.4264 → 99.9801 | 45° → 37.6096° | 0.4660 | 0.0194325% |
| 4 | 5 | 187.2792 → 184.7874 | 45° → 39.5761° | 0.7366 | 0.0695715% |

13 条已有合法边形成三个可显示替换候选，5 个内部节点移动，最大位移 1.875m。源、汇流及终端锚点未变；床面通过实际三角网分段下降、原床 owner 插值模板、4m 切深、非局部相交、共享断面与冷加载复核，细化误差低于固定 2% 门槛。组件 3 的 11 条边候选在真实床面检查中仍出现平/反坡，拒绝原因保存在 manifest 的 outcomes，未算入成果。

切量对比统一使用 `.5m`：组件 0 为 327.9939 → 317.3173m³，组件 1 为 214.4249 → 212.1788m³，组件 4 为 436.9776 → 431.3144m³。manifest 的 `comparison_spacing_m / original_cut_volume_m3 / shaped_cut_volume_m3` 明确该同精度比较，`.25m` 值另列 `shaped_fine_cut_volume_m3` 用于细化验收。

全域覆盖仍为 **623/673**（92.5706%），保留 **50** 条 owner divide 拒绝边。原 `refusal-diagnostic.json` 给出逐边原因：27 条零半径中心线的原床插值 stencil 已跨 owner，另 23 条最小合法 0.1m 半径仍跨 owner；固定端点不能用路径绕行消除该问题。此次未缩窄河岸、放宽 owner 或细化阈值。三个候选尚未替换进全域唯一切量账，因而没有宣称全域改善验收、水力可用或自然出口成立。

展示读取 cases[].artifacts 的路径、sha256 与 identity_sha256。床面数组沿用 `vertices_xz_m / triangles / source_elevation_m / bed_elevation_m / cut_depth_m`；前后中心线为 `original_node_xz_m / node_xz_m / receiver`；断面为 `port_profile_xz_m / port_triangle_ids / port_barycentric / port_cut_depth_m`，可按保存网格读取原/新高度。每个组件还提供 comparison.png，左侧前后路径，右侧保存床面切深。

复现：`D:/anaconda/python.exe -m tools.prepare_td_shaped_valley --output verification/td-shaped-valley/<new-run>`。本次相关 4 个单元回归通过，其中新增真实 shaped 床面生成、禁优化器冷加载、锚点篡改拒绝检查。
