# 特殊地形：资料、尺度与接入路径盘点

日期：2026-10-19。范围：用户指定的**六类 Terrain Diffusion 目前无法生成的地形**——魔鬼塔、天坑、喀斯特、张家界石柱、乌鲁鲁、魔鬼岩。

方法：四个只读探索子代理并行盘点（六类地形资料与尺度 / 地形侧局部细化与封闭洼地契约 / Minecraft 消费端接入路径 / Java 端体积—密度场消费能力）。本文**只做盘点与分层判定，不改任何源码，不改变任何既有验收状态，不提出已定方案**；方案与排期须先等用户对第 7 节三个岔路拍板。

来源纪律（全文适用）：
- 标注**「已核实」**= 机构/学术原件或本仓代码逐行核对；标注**「二手」**= 检索片段转述（多为百科/媒体），未取得机构原件；标注**「未取得」**= 本次没找到可用来源。
- 本地文件引用均为实际打开过的文件。
- 本仓已有的相关设计记录：`docs/dynamic-feedback-and-landward-plain-v1.md:48,50`、`CONTEXT.md:105`、`research/VDM岩壁形态资料-20261003.md:21`、`geography/06-岩壁悬挑与VDM/岩壁形态摘要.md:14`。

---

## 1. 六类地形的资料与尺度

### 1.1 魔鬼塔 / 火山颈柱塔（Devils Tower, WY）

| 字段 | 内容 | 等级 |
|---|---|---|
| 高度 | 相对塔基约 **264 m**（NPS 原文 867 ft） | 已核实 |
| 水平尺度 | 底径约 305 m、顶径约 84 m | 二手 |
| 岩性 | **phonolite porphyry**（响岩斑岩），非花岗岩/玄武岩 | 已核实（NPS） |
| 机制 | 柱状节理（岩浆冷却收缩破裂，120° 三向相交 → 多为六边形，柱体 3–7 边）；火山颈经**差异侵蚀**逐渐暴露 | 已核实（NPS） |
| 可编程量 | 柱体边数 3–7；**柱径 / 节理间距 / 层厚未取得来源** | — |

- NPS 明确否定了「从地下顶出来」：原文「exposed gradually through the processes of weathering and erosion」。
- 柱状节理同时是「石柱群 / 玄武岩柱」类的通用参数来源（NPS《Columnar Jointing》同页给出 3–7 边与 120° 成因）。

### 1.2 天坑（单体：小寨天坑，重庆奉节）

| 字段 | 内容 | 等级 |
|---|---|---|
| 尺寸 | 坑口最大直径 **626 m**（另有 622 m 版）、垂深 **666.2 m**（相对坑口）、坑底直径 522 m、容积约 1.19 亿 m³ | 二手（多源一致） |
| 形态 | 近直立斗壁 + 坑壁两级台地（约 300 m 深处宽 2–10 m；约 400 m 处为斜坡台地） | 台地数据未核 |
| 机制 | **塌陷型**：地下河长期溶蚀—侵蚀 → 洞顶大型崩塌至地表（央视引中国地质调查局岩溶所张远海） | 已核实 |

- **规范定义（判「是不是天坑」的尺度门槛）**：巨大容积、陡峭圈闭岩壁、井状/桶状轮廓、平面宽度与深度从 >100 m 至几百米、底部与地下河相连或可证已迁移。
- 可辨识三层结构：**近直立斗壁 → 阶地 → 坑底暗河天窗**（第三层属地下拓扑）。

### 1.3 天坑群（乐业大石围，广西）

| 字段 | 内容 | 等级 |
|---|---|---|
| 单体 | 大石围 **600 m × 420 m**、垂深 **613 m**、容积约 0.8 亿 m³、坑底原始森林 9.6 万 m² | 二手 |
| 群体 | 20 余 km² 内数十个天坑（口径 24/26/29/31 不等）；国家地质公园约 175 km² 含 26 个深 >100 m 天坑 + 30 余溶洞 | 二手 |
| 机制 | 天坑群由**同一地下河**孕育 →「一个地下河系统 = 一个天坑家族」 | 已核实（央视） |

