# 基于现有算法完善整个工程的可行性评估

日期：2026-10-19。范围：**真实气候、生物群系、特殊地形、岩石构造**四个方向。
方法：三个只读探索子代理并行摸底（气候与水文驱动 / 群系与岩石材料 / 特殊地形与三维几何）+ 顶层文档对齐（`CONTEXT.md`、`Terragenesis河流地貌长期路线图.md`、`IMPLEMENTATION_STATUS.md`、`TODO.md`）。
本文只做评估与分期建议，**不改动任何源码，不改变任何既有验收状态**。

---

## 0. 结论摘要

四个方向**都不是白地**，但也都不是「照现有算法接着写就行」：

1. **瓶颈不在算法缺失，在契约层缺失**。物理侧已经有气候场、材料场、岩壁形态、洞穴实体与独立审计；缺的是把它们**接出去**的契约（气候→群系、岩性→形态、风化→侵蚀→输沙）。
2. **多处已是「实现完备但验证未完成」**，不是实现缺口。最典型：VDM 六形态与走滑断层早已实现并有测试，挂在那里的是自交/稳定性/侧壁实体/水力耦合四项**未认证**标志。
3. **工程有极强的状态纪律**（`diagnostic → candidate → bounded → validated → publishable`，各处 `*_verified=false` 标志）。任何「完善」都必须先声明边界，不能把已有能力直接升级成发布状态。
4. **改 `metric_*` 算法会改身份**。`ALGORITHM`/`SCHEMA` 常量与 `identity_sha256` 被下游证据引用，必须走版本升迁（本工程已有 A-P0 v6→v7 与 ADR 的先例），不能原地改。

分层判定：

| 层 | 含义 | 本评估中的项 |
|---|---|---|
| **A 可直接接** | 两侧都已实现，只缺一根接口 | 物理气候场 → Minecraft 群系选择 |
| **B 需先补契约** | 有底座、有资料，缺数据契约与算法 | 米制气候的纬度/迎风/辐射项；岩性—地层；特殊地形的布置规则 |
| **C 真空白** | 无实现，但方法路线已调研清楚 | 风化—侵蚀—输沙闭环；土壤/植被→生态群系 |
| **D 方向性不成立** | 与工程定下的路线冲突 | 「与真实地理数据对齐的气候/地貌」 |

---

## 1. 真实气候

### 1.1 现状（已实现且有验收）

**主线**：`terrain_pipeline/surface_rivers/metric_noise_forcing.py`
- 文件头即自陈：`"""Seeded metric climate and rain fields; synthetic physical inputs, not observations."""`
- `NoiseClimateParameters`（`:147-168`）：`climate_scale_m=240000`、`regional_scale_m=60000`、`lapse_rate_c_per_m=-0.0065`（强制 `-0.012 ≤ lapse ≤ 0`）、`weather_scale_m=12000`、`weather_detail_scale_m=3000`、`velocity_x_m_s=8`、`velocity_z_m_s=2`、`absolute_weather_step_s=900`。
- `sample_climate(seed, x_m, z_m, elevation_m=0.)`（`:180-207`）：噪波 → `thermal` / `moisture` / `continentality` 三个强度场 → 12 月气温与降水 → BIO1/BIO4/BIO12/BIO15 **由同一月序列导出**；返回里带 `semantics="synthetic_monthly_climate_targets_not_measured_weather"`。
- 短时降雨 `interval_mean_rain_mm_h`（`:217-244`）：月降水速率 × 900 秒绝对天气节点间线性插值，按月边界精确切分；工作预算 4096 节点。
- 网格出口 `grid_rainfall`（`:247-278`）：2×2 等面积中点近似，输出冻结契约 `RainfallForcing`（`temporal_semantics="interval_average"`、`spatial_semantics="cell_average"`、`missing_policy="reject"`）。元数据明写 `"monthly_target_is_not_realized_annual_forcing": True`。
- 定点阵暴雨 `interval_seasonal_storm_rain_mm`（`:64`）+ `StormParameters`（`:19-43`），整数哈希保证与采样窗口无关。

