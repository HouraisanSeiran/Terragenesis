# 山地来源与湖河耦合 v1（A 写集）

仅新增 `terrain_pipeline/mountain_source_adapter.py`、`mountain_lake_coupling.py`、对应 tests、两个 verify 工具、本说明与新 verification 目录。不写 B 的几何模块，不改冻结 backend、TODO、issues、原数据与 Sonnet。

## 接口提案与固定预算

- source：`arrays.height_m` 为不可变 float64 `[z,x]`、海面零米；`display_mask` 与 `hydrology_mask` 分别表达展示域和有限水文计算覆盖，不能据名称认证完整流域。`metadata.origin_m_xz`、`spacing_m`、`provenance`、`boundary` 与 `domain` 纳入身份。
- domain：计算域 `finite_window_experiment` 或 `complete_contribution_subdomain`；`hydrological_closure_certified=false`、`closure_evidence_sha256=null`。本适配器不具备完整水文规划域认证能力。陆地截断终端为 `external_open_boundary`，不是天然海口。
- boundary：`legacy_lowest_edge`、`all_edges_open` 或 `explicit`；halo 格数与外部上游贡献 `excluded_finite_experiment` / `full_domain` / `explicit_forcing` 独立声明。全窗口全边界开放仍是有限计算窗口实验，不是 CONTEXT 所述地表/地下河不穿越陆边的完整规划域。
- B → A 提案：提供同源 `receiver:int64[z,x]`（-1 终端）、河道节点锚点 `anchor_node:int64[z,x]`（-1 非锚点，湖盆所有格映射其湖节点）、`node_downstream:int64[N]`、`node_kind`、`node_boundary_type`，并提供源 identity、几何证据 hash、accepted mask/失败 mask 与明确的通过状态。A 在新 receiver 上独立重算首次节点归属及 HRU×节点相交面积，不接收旧累计 Q。
- lake 节点：先只支持单池且无尾水/回水的有界蓄水数学；B 提供真实盆底、spill、严格递增 V(h)、边界范围及 rating Q(h) 证据。任何湖都不是零驻留河段。容量/连通性未通过只输出诊断，不发布伪造水位。
- 总计算格最多 250000、HRU 最多 256；全域出口归属统计可达 250000 终端，但动态最多 2048 节点、3000 步、8000000 时间×节点项、768 MiB 与 30000000 工作单元。大量边缘终端先统计，再选代表性真实完整贡献子域，不放宽动态节点预算。

## 来源证据

固定旧 normal/pressure 使用上一轮三个独立外部 hash（原 TD、河网包、provenance），保留历史游戏限高身份。减 126m 仅改变基准，不恢复被限高的山。

新 TD 仅接受既有 runtime `elevation_m`、五通道 `climate`、`metadata_json` 真实输出；校验 physical-generation-v1 内部身份、原生格与窗口。`conditioning_only` 拒绝。重签 hash 不是实际推理认证：加载仍须外部可信 archive hash；任何自造 metadata/数组只能用于契约负测试，不能声称实际 TD。

`make_source` 是受信任的进程内构造 API，不是认证器；其自报来源字段只能表示声明。最终消费必须使用外部可信 SHA、源 identity，并以 `trusted_source` 对照从固定原 payload 导出的全部数组与元数据。适配器最多 250000 格，因此拒绝 backend 允许的 513²（263169 格）；本轮实际推理入口上限 256²。

旧源加载暂时依赖 `tools.verify_mountain_rainfall` 的固定 hash/读取入口，仅供本轮独立实验复用，不声称长期生产 core 边界已整理。验证器开头保存 37/38 冻结14文件及相关36来源/单池模块快照，末尾逐项比较；失败保留独立 evidence。

GPU 尚未获空闲通知，不启动推理，不触及用户游戏。准备入口限定单种子 batch1、256² 与一份同种子重叠窗口，复用 `PhysicalTerrainDiffusionBackend` 与本地模型，不下载。只有明确 GPU 放行参数才可能启动，不能由 CPU 验证自动触发。

## 对照与账本