- 群体密度 ≈ **1.2–1.6 个/km²**；单体长宽比 600:420 ≈ **1.43（非圆）**、深宽比 ≈ 1.02。**「天坑」不是单一几何模板**（小寨近圆、大石围椭球状）。
- 布局层最有用的结论：天坑沿地下河**串珠状**排列，而非随机散布。

### 1.4 喀斯特峰林—峰丛与溶洞（桂林/阳朔、一般岩溶）

| 字段 | 内容 | 等级 |
|---|---|---|
| 尺度 | 峰体相对高度从数十米到二百余米（**未取得统一值**）；遗产地核心区 971.25 km² | 二手 |
| 机制 | 溶蚀（碳酸盐岩化学溶解）为主 + 流水侵蚀 + 重力崩塌；中国学者 300 年前已分峰丛/峰林/孤峰 | 已核实（学术文献） |
| 形态分类 | **塔状（tower karst，近直立，桂林）vs 锥状（cone karst/峰丛，施秉）** | 二手 |

- **单体峰体基座直径、峰间距、壁坡度分布均未取得来源。**
- 峰林区**普遍伴生溶洞与地下河**（荔波、芙蓉洞、乐业同属遗产地要素）→ 峰林图层必须与地下洞穴图层同时规划。
- 六类中唯一「表面形态最平凡、地下拓扑最复杂」的一类。

### 1.5 张家界石柱群（湖南武陵源石英砂岩峰林）

| 字段 | 内容 | 等级 |
|---|---|---|
| 群体 | **3000+ 座石柱**；景区 369 km²；遗产地约 26,400 ha | 已核实 |
| 单体 | 峰柱高几十米至 400 m；超 200 m 的千余座；乾坤柱约 **150 m**、金鞭岩约 350 m | 二手 |
| 机制 | 泥盆纪**石英砂岩**经流水侵蚀、重力崩塌、风化形成；被国际地质学界命名为独立地貌类型 | 已核实 |
| 附加结构 | 顶部约 30 m 厚铁质石英砂岩「铁帽」 | 二手 |

- **必须纠正的分类错误**：英媒常写「surreal karst formations」，实际是**石英砂岩、物理侵蚀/崩塌为主，非碳酸盐岩溶蚀** → 归类时**不要放进岩溶通道**。
- 有清晰演化序列（方山→峰墙→峰林→残林），可作成熟度参数；**单柱底径 / 柱间距 / 垂直节理间距未取得来源**。
- 六类中最典型「纯高度场可表达」。

### 1.6 乌鲁鲁 / 巨型孤山（Uluru；inselberg/bornhardt）

| 字段 | 内容 | 等级 |
|---|---|---|
| 尺寸 | 相对平原高 **348 m**（另有 335 m 版，**两版冲突**）；长约 3.6 km、基围周长 9–9.4 km | 二手 |
| 岩性 | 长石砂岩 arkose | 二手 |
| 机制 | **野火致岩石剥落（fire-induced rock spalling）**沿周边形成**外扩坡（flared slope）**：Nature Communications 2021 | 已核实 |
| 同伴 | Kata Tjuta 由 **36 个圆顶岩体**组成，最高点相对平原约 546 m | 二手 |

- **关键形态学**：Uluru 不是光滑半圆丘，而是**陡壁 + 底部外扩（负坡度/悬挑）**——「悬挑」正是本仓明确记录为 **VDM 改不动**的形态（见 §2）。
- inselberg 同类高度量级 300–600 m、长宽比 1–5（Spitzkoppe、Stone Mountain、Sugarloaf 等）。
- **官方（Parks Australia）高度与周长原文未取得**，335/348 冲突待消除；flared slope 外扩幅度未取得。

### 1.7 魔鬼岩 / 花岗岩球状风化石蛋堆（Karlu Karlu / Devils Marbles）

| 字段 | 内容 | 等级 |
|---|---|---|
| 单体 | 巨石**高至 6 m**（北领地官方旅游页） | 已核实 |
| 机制 | 北领地官方页仅定性「weathering and erosion」；**corestone/tor 两阶段机制未取得权威来源** | 部分 |
| 通用过程 | NPS City of Rocks 页：weathering / mass wasting / erosion，节理垂直最大主应力、切割 + 块体分离 | 已核实（非本地点） |