**旧路线（仍在用）**：`diffusion/geography_v5.py`、`geography_physical.py`、`geography_v2/3/4.py` → 五通道条件（高程米、气温°C、气温 SD×100、年降水 mm、降水 CV×100）。`geography.py:27` 注释 `# Z acts as latitude;`，`:54` `latitude = 22 * np.sin(z / 96)`。
**独立物理生成路径**：`diffusion/physical_config.py`（`PhysicalGenerationConfig`，`geography_physical_v1`，海平面基准 0 m，条件格 7680 m = 32×8×30 m）+ `tools/verify_physical_generation.py`。

**消费端**：`terrain_pipeline/rainfall_runoff.py`（`rainfall-runoff-v1`，`RunoffParameters` 明确自陈「spatially uniform illustrative parameters, not a calibrated catchment」）；`regional_surface_forcing.py`、`hydrology_seasonal.py`（唯一「气候化」的蒸散：`pet = pet_base + pet_temperature * max(T,0)`，注释直言 `"Explicit illustrative temperature-index PET; no observed radiation/humidity."`）。

**验收状态**：`docs/td-noise-climate-reference-20261011.md` 记录了完整的独立留出流程——六原始包、六评价报告、十二派生月气候包全部冷核验一致；**12 窗口 10 通过 / 2 拒绝**，20 项聚焦测试通过；`noise-water-cycle-20261011-02` 的 900 秒水账独立积分残差 **0**，native 最大差 1.73e-18 m³。真实资料（WorldClim2.1 BIO 四通道、808,053 共同有效像元）只作**范围与联合统计参照**，从不进入生成链。

### 1.2 缺口清单

| 项 | 状态 | 证据 |
|---|---|---|
| 大尺度空间梯度 | 有（240 km / 60 km 噪波湿润度） | `metric_noise_forcing.py:148-149,187-193` |
| 季节 | 有（12 月季节相位） | `:194-201` |
| 大陆性 | 有（但**只用于温度振幅**，不进降水） | `:190,192` |
| **纬度** | **无**（`_coordinates` 只有 x/z 绝对米制，无纬度概念） | `:171-177` |
| **海拔对降水** | **无**（`elevation_m` 只进温度递减，无迎风抬升、无背风减湿） | `:191,193` |
| **迎风/背风湿效应** | 仅旧路线有（`geography_v5.py:63-66` 的 `windward/lee`），米制主线没有 | 对比 `metric_noise_forcing.py` 全文 |
| **湿度（相对湿度）** | 仅 1 处注释 | `hydrology_seasonal.py:73` |
| **风场 / 辐射 / 日照 / 雪线 / 气候分区** | **0 处实现**（专项 rg 无命中） | — |
| 上游递减率通道 | 被本项目在边界丢弃 | `diffusion/backend.py:70-71` 只取 `climate[:4]` |

### 1.3 可行性判断

- 「真实气候」必须分两种解读：
  - **(a) 物理上自洽**（有纬度带、有迎风背风、有海陆性、有干湿季、有辐射季节）。**可行且改动局部**：纬度项需要先定一个「绝对 Z → 纬度」的全局约定（旧路线用 `22*sin(z/96)` 把 conditioning 格当纬度，米制主线不能沿用）；迎风抬升可复用 `geography_physical.py:50-53` 的差值代理思路；辐射可由纬度+季节解析算出，**不需要外部数据**。改动集中在 `metric_noise_forcing.py` 一个文件 + 其测试，有现成底座。
  - **(b) 与真实地理数据对齐**。**方向性不成立**：`CONTEXT.md` 已把「实测地形 vs 扩散生成山地」定为术语分界，`IMPLEMENTATION_STATUS.md:57` 明确「未重新训练模型，尚未实现完整气候动力学」。WorldClim 只作参照是**刻意设计**，不是缺口。