旧单出口与新多出口是边界条件改变，不能称同边界算法改进。对照元数据分别保存边界身份，标注 `boundary_condition_changed`。潜在填洼几何容量不是实际蓄水，不加入动态水账。

动态分别保存雨、蒸散、土壤/快慢地下库变化、湖储水、河储水、每开放出口和合计体积。内部转移只记一次局地输入。线性河库不显示水深；湖数学可解也不自动获得 accepted 几何认证。

## 已实施的完整贡献组接口

`build_group_topology(source, geometry, group)` 保留所选完整贡献组每个干格路径节点和所有湖节点；超过2048拒绝，不删边缘终端。B `validate_mountain_geometry` 静态验证 H0、米制网格、边界与 source_binding，再调用其独立 `certify_no_cut_groups`。施工选择 `accepted_mask` 与无需切床的合法证据独立，A 不擅自改 B 的 accepted。

source 全域身份保持不变。`make_selection` 独立身份绑定全源身份、full receiver、选取 mask 与完整贡献证明；静态验证全源每个 donor 与 receiver 的选中状态一致，仅有声明的一个终端，禁止删上游格而保留其下游。A 静态加载只检查 saved cell_node 的逐边递推、锚点、相交计数和水账，不调用 local_allocation/terminal_ownership 重建。

`group_lake_specs` 采用未校准 broad-crested weir 示例：Q=1.7×完整30m边宽×head^1.5；存档为65点分段线性 rating，零水头无流量。最大水位等于除显式 spill 以外最低岸线，不加人为高度。逐所有高程事件的 union-find 证明非空湿子级只有一个4连通组件。每个显式 spill/path 检查同源 receiver；路径可终止在开放终端或另一实际湖节点，内部溢流沿 DAG 仅传一次。cascade 为单向无尾水近似，不是 Fill-Spill-Merge 论文复现或父盆合并水位模型。遇到等高多 spill、反坡、跨干鞍或超岸只保留诊断和最后有效单池前缀。

`couple_rainfall(..., surface_rain=False)` 是固定全部格概念陆地产流支持，湖格也经土壤/快慢库，不是水面过程。`surface_rain=True` 把固定完整湖 footprint 从陆地面积扣除，直降雨进入对应湖；`lake_evaporation_mm_h` 单独给定、以同一固定 footprint 换算损失，缺水时拒绝，不透支。湖格干初态仍固定为 footprint，此为显式近似，尚无动态湿面积、真实蒸发校准和尾水反馈。每 HRU 必须仍有正陆地面积；纯水面 HRU 暂不支持。

normal group154（978300m²，lake100两格）与pressure group1639（325800m²，lake2760单格）只代表30m离散蓄水单元实验，不可渲染为整个流域都受湖控制。保存真实湖贡献面积及绕湖支路比例。原≥4格的全域候选统计不删除，小池实验单列。normal1208与pressure1623各四池作为真实 cascade 扩展，逐池容量与边界限制不放宽。

## 审查消费

consumer JSON为只读可视副本，绑定NPZ SHA、source/geometry/selection身份与dt。T+1状态含t0和t336；滑块状态k展示前一时段k−1平均流量，k=0不显示不存在的时段。保存逐步雨量、土壤/快慢库存量、湖位/存量、河库存量、外流与联合残差；原始全节点精度保留NPZ。网页请求 ticket 防止快速切换旧fetch覆盖新案例。地图为米制坐标的km显示，高程色标m，灰线仅坡面receiver路径，蓝线为≥1km²起河阈值，不能把全部receiver当可见河。

失败案例须保留单池求解输入/前缀NPZ和失败JSON，不把下游未计算状态显示为成功。网页独立于Sonnet，不进行准备、推理或推进。新TD实际推理未执行，CPU条件场不作为地形证据。

ZIP/NPY header 在数组分配前检查，禁 pickle、重复成员和超预算；静态读取不调用推理/准备/推进。排他硬链接作为原子提交点，已有目标或竞态覆盖均拒绝。失败证据独立保存，不覆盖已冻结产物。
