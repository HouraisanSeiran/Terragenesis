# dreamulator 与 Terragenesis 河网算法对比（2026-11-08）

对照对象：[fyabc/dreamulator](https://github.com/fyabc/dreamulator)，MIT，`pyproject.toml` 版本 1.2.0。上游版本固定为 commit **`90e5ad96acf92a597090bc2fa70c1a5b1e646041`**（2026-11-07 推送）；下文外链一律指向该提交，默认分支后续更新不影响证据。

## 0. 证据边界

**本地逐行读过并复核过行号**（副本在 `.scratch/dreamulator-comparison-20261108/raw-source/`）：

- `media/_hydrology_kernels.py`：分块 Priority-Flood 的 numba 内核、`(level, cell)` 字典序堆、ε 坡化内核
- `media/canvas_hydrology.py`：oracle（全局 PF、D8 receiver、全局降序累积、跨 chunk 湖泊连通、`solve_isthmus`）
- `media/canvas_hydrology_tiled.py`：Barnes 2016 三阶段填洼 + Barnes 2017 三阶段累积 + ε ramp
- `media/canvas_pipeline.py`：生产画布链（海陆判定、填洼、坡道、径流权重、`run_canvas_rivers`）
- `media/canvas_lakes.py`：Fill–Spill–Merge 的独立实现（`DepressionHierarchy`、`fill_spill_merge`）
- `map/prog_erosion.py`：区域包侵蚀链、全部常数、`terminal_equilibrium_routing`、`river_segments`
- `map/_erosion_kernels.py`、`map/water_bodies.py`、`map/surface_transport.py`
- `tests/test_canvas_hydrology_tiled.py`、`tests/test_canvas_rivers.py`

**据仓库文档与并行调查摘录、本轮未逐行复核行号**：`cli_export_canvas.py`、`docs/design/pipelines/canvas-chain.md`、`engine/climate_physics.py`、`td_canvas_build.py`、`carto_render.py` 全文、`pipeline_types.py`。凡引用这些文件的具体行号，均标注"未本地复核"。

本工程侧证据：`terrain_pipeline/new_world_stage1.py`、`drainage.py`、`basin_topology.py`、`channel_geometry.py`、`surface_rivers/metric_sediment.py`、`metric_depression_gate.py`、`metric_world_domains.py`、`metric_world_reaches.py`、`native_30m_hydrology_ledger.py`、`metric_cross_region.py`，以及 [第 1–3 阶段科学评估](../Terragenesis-1-3阶段科学评估与开源对照-20261104.md) §11、§15。

## 1. 一句话结论

两边**共享同一套教科书骨架**：DEM → 填洼 → 单下游 → 汇流累积 → 阈值出水系。差别在目的：

- dreamulator 是**有限图幅的地图生产线**。物理（隐式 stream power 侵蚀）只负责把地形揉出河谷，交付物是**矢量河线与制图符号**；算法重心在"分块可扩展到 6 亿格 + 河线像不像地图 + 气候—河湖闭合"。
- Terragenesis 是**无限世界的物理地表准备链**。河网是**米制拓扑与床面**（节点、河段、断面、水量/泥沙账），交付物是可跨区重算的 artifact；重心在"拓扑完整、账本守恒、跨窗一致"。

判断：**分块路由这一项 dreamulator 明显领先**（它已实现本工程 §11.1 列为"最关键一步"的 Barnes 2016/2017，并有等价性测试）；**"河网作为物理对象"这一整层本工程领先**（断面、床面、湖泊库容、水沙账、三角洲、跨区身份）。两边同属**单流向最陡坡**、都没有 MFD、都没有二维水力——这是**共同短板**，不是差异。

## 2. dreamulator 的两条执行链

| 路线 | 入口与顺序 | 输出与含义 |
| --- | --- | --- |
| **画布主线 S1→S2→S3** | 先在 TD 分块画布上生成地形；S2 读 `canvas.json`、`chunks/`、`climate/`，依次 `run_canvas_fill` → `run_canvas_rivers`；S3 裁窗消费 | `rivers.line.npy`（M×2×2 线段，画布西南原点 km）、`rivers.flow.npy`（归一化累积）、`rivers.regime.npy`（常流/非常流）；另有河道 PNG、稀疏湖掩膜与湖表。**不是**带断面、床面、水面的三维河段 |
| **区域包程序化侵蚀** | `erode_region_pack` 读 `input/height.meters.npy` + 降水 + 海平面 → 处理内陆低水体 → `spl_erode`（降水权重）→ 重新填洼 → 用年径流提取河网 → 年度湖平衡 | `prog-out/` 下的高程、河线、累积、湖/海掩膜、参数元数据；原始 DEM 不被原地重写 |

两条链的网格不同：画布像素 `PX_KM = 23/256 ≈ 0.09 km`，`ChunkGrid(rows, cols, tile)` 分块；区域包是 2048²/550 km 级（≈0.27 km/px），另有 4096 精化。**球面 CVT 地质网格不参与现行河网路由**——`map/hydrology.py` 只保留球面填洼与闭盆湖标记，粗网格流水侵蚀因"单格人工沟壑"被移除（配置说明，未本地复核行号）。

## 3. dreamulator 的算法逐项

### 3.1 填洼：PF + ε，分块三阶段

- 单块/参考实现：经典 Priority-Flood，出口是海洋、画布外缘、缺失 chunk；`filled = max(dem, level + ε)`，堆按 `(level, cell)` 字典序破平（`canvas_hydrology._flood_graph`、`_hydrology_kernels._local_flood_kernel`）。
- 生产分块版：**Barnes 2016 三阶段**——块内带标签 PF 并记录块内溢出图 → 标签全局化、跨块边配对、在溢出图上再洪泛一次 → 把全局水位回灌每块（`fill_canvas_tiled`）。块边界**不是**出口，只有海洋/画布外缘/缺块才是 `external`。
- ε 坡化：填平后对每个等值面做多源 Dijkstra（种子=出口与鞍部，同值面内每步 +ε），使湖面与平地都有确定且单调的流向（`_apply_eps_ramp`；内核 `_grade_flats_kernel`）。代码明确说明**不采用** Barnes 2014 的 flat-resolve 方案，因为它把流向改成汇聚型，与本链语义不符。
- 验收：`tests/test_canvas_hydrology_tiled.py` 断言分块填洼与 oracle **逐位相等**（`np.array_equal`），分块累积与 oracle 数值等价（`rtol=1e-12`）。这两条力度不同，引用时不要都写成"逐位"。
- 另有 `solve_isthmus`：把两个 canvas 沿一条接缝像素对耦合，作为**一个联合图**洪泛，等于拼起来算，不需要外部迭代。

### 3.2 流向与汇流：规则栅格 D8，单 receiver

- 在填平面上按固定顺序检查 8 邻域，坡度 = 高差 / （1 或 √2），取最大者；无下游则 `-1`。这是**真正的栅格 D8**：不是 Delaunay/Voronoi 图路由，也不是 MFD。
- 累积：按填平面高度全局降序，把权重加到 receiver（`flow_accumulation_canvas`）；生产分块版为 **Barnes 2017**：块内累加 + 记录边界转移事件 + 沿接收块内的 receiver 链走到下一个出口，再折回（`accumulate_canvas_tiled`）。块级 DAG 不可用——两块的边界像素可以互换流量形成伪环，代码注释写明了这一点。
- 这条路由允许支流汇入同一下游，但**不产生分汊、辫状复合通道或三角洲分流网**。

### 3.3 海洋与湖泊

- **海洋**：有 connected-sea 产品时，海洋必须是"地表 ≤0 m、连通到画布开放边界、且含粗地质海洋格"的连通体；未连通地质海洋的海平面以下区域按普通盆地参与填洼（否则被判成海）。无该产品时回退旧规则（`canvas_pipeline` 判海段，未本地复核行号）。
- **几何湖**：填深 > `LAKE_MIN_FILL_M=5 m` 且 ≥ `LAKE_MIN_CELLS=64` 格；再套 **MMU 4.616 km²** 与 **最小宽度 1.5 km** 双门。阈值带明显制图可读性与作者标定依据，不是普适成湖物理常数。
- **年度水量平衡湖图（生产路径）**：`terminal_equilibrium_routing` 先把所有湖临时切成汇，按"首触"只把陆地贡献计给路径最先到达的湖（避免湖臂反复进出重复计水）；再收缩成湖图，算年净需水 `(0.9×PET − P)×面积`，传播过路湖的水量盈余；不足者按平衡面积缩水或变干盐滩；过路湖在出口用负点权重扣掉净蒸散，再重新累积，下游河道起点与线宽读耗减后的年水量。缺径流/温度/降水则退回几何湖。
- **未接线的 FSM**：`canvas_lakes.py` 自带洼地层级、容量、子湖先填、兄弟合并、溢到父节点/海洋、以及 `Σ max(0, z_w − z_i)·area = W` 反求水位。但 `run_canvas_rivers` 调用的是上面的年度平衡，`canvas_lakes` 在设计文档里被保留为算法实现与测试基准。不能把这份可运行模块写成主线已完成瞬变湖库耦合。
- **一个真实缺口**：`is_term = (demand > 0.0) & (total < demand)` 在循环**前**一次判定，拓扑循环只更新下游 `total`，不重判终端。于是"初始外部来水不足、后被上游溢流补足"的湖仍保留终点标记。本轮只做了孤立逻辑复核（`external=[0,100,0]`、`demand=[0,10,50]`、`1→2→出口`，得 `total=[0,100,90]` 而第二个湖仍是终端），**没有构造对应真实 DEM 端到端复验**，不能推算实际地图错误率。

### 3.4 径流、流量与河道可见性

- 上游权重不是"每格 1"：年径流用 **Turc–Pike/Budyko**（`E/P = (1+(PET/P)^−n)^(−1/n)`，`n=2`）配 Hamon PET；月分配形状来自土壤桶与基流库，退化时用 `max(P−PET,0)` 或均匀分配，月总量再缩放到同一年径流（`climate_physics.py`、`td_canvas_build.py`，未本地复核行号）。
- 权重按**固定 300 mm/yr 参考径流**归一，不用窗口均值——"干旱窗口不得把自己重新归一化成到处是河"。
- 河道门槛：CLI 默认 27000 参考径流格（≈90 m 下 2.1 m³/s 年平均流量），而 `run_canvas_rivers` 函数默认 **7000**（本地复核：`canvas_pipeline.py:840`）。评估必须记录真实调用参数；`rivers.flow.npy` 是归一化累积，换算 m³/s 还需乘参考径流深度与像元面积。
- 情相：有月径流时，在最终 receiver 上分别累积 12 个月，全部月份超过 `1 L/s`（`REGIME_ACTIVE_DISCHARGE_M3S = 0.001`）为常流，否则非常流；不区分间歇与事件性暴洪。月累积**不扣**月湖泊蒸发，代码承认这会把荒漠湖下游向常流方向偏置。

### 3.5 河宽、曲流与侵蚀

- 河段从 D8 链提取，合并共线点后做两轮 **Chaikin** 平滑，解决 45°/90° 折线观感；不改 receiver、不重刻河床，不是河岸迁移或截弯取直模型。
- 地图线宽 `0.4 + sqrt(flow/max(flow)) pt`（`carto_render._river_collections` 一带），是**符号宽度**，不是米制河宽；画布产品没有河深或湿断面。
- 区域包侵蚀：**隐式 stream power**（Braun–Willett，n=1、m=0.5、K=2e-6/2e-7，30–40 步 × 5e4 年）+ 坡面线性扩散（σ=0.5 px）。路由前注入 **1.5 m fBm 噪波**（波长 12 格，种子 42）打破栅格对称，作者注明"远低于数据分辨率"。
- 侵蚀用**降水**权重，出水系与河宽用**年径流**权重——两套权重是有意分开的。

## 4. 与本工程的对照

| 项目 | dreamulator | Terragenesis | 判断 |
| --- | --- | --- | --- |
| 空间离散 | 规则栅格 8 邻域（D8） | **不规则抖动三角图**：30 m 节点 + 0.7 抖动，块内 Delaunay → CSR（度约 6） | 本工程从构造上去掉栅格方向量化；对方靠 1.5 m fBm 打破对称 |
| 洼地 | PF + ε（1e-4），可选 breach；**分块三阶段** | 填洼（不破平）+ 盆地层次树 + 破堤候选；**无分块版** | dreamulator 领先 |
| 平地 | ε 坡化（等值面多源 Dijkstra） | 不做平地方向，平地保持显式汇点 | 两种取舍；本工程更保守，但会留下断头 |
| 流向 | D8 最陡坡，单 receiver | 图上最陡坡（`strict_receivers`），单 receiver | 同为单流向；都没有 MFD/D∞ |
| 汇流 | 全局降序；生产为 Barnes 2017 块边转移 | CSR 拓扑序全局累加，**无块级 DAG** | dreamulator 领先 |
| 出水系判据 | 年径流加权累积 > 阈值，按 res² 缩放，固定 300 mm 参考 | 最小集水格数 + 干流长度；永久河网定义为 Q̄·S^α（已定，未全部落地） | 理念接近；对方的"固定参考归一"更完整 |
| 拓扑表达 | 矢量河段（polyline） | 不可变节点 + 河段 + 下游边 + 终端；Strahler 作属性并参与网形评分 | 本工程领先 |
| 河宽 | **制图线宽** ∝ √A，毫米级 | **物理河宽** 4·Q^0.45、深 0.6·Q^0.3，岩性加权，切深 ≤ 4 m | 不是同一层次的量 |
| 断面/床面 | 无（侵蚀只改高程） | 梯形断面、单调并集床、连续床、中心线转角上限 | 本工程领先 |
| 湖泊 | 几何阈值 + **年度 P−E 平衡**（首触、穿流扣减）；FSM 未接线 | 库容—水位曲线、河湖端口、溢流网络、鞍部破堤 | 对方的"气候裁决湖泊存亡"更简洁；本工程湖体水力更完整 |
| 水量 | 只有稳态 P−E，无时序、无河道储量 | 逐格逐时段水量账 + 有界 Manning 储量（回水/二维浅水未做） | 本工程领先 |
| 侵蚀 | **隐式 SPL**（detachment-limited）+ 坡面扩散 | **超量剪切输沙能力** C=k·w·max(τ−τc)^1.5 + 分项固体账 | 两条流派；本工程保留预算口径 |
| 三角洲/海岸 | 无 | 三角洲 v5、河口输沙、海岸输运、潮汐 | 本工程独有 |
| 确定性 | 固定邻居顺序、堆按全局 index 破平、噪波种子写死 42 | 世界种子派生抖动（`_mix64`），内容寻址身份；**平局按窗口局部编号**（已知缺陷） | 对方的破平更彻底 |
| 跨区/无限 | 块边界**不是**出口；isthmus 接缝；canvas 范围仍有限 | 窗口外缘 unknown 当出口（已知缺陷）；有跨区一致性模块与 42 km 交接；无限调度未完成 | 对方的块语义正确 |
| 规模 | 600M+ 格 canvas，float32 降内存 | 196 万格跨区 78.77 s / 601 MB；1600 km 世界过程 162.71 s | 不可直接比 |
| 验证 | 分块填洼 == oracle 逐位；累积 rtol 1e-12 | 619 个测试文件 / 11 万行 + 审计器 + 冷读 + 身份哈希 | 本工程量大；对方等价性断言更锋利 |

### 4.1 术语勘误：本工程不用栅格 D8

上一版对照曾把本工程写成"D8"，这是错的。**30 m 主线是 Delaunay 不规则图上的单流向最陡坡**：

- `drainage.strict_receivers` 的 docstring 首句即 "Strict downhill **metric graph** routing; flats remain explicit sinks"，内核从 CSR 邻接取坡度最大者，平局按节点编号。
- `grid_mesh` / `build_native_graph`：节点 = 30 m 格 + 0.7 抖动，块内 `(core+8)` 光晕 `scipy.spatial.Delaunay`，过滤细长三角形后转 CSR；抖动键 `_mix64(nx, nz, WORLD_SEED)` 只依赖绝对世界坐标。
- `native_30m_source.build_strict_topology` = `grid_mesh → masked_mesh → strict_receivers`，不经栅格邻域。
- 栅格 D8 只剩在宏观规划与审计掩膜（`hydrology_detail` 的 `cross_owner_d8_mask` 等）、三角洲与河口的 8 邻域几何搜索；D4 只用于分组、湖盆面与有限体积面。

完整定义与历史改名见 [路由术语](../docs/architecture/routing-terminology.md)。

### 4.2 三个值得单独说的差异

1. **块边界语义。** dreamulator 把块边界当内部邻接，靠块间溢出图在全局水位重新合并；本工程当前 `outlets = ocean | unknown`，窗口外缘即出口，所以"换窗口 → 溢出水位与接收点可能改变"的风险仍成立。这正是 §11.1 的病根。
2. **ε 坡化。** 它同时解决"平地路径不自然"与"平局按局部编号"两个已知缺陷，不改高程层级、不引入新阈值族，是 §11.2 与 §11.3-1 的合并解法。
3. **固定参考径流归一。** 河网判据必须与窗口无关，否则干旱窗口会把自己的河网密度放大。

## 5. 可借鉴清单（按收益/成本）

| 顺序 | 借鉴内容 | 出处 | 意义 | 成本 |
| --- | --- | --- | --- | --- |
| 1 | ε 坡化：填后对等值面多源 Dijkstra，+ε 破平 | `_apply_eps_ramp`、`_grade_flats_kernel` | 一改解两缺陷 | 小 |
| 2 | 块边界非出口 + 块边溢出图 | `fill_canvas_tiled` | 修"窗口决定结果" | 中 |
| 3 | Barnes 2016 / 2017 作为参照实现 | 同上、`accumulate_canvas_tiled` | §11.1 处方已有可读实现（MIT，须注明来源） | 大 |
| 4 | "分块结果 == 单块 oracle"的验收模板（填洼逐位、累积数值等价） | `tests/test_canvas_hydrology_tiled.py` | 补"扩窗后内部逐格一致"判据 | 小 |
| 5 | 固定 300 mm/yr 参考径流归一 | `prog_erosion.RUNOFF_REFERENCE_MM` | 永久河网判据全球可比 | 小 |
| 6 | 湖的 MMU + 最小宽度双门 | `keep_large_lakes` | 与 `metric_depression_gate` 同源思路，更贴交付形态 | 小 |
| 7 | 湖的 P−E 稳态裁决（首触、穿流扣减） | `terminal_lakes`、`terminal_equilibrium_routing` | 内流终点由气候收支决定；注意 `is_term` 一次性判定的缺口 | 中 |
| 8 | isthmus 接缝联合洪泛 | `solve_isthmus` | 相邻域/块的共享边界验收可借用 | 中 |
| 9 | 制图符号层（0.5 mm 单双线、√Q 线宽、常流/非常流双线型） | `river_symbolization.md`、`carto_render` | 第 4 阶段与图集交付；与算法解耦 | 小 |

**不建议照搬**：① 用制图线宽代替物理河宽；② 把 SPL 当唯一泥沙机制（会丢掉分项固体账与三角洲口径）；③ 全局降序排序做汇流（对方自己也已在生产路径改成块级转移）；④ 把 `canvas_lakes` 的 FSM 当成主线已完成瞬变湖库耦合。

## 6. 参考

- 仓库主页：<https://github.com/fyabc/dreamulator>
- 许可证：MIT
- 其自述依据：Barnes 2014（C&G 62:117-127，PF+ε）、Barnes 2016（C&G 96:56-68，分块填洼）、Barnes 2017（EMS 92:202-212，分块累积）、Braun & Willett 2013（隐式 SPL）、Lindsay 2016（破堤—填洼混合）、Turc–Pike/Budyko 水量平衡
- 本工程依据：[第 1–3 阶段科学评估](../Terragenesis-1-3阶段科学评估与开源对照-20261104.md) §11.1–§11.6、§15.2；[长期维护与三维河网设计](长期维护与三维河网设计.md)；[路由术语](../docs/architecture/routing-terminology.md)；[河网系统模块登记](../river-system/MODULES.md)