- **风险（必须记住）**：改 `sample_climate` 会改 `NoiseClimateParameters.identity_sha256`（schema `metric-noise-climate-v1`）→ 既有 v7 河网证据、12 项气候检查、holdout 结论的来源身份全部串联变化。**必须起 v2 schema，保留 v1 可复现**（本工程已有先例：`metric-vdm-forms-v1/v2`）。

---

## 2. 生物群系

### 2.1 现状

**物理侧**：`terrain_pipeline/metric_region.py`
- `RegionRecipe`（`:11-31`），`METRIC_30M_RECIPE_V1`（`:60-64`）：趋势 120/360 m、局部 60/180 m、海岸 90/270 m sigma/radius。
- 权重公式（`:128-129`）：`np.stack(((1-high)*(1-rugged), (1-high)*rugged, high*(1-rugged), high*rugged))` → 顺序 **plain / hill / plateau / mountain** 四类**连续隶属度**；`dominant_type = argmax`（`:140`），只是一个 0–3 标签。
- **输入只有高程 + 相对起伏 / 坡度 / 凸出度，不含气候、土壤、植被、岩性。**
- 存储 `metric_region_storage.py`（`prepare_metric_region` / `load_metric_region` 只校验不重算）。

**Minecraft 侧**：
- `core/Landform.java:3-9`：`INSELBERG("平原孤山") RIFT("裂谷") KARST("桂林喀斯特") PILLARS("张家界石柱群")`。
- `core/Landscape.java:5-35`：`Climate(temperature, rain)`，`variant()`（`:8`）返回 0/1/2/3 = 冷/旱/温/湿；KARST/PILLARS 改岩石风化系数。
- `world/SurfacePalette.java`：按密度/岩类/气候标签出方块。
- `region/MetricProcessedTerrainSource.java:22`：**`ADAPTER_CLIMATE = new Landscape.Climate(0.5, 0.5)` 硬编码**；`:131` 注释逐字 *"These four categories only select Minecraft biomes; the source contains no climate field."*
- 资源：`src/main/resources/data/remotemountains/worldgen/biome/` **16 个 json = 4 地貌 × 4 气候**；`world_preset/landforms.json` 用 `terrain_source="metric_processed_readonly_v1"`。
- `docs/metric-minecraft-consumer.md:30-38` 逐字：*"Water, cave topology, materials and climate are absent from this metric region version… Minecraft's fixed `temperate` biome variant and basic block palette are explicit adapter policy, not source climate or geology."*

**真空白**：`terrain_pipeline/` 下检索 `biome|vegetation|Köppen|koppen|landcover|ecotone|climate_class` → **0 命中**（741 个文件）。`research/` 下的命中全在第三方项目快照里。土壤类型学同样不存在。

### 2.2 可行性判断

- **第一步（A 层，低成本高收益）**：把 `sample_climate` 的 BIO1/BIO12 接到 metric 消费路径，替换 `ADAPTER_CLIMATE` 硬编码。
  两侧都已实现，缺的只是**一根接口**：快照格式带气候通道 + Java 读取。注意 `metric-minecraft-consumer.md:39-41` 已预告 *"joining multiple storage chunks and richer consumer data need a later format version"* —— 需要新 format version，不能塞进 `TGMCMT01`（该格式只接受垂直位移）。
  验收门槛应直接复用已冻结的 `variant()` 4 档语义与 16 群系资源，不新增群系定义。
- **第二步（C 层，需要新算法 + 新契约）**：土壤类型学 + 植被/生态分类。
  这一步与「风化—侵蚀」强耦合（`.scratch/terrain-framework/additional-material-needs.md:37-41` 已列出所需字段：淹水时长、地下水位、土壤排水性、植被类型，并明确 **「先支持核心水文条件，再由 Java 映射群系，不靠群系标签反推积水」**）。
- **纪律约束**：`CONTEXT.md:31-35` 已定「地貌群系 ≠ 游戏生物群系」；`research/区域数据流程.md:9` 承认「地貌归属和过渡权重目前只是标签与过渡条件」。任何新工作都要沿用这条术语分界。

---

## 3. 岩石构造

### 3.1 现状