- **信息最缺**：单体直径、堆叠数量、群间距**全部未取得**。
- 几何本质 = **互不连接的独立块体 + 块间空隙 + 可悬空叠置** → 单值高度场在定义上无法表达。

### 1.8 跨类尺度分档

| 档 | 类别 |
|---|---|
| 米级–数十米 | 魔鬼岩石蛋（单体 ≤6 m）；张家界单柱；喀斯特孤峰基座 |
| 数百米 | 小寨天坑（626×666 m）；大石围（600×420×613 m）；魔鬼塔（底径约 305 m） |
| 公里级 | 乌鲁鲁（长 3.6 km）；喀斯特峰林遗产地（971 km²）；乐业天坑群（20–175 km²）；张家界（369 km² / 26,400 ha） |

---

## 2. 可表达性分层（决定用高度场/VDM 还是体积）

判据（本仓既有记录，非本次新立）：`research/VDM岩壁形态资料-20261003.md:21`——**VDM 只移动已有顶点，不增加表面拓扑**；穿孔、分离岩块、贯通洞穴必须交给可改拓扑的体积/密度表示。

### L0：纯位移 / 高度场（含 VDM 竖直位移）即可表达

都是「凸出的、实心的、单值表面」：

1. **魔鬼塔**——实心柱塔，无穿孔。
2. **乌鲁鲁 / inselberg 主体**——实心孤山 + 陡壁（**底部 flared slope 悬挑属边缘情形，落 L1**）。
3. **张家界石柱群**——柱体单值，柱间为坳谷。
4. **喀斯特峰林/峰丛**——峰体为凸出单值面。

### L1：必须体积 / SDF / 体素（新增拓扑）

5. **天坑—竖井**——凹陷本身勉强可用高度场，但**坑底暗河天窗、侧壁溶洞开口、与地缝的连通**是内部连通空腔。
6. **喀斯特溶洞 / 天生桥 / 天窗**——地下连通洞穴系统与**穿孔**（乐业布柳河仙人桥跨度 177.14 m）。
7. **魔鬼岩石蛋堆**——独立块体 + 块间空隙 + 悬空叠置，定义上不可用单值高度场表达。
8. **悬挑类（Uluru flared slope、岩壁 alcove）**——与 5–7 同类。

本仓已有对接点：`CONTEXT.md:105` 已把 **Nucleation**（SDF/三维标量场/体素构造/schematic 导出）登记为**后续局部三维几何与消费适配候选**，只核查过官方文档、未安装未接入；`docs/dynamic-feedback-and-landward-plain-v1.md:48` 把「Valley overhangs, enclosed valleys, and underground channels」归入同一阶段，理由是它们**改变域图并要求显式的地表/地下边界契约**。

---

## 3. 地形侧接入路径（Python）与硬约束

### 3.1 局部细化：现实上限约 250 m × 250 m @ 1 m

| 约束 | 值 | 位置 |
|---|---|---|
| 1 m 基床单元上限 | 62,500 | `terrain_pipeline/single_domain_fine_geometry.py:18` |
| 原生单元上限 | 250,000 | 同上 `:17` |
| 自适应几何单元上限 | 65,536 | `terrain_pipeline/surface_adaptive_io.py:41` |
| 自适应字节/墙钟预算 | 256 MiB / 1800 s | 同上 `:466`、`:17` |
| VDM chart 单元上限 | 250,000 | `terrain_pipeline/mountain_source_adapter.py:17` |

- 「2 km × 2 km 窗口细化到 1 m」**走不通**：4,000,000 单元 = `build_fine_geometry` 上限的 64 倍；必须多窗口拼接。
- 1 m 基床来自 `single_domain_fine_geometry.build_fine_geometry(hierarchy, native_window=…)`（`:244-260`），是**对 30 m TD 的双线性细化**（自陈 `fine_detail_semantics="bilinear source landform plus declared artificial channels; no new Terrain Diffusion detail"`），**不是新采样的 1 m 地形**。
- 缺两件薄适配：①以米为单位、把任意 xz 山顶换算成 `native_window` 整数索引的**窗口选择器**（现只存在于 `:253-254` 的调用方约定）；②把 1 m 床转成 chart + `protected_mask` + `source_identity` 的**瘦适配器**。

