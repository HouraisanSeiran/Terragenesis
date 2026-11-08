# Terragenesis 与 dreamulator 河网算法对照

日期：2026-11-08。对照对象：[fyabc/dreamulator](https://github.com/fyabc/dreamulator)（MIT，`main` HEAD `90e5ad9`，`pyproject.toml` 版本 1.2.0，最近推送 2026-11-07）。

## 0. 阅读范围与证据边界

**已直接读代码**（下文行号以 GitHub `main` 为准）：

| 文件 | 读到的内容 |
| --- | --- |
| [`media/_hydrology_kernels.py`](https://github.com/fyabc/dreamulator/blob/main/src/dreamulator/media/_hydrology_kernels.py) | 分块 Priority-Flood 的 numba 内核：`_local_flood_kernel`、`_grade_flats_kernel`、`(level, cell)` 字典序堆 |
| [`media/canvas_hydrology_tiled.py`](https://github.com/fyabc/dreamulator/blob/main/src/dreamulator/media/canvas_hydrology_tiled.py) | 生产路径：Barnes 2016 三阶段填洼 + Barnes 2017 三阶段汇流 + ε 坡化 + 块边溢出图 |
| [`media/canvas_hydrology.py`](https://github.com/fyabc/dreamulator/blob/main/src/dreamulator/media/canvas_hydrology.py) | 正确性 oracle：全局 PF、D8 receiver、全局降序汇流、跨 chunk 湖泊连通、`solve_isthmus` 接缝耦合 |
| [`map/prog_erosion.py`](https://github.com/fyabc/dreamulator/blob/main/src/dreamulator/map/prog_erosion.py) | 区域包侵蚀链：`priority_flood`、`spl_erode`（隐式 SPL）、`flow_accumulation`、`river_mask`、`lake_mask`、`terminal_equilibrium_routing`、`river_segments`、`erode_region_pack`，以及全部常数 |
| [`media/carto_render.py`](https://github.com/fyabc/dreamulator/blob/main/src/dreamulator/media/carto_render.py) | 制图层：线宽 `0.4 + 1.0 * w_n`、常流/非常流双线型 |
| [`docs/knowledge/cartography/river_symbolization.md`](https://github.com/fyabc/dreamulator/blob/main/docs/knowledge/cartography/river_symbolization.md)、[`drainage_cartography.md`](https://github.com/fyabc/dreamulator/blob/main/docs/knowledge/cartography/drainage_cartography.md) | 线宽律 `w ∝ Q^0.5`、0.5 mm 单双线判据、湖泊 MMU 与配色规则 |

**未读**：`canvas_lakes.py` 内部（只读到其被引用关系）、`canvas_pipeline.py` 的 `_grade_flats_reference`、其 `tests/` 目录（GitHub 匿名 API 在后半程返回 504）。这些缺口不影响本文的算法判断，但凡涉及"它没有做 X"的结论，均按"代码与文档中未见"表述，不按"确认不存在"。

本项目侧的证据：`terrain_pipeline/new_world_stage1.py`、`drainage.py`、`basin_topology.py`、`channel_geometry.py`、`surface_rivers/metric_sediment.py`、`metric_depression_gate.py`、`metric_world_domains.py`、`metric_world_reaches.py`、`native_30m_hydrology_ledger.py`、`metric_cross_region.py`，以及根目录 [第 1–3 阶段科学评估](Terragenesis-1-3阶段科学评估与开源对照-20261104.md) §11、§15。

## 1. 一句话结论

两边**共享同一套教科书骨架**（Priority-Flood 填洼 + 单流向最陡坡 + 汇流累积 + 阈值出水系），差别在**目的**。注意"单流向"的具体形式并不相同：dreamulator 是规则栅格上的 **D8**，本项目是 **Delaunay 不规则图上的最陡坡**（见 §3.1 勘误），两者的邻域与度数是不同的：

- dreamulator 是**有限图幅的地图生产线**：物理（隐式 stream power 侵蚀）只负责把地形"揉出河谷"，最终交付物是**矢量河线与制图符号**，因此它的算法重心在"分块可扩展到 6 亿格 + 河线像不像地图"。
- Terragenesis 是**无限世界的物理地表准备链**：河网是**米制拓扑与床面**（节点、河段、断面、水量/泥沙账），交付物是可跨区重算的 artifact，因此重心在"拓扑完整、账本守恒、跨窗一致"。

结论上：**在"分块路由算法"这一项 dreamulator 明显领先本项目**（它已经实现了本项目 §11.1 列为"最关键一步"的 Barnes 2016/2017，并有逐位等价测试）；**在"河网作为物理对象"这一整层本项目领先**（断面、床面、湖泊库容、水沙账、三角洲、跨区身份）。两边同属**单流向最陡坡**、都没有 MFD、都没有二维水力——这是**共同短板**，不是差异。

## 2. 两个工程的算法骨架

### 2.1 dreamulator

```
区域包 region pack（height + precipitation，有限 km 范围）
  └─ heal_inland_water（小于 MMU 的内陆水体治成陆地）
  └─ spl_erode：30–40 步 × 5e4 年，每步
        priority_flood(h, land, eps=1e-4)          ← Barnes 2014 + ε
        flow_accumulation(order, receiver, precip) ← 降序，降水权重
        _spl_step_numba（Braun–Willett 隐式 SPL，n=1, m=0.5）
        _hillslope_step（线性扩散，σ=0.5 px）
  └─ priority_flood（终态）
  └─ renderable_lakes / terminal_equilibrium_routing（P−E 平衡、Hamon PET）
  └─ river_mask(acc > 3000 参考径流格) → river_segments（矢量、Chaikin 平滑）
  └─ carto_render（线宽 ∝ Q^0.5，常流实线 / 非常流虚线）
```

大尺度另有 canvas 链：`CanvasTiles`（`ChunkGrid`，像素 23 km/256 ≈ 90 m）上跑
Barnes 2016 三阶段填洼（块内带标签 PF → 块边溢出图 → 全局水位回灌）与
Barnes 2017 三阶段汇流（块内累加 → 边界转移事件求解 → 折回），并可用
`solve_isthmus` 把两个 canvas 沿一条海岸/地峡接缝耦合起来一起洪泛。

### 2.2 Terragenesis（当前主线）

```
TD 30 m 页 / 米制来源 + 雨水 forcing
  └─ 不规则抖动图（node 30 m + 0.7 抖动，绝对世界坐标 _mix64 抖动）
  └─ A 线：priority-flood 填洼（出口 = 海洋 | unknown 边界）
          → 池标记（_label_pools）→ 池库容/溢流水位 → 单流向 receiver（填后最陡坡）
          → 终端分类（海洋 / 非海出口 / unknown）
  └─ B 线：strict_receivers（严格下坡，平地保持显式汇点，不伪造路径）
  └─ 盆地层次树 build_basin_hierarchy（并查集合并树）
          → 溢出网络 make_basin_spill_network → 鞍部破堤 generate_saddle_breach
  └─ 洼地闸门 metric_depression_gate（这是湖还是河应直接穿过的水坑）
  └─ 河段选取（最小集水 256 格、干流 2000 m）+ 完整河段网 metric_world_reaches
  └─ 断面/河床：w = 4·Q^0.45，d = 0.6·Q^0.3，切深 ≤ 4 m，岩性硬度加权，单调并集床
  └─ 有界 Manning 储量水力 + 湖泊库容/水位/端口耦合 + 逐格逐时段水量账
  └─ 超量剪切输沙能力 + 固体账 + 三角洲/海岸形态
```

## 3. 逐项对照

| 项目 | dreamulator | Terragenesis | 判断 |
| --- | --- | --- | --- |
| 地形输入 | TD/引擎 DEM 的 region pack，有限幅面（550 km / 2048 px ≈ 0.27 km/px）；canvas ≈ 90 m/px | TD 30 m 原生页（及 100 m/2 km 派生），无限世界按需 | 本项目分辨率更细、目标更大 |
| 栅格 vs 图 | 规则栅格，8 邻域（D8） | **不规则抖动三角图**：`grid_mesh` 生成 30 m 抖动节点，块内 Delaunay 三角化后建成 CSR 邻接（度约 6，非固定 8） | 本项目刻意去栅格化，从构造上避免 45°/90° 走线；dreamulator 靠注入 1.5 m fBm 噪波打破栅格对称 |
| 洼地 | Priority-Flood + ε（`PF_EPS_M=1e-4`），可选 breach；分块版 Barnes 2016 三阶段 | 填洼（无 ε）+ 盆地层次树 + 破堤候选；**无分块版** | dreamulator 领先（见 §5） |
| 平地 | ε 坡化（同值面多源 Dijkstra，种子=出口/鞍部） | 不做平地方向；平地保持显式汇点 | 两种路线，本项目更保守但平地会出现断头 |
| 流向 | D8 最陡坡（规则 8 邻域），单流向 | 图上最陡坡（`strict_receivers`，Delaunay 邻域），单流向 | 同为单流向最陡坡，但邻域与度数不同；两边都没有 MFD/D∞ |
| 汇流 | 全局降序排序；生产路径为 Barnes 2017 块边转移 | CSR 拓扑序全局累加，**无块级 DAG** | dreamulator 领先 |
| 出水系判据 | 径流加权累积 > `RIVER_THRESHOLD_CELLS=3000`（≈2.1 m³/s），按 res² 缩放 | 最小集水格数 + 干流长度 + 坡度/流量规则；永久河网定义为 Q̄·S^α（已定，未全部落地） | 理念接近，dreamulator 的"按分辨率缩放"实现更完整 |
| 河网拓扑表达 | 矢量河段（polyline），无显式节点/河段图 | 不可变节点 + 河段 + 下游边 + 终端；Strahler 作为属性并参与网形评分 | 本项目领先 |
| 河宽 | **制图线宽** ∝ A^0.5（`0.4 + 1.0 * w_n`），毫米级 | **物理河宽** 4·Q^0.45，深 0.6·Q^0.3，岩性加权，切深上限 4 m | 不是同一层次的量；本项目是床面，dreamulator 是符号 |
| 断面/床面 | 无（侵蚀只改高程） | 梯形断面、单调并集床、连续床、中心线转角上限 | 本项目领先 |
| 湖泊 | 填深 > 5 m 且 ≥ 64 格的封闭洼地；MMU 4.6 km² + 最小宽度 1.5 km；**终端湖做 P−E 平衡**（Hamon PET，蒸发系数 0.9），收支平衡决定是否成湖 | 库容—水位曲线、河湖端口耦合、溢流网络、鞍部破堤；湖泊水位由水量账与共步求解 | dreamulator 的"气候平衡裁决湖泊存亡"更简洁；本项目的湖体水力更完整 |
| 水量 | 只有稳态 P−E（无时序、无河道储量） | 逐格逐时段水量账 + 有界 Manning 储量（回水/二维双向浅水未做） | 本项目领先 |
| 侵蚀 | **隐式 SPL**（Braun–Willett，n=1，m=0.5，K=2e-6/2e-7，30–40 步 × 5e4 年）+ 坡面线性扩散 | **超量剪切输沙能力** C=k·w·max(τ−τc)^1.5，岩石/冲积分参数，固体体积账 | 两条不同流派：dreamulator 是经典 detachment-limited 地貌演化，本项目是输沙能力 + 预算 |
| 泥沙账 | 无（只有高程变化） | 有（梳状分类：松动/沉积/岩石移除/输出） | 本项目领先 |
| 三角洲/海岸 | 无（文档里只有海岸配色与"内流湖"） | 三角洲 v5、河口输沙、海岸输运、潮汐 | 本项目独有 |
| 确定性 | 邻居顺序固定、堆按 `(level, 全局 index)` 破平、噪波种子写死 42 | 世界种子派生抖动（`_mix64`），内容寻址身份；**平局按窗口局部编号**（已知缺陷） | dreamulator 的破平更彻底 |
| 跨区/无限 | 一个 canvas 内部块边界**不是**出口（块只用于扩展规模），另有 isthmus 接缝；但 canvas 范围本身是有限选定的 | 窗口外缘 unknown 直接当出口（已知缺陷）；有跨区一致性模块与 42 km 交接受验；无限调度未完成 | dreamulator 的块语义正确，本项目仍在修 |
| 规模/性能 | 600M+ 格 canvas，float32 省内存，专门绕开 4.9 GiB bincount 峰值 | 196 万格跨区 78.77 s / 601 MB；1600 km 世界过程 162.71 s | 两者都在 GB 级内存上做工程妥协，不可直接比 |
| 验证 | pytest；断言分块结果与 oracle **逐位相等** | 619 个测试文件 / 11 万行；审计器 + 冷读 + 身份哈希 + 208 个验收目录 | 本项目量大，dreamulator 的等价性断言更锋利 |

## 3.1 勘误：本工程当前并不使用栅格 D8（2026-11-08 核对）

先前的口头对照把本项目说成"D8"，这是错的。核对代码后的准确说法：

**主线的 30 m 河网拓扑不是栅格 D8，而是 Delaunay 不规则图上的单流向最陡坡。**

| 证据 | 内容 |
| --- | --- |
| [drainage.py:558](terrain_pipeline/drainage.py#L558) | `strict_receivers(height, mesh, ...)`："Strict downhill metric graph routing; flats remain explicit sinks"。接收点在内核 `_strict` 中从 CSR 邻接里取坡度最大者，平局取**节点编号更小**者，不读栅格 8 邻域 |
| [drainage.py `grid_mesh` / `_block_neighbors`](terrain_pipeline/drainage.py#L520) | 节点 = 30 m 栅格 + 0.7 随机抖动；块内取 `(core+8)` 光晕建 `scipy.spatial.Delaunay`，过滤细长三角形后转 CSR。度数由三角化决定（约 6），不是固定 8 |
| [new_world_stage1.py:23-80](terrain_pipeline/new_world_stage1.py#L23-L80) | `build_native_graph` 用同一套抖动与三角化建盘上 CSR；抖动键为 `_mix64(nx, nz, WORLD_SEED)`，**只依赖绝对世界坐标**，不依赖窗口原点 |
| [native_30m_source.py:472-505](terrain_pipeline/surface_rivers/native_30m_source.py#L472-L505) | 主线入口 `build_strict_topology`：`grid_mesh` → `masked_mesh` → `strict_receivers`，明确不经过栅格邻域 |
| [metric_world_domains.py:622-628](terrain_pipeline/surface_rivers/metric_world_domains.py#L622-L628) | 接收点用 `receiver_edges_valid(receiver, grid_mesh(...))` 校验，即"必须是该网格的真实边" |
| [metric_highland_sources.py:30](terrain_pipeline/surface_rivers/metric_highland_sources.py#L30) | 原话："receiver … `irregular_grid.strict_receivers`；**D4 is used here only to group source patches**" |

**栅格 D8 / D4 仍然真实存在于下列局部位置**，但都不是主流向：

- [hydrology_detail.py:21](terrain_pipeline/hydrology_detail.py#L21) `DIRECTIONS`（8 邻域）：宏观规划层的一致性判据（`cross_owner_d8_mask`、`unplanned_sink_mask` 等），用于检查"实际排水没有穿出冻结域"，不是 30 m 河网生成。
- [coastal_delta_product.py:85](terrain_pipeline/coastal_delta_product.py#L85)、[metric_delta.py:60](terrain_pipeline/surface_rivers/metric_delta.py#L60)、[metric_fluvial_delta.py:95](terrain_pipeline/surface_rivers/metric_fluvial_delta.py#L95)、[coastal_river_connector.py:45](terrain_pipeline/coastal_river_connector.py#L45)：掩膜上的 8 邻域几何搜索（三角洲/河口连通），不是汇流路由。
- D4：`basin_topology._neighbors`（`_flat_receivers`、盆地层次）、`td_natural_river_network._neighbors`、`metric_highland_sources._D4_STEPS`（仅源区分组）、`environment_delta_fv` / `world_process_estuary` 的有限体积 D4 面。

**命名债（2026-11-08 已清理）**：多处 docstring 曾写 "strict-D8"（如 `finite_river_block_schedule.py:1-8`），但其 `receiver_active` 来自上述不规则拓扑。现已统一改为"图接收点 / graph receiver"，并新增 [路由术语](docs/architecture/routing-terminology.md) 作为唯一权威定义；持久化策略名中的 `d8` 保留原字面，见该文档 §6。

**这个差异的实际后果**，对比较结论有影响但不改变结论：

- dreamulator 要在规则栅格上解决"45°/90° 走线"，办法是**改高程**：路由前注入 1.5 m fBm（`NOISE_AMPLITUDE_M`），并明确写"远低于数据分辨率"。本项目解决同一问题靠**改节点位置**（0.7 格抖动，不改高程），代价是邻域度数不固定、坡度统计与固定 8 邻域不同。
- 两边都必须处理"抖动/噪波改变了什么"的可追溯性：本项目的抖动键是可复算的绝对坐标哈希，dreamulator 是写死的种子 42。
- 块三角化的边集由抖动坐标与 8 格光晕决定，与窗口原点无关；这是本项目少见的、**已经做对**的跨窗一致性基础。

## 4. 关键的三个算法差异（值得单独说）

### 4.1 块边界语义：dreamulator 做对了，本项目还没有

dreamulator 的注释把这件事写得很清楚：块边界**不是**外部出口，每个块的边缘格各自起一个流域标签，靠块间溢出图（Barnes 2016 stage 2）在全局水位里重新合并；只有海洋、canvas 外缘、缺失 chunk 才是 `external`。这正是本项目 §11.1 第 1 条指出的问题，也正好对应它给出的处方。本项目当前 `outlets = ocean | unknown`（窗口外缘即出口），所以"换窗口 → 洼地溢出水位与接收点可能改变"这个风险仍然成立。

### 4.2 ε 坡化：一条便宜的改进，能同时解决两个已知缺陷

dreamulator 填洼后对每个等值面做一次多源 Dijkstra（种子=出口与鞍部，同值面内每步 +ε），于是湖面/平地都有确定且单调的流向，且明确写了"不采用 Barnes 2014 的 flat-resolve 方案，因为它把流向改成汇聚型，不符合本链语义"。本项目目前：填洼不破平（`max(bed, level)`），平地 receiver 靠坡度 0 + 局部 rank 裁决。**这既是"平地路径不自然"，也是"平局按局部编号"的根源**。ε 坡化本身不改高程层级、不引入新参数族，是 §11.2 与 §11.3-1 的合并解法。

### 4.3 两套权重：物理用降水，出水系用径流

dreamulator 明确区分：侵蚀物理用降水权重（"风暴径流是侵蚀媒介"），**出水系/河宽用年径流权重**（Turc–Pike 水量平衡，并按 300 mm/yr 固定参考径流归一，"干旱窗口不得把自己重新归一化成到处是河"）。这个"固定参考而非窗口均值"的细节，恰好避开了本项目在跨窗口一致性与干旱区河网密度上会踩的坑。本项目已有独立的 forcing/产流层，但"河网判据必须用与窗口无关的绝对阈值"这一条值得写进永久河网定义。

## 5. 可以借鉴的清单（按收益/成本排序）

| 顺序 | 借鉴内容 | 出处 | 对本项目的意义 | 成本 |
| --- | --- | --- | --- | --- |
| 1 | **ε 坡化**：填后对等值面做多源 Dijkstra，+ε 破平 | `canvas_hydrology_tiled._apply_eps_ramp`、`_grade_flats_kernel` | 一次改动同时缓解 §11.2（平局确定性）与 §11.3-1（平地路径不自然）；不引入新阈值 | 小 |
| 2 | **块边界不是出口**的显式语义 + 块边溢出图 | `fill_canvas_tiled` stage 1–3 | 修正"窗口范围决定结果"这一结构性问题 | 中 |
| 3 | **Barnes 2016 三阶段填洼 + Barnes 2017 三阶段汇流** 作为参照实现 | 同上、`accumulate_canvas_tiled` | §11.1 的处方已有人写成可读 Python + numba，可直接对照复现（MIT，须注明来源） | 大（正确实现仍要自己写） |
| 4 | **分块结果与单块 oracle 逐位相等**的验收方式 | `canvas_hydrology` 模块文档 + 其测试意图 | 本项目正缺"扩窗后内部逐格一致"这类判据；这是最直接的验收模板 | 小 |
| 5 | **固定参考径流归一**的河网阈值 | `prog_erosion.RUNOFF_REFERENCE_MM`、`RIVER_THRESHOLD_CELLS` | 永久河网判据在全球尺度上可比，不随窗口气候漂移 | 小 |
| 6 | **湖的 MMU/最小宽度双门**（面积 + 包围盒宽度） | `keep_large_lakes`、`LAKE_MMU_KM2`、`LAKE_MIN_WIDTH_KM` | 与本项目 `metric_depression_gate` 同源思路，但"河线要能画进湖里"的判据更贴合交付形态 | 小 |
| 7 | **湖的 P−E 稳态裁决**（含穿流湖的净蒸发扣减） | `terminal_lakes`、`terminal_equilibrium_routing` | 内流终点"是不是湖"可以由气候收支决定，而不是靠固定阈值 | 中 |
| 8 | **isthmus 接缝联合洪泛**：两幅图沿一条海岸接缝当成一个图洪泛 | `solve_isthmus` | 相邻水文域/相邻块的"共享边界"验收可直接借用这个结构 | 中 |
| 9 | **制图符号层**（0.5 mm 单双线判据、`w ∝ Q^0.5` 线宽、常流/非常流双线型） | `river_symbolization.md`、`carto_render._river_collections` | 本项目第 4 阶段与图集交付缺这一层；与算法解耦，可后置 | 小 |

**不建议照搬**：① 用制图线宽代替物理河宽（本项目要的是床面与断面，符号宽度不能回灌地形）；② 把 SPL 当唯一泥沙机制（本项目已有分项固体账与三角洲，换成 SPL 会丢掉预算口径）；③ 用全局降序排序做汇流（在无限世界上不可流式扩展，dreamulator 自己也已在生产路径改成块级转移）。

## 6. 不够领先、也不该自满的地方

- **两边都没有 MFD / D∞**：坡面汇流在两边都会被压成细线，河源位置对阈值敏感。这不是"谁落后"，是共同未做项。
- **两边都没有二维水力**：dreamulator 根本没有时序水量；本项目是有界 Manning 储量，回水与洪泛仍未做。dreamulator 的"没有"更彻底，本项目的"有界"也不算通过。
- **dreamulator 的物理可信度边界很清楚**：SPL 是地貌演化玩具级参数（K=2e-6，40 步 × 5e4 年），湖泊水位是稳态 P−E，河宽是符号——它从不宣称水文一致。本项目宣称的目标更高，因此 dreamulator 的"算法正确性"不能作为本项目物理验收的替代。
- **本项目在"分块路由"上确实落后**：这是同一条技术路线上的代差，不是取舍差异。对方已有可用实现与等价性测试，本项目 §11.1 仍列为"最关键的一步"且未落地。

## 7. 建议的下一步（若要动手）

1. 先做**只读对照**：在固定种子的一块 30 m 窗口上，用 dreamulator 的 `fill_canvas_tiled` + `accumulate_canvas_tiled` 逻辑（离线脚本，不进生产依赖）与 `strict_receivers`/priority-flood 结果逐格比较 receiver 与汇流量，差异应集中在平地、池内与块边界。这与本项目 §11.5 第 1 条、§8.2 第 1 项一致。
2. 再做**ε 坡化**：新模块、新产物版本（如 `native-routing-v2`），旧 routing 与证据不动；验收用"扩窗后内部逐格一致"。
3. 最后才做**分块填洼 + 块级 DAG 汇流**：这是唯一能真正兑现"无限世界"的改动，工作量大，且必须先把平局键换成世界坐标稳定键，否则分块化会把现在的窗口依赖变成块依赖。

## 8. 参考

- 仓库主页：<https://github.com/fyabc/dreamulator>
- 许可证：MIT（`LICENSE`，1065 字节）
- 其自述的算法依据：Barnes 2014（C&G 62:117-127，PF+ε）、Barnes 2016（C&G 96:56-68，分块填洼）、Barnes 2017（EMS 92:202-212，分块汇流）、Braun & Willett 2013（隐式 SPL）、Lindsay 2016（破堤—填洼混合）
- 本项目对应依据：[第 1–3 阶段科学评估](Terragenesis-1-3阶段科学评估与开源对照-20261104.md) §11.1–§11.6、§15.2；[长期维护与三维河网设计](research/长期维护与三维河网设计.md)；[河网系统模块登记](river-system/MODULES.md)