| 模块 | 内容 | 状态 |
|---|---|---|
| `terrain_pipeline/td_material_field.py` | `td-continuous-global-value-noise-v1`，连续标量：可蚀性 `[0.25,1]`、可蚀层厚 `[0.25,4] m`、弱面偏好 `[0.8,1.2]`、相关长度 900 m、固体密度 2650、源/沉积孔隙率 0.10/0.35 | 已实现；**自陈 `synthetic_material: True, measured_lithology: False`** |
| `td_fine_bed_material.py` | `td-fine-bed-material-v1`，切填材料账 | 已实现；`hydraulic_solved/natural_outlet_certified/publish_ready/material_ledger_certified` **全 false** |
| `surface_rivers/metric_sediment.py` | `MaterialParameters`：**二分材料**（松散沉积物 / 基岩），临界剪切 1 vs 5 Pa，可蚀性 1e-6 vs 1e-8 | 已实现 |
| `surface_rivers/metric_upstream_sediment.py` | `hardness∈[0,1]` → `rock_tau=rockcrit*(1+4h)`、`rock_K=rockK*(1-h)²` | 已实现；文档明说「虚拟材料场，不是实测岩性」 |
| `metric_vdm.py` | `cliff-skeleton-v1`，`CliffRecipe(center_xz_m, outward_xz, height_m, half_length_m, half_depth_m, wall_half_width_m, end_fade_m, angle_degrees∈[60,90], lean∈{-1,1})` | 已实现 |
| `metric_vdm_forms.py` | `coherent-cliff-forms-v1/v2`，**六形态** | 已实现 + 212 行测试 + 真实 TD gallery |
| `metric_vdm_fault.py` / `_v2.py` | 竖直平面 + 水平走滑，带边溯源 | 已实现；自交/稳定性/侧壁/封闭实体未认证 |
| `hybrid_cave_geometry.py` + `tools/hybrid_cave_saved_audit.py` | 洞道实体 + 684 行**独立冷读审计**（绕数判内外、独立线段-三角求交、Boolean 对称差、端口位移必须为 0、`manifold3d==3.5.4`） | 已实现，seed17 实际 TD 包**审计通过** |
| `hybrid_surface_composition_v3.py` | 续接 checkpoint 的有界 portal collar | 有实现；`two_sided_complete_port_verified=False` |
| `underground_channel.py` | 栅格级连通诊断 | `status="diagnostic_not_publishable"`，**不生成三维实体** |
| `metric_region.py` | 四类地貌连续权重 | 见 §2 |

**真空白**：岩性分类、地层分层（strata/lithology）—— 全仓无实现，只有形参命名与文档提案。
**仅文档设想**：`research/区域风化与流域侵蚀资料.md` 给出的六职责分离（`RegionWeatheringMask` / `WatershedGraph` / `RunoffAccumulator` / `ChannelCorridor` / `FluvialErosion` / `SedimentTransport` / `OutletBoundary`），并已核实 6 篇文献 + 4 个 Landlab 组件（ExponentialWeatherer、FlowAccumulator、Priority-Flood、SPACE、lateral erosion、FastScape）。

### 3.2 可行性判断

- **岩壁/断层（B 层，改动小）**：算法齐备、测试齐备，**缺的是验证不是实现**。可用 0.8.0「峡谷补充岩壁」的现成模式（版本化配方 + 两个独立预设 + 不动旧世界配方）扩展配置，把六形态从 gallery 演示推进到「按规则布置」。
- **岩性—地层（B 层，中等新功能）**：需要一个离散类型 + 层序契约（岩性、厚度、倾斜、年代），并接到 VDM 形态（`layered_ledge` / `stepped_wall` 已预留层状语义）与断层。断层当前是竖直平面走滑、**不切割地层**——要支持地层错断，需要新契约。底座充分（`CliffRecipe` 的 `angle`/`lean`、材料场的孔隙率/密度已在体积账中使用）。
- **风化—侵蚀—输沙闭环（C 层，最大真空白、最长链条）**：工程已有 `metric_morphology_coupling.py`（双库存耦合）、`surface_rivers/transport.py`、`delta.py`、Exner 类床变更新，但**没有「风化把基岩转为风化物 → 坡面搬运 → 流域约束侵蚀 → 向河口输出」的闭环**。方法路线与文献已调研清楚，属于「可以照着做但工程量大」。
  硬约束（资料文档已写死）：风化不得让物质不经搬运消失；变系数坡面输运不能写成 `D∇²h` 漏掉系数梯度项；蒙版边缘必须有明确通量边界，不能裁剪后宣称守恒。

