# Terraindiffusion 河网算法完整实施建议

## 交给 GPT 的实现说明

本文档是 Terragenesis / Terraindiffusion 河网算法的实现蓝图。目标不是在已有界面上画出一组看起来像河流的线，而是建立一条可以审计、可以守恒、可以分阶段验收、不会把诊断结果冒充最终自然河网的完整链路：

> 地形输入 → 数据质量与来源审查 → 降雨／积雪／地下补给 → 入渗与产流 → 地形汇流 → 湖泊与内流盆地 → 河道水动力 → 泥沙与侵蚀 → 河床几何 → 多分辨率重建 → 保存、可视化与验收。

实现时必须将以下四类对象分开：

1. **地形与地形来源**：Terraindiffusion 生成或输入的高程场，不自动称为实测 DEM。
2. **诊断排水拓扑**：由高程和边界推导出的 receiver graph，只说明水往哪里走，不等于已认证河流。
3. **候选河床几何**：由流量、坡度、侵蚀和宽度模型生成的可视化／几何候选。
4. **已验证水动力与最终河网**：只有通过质量守恒、边界、稳定性、河床连通性、湖泊耦合和来源登记后，才允许使用“最终”“自然河网”或“可发布河流”等名称。

---

## 一、必须遵守的工程边界

### 1. 真实地形来源与 Terraindiffusion 生成地形必须分开

Terraindiffusion 输出的是模型生成地形或条件生成地形。除非来源链明确证明输入来自测绘 DEM，界面、元数据、报告和变量名都不得称其为“实测 DEM”。推荐使用以下术语：

- `generated_terrain`：模型生成地形。
- `conditioned_terrain`：由外部条件约束的生成地形。
- `observed_dem`：来源可验证的实测 DEM。
- `diagnostic_dem_proxy`：用于诊断或对照的 DEM 代理。

每个地形包必须保存：来源类型、来源路径、空间参考、坐标单位、原点、网格间距、缺测规则、哈希、生成种子、模型版本、条件摘要和是否允许用于水动力认证。

### 2. AMR 是局部高精度对照，不是自动的全域真值

AMR 用于局部高分辨率验证、断面解析、河床细节或关键汇流节点对照。uniform 网格保留为失败对照和数值偏差基线。不能因为 AMR 画面更细，就把 AMR 结果自动视为正确结果。

要求：

- 原生网格或统一基准网格负责全域水量体积基准。
- AMR 必须报告细化区域、细化比、边界通量、限制器和与原生网格的体积差。
- AMR 与 uniform 之间必须比较：总水量、出口流量、峰值到达时间、河床侵蚀量和关键断面水面。
- 如果 AMR 只覆盖局部，输出名称必须含 `local_high_resolution_diagnostic` 或等价标志。

### 3. 原生网格是水体积基准

视觉水面可以通过插值或重构得到，但水体积、降雨输入、入渗、蒸散、河道交换和域外出流必须在原生网格上记账。任何水面重构都必须保存：

- 重构前的原生水量。
- 重构后的几何水量。
- 二者差值与相对误差。
- 重构是否经过守恒修正。
- 是否允许用于认证。

不能用渲染网格的像素数量或显示抽稀后的高度场重算全域统计。

### 4. 时间语义必须显式

内部求解可以使用短子步，外部保存帧可以抽样。保存帧不能默认等于一秒，也不能把一个时间区间内的累计体积标成瞬时流量。

每个时间序列必须保存：

- `time_seconds`：保存帧对应的物理时间。
- `dt_solver_seconds`：内部求解子步。
- `dt_output_seconds`：输出帧间隔，允许不均匀。
- 字段是瞬时值、时间平均值、区间累计量还是区间末态。
- 对流量、降雨、入渗、出口体积、水面和河床的不同时间语义。

推荐字段命名：

- `q_instantaneous_m3_s`
- `q_timestep_average_m3_s`
- `volume_interval_m3`
- `stage_end_of_interval_m`
- `rainfall_mm_h`

不要使用一个含义不明确的 `q` 字段承载所有语义。

### 5. 自由出流只能单向出域，禁止倒灌

域外边界必须明确标记为：

