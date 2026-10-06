# 移动中心线细准备 v1

本切片是实施验证，主协调另行独立验收；不表示完整地表系统、真实山地域、自然度或游戏验收完成。来源 H0、累计 Q、拓扑与锚点保持不变，移动后的坐标实际参与断面切床、静态水位与淹水计算，不吸附回 D8 格点。格式与旧 surface-network/recovery/consumer 独立，不自动接入默认世界。

## 接口

模块 `terrain_pipeline.surface_centerline_prepare`：

- `prepare_surface_centerline(plan, centerline, fine_origin_x_m, fine_origin_z_m, fine_spacing_x_m, fine_spacing_z_m, fine_shape_zx, domain_mask, protected_mask, legal_outlet_mask, outlet_stage_m, section_recipe, stage_recipe, inundation_recipe, budget)`：显式 CPU 准备。输入为既有 `plan_channel` 与 `build_centerline` 的诊断结果，细网格为米制节点格，数组轴顺序为 `(z, x)`，origin 为第一个节点坐标；高程沿用 plan 的海面基准。mask 必须为同形 boolean。配方为 `SectionRecipe`、`StageRecipe`、`InundationRecipe` 与 `SurfaceNetworkBudget`；出口水位按 stage 既有接口解释。
- `save_surface_centerline(result, path, allow_diagnostic=False)`：完整语义重放后另存 NPZ。父目录须存在，不覆盖任何现有目标；不创建任务、分支或默认发布状态。
- `load_surface_centerline(path, allow_diagnostic=False)`：有界 NPY/ZIP 预检后读取并重放自包含原输入。不读取原始来源目录、不调用模型/GPU/游戏；为核对物理语义，会执行 CPU sections/stage/inundation 重算，不是 lazy reader。不是仅凭 hash 接受几何。
- `slice_surface_centerline(result, z_slice, x_slice)`：仅 prepared，同格只读窗口；slice 需明确非负 start/stop、非空、界内、unit step。不生成或重算，返回窗口 origin、spacing、来源 prepare 身份及数组视图。

返回结果含 `identity`、`identity_sha256`、`status`、`components`、`arrays`、`summary`。状态为 `prepared` 或 `diagnostic_not_publishable`。输入非法、身份/重放不符、负 local Q 或资源越界抛 `ValueError`；可计算但物理不通过则返回 diagnostic。诊断包 save/load 均须显式 opt-in，不能 slice。字典 metadata 是普通可变对象，不应视为认证；数组及其 ndarray 底层链均来自 immutable bytes，无法恢复 writeable。

## 物理与几何门禁

plan 及 centerline 的身份记录、status、所有数组/dtype 和 summary 按原配方重建比较。prepare 包所有 component metadata、summary、实际输出与 joint 身份也重放比较；重新计算 hashes 不能掩盖不一致。Q 对**全部节点、全部上游（含 inactive）**求和，要求 `Q[node] - sum(Q[donors]) >= 0`；仅允许 IEEE float64 求和舍入尺度，非物理流量容差。允许正 local inflow，不允许两个 0.2 流入 0.2。

节点床面以实际位置双线性采样，对原 `bed_match_tolerance_m` 检查；edge 以不大于半格的轴向步长采样。仅严格正权重角点参与有限性/mask 检查与求和，零权重 NaN 不污染合法节点，极小正权重也不能跳过。床支持须 domain 且非 protected 且有限；水面支持另须 wet，不在 dry、unknown 或保护格间插值造水。无独立 unknown_mask 输入：非有限 sampled field 表示 unknown；plan 的 H0 仍需有限，未知 H0 不得冒充完整有效 DEM。

同时检查理想 stage 与真实 `water_surface_m - bounded_surface_m` 的 min clearance/max depth，保留真实水面重构误差诊断。切深、面积、体积、保护、域外切床、section/stage/joint、全湿面到 legal outlet 的四邻接连通均保持原门禁。面积/体积在 fine 节点格积分，边界半权重、角点四分之一；不将累计 Q 作为 wet 栅格求和。

`summary` 另含 `support_failures`（outside_grid/domain/protected/unknown/dry 样本失败次数，非唯一节点数）、`max_stage_bed_error_m`（节点）、`max_edge_bed_error_m`（edge 实床相对理想床）、`max_water_reconstruction_error_m`、`edge_reverse_bed_observed`、`edge_samples`、`needs_finer_grid`。节点床误差或原 joint resolution 不合格时显式提示细化；支持点失败单独诊断，不保证仅细化可修复。edge 离散床误差和局部逆坡仍按原语义记录，不新增理想 edge 误差硬门禁，也不放宽节点床容差。

## 文件与资源

NPZ `manifest` 是 scalar Unicode JSON，`format_version=1`，算法 `surface-centerline-prepare-v1`；数组使用 `plan__`、`centerline__`、`section__`、`stage__`、`flood__` 前缀，另含 domain/protected/legal masks 与 outlet stage。自包含所有重放输入，hash 仅保证一致性，不提供发行者认证。

硬限：coarse/fine 各 2,000,000 节点；active graph 4,096 节点；edge 合计 2,000,000 样本；ZIP 最多 100 成员、展开总字节 1,000,000,000；manifest payload 最大 1,000,000 字节。NPY 仅 v1/v2、非 object、至多二维，每数组最多 40,000,000 元素；实际 payload 必须与 header 声明和 ZIP file_size 完全相符（不允许截断或尾随字节）。数组仅 bool/int/uint/float。ZIP 重名、路径成员、不支持 header/非法 dtype 在 `np.load` 前拒绝。读取保持同一打开文件描述符，避免 preflight 后重新打开路径的竞争窗口。

保存在目标父目录生成唯一临时文件，完成并重载验证后使用 `os.link` 原子无覆盖发布，finally 只清理本次临时文件；两并发保存仅一胜出，另一抛 `FileExistsError`，不删除胜者。要求目标文件系统支持同目录 hard link（本实施在 Windows 工作区验证）；无 hard-link 支持会安全失败，不提供 overwrite fallback。未声明 fsync/断电持久性或恶意原地修改文件的抗攻击保证。

## 固定实施验证

```powershell
D:/anaconda/python.exe -X utf8 -m unittest tests.test_surface_centerline_prepare -v
D:/anaconda/python.exe -X utf8 tools/verify_surface_centerline_prepare.py
```

每次新建 `verification/surface-centerline-prepare/run-<UTC>/`，保存 `report.json`、两个 prepared 包及同格窗口、八个失败诊断包、移动前后实际 fine-bed 比较、非守恒输入及重哈希不一致拒绝包。失败验证也留 report 并以非零状态退出。报告明确是 implementation verification，不创建 independent-review，不更新总览状态。

合成双支流正例为源 9/11 各 0.1 m³/s、汇合 17 与下游 0.2 m³/s；2 个内部节点移动、锚点不动，1 m fine 实床相对零强度路线变化。2 m 网格保留精度失败，不增大原 1e-6 m 节点床容差。聚焦测试覆盖重哈希重放、Q、全部 hard-readonly、亚格域/保护/未知/干支持、真实水深、NPY 与资源预检、诊断重载、无覆盖保存竞争和切片边界。

静态 stage 不是动态水动力；不处理跨精度交付、湖河 spill 连续水几何、双向回水、真实自然出口认证或自然度。本切片不改原数据、不启动 GPU/游戏、不安装依赖，不声称旧 176 项是本实施重新运行的结果。