---

## 4. 特殊地形

### 4.1 现状

- **六形态**（`metric_vdm_forms.py:19-20`）：`layered_ledge`（层状岩棚）、`undercut_alcove`（凹蚀岩厦）、`fluted_wall`（纵向槽脊）、`stepped_wall`（阶梯崖壁）、`curved_escarpment`（弯曲崖带）、`massive_overhang`（厚顶悬挑）。
  统一包络 + 形态分支配方 + 附加控制项（`surface_curvature_m`、`end_elevation_difference_m`、`extension_direction_degrees`）；硬约束 `_check_form_scale`：`wavelength_m ≥ 4×格距`、`amplitude ≤ min(0.25·height, 0.5·wall_half_width)`。
  验收：`tests/test_metric_vdm_forms.py` 212 行 + `tools/prepare_vdm_forms_gallery.py` 真实 TD 六形态对照导出。报告自陈 `self_intersection_verified=False, stability_verified=False, hydraulic_ready=False, natural_outlet_verified=False`。
  > **健壮性隐患（新发现）**：`massive_overhang` 在 `_shape` 里是 `else` 兜底分支（`:119-122`），任何新增 `kind` 都会静默落进这个分支。新增形态前应先加显式 `elif` + `raise`。
- **明确能力边界**（`research/VDM岩壁形态资料-20261003.md:21`）：VDM **不会自动增加表面拓扑**；穿孔、独立掉块、贯通洞穴、真正悬空实体必须交给可改拓扑的体积/密度表示。
- **洞穴实体**：`hybrid_cave_geometry.py`（Hermite 路线 sin² 埋深、`void_witnesses` 射线验证真实地表开口、有符号体积平衡 < 1e-7、覆岩 < 0.5 m 拒绝、资源预算 64 MiB / 1 GiB / 300k 格）+ 独立冷读审计，**已有 seed17 实际 TD 包验收**。
- **前端**：`?workspace=fault` 已接入（`TODO.md:276`）；VDM/三维几何纯 IO 审查入口 `td-vdm-geometry-io-review-v1` 已交付（`TODO.md:225`）。
- `CONTEXT.md:105` 记录了用户提出的 `Nucleation`（SDF / 体素 / schematic 引擎）作为**后续局部三维几何候选**，本轮只核查官方文档，**未安装、未接入**。

### 4.2 可行性判断

- **这是四个方向里最可行的一个**。缺的不是形态生成，而是**布置与选择**：现在 canyon 预设是「预设面片」，`IMPLEMENTATION_STATUS.md:85` 明说「沿岩层/山嘴分裂的自然崖带、全域峡谷识别、真实崖顶汇水路径仍待完成」。
- 可直接接的输入**都已存在**：`metric_region` 的四类连续权重（地形背景）、`td_material_field` 的硬度/可蚀性、`metric_upstream_sediment` 的 `hardness`、河网与坡度。缺的是一条**从这些场派生「哪里该放哪种形态、什么朝向、多大尺度」的规则**，并输出到 `CliffRecipe`/`FormRecipe`。
- 工作形态应与 0.8.0 一致：**新版本化配方 + 独立预设 + 不动已有世界配方 + 定向验收 + 保留失败**。
- 硬约束：任何全域宣称前，必须先解决 `self_intersection_verified` 与 `stability_verified`；真洞穴/天生桥只能以**局部案例**形式交付（`hybrid_cave_geometry` 那条路），不能由 VDM 冒充。

---