- `open_outflow`：允许水从域内流出，不允许反向进入。
- `closed_wall`：不允许通量穿过。
- `prescribed_stage`：外部水位边界。
- `prescribed_discharge`：外部流量边界。
- `unknown_boundary`：来源或下游信息不足，不能自动推断。

自由出流边界必须满足：

\[
Q_{boundary} \ge 0
\]

其中正号代表出域。任何反向数值通量必须被截断、拒绝或显式标记为边界条件不一致，不能直接变成倒灌。

### 6. 内流盆地应保留为湖泊

没有自然出口的洼地不能被算法强制接成河流。应识别为：

- 内流湖泊。
- 暂时性积水盆地。
- 由于未知地形而无法判断的封闭水体。

只有当有数据支撑的下游地形被扩大并重算、且存在经过验证的自然出口时，才允许将湖泊转为河流源头或下游河段。

### 7. unknown 地形不向外追踪

缺测、无效或未知地形区域不能被填充成“可通行地形”后继续追踪。默认规则：

- unknown 区域不作为可靠 receiver。
- unknown 区域不能自动成为湖泊出口。
- unknown 区域不能制造下游河网。
- 在计算域边界或未知边界处，输出域外出流候选并记账。
- 如需验证下游路径，扩大有数据区域后重新计算，而不是延长当前结果。

---

## 二、建议的整体架构

建议把河网系统拆成相互独立、具有明确数据契约的模块，而不是在一个函数里同时完成降雨、汇流、侵蚀、河床、水动力和渲染。

推荐目录：

```text
terrain_pipeline/
  terrain_sources/
    contracts.py
    provenance.py
    nodata.py
    resampling.py
  hydrology/
    forcing.py
    rainfall.py
    snowmelt.py
    infiltration.py
    runoff.py
    soil_storage.py
  surface_rivers/
    contracts.py
    conditioning.py
    depression.py
    routing.py
    accumulation.py
    lakes.py
    outlets.py
    channel_geometry.py
    hydraulics.py
    sediment.py
    geomorphology.py
    coupling.py
    multiresolution.py
    diagnostics.py
    io.py
    pipeline.py
  validation/
    mass_balance.py
    boundary_audit.py
    topology_audit.py
    geometry_audit.py
    resolution_audit.py
```

现有 `terrain_pipeline/surface_rivers` 可以作为第一阶段基础，但不能把当前 `route → accumulate → carve_channels` 直接称为完整河网算法。它目前更接近确定性离线排水和有界通道几何原型，适合作为可测试核心，不足以替代动态水动力和完整地貌演化。

---

## 三、核心数据契约

### 3.1 TerrainGrid

```python
@dataclass(frozen=True)
class TerrainGrid:
    elevation_m: np.ndarray       # [rows, cols], float64
    valid_mask: np.ndarray        # [rows, cols], bool
    x0_m: float
    z0_m: float
    dx_m: float
    dz_m: float
    crs: str | None
    source_kind: str               # observed_dem / generated_terrain / proxy
    source_id: str
    source_sha256: str
    vertical_datum: str | None
    nodata_semantics: str
```

约束：

- 高程使用米制 float64 进入水动力核心。
- `valid_mask=False` 的单元不能参与普通 receiver 搜索。
- `dx_m`、`dz_m` 必须是有限正数。
- 必须明确数组索引对应的世界坐标方向。
- 不能根据数组行列顺序猜测世界坐标。

### 3.2 BoundaryGrid

```python
@dataclass(frozen=True)
class BoundaryGrid:
    kind: np.ndarray       # open_outflow / closed_wall / unknown / stage / discharge
    stage_m: np.ndarray | None
    discharge_m3_s: np.ndarray | None
    allow_inflow: np.ndarray
    provenance: dict
```

边界条件不能只存一个 `outlet_mask`。`outlet_mask` 可以作为兼容字段，但新算法必须保存每个边界单元的类型和方向。

### 3.3 RainfallForcing

```python
@dataclass(frozen=True)
class RainfallForcing:
    time_seconds: np.ndarray       # [T]
    rain_mm_h: np.ndarray           # [T, rows, cols] 或可索引外部源
    source_id: str
    source_sha256: str
    temporal_semantics: str        # interval_average / instantaneous / accumulated
    spatial_semantics: str         # cell_average / point_sample / interpolated
    missing_policy: str
```