### 3.2 VDM chart 的形态门槛

| 事实 | 位置 |
|---|---|
| chart 是规则矩形格点，允许旋转、**不要求轴对齐、不要求 30 m** | `terrain_pipeline/metric_vdm.py:98-121`；`tests/test_metric_vdm.py:13-25` |
| 位移只有**两个自由度**（外法向 + 竖直） | `metric_vdm.py:117-121` |
| active 区**不得触碰 chart 四边**，必须留 collar | `metric_vdm.py:108-109` |
| validate 强制**四边位移严格为 0** | `metric_vdm.py:183-185` |
| 最小波长 ≥ **4 × 相邻最大格距** | `metric_vdm_forms.py:75` |
| 六形态白名单（`layered_ledge/undercut_alcove/fluted_wall/stepped_wall/curved_escarpment/massive_overhang`） | `metric_vdm_forms.py:19-20` |
| **`massive_overhang` 是 `_shape` 的 `else` 兜底分支** | `metric_vdm_forms.py:119-122` |

**直接后果**：
- **无法绕塔体/天坑口闭合成环**：四边必须回归原床、且没有「相邻 chart 领圈一致」的校验 → 多块拼接会各自摊平。要做闭合环必须新增 chart 类型或补自交检查（`self_intersection_verified` 现为 False）。
- **30 m chart 会把石柱尺度打回**：最小波长 120 m；魔鬼塔/张家界石柱/石蛋需要 **1 m 级 chart**（最小波长 4 m）才过形态尺度门。
- 1 m 床喂进 `build_channel_vdm` 必须自带 `_triangles` 的规则 (rows−1)×(cols−1) 双三角 pattern（`terrain_pipeline/td_channel_vdm.py:79-80` 强制逐字节相同）。
- **新增形态 kind 前必须先给 `_shape` 加显式 `elif` + `raise`**，否则新 kind 会**静默**落进兜底分支并产出成功结果。

### 3.3 封闭洼地：天坑会撞上的四道契约

| 契约 | 事实 | 位置 |
|---|---|---|
| 显式出口 | 无显式 outlet 直接 `raise`；填洼产物只是 `routing_height`，原输入不变 | `surface_rivers/drainage.py:26-27`；`contracts.py:44` |
| 未声明内陆汇 | 平坦底在真实 D8 里 receiver = −1 → `unexpected_sink` → 拒绝原因 `actual_d8_has_unplanned_interior_sinks`；**不偷偷填平** | `hydrology_detail.py:98,347,383-384` |
| 填深预算 | 默认 `max_fill_depth_m = 4.0`；超限即 `unresolved_fill_budget` | `surface_rivers/metric_bounded_confluence.py:90,211-213` |
| 内流蓄水 | `closed` 是合法边界 kind，但**通量恒 0** → 水位只升 → 触 `capacity_event` 终止 | `surface_rivers/metric_natural_lakes.py:21,225-237,422-427` |

- 天坑的填到高度是**坑缘鞍点**，落差几十米 ≫ 4 m → 走浅水/细网格路径必然被 `unresolved_fill_budget` 挡下；走 `hydrology_detail` 则被判未声明内陆汇。
- **同一块平地在两套路由里行为不一致**：`hydrology_detail` 视平坦为未解决汇，而 `td_basin_hierarchy._flat_receivers:25-61` 会给平坦台面人为指定 receiver 使其 D4 非上升 → 层级/容量侧「看起来可路由」。这是天坑**必须显式声明**的根因。
- 让它合法通过需要补：工程终点声明（`open_boundary_mask` `td_basin_source.py:17-38` 或 `engineering_open_boundary_cell_ids`，并登记进 `plan["domains"][*]["terminal_indices"]`）、显式湖泊域记录（`seed_cell_ids`/`owner_grid`/`max_stage_m`/`support_cell_ids`/`internal_faces`/`boundary_faces`/`boundary_kinds`/`boundary_crest_m`/`unresolved_stage_limit_m`）、以及**一条内流耗损契约**（现有唯一可借鉴：`td_basin_storage.py:12-13` 的 `surface_evaporation_mm_h` 与 `face_conductance_m_s`）。
- 纪律原文：`hydrology_detail.py:98`「Flats are unresolved sinks, never secretly priority-flooded or routed」；`research/地形算法与数学方法调研.md:82`「不能把设计湖泊、喀斯特洼地和天坑全部填掉」。