## 5. 分期建议

### P0：把已有能力接出去（低成本、可独立验收）

| # | 任务 | 依据 | 验收门槛 |
|---|---|---|---|
| 1 | 物理气候场接入 metric 消费路径，替换 `ADAPTER_CLIMATE=(0.5,0.5)` | 两侧已实现，仅缺契约 | 新 snapshot format version；Java 读取气候通道；16 群系选择可复现；旧 `TGMCMT01` 读者不受影响 |
| 2 | 米制气候补纬度 / 迎风背风 / 辐射季节项（**起 v2 schema**） | `metric_noise_forcing.py` 单文件改动 | v1 身份仍可复现；新增字段有物理单位与取值范围检查；12 项气候检查与 holdout 结论按新身份重跑并保留旧失败 |

### P1：补契约（中等规模）

| # | 任务 | 依据 | 前置 |
|---|---|---|---|
| 3 | 岩性—地层契约（离散类型 + 层序 + 倾斜），接到 VDM 形态与断层 | 六形态已预留层状语义；材料场已在体积账中使用 | 需先定「地层身份」如何进入 artifact 校验 |
| 4 | 特殊地形布置规则（从地貌权重 / 硬度 / 坡度 / 河网派生形态选择与朝向） | 输入全部已存在；canyon 预设已有先例 | 建议先加 `massive_overhang` 的显式 `elif`，修掉兜底分支隐患 |

### P2：大工程（需先立方法与失败判据）

| # | 任务 | 依据 |
|---|---|---|
| 5 | 风化—侵蚀—输沙闭环（六职责分离，自 `research/区域风化与流域侵蚀资料.md`） | 文献与方法路线已核实；工程有 Exner 类床变、双库存耦合、输沙原型 |
| 6 | 土壤 / 植被 → 生态群系（依赖 #5 的土壤与水分条件） | `.scratch/terrain-framework/additional-material-needs.md:37-41` 已列出所需字段 |

### P3：长期（路线图阶段 8–10）

7. 局部三维岩体与地表河网统一水量账本；AMR / 多分辨率；发布包
8. 跨水文域地下连接（用户已登记，`TODO.md:75`，当前仍禁止跨域）

---

## 6. 纪律与风险（动手前必读）

1. **身份纪律**：改 `metric_*` 算法/参数会改 `ALGORITHM`/`SCHEMA`/`identity_sha256`，下游证据会全部失效。必须走版本升迁 + 作废声明（A-P0 的 `verification/td-terrain-generated-rivers/CENTERLINE-V6-SUPERSEDED.md` 是范本）。
2. **状态纪律**：`validated` / `publishable` 不能因渲染好看而自动获得；各处 `*_verified=false` 标志是**有意保留**的能力边界，不是待办遗漏。
3. **术语纪律**：地貌群系 ≠ 游戏生物群系；合成气候 ≠ 实测气候；候选形态不得自动升级为主图；原始 TD 输入不可变。
4. **资料现状**（`D:\geography` 与 `.scratch/terrain-framework/material-intake-20260929.md`）：Ancey 数据集单位仍需原作者说明（公式自洽不能唯一证明单位）；凫溪仍是候选样本（184 km² 是按官方面积反选出口得到的）；120 个月气候表**不是实测径流表**；断面是 **DEM 派生估计**，缺真实中心线。这些资料**可用于研究输入，仍非整体验收依据**。
5. **工程卫生**：当前工作区有 **376 个未提交改动**（`git status --short`，分支 `main`，HEAD `fc794da`），本轮评估前即已存在。是否分段提交、如何绑定证据，需要另行决定。

---

## 7. 一句话结论

四个方向**都能做**，但正确做法不是「新增四个平行模块」，而是**分三层推进**：先把已实现的物理气候接出去（P0，可立刻验收），再补岩性—地层与地形布置两类契约（P1），最后才做风化—侵蚀与生态群系这两个需要新算法的大工程（P2）。每一步都必须沿用本工程的身份纪律与状态词表，不能把已有能力直接升级成发布状态。