降雨不能从地形噪波直接隐式推断。若使用 Terraindiffusion 的高度或气候条件生成降雨场，必须把它作为独立的、可替换的 forcing 模块，并保存随机种子、空间尺度和降雨校准信息。

### 3.4 HydrologyState

至少包含：

```python
@dataclass
class HydrologyState:
    soil_water_mm: np.ndarray
    canopy_storage_mm: np.ndarray
    snow_water_equivalent_mm: np.ndarray
    surface_storage_m3: np.ndarray
    groundwater_storage_m3: np.ndarray
    runoff_m3_s: np.ndarray
    infiltration_mm: np.ndarray
    evapotranspiration_mm: np.ndarray
    percolation_mm: np.ndarray
```

当前 `rainfall_runoff.py` 已实现独立单元产流和守恒校验，其 `local_q_m3_s` 明确是 `timestep-average local discharge; not river-routed`。该模块应保留为产流层，不能直接把 `local_q_m3_s` 当成河道流量。

### 3.5 RoutingGraph

```python
@dataclass(frozen=True)
class RoutingGraph:
    receiver: np.ndarray           # flattened receiver, -1 only for terminal/outlet
    donors: tuple[tuple[int, ...], ...]
    order_downstream_first: np.ndarray
    edge_length_m: np.ndarray
    edge_slope: np.ndarray
    outlet_kind: np.ndarray
    lake_id: np.ndarray
    topology_status: str
```

必须支持：

- D8 作为基线。
- D-infinity 或多流向作为可选增强。
- 汇流分叉／合流的明确语义。
- 平地和洼地的确定性处理。
- 湖泊单元的汇聚和出流。
- unknown 区域阻断。

当前实现使用优先泛洪和 D8 receiver，并要求显式出口。这是一个合理的第一阶段基线，但不能掩盖洼地、湖泊、多流向和动态水面之间的差异。

### 3.6 ChannelState

至少包含：

```python
@dataclass
class ChannelState:
    bed_elevation_m: np.ndarray
    bankfull_width_m: np.ndarray
    bankfull_depth_m: np.ndarray
    wetted_width_m: np.ndarray
    wetted_area_m2: np.ndarray
    hydraulic_radius_m: np.ndarray
    roughness_n: np.ndarray
    sediment_mass_kg: np.ndarray
    erosion_rate_m_s: np.ndarray
    deposition_rate_m_s: np.ndarray
    active_mask: np.ndarray
    unresolved_mask: np.ndarray
```

`width_blocks` 只能作为旧版兼容输出。新接口应使用实际米制，并明确宽度是几何宽度、湿润宽度、满岸宽度还是显示宽度。

---

## 四、完整算法链路

## 阶段 A：地形输入与预处理

### A1. 来源登记

读取 Terraindiffusion 输出或外部 DEM 时，先生成 `TerrainSourceRecord`。在进入任何水文计算前完成：

- SHA-256。
- 形状和 dtype。
- 坐标范围。
- 网格间距。
- 垂直范围。
- nodata 比例。
- 空间参考和单位。
- 生成参数与随机种子。

如果任何关键字段缺失，标记为 `pending_provenance`，允许诊断计算，但禁止认证。

### A2. 无效值与异常值

不得把 nodata 直接替换为邻近高程并继续生成河网。建议支持三种策略：

- `block`：阻断水流，适合未知区域。
- `mask_and_report`：从计算域移除并报告边界。
- `fill_for_visualization_only`：只为显示填充，绝不进入水动力核心。

异常高程检测应包括局部尖峰、负无穷、过大坡度、孤立台阶和跨 tile 接缝。修复后的地形必须保存原始与修复差值。

### A3. 坐标和面积

每个网格单元面积必须来自 `dx_m * dz_m` 或明确的地理面积计算。不能把数组索引间距当作米，也不能从 30 m 原生网格直接推断任意显示网格的面积。

---

## 阶段 B：降雨与产流

### B1. 降雨输入

降雨 forcing 可以来自：

- 固定暴雨场景，用于单元测试。
- 观测雨量或雷达产品。
- Terraindiffusion 条件生成的空间雨量场。
- 高程相关的诊断雨量场。

无论来源，都要经过独立接口进入产流层。建议不要让地形生成器直接调用河网函数。