### 3.4 体积/闭合实体：本仓已有先例

- `terrain_pipeline/hybrid_cave_geometry.py` = **局部岩石布尔 + 多 chart VDM + 独立冷读审计**（`POLICY` `:18-30`，参数 `rock_spacing_m ∈ [0.175, 2]`、`stations 9..33`、`MAX_GRID = 300,000`，`:35-50`）。
- 但它的产物状态只到 **`candidate`**，且 `independent_audit_passed` / `hydraulic_ready` / `full_network_verified` **全为 False**（`:529,544-545`）——即「体积路线有现成骨架，成才路径尚未走通」。

---

## 4. Minecraft 消费端接入路径

### 4.1 快照契约（`TGMCMT01` v1）逐字节锁定

| 门禁 | 位置 |
|---|---|
| `MAGIC = b"TGMCMT01"`、`VERSION = 1`、`MAX_SAMPLES = 16_000_000` | `terrain_pipeline/minecraft_export.py:15-17` |
| 拒绝水面 / 拒绝非垂直位移 | 同上 `:40-43` |
| 载荷 = magic(8) + version/seed(12) + identity(64) + contentId(64) + 固定段(40+24) + **每样本 9 字节**（float64 高程 + uint8 标签） | 同上 `:57-66` |
| Java 侧尺寸**精确等式**断言 | `region/MetricProcessedTerrainSource.java:74-75` |
| Java 侧版本/种子硬校验 | 同上 `:45-47` |
| 标签必须 **0..3** | 同上 `:100-104` |

**结论：米制通道只有「垂直高程 + 4 档地貌标签」两个通道**；任何新通道（洞穴/悬挑/材料/水/气候）**必须同时改 Python 与 Java 的 MAGIC/VERSION**，并起新 format version（`docs/metric-minecraft-consumer.md:39-41` 已预告）。

### 4.2 新增地貌标签会打破的 11 处冻结物

1. `core/Landform.java:3-5` 枚举（序数被下游索引）
2. `core/Landscape.java:20` 的 4 元素 `shapes` 数组
3. `world/TerrainBiomeSource.java:20,34` 的「16 = 4 地貌 × 4 气候」断言与 `ordinal*4+variant` 映射
4. `world/RemoteGenerator.java:56` 同一断言
5. `region/MetricProcessedTerrainSource.java:100-104` 的 0..3 拒绝
6. 16 个 biome json + 其生成器 `tools/create_resources.py:19,26-31,94-95`
7. `terrain_pipeline/metric_region_storage.py:34-37` 的 `(…,4)` 权重形状与 `labels>3` 校验
8. `core/Landscape.java:7-9` `variant()` 四档语义（文档已定「不新增群系定义」）
9. 已发布世界的 `diffusion_identity`（`world/RemoteGenerator.java:62` 不符即 `IllegalStateException`）
10. `region/RegionLandformLayout.java:54-56` 对 `Landform.values().length` 取模
11. 测试锚点 `src/test/java/com/remotemountains/region/MetricProcessedVerification.java:22`

### 4.3 纯 VDM 形态的最小接入清单（照抄 0.8.0 canyon 范本，**不动 TGMCMT01**）

canyon 先例：新增包 → 接配方 → 注册模式（三处）→ 客户端枚举 → 独立预设 json → 语言键 → 验证工具 → 模式契约测试。要点：