### B2. 入渗与土壤蓄水

基础版本可以继续使用当前概念：土壤容量、入渗能力、蒸散、深层渗漏、快储库和慢储库。建议后续逐步替换为 Green-Ampt、Horton 或分层土壤模型，但每次替换必须保持质量平衡测试。

每个时间步应验证：

\[
P - ET - Q_{local} - \Delta S = R
\]

其中：

- `P`：降雨体积。
- `ET`：蒸散体积。
- `Q_local`：从产流层释放的本地水量。
- `ΔS`：土壤、快储库和慢储库变化。
- `R`：数值余额，必须接近零。

当前代码已经对这一层做了严格的保存结果校验，应保持这一性质。

### B3. 降雨噪波的使用建议

如果要让河网受 Terraindiffusion 风格的空间噪波驱动：

1. 先用固定绝对坐标生成 tile-independent 噪波。
2. 再将噪波映射为降雨倍率，而不是直接把噪波当毫米／小时。
3. 对降雨倍率进行正值、均值和极值约束。
4. 保存 `rainfall_seed`、频率层、权重、基准雨强和校准规则。
5. 用相同世界坐标抽样，确保 tile 拼接无跳变。
6. 单独测试降雨场的拼接一致性和统计稳定性。

推荐：

```text
rain_mm_h = base_storm_mm_h(t) * spatial_multiplier(x, z)
```

而不是：

```text
rain_mm_h = terrain_noise(x, z)
```

---

## 阶段 C：地形汇流与湖泊识别

### C1. 洼地处理不能等同于简单填平

需要区分：

- 数值噪声造成的微洼地。
- 真实内流盆地。
- 被 unknown 区域截断的假洼地。
- 需要湖泊蓄水的低地。

建议先做洼地分类，再决定：

- 轻微洼地：最小抬高或 breach。
- 真实盆地：构建 lake storage curve。
- unknown 截断：保留为不确定，不强行贯通。

### C2. 湖泊模型

每个湖泊应保存：

- lake ID。
- 湖盆单元集合。
- 水面高程—体积曲线。
- 水面高程—面积曲线。
- 出口候选。
- 蒸发和入流。
- 是否为内流盆地。
- 是否允许溢流。

湖泊出流可以按溢流堰、宽顶堰或简化关系计算，但必须显式声明公式和参数。无出口的湖泊不能在 receiver graph 中伪造一个下游节点。

### C3. Receiver graph

第一版建议：

- 保留当前优先泛洪＋D8。
- 将 `outlet_mask` 扩展为 `BoundaryGrid`。
- 将 receiver、排序、donors、边长、坡度一次性保存。
- 所有平地 tie-break 规则写入 metadata。
- 检查图无环，除湖泊内部状态外不得出现循环。

第二版可增加 D-infinity 或多流向，但不要在第一版同时更换所有拓扑规则、产流模型和水动力模型。

---

## 阶段 D：从本地径流到河道流量

当前 `accumulate` 是稳态或单时间片的拓扑累积，适合建立基线：每个 cell 的本地产流沿 receiver 传播，显式出口收集总量，检查输入和出口守恒。

完整时间变河网需要将其扩展为：

```text
for each output interval:
    generate local runoff
    inject runoff into surface storage / channel storage
    route water with internal substeps
    update lakes
    apply boundary fluxes
    save output frame
```

每个河道 cell 至少保存：

- 入流。
- 出流。
- 水面体积。
- 断面面积。
- 水深。
- stage。
- 区间平均流量。
- 区间末流量。
- 边界通量。

连续性方程为：

\[
V^{n+1} = V^n + \Delta t(Q_{in} - Q_{out} + R - I - ET) + B
\]

其中 `B` 是边界通量贡献。每一步和整个模拟都要报告余额。

---

## 阶段 E：河道水动力

### E1. 选择模型顺序

不要一开始直接实现二维 Saint-Venant 全模型。建议分三层：

**层 1：运动波或扩散波基线**

适合建立方向、峰值、到达时间和守恒基线。每个 receiver edge 根据坡度、糙率和断面关系得到出流。

**层 2：一维河段水动力**

沿中心线使用 Saint-Venant 方程，断面参数来自河床几何。适合计算回水、汇流和湖泊连接。

**层 3：二维浅水方程**

只在必要区域使用，例如宽泛滩、复杂汇流、分汊、湖泊和 AMR 局部验证区。

### E2. 断面与糙率

建议支持至少三种断面：矩形、梯形、自然断面。核心公式可以从 Manning 关系开始：

\[
Q = \frac{1}{n} A R^{2/3} S^{1/2}
\]

但是必须保存：

- `n` 的来源和空间分布。
- 断面几何。
- 坡度裁剪规则。
- 湿润周长。
- 水深上下限。
- 是否使用局部或累计流量。

不能用显示线宽代替水动力宽度，也不能用 `sqrt(Q)` 的视觉宽度直接声称是物理断面。

### E3. 稳定性

对于显式求解，至少检查 CFL 条件。内部短子步由最大波速、网格间距和安全系数决定。输出时间可以较粗，但每个输出区间内部要完整推进。

当 CFL、负水深、负体积、非有限值或边界冲突发生时：

- 中止当前时间步。
- 保存失败原因。
- 不发布部分成功的最终河网。
- 可以输出 `failed_prefix`，但必须明确它是失败前缀。

---

## 阶段 F：河床、侵蚀和泥沙

### F1. 侵蚀不是简单按雨量减高度

建议至少区分：

- 降雨溅蚀。
- 坡面径流侵蚀。
- 河道冲刷。
- 河岸侵蚀。
- 泥沙输运。
- 沉积。

第一版可先实现河道内的简化 Exner 更新：

\[
(1-p)\frac{\partial z_b}{\partial t} + \frac{\partial q_s}{\partial x} = 0
\]

其中 `p` 是孔隙率，`q_s` 是单位宽度泥沙输运率。任何切割都必须满足：

- 只切不凭空抬高，除非发生沉积。
- 最大切割深度有上限。
- 总土石体积变化有账本。
- 物质不能跨 unknown 区域悄悄消失。
- 边界输出的泥沙量单独记账。

### F2. 侵蚀和水动力的耦合顺序

推荐采用分裂算法：

1. 固定床面推进水动力。
2. 根据剪切应力和流量计算侵蚀／沉积。
3. 更新床面与断面。
4. 做几何合法性修复。
5. 重新计算局部水力几何。
6. 进入下一子步。

每一步都保存床面差值和泥沙余额。不要在第一版中同时让地形生成网络、降雨网络、水动力网络和侵蚀网络互相隐式调用。

---

## 阶段 G：河流几何生成

### G1. 逻辑中心线

中心线应来自 receiver graph 或河道 cell 的有序路径，而不是从渲染像素拟合。每条路径保存：

- cell ID 序列。
- 世界坐标序列。
- 累积距离。
- 高程。
- 流量。
- 坡度。
- 河段 ID。
- 上游支流 ID。
- 下游连接类型。

### G2. 宽度模型

宽度至少区分：

- 几何中心线宽度。
- 湿润宽度。
- 满岸宽度。
- 洪泛宽度。
- 渲染宽度。

第一版可以使用经过限制的幂律：

\[
W = \operatorname{clip}(a Q^b, W_{min}, W_{max})
\]

但 `a`、`b` 必须是可追踪参数，并且要通过合成测试验证单调性。不能把这套公式直接称为自然河宽预测，除非有校准数据。

### G3. 断面和体积

从中心线生成河床时，需要建立左右法向、底宽、边坡、岸顶和洪泛台阶。必须处理：

- 急弯法向翻转。
- 分汊汇合。
- 支流接入。
- 断面自交。
- 河床切穿地形边界。
- 河床与湖泊水面连接。
- 入口和出口闭合。

最终几何必须进行体积审计：

```text
挖除体积 = 岩土／沉积物移除体积 + 数值误差
沉积体积 = 输入泥沙 - 输出泥沙 - 系统内存留泥沙 + 误差
```

---

## 阶段 H：多分辨率与 Terraindiffusion 集成

### H1. Terraindiffusion 的职责边界

建议 Terraindiffusion 负责：

- 生成或补全地形先验。
- 生成空间条件变量。
- 生成可选的降雨空间场或气候条件场。
- 生成局部地形细节候选。

建议不要让 Terraindiffusion 直接负责：