1. **Java 形态类**：实现 `vdm/SurfaceModifier.java:4-6` 的 `Displacement apply(double,double,Displacement)`，参考 `canyon/CanyonCliffModifier.java:74-86`。
2. **接配方**：`vdm/GeneratedVdmSource.java:41-45` 加新 recipe 分支（`new VdmBuilder(base, modifier, 2, 64)`），末尾 `else throw`。
3. **注册模式三处（缺一即抛）**：`core/TerrainModeRegistry.java:18-27` `SELECTABLE`、`:28-35` `LEGACY_RECIPES`、`:81-97` `requireNonRegionPair` 的 `switch`。
4. **客户端枚举**：`client/LandformMode.java:11-14`。
5. **独立预设 json**：`world_preset/<name>.json`（模板 `world_preset/canyon.json:3-28`）。
6. **语言键**：`tools/create_resources.py:63-64,77-78` → `assets/remotemountains/lang/{en_us,zh_cn}.json`。
7. **验证**：`tools/verify_world_presets.py:24,34-37,40,56-58,93`、`world/VerificationProbe.java:23`、新写 `*WorldVerification`（照 `world/CanyonWorldVerification.java:19,31,39,41`）、`TerrainModeRegistryVerification.java:6-7`。
8. **保持不动**：旧世界配方 json 与旧模式条目原样保留（「新增独立预设、不改已有配方」）。

### 4.4 米制路径的既有能力上限（**目标若含「进游戏」，这些必须先改**）

| 缺什么 | 证据 |
|---|---|
| **无体积/密度场** | `MetricProcessedTerrainSource.sample:130-134` 只返回一个高程，且用**三参**构造 `Terrain.Column` → `density == null` |
| **实心柱填充** | `world/RemoteGenerator.java:104-107` 每列 `for(y=minY..top)` 连续填实 → **孤立塔状体、石柱间空缝无法表达** |
| **无洞穴** | `core/Terrain.java:116-119` 对米制/区域源**提前 return**，`core/CaveModel.java:2-15` 的真实实现（噪波隧道 + KARST 洞厅）永不执行 |
| **无材料/方块类型** | `world/SurfacePalette.java:8-23` 米制分支硬编码（顶面草、下 3 格土、其余石/深板岩），**完全不读 `Landform`** |
| **无水** | 导出侧拒绝含水（`minecraft_export.py:40-41`），`sample()` water 固定 `NaN` |
| **无气候** | `MetricProcessedTerrainSource.java:22` `ADAPTER_CLIMATE = (0.5, 0.5)` 硬编码 |

---

## 5. Java 端能否吃体积/密度场（七问结论）

1. **位移本就是三自由度**（`vdm/Displacement.java:3-4`：`dx,dy,dz`；`VdmBuilder` 初始只给 y）。
2. **仓库里已经有一套体积表示**：`VectorDisplacementMap`（参考平面三通道位移）→ `VdmVoxelizer` 光栅化 → **`DensityColumn`（逐列带符号交叉表，多重交叉即支持悬挑/缝隙/孤立体；空表直接抛 `"VDM mesh has a coverage hole"`）**。`GeneratedVdmSource.sample:57-61` 已把它塞进 `Terrain.Column` 第 4 字段。**缺的不是 SDF 能力，是米制源头吐不出非垂直网格 + 快照格式不带这个通道。**
3. `DensityColumn.solid(y)` **不是**「只能查 y」的能力上限：完整 3D = `densityOf(x,z).solid(y)`，`(x,z)` 由「取到哪一列」决定；`Terrain.solid(int x,int y,int z,Column)` 的 `column` 参数就是这个职责。分辨率 = 每世界方块 1 列，y 连续无量化。
4. **`CaveModel` 技术上可在米制世界启用，但不可接受**：它没有身份契约，同 `diffusion_identity` 会生成不同方块；且米制世界里 `local()/localHeight()` 是恒等函数（`core/TerrainScale.java:19-29`）→ 噪波以米制世界坐标取值，形态与 legacy 不同；还会与 vanilla carver（群系 json 已声明 `cave/cave_extra_underground/canyon`）叠加。
5. **Java 侧没有任何引擎级 SDF / DensityFunction / NoiseRouter / NoiseChunk / ChunkStatus / Aquifer / OreVein 使用**：唯一引擎密度包引用是 `RemoteGenerator.java:18` 的 `SamplerContext`（只用于 debug 签名）。自研体素资产 = `DensityColumn`/`VdmVoxelizer` + `erosion3d.SedimentLedger`（体素粒数账，非可查询场）。
6. **构建**：`build.gradle` — MC `26.3`、Fabric Loom `1.18.2`、fabric-loader `0.19.5`、fabric-api `0.161.0+26.3`，**无第三方地形库**。
7. **插入点已确定**：`core/Terrain.java:116-119` 的早退分支 + `world/SurfacePalette.java:8-23` 的米制硬编码分支，**不需要动配方注册表**；但快照必须带新通道（新 format version）。