- 水量守恒。
- receiver graph 的唯一真值。
- 河道流量守恒。
- 最终河床水动力。
- 自由出流边界决定。
- 湖泊是否存在的无证据推断。

### H2. 条件输入

可以将以下变量作为 Terraindiffusion 的条件，但要分清“条件生成”和“物理求解”：

- 高程粗尺度场。
- 坡度和曲率。
- 土壤类型。
- 降雨统计。
- 汇流累积量的低分辨率先验。
- 河流候选 mask。
- 湖泊候选 mask。

模型生成的细节必须通过物理后处理：

- 不制造负面积。
- 不破坏有效边界。
- 不产生无法连接的河床。
- 不改变原生水量基准。
- 不引入无来源的新水。

### H3. AMR 交换

粗网格与细网格之间必须交换守恒量，而不是只交换高度：

- 水量。
- 动量或流量。
- 泥沙量。
- 边界 stage。
- 边界通量。

细网格边界必须与粗网格通量一致；细网格结果回限制粗网格时必须检查水量和泥沙量误差。

---

## 五、推荐实现顺序

不要一次性实现“完整算法”。建议按以下阶段提交，每阶段都可以独立运行和验收。

### Milestone 0：契约与来源

交付：

- `TerrainGrid`、`BoundaryGrid`、`RainfallForcing`、`RoutingGraph`。
- provenance 和哈希。
- unknown 语义。
- 单元面积与坐标测试。

验收：同一输入重复运行得到相同哈希；tile 拼接没有坐标跳变。

### Milestone 1：静态诊断排水

交付：

- 优先泛洪。
- D8 receiver。
- donors 和 downstream-first order。
- 显式边界。
- 汇流累计。
- 湖泊候选识别。

验收：无环、显式出口一致、合流守恒、边界出流不倒灌、unknown 不被追踪。

### Milestone 2：时间变产流

交付：

- 降雨 forcing。
- 入渗、土壤储量、快慢储库。
- 时间步水量账本。
- 本地产流到 routing graph 的接口。

验收：逐步余额和全局余额都通过；改变输出帧间隔不改变总水量。

### Milestone 3：河道储量与简化水动力

交付：

- channel storage。
- 运动波／扩散波。
- 简化断面。
- 内部子步。
- 输出帧采样。

验收：非负水量、稳定性、出流峰值、单支流和 Y 型汇流基准案例。

### Milestone 4：湖泊和边界耦合

交付：

- lake storage curve。
- 溢流。
- open outflow、closed wall、stage、discharge 边界。
- 内流盆地保留。

验收：湖泊蓄水曲线、溢流时刻、自由出流不可倒灌、边界账本完整。

### Milestone 5：河床几何

交付：

- centerline。
- 宽度与深度模型。
- 断面生成。
- 河床与湖泊连接。
- 自交和体积审计。

验收：河床连续、中心线连接、没有非预期自交、切割／沉积体积守恒。

### Milestone 6：泥沙与侵蚀

交付：

- 剪切应力。
- 侵蚀和沉积。
- Exner 更新。
- 泥沙边界通量。

验收：无负床面、泥沙守恒、侵蚀只发生在满足条件的水流区域、时间步收敛。

### Milestone 7：Terraindiffusion 条件生成与 AMR

交付：

- 生成地形／降雨条件接口。
- 局部细化。
- 粗细网格守恒交换。
- uniform 失败对照。

验收：不同分辨率结果的量化比较，不能仅凭截图判断。

### Milestone 8：发布级审查与前端

交付：

- 固定入口登记。
- 元数据、哈希、版本和参数。
- 可视化分层。
- diagnostic / candidate / accepted 状态。
- 审查记录导出。

验收：前端不能把诊断拓扑、水面投影、候选河床和最终河流混为一谈。

---

## 六、必须实现的验证案例

### 1. 平面坡度

输入为解析平面，降雨均匀。预期：流向稳定、出口总水量等于输入总水量减去储量变化，河床不出现无理由分叉。

### 2. 单洼地

输入包含一个真实洼地。预期：先形成湖泊；水位达到出口阈值后才溢流。若没有出口，永远保留内流盆地状态。

### 3. Y 型汇流

两条支流汇入主河。预期：汇合点下游流量等于两支流加本地输入，宽度或断面容量随流量单调变化。

### 4. 多出口盆地

输入包含两个显式出口。预期：根据拓扑和水位分配出流；出口账本之和等于全局出流，不出现隐式第三出口。

### 5. unknown 边界

将下游区域设为 unknown。预期：河网在 unknown 前终止并记录域外候选；不能在 unknown 内继续画出确定河道。

### 6. 暴雨脉冲

短时强降雨后无雨。预期：产流、河道流量和湖泊水位有时间延迟；改变输出采样不能改变输入总量和累计出口量。

### 7. 自由出流

出口外部水位下降。预期：只允许出流；外部水位升高也不能自动倒灌，除非边界类型明确改为允许入流的 prescribed stage。

### 8. 分辨率对照

同一地形分别运行原生、uniform 细网格和 AMR。预期：报告体积、峰值、到达时间、河床侵蚀和断面差异；不能只比较河流图像。

### 9. tile 拼接

将一个区域分成多个 tile，分别生成地形和雨量，再拼接。预期：绝对坐标噪波、降雨和汇流边界一致，没有 tile 缝隙。

### 10. 失败前缀

人为注入不稳定参数或坏边界。预期：输出 `failed_prefix`，保存失败时刻和原因，不生成看似完整的最终河网。

---

## 七、验收指标

### 数值守恒

至少报告：

- 降雨输入总量。
- 入渗总量。
- 蒸散总量。
- 地表储量变化。
- 河道储量变化。
- 湖泊储量变化。
- 地下储量变化。
- 域外出流。
- 域外泥沙输出。
- 水量余额最大绝对值和相对值。

### 拓扑正确性

至少报告：

- 非出口节点 receiver 数量。
- 无 receiver 节点数量。
- 环数量。
- unknown 穿越数量。
- 内流盆地数量。
- 显式出口数量。
- 隐式出口数量，必须为零或明确列为候选。

### 几何正确性

至少报告：

- 河床连通分量。
- 与湖泊连接数量。
- 断面自交数量。
- 非法负宽度／负深度数量。
- 切割体积。
- 沉积体积。
- 河床最大变化。
- 未解析水面单元数量。

### 水动力正确性

至少报告：

- CFL 最大值。
- 负水深次数。
- 非有限状态次数。
- 时间步拒绝次数。
- 输出帧与内部积分的质量差。
- 峰值流量和到达时间。
- 断面水面单调性或回水关系。

### 来源和可重复性

至少报告：

- terrain source SHA-256。
- rainfall source SHA-256。
- 模型版本。
- 参数哈希。
- 随机种子。
- solver 版本。
- 网格和边界摘要。
- 输出包 SHA-256。

---

## 八、状态和命名规范

推荐使用以下状态，而不是模糊的“完成”：

- `pending_provenance`：来源尚未完整登记。
- `diagnostic_topology`：只有排水拓扑。
- `diagnostic_runoff`：有产流但未路由到动态河道。
- `candidate_channel_geometry`：有候选中心线或河床几何。
- `hydraulic_unresolved`：水动力存在未解析单元或失败前缀。
- `boundary_unverified`：边界或自然出口未验证。
- `lake_preserved`：内流盆地保留为湖泊。
- `accepted_bounded_result`：在明确有界域内通过了验收。
- `accepted_natural_outlet_result`：自然出口有来源和验证证据。
- `publishable_river_network`：仅在所有发布门槛通过后使用。

禁止把以下对象称为最终河流：

- 只有 graph edges 的线。
- 只在床面节点上绘制的箭头。
- 由 `sqrt(Q)` 产生的显示宽度。
- 未经过水量守恒的水面插值。
- 未验证自然出口的域外路径。
- 只在 unknown 地形前推断出的下游河道。
- 单个暴雨场景的静态截图。

---

## 九、给 GPT 的实现提示词

请按以下方式实现，不要一次性重写整个工程：