---

## 6. 资料缺口（本地 + 外部）

1. 六类目标地形在本地**几乎零专门资料**；最近邻 `geography/06-岩壁悬挑与VDM/` 只覆盖岩壁六形态，与本文六类**无一重叠**。
2. 可复用但**不等于本体**的本地条目（引用时须标「非本类数据」）：Worley 噪声→石柱群（`geography/07-程序化地形生成与扩散模型/基础地形算法实验课/lessons/08_worley.py:24`、`src/terrain_noise.py:314`，无尺度数值）；Minecraft `caves/pillars` 密度函数（只有柱密度/柱粗细三个旋钮）；「fields of hoodoos」类工具能力声明。
3. **必须新收集的硬数据**：
   - 魔鬼塔：柱径 / 节理间距 / 层厚（官方）
   - 小寨、大石围：机构级核定口径·深·容积
   - 喀斯特峰林：单体基座直径、峰间距、壁坡度分布
   - 张家界：单柱底径、柱间距、垂直节理间距、高宽比分布
   - 乌鲁鲁：Parks Australia 原文（消除 335 vs 348 冲突）、flared slope 外扩幅度
   - 魔鬼岩：NT 政府 Karlu Karlu 管理计划（单体直径/堆叠/群密度）、corestone-tor 权威来源
4. 设计意图侧书签（可直接引用、**勿当数据**）：`docs/dynamic-feedback-and-landward-plain-v1.md:50` 的「四族地貌各需显式 height-scale / slope / roughness / drainage / material mask 契约」——**本文六类与那四族（inselberg、volcanic plugs、volcanic cones & calderas、tundra）不重合**，「魔鬼岩石蛋」与「喀斯特」属需**新增的设计 family**。

---

## 7. 待用户决定的三个岔路（未定则不动手）

1. **交付目标**：离线几何 + 预览 / 进 Minecraft 世界 / 分期两者都要。
2. **是否允许引入局部体积表示**（SDF/体素；Nucleation 或扩展现有 `hybrid_cave_geometry`）。
   - 新证据收窄了取舍：若目标含「进游戏」，体积路线**必须连 Java 消费端一起改**（新 snapshot format version + `Terrain.solid` + `SurfacePalette`），量级远大于照抄 canyon 的 9 步纯 VDM 配方（后者不动 `TGMCMT01`）。
3. **新形态与现有世界的关系**：本工程纪律是「不动已有世界配方，新增版本化配方 + 独立预设」。

---

## 8. 一句话结论

六类地形**按可表达性天然分成两组**：魔鬼塔 / 乌鲁鲁主体 / 张家界石柱 / 喀斯特峰林属 **L0 纯高度场**，可沿用现行 VDM 路线（但要 1 m 级 chart，且要解决闭合环与形态尺度门）；天坑内腔、溶洞天窗天生桥、魔鬼岩石蛋堆、Uluru flared slope 属 **L1 体积拓扑**，仓库里已有 `DensityColumn` 与 `hybrid_cave_geometry` 两套骨架，但**米制消费者目前连「实心柱之外的任何东西」都做不出来**，且天坑会正面撞上四道洼地水文契约。

**资料层面**：六类的定量尺度大部分只有二手来源，官方原件普遍未取得 → 写生成器合法性门槛前应先补 §6.3 的六项硬数据。