```text
你正在实现 Terragenesis / Terraindiffusion 的完整河网算法。请先阅读现有 terrain_pipeline、tests 和 web-preview 数据契约，列出当前已实现、部分实现和缺失的能力。不要凭字段名猜测水动力单位，也不要把诊断排水拓扑命名为最终河流。

实现原则：
1. 保留现有公开接口，新增接口必须向后兼容。
2. 将地形来源、产流、receiver graph、湖泊、河道水动力、泥沙、河床几何、多分辨率和渲染分层。
3. 原生网格水量是基准；AMR 是局部高精度对照；uniform 是失败对照。
4. 内部可用短子步，保存帧必须携带真实 time_seconds 和字段时间语义。
5. 自由出流单向出域，禁止未经声明的倒灌。
6. 内流盆地保留为湖泊；unknown 地形不向外追踪。
7. 所有水量、泥沙、边界通量、切割和沉积都必须有账本。
8. Terraindiffusion 负责地形或条件生成，不替代物理守恒求解器。
9. 每完成一个 milestone，先增加测试，再改实现，再运行测试。
10. 失败时输出明确的 failed_prefix 或 unresolved 状态，不伪造完整结果。

第一轮只做：
A. 阅读并审计现有代码；
B. 建立 TerrainGrid、BoundaryGrid、RainfallForcing、RoutingGraph 的契约；
C. 将现有 outlet_mask 扩展为带方向和类型的边界语义；
D. 保留现有 route、accumulate、rainfall_runoff、carve_channels 的兼容行为；
E. 增加平面、Y 型汇流、内流盆地、unknown 边界、自由出流和时间语义测试；
F. 输出实现报告，说明哪些仍然只是 diagnostic，不能称为最终河网。

之后按 Milestone 0 到 Milestone 8 顺序实现。每一步都要：
- 给出修改文件清单；
- 说明数据契约变化；
- 增加或更新测试；
- 运行目标测试和回归测试；
- 报告守恒误差、边界状态、未解析单元和来源哈希；
- 不删除现有失败对照；
- 不把渲染层结果反向当成水动力真值。
```

---

## 十、建议的最终输出包

最终算法不应只输出一个高度数组。建议输出一个版本化目录：

```text
river-product/
  manifest.json
  provenance.json
  terrain-grid.npz
  rainfall-forcing.npz
  hydrology-timeseries.npz
  routing-graph.npz
  lake-catalog.json
  channel-state.npz
  hydraulic-timeseries.npz
  sediment-timeseries.npz
  river-geometry.glb
  river-geometry-audit.json
  mass-balance.json
  boundary-audit.json
  resolution-comparison.json
  diagnostics.json
  review-record.json
```

`manifest.json` 至少包含：

```json
{
  "schema": "terragenesis-river-product-v1",
  "status": "diagnostic_topology",
  "terrain_source_kind": "generated_terrain",
  "terrain_source_sha256": "...",
  "rainfall_source_sha256": "...",
  "solver_recipe": "...",
  "parameter_sha256": "...",
  "time_semantics": "...",
  "boundary_semantics": "...",
  "unknown_semantics": "unknown_is_not_traced",
  "native_grid_is_volume_basis": true,
  "amr_role": "local_high_resolution_diagnostic",
  "uniform_role": "failure_control",
  "natural_outlet_verified": false,
  "publishable": false,
  "limitations": []
}
```

---

## 十一、最终判断标准

只有同时满足以下条件，才可以把结果称为“完整的基于 Terraindiffusion 的河网算法结果”：

1. 地形、降雨和边界来源完整登记。
2. 地形坐标、面积、nodata 和单位没有歧义。
3. 产流、汇流、湖泊、河道和边界都在同一时间账本中守恒。
4. receiver graph 无非法环，unknown 不被错误穿越。
5. 内流盆地被正确保留为湖泊或有明确溢流证据。
6. 自由出流不倒灌，边界流量有方向和单位。
7. 水动力内部子步稳定，输出帧时间语义明确。
8. 河床宽度和深度来自显式模型，不由渲染线宽冒充。
9. 泥沙、侵蚀和沉积有物质守恒审计。
10. AMR、原生和 uniform 结果有量化对比。
11. 河床几何无自交，入口、出口、湖泊连接和体积通过审计。
12. 所有失败、未解析和未知区域都被明确标记。
13. 前端显示层、诊断层、候选层和认证层没有混称。
14. 结果可以由固定来源、固定参数和固定种子重复生成。

在这些条件满足之前，最诚实的产品名称应是：

> **Terraindiffusion 条件地形上的诊断排水拓扑与有界河道候选系统**

而不是“最终自然河网”。
