# Terragenesis TD 河网可复用工程对照研究

日期：2026-10-09
范围：只读研究；未运行长时间求解，未修改算法、前端或测试源码。本文把官方仓库、官方文档和论文原文作为一手来源，并将其能力与当前 TD 河网状态对照。

## 2026-10-09 实施后修正

后续用户授权的实际接入见 [pyflwdir接口与验证](../reference-routing.md)。已直接复用 `pyflwdir==0.5.12` 的图分析，在TD256完整图上核对流向/贡献域/面积一致，新增河流等级。原报告中“这些部分仍需自研”应区分项目适配与数值内核：来源、单位、边界和跨模块耦合由本项目维护；水动力、侵蚀和地下水内核仍应优先专项评估成熟后端，不能因GIS工具不覆盖就认定必须从零实现。

pyflwdir实际也有 `from_dem` 的填洼/路由，并非仅流向图工具；其出口候选、nodata边缘及高程精度政策与TD不同。WhiteboxTools官方仓库当前标为legacy，并指向 [Whitebox Next Gen](https://github.com/jblindsay/whitebox_next_gen)，采纳时应分别核对版本及许可证。无需同时引入本报告所列全部库；首轮只接一个后端，按实际差异增补必要对照。Minecraft按最新指示作为后续子项目，本阶段不开发。

下文为研究时点的候选清单与能力描述；最新M3–M6局部床变重耦合/共同水面进度以 `docs/td-river-m3-m6-supplement-20261008.md` 和对应保存包为准，不沿用旧段落的“尚未完成”描述覆盖新证据。

## 结论先行

1. **不应重复造轮子**：DEM 的流向、汇流、洼地处理、流域划分和候选河网提取，已有 TauDEM、WhiteboxTools、RichDEM、pyflwdir、TopoToolbox 和 Landlab 的成熟实现。Terragenesis 应保留来源身份、边界政策、TD 特有验收和适配层；不应再维护一套“通用 D8/D∞/priority-flood”核心。
2. **可借用但不能直接宣称完成**：Landlab 已有产流、汇流、坡面水流、侵蚀及部分地下水组件；其组件是科研建模积木，不等于 TD 的保存身份、跨 tile 账本、湖河共同水面或 Minecraft 交付。适合做参考实现、对照基准或可选后端。
3. **1D/2D 水动力是分界线**：多数 GIS 河网工具不是水动力求解器。Landlab 有 OverlandFlow、KinWaveImplicitOverlandFlow、OverlandFlowBates 等栅格地表水流组件；TopoToolbox 主要是地形/河网分析；WhiteboxTools、TauDEM、RichDEM、pyflwdir 主要不是 Saint-Venant 求解器。TD 当前 M3–M4 是有限矩形 Manning 储量/运动波与有界湖河交换，仍不是完整 Saint-Venant 回水或已认证 2D 浅水。
4. **地下水与洞道应拆成两条能力**：MODFLOW 6/FloPy 适合多孔介质地下水 PDE；Therion/CaveWhere 适合洞穴测量、中心线和三维表达；OpenPNM 适合孔隙网络。它们都不能直接替代 TD 的地表—洞道—复出拓扑、覆岩/布尔几何、洞口接回、材料账和地下明渠/压力管水力。
5. **TD 真正需要自研的部分**：TD 来源与 CRS/坐标语义、跨 tile/跨精度守恒交换、河谷中心线与河槽实体、湖泊天然盆地与回水、可审计的动态水量与沉积反馈、三维 VDM/洞道几何接回、地下水与地表网络耦合，以及最终的 Minecraft 适配。这些是产品边界和数据契约，不是通用 DEM 工具会替本工程解决的算法。

## 当前 TD 基线

根据工程内的 `docs/td-river-milestones-1-2-20261008.md`、`docs/td-river-m3-m4-coupling-20261008.md`、`docs/td-river-m5-m6-20261008.md`、`docs/dynamic-surface-hydraulics-v1.md`、`docs/surface-fine-mosaic-v1.md`、`docs/underground-river-v1.md` 和 `docs/hybrid-river-network.md`：

| 能力 | 当前状态 | 研究判断 |
|---|---|---|
| TD 二维静态排水/汇流 | 已有原床 D8、泛洪 D8、D4 边界适配、donor CSR、局部/累计 Q 和 DAG 验收 | 算法类别已有成熟外部实现；TD 特有的是来源绑定、边界策略和保存审计 |
| 洼地/盆地 | 有闭合候选、最低鞍点、有限 overflow/reception、湖泊储量/溢流基线 | 仍不是天然湖盆合并、自然出口认证或完整回水 |
| 河网/河槽 | 有节点/河段/typed graph、中心线和有限河床/断面几何；大量边仍标记 `needs_refinement` | 通用河网提取可复用外部库；TD 的谷地河槽实体和材质账需自研 |
| 降雨产流 | `rainfall-runoff-v1` 为独立 cell/HRU 两储库：入渗、土壤、ET、快慢库及守恒账；尚无完整空间路由 | 适合作为 TD forcing/ledger 适配；Landlab 可做参考，但不能替换 TD 身份和保存契约 |
| 河道动态水量 | 有限 1D 矩形 Manning、CFL/内部步、湖河共同步、显式边界；部分完整 900 s 事件仍因精度/预算/模型门槛未接受 | 不应称 Saint-Venant、动力波或已完成全网水动力 |
| 2D 地表水 | 有动态地表模块和多域/细网格实验接口；当前文档明确不是完整 2D 浅水发布能力 | 仍需自研 TD 的多域调度、面交换、边界和发布审计；方程可参考 Landlab/外部专用求解器 |
| 侵蚀/泥沙 | M5/M6 有单向冻结水流泥沙、Exner/床变和固体/孔隙/岩石账；床变后水力重耦合仍未完成 | 不是通用 DEM erosion 的替代；反馈和全域耦合需自研 |
| 跨尺度/拼接 | 有 fine mosaic、shared boundary、tile、Q cut、细化和资源门禁；跨精度水力交换仍开放 | 这是 TD 产品核心，不应被普通栅格 merge/resample 替代 |
| 三维/地下 | 有局部 typed graph、VDM、Boolean 切岩、覆岩/空气路径和固定两端洞道；`water=null`、完整接回和地下水力未认证 | 几何内核可借用通用库；洞道发现、地质约束、拓扑和水力需自研/耦合 |

## 工程逐项对照

### Landlab

**官方一手资料**：

- 仓库：[landlab/landlab](https://github.com/landlab/landlab)
- 官方文档：[Landlab documentation](https://landlab.readthedocs.io/)
- 组件参考：[Landlab components](https://landlab.readthedocs.io/en/latest/reference/components.html)
- 原始论文：[Hobley et al., 2017, Geoscientific Model Development](https://doi.org/10.5194/gmd-10-1645-2017)

**已有能力**：Landlab 提供规则/非规则网格、Field/Link/Grid 数据模型，`FlowAccumulator`、D8/D∞ 等流向与汇流，洼地处理/路由组件，`ChannelProfiler`/河网分析，`OverlandFlow`、`KinWaveImplicitOverlandFlow` 和相关坡面水流组件，`GroundwaterDupuitPercolator`，以及 Stream Power、SPACE、沉积/侵蚀等地貌组件。它的强项是把地形、产流、侵蚀和网格过程组合成可重复实验；不是一个开箱即用的全流域 GIS 发布器。

**对 TD 的取舍**：

- 可复用：网格抽象、流向/汇流参考、降雨到坡面水流的方程级对照、侵蚀组件的实验基线。
- 不直接复用为产品核心：Landlab 网格和组件的状态/单位/边界契约不能自动满足 TD 的 source identity、tile owner、shared node、Q cut、湖河库存、材料所有权和原子保存。
- 优先级：先用 Landlab 做小型解析地形交叉验证；只有当方程和数据模型吻合，才考虑可选 adapter，不把 Landlab API 渗入 TD 核心。

### WhiteboxTools

**官方一手资料**：

- 仓库：[jblindsay/whitebox-tools](https://github.com/jblindsay/whitebox-tools)
- 官方手册：[WhiteboxTools User Manual](https://www.whiteboxgeo.com/manual/wbt_book/)
- 原始论文：[Lindsay, 2014, Whitebox Geospatial Analysis Tools](https://www.uoguelph.ca/~hydrogeo/Whitebox/)
- 工具索引中的典型工具：[Flow Accumulation](https://www.whiteboxgeo.com/manual/wbt_book/available_tools/hydrological_analysis.html)、[Fill/Breach Depressions](https://www.whiteboxgeo.com/manual/wbt_book/available_tools/hydrological_analysis.html)、[Extract Streams](https://www.whiteboxgeo.com/manual/wbt_book/available_tools/hydrological_analysis.html)

**已有能力**：面向栅格/矢量 GIS 的洼地填充与 breach、D8/D-infinity/MFD 流向和汇流、流域/河网提取、stream burning、河谷/形态分析、部分降雪/水文分析、TIN/点云和大量地形预处理工具。它是很好的批处理基线和外部 oracle，尤其适合对照 TD 的静态 DEM 结果。

**边界**：WhiteboxTools 的主价值是 terrain/hydrology analysis，不是持续时间水动力、湖河动态交换、Exner 反馈、地下水 PDE 或洞道实体布尔。其 fill/breach 结果还会改变高程或排水假设，不能未经策略登记直接覆盖 TD 原始床面。

**对 TD 的取舍**：可作为只读外部参考和输入预处理；不应复制整套基础工具。TD 必须保存使用了 fill、breach、原床或保留 sink 的政策，并把外部结果当 derived artifact，不改原始 TD。

### TauDEM

**官方一手资料**：

- 仓库：[dtarb/TauDEM](https://github.com/dtarb/TauDEM)
- 官方文档：[TauDEM 5 documentation](https://hydrology.usu.edu/taudem/taudem5/)
- 典型文档：[D8 Flow Directions/Area](https://hydrology.usu.edu/taudem/taudem5/), [D-infinity](https://hydrology.usu.edu/taudem/taudem5/), [Stream Definition/Network](https://hydrology.usu.edu/taudem/taudem5/)
- 基础论文：[Tarboton, 1997, A New Method for the Determination of Flow Directions and Upslope Areas](https://doi.org/10.1029/96WR03137)

**已有能力**：MPI/并行大栅格处理，D8、D∞、多流向/上坡面积，pit removal，stream definition/order/network，watershed、褐地/湿度指数等。TauDEM 的分布式处理、边界 halo 和大栅格思路对 TD 的大区域预处理有参考价值。

**边界**：它解决的是基于 DEM 的地形水文派生，不是降雨—土壤—ET—地下水完整模型，也不是 1D/2D 河道水动力或河床演变。pit removal 是一个明确的地形预处理政策，不能与 TD 的“闭合盆地作为湖泊/内流域候选”混用。

**对 TD 的取舍**：优先作为 D8/D∞/大栅格静态结果的交叉实现；必要时通过进程/文件 adapter 使用，保留版本、参数、投影、nodata 和 tile 边界证明。不要把 TauDEM 的 stream raster 直接当作 TD 的河段实体、断面或自然出口。

### TopoToolbox

**官方一手资料**：

- 仓库：[wschwanghart/topotoolbox](https://github.com/wschwanghart/topotoolbox)
- 官方文档：[TopoToolbox documentation](https://topotoolbox.github.io/)
- 原始论文：[Schwanghart & Kuhn, 2010, TopoToolbox](https://doi.org/10.1016/j.envsoft.2009.12.002)
- 后续论文/版本入口：[TopoToolbox publications](https://topotoolbox.github.io/papers.html)

**已有能力**：MATLAB 地形对象、流向/汇流/流域、河网提取和 graph analysis、纵剖面、chi/ksn 等河流地貌分析、DEM 处理和尺度研究。它在“地形—河网—河流纵剖面—地貌解释”链条上很强。

**边界**：不是 TD 的动态水量或三维几何运行时；MATLAB 数据对象和 TD 的 Python/保存契约需要明确转换。其河网分析结果不包含 TD 所需的水面库存、shared face、材料账和 Minecraft 坐标消费。

**对 TD 的取舍**：用于纵剖面、河网形态、尺度敏感性和候选提取的独立参照；不移植其对象模型到核心，不把“提取出河线”当成“生成可施工河槽”。

### RichDEM

**官方一手资料**：

- 仓库：[r-barnes/richdem](https://github.com/r-barnes/richdem)
- 官方文档：[RichDEM documentation](https://richdem.readthedocs.io/)
- 原始论文：[Barnes, 2016, RichDEM: High-Performance Terrain Analysis](https://doi.org/10.1016/j.cageo.2016.07.001)

**已有能力**：高性能栅格地形分析，Priority-Flood 系列洼地处理、D8/D∞/MFD 流向和汇流、watershed、坡度/曲率及相关派生。它适合作为快速、确定性的静态基线。

**边界**：不提供 TD 需要的降雨产流状态、河道/湖泊动态库存、1D/2D 水动力、沉积反馈、地下水或洞道几何。Priority-Flood 只回答“如何处理栅格洼地”，不回答“这个 TD 洼地是否应成为湖、内流域、受控边界或未认证区域”。

**对 TD 的取舍**：可用于算法交叉验证和性能对照；不复制为 TD 的第二套排水内核，不直接消费其填洼后的高程生成实体河槽。

### pyflwdir

**官方一手资料**：

- 仓库：[Deltares/pyflwdir](https://github.com/Deltares/pyflwdir)
- 官方文档：[pyflwdir documentation](https://pyflwdir.readthedocs.io/)
- Deltares 官方项目组织：[Deltares hydrology software](https://github.com/Deltares)

**已有能力**：从栅格流向编码构造流向对象，支持 D8、LDD 等常见编码，进行 upstream area/accumulation、basin、subbasin、stream order、flow distance、出口和沿流路径等无循环图操作；对全球/大栅格和 GIS 数据管线友好。

**边界**：主要是 flow-direction graph utilities，不是降雨—入渗模型、水动力、侵蚀或地下水模拟器；它不会替 TD 决定填洼/破洼政策，也不会生成河槽横断面或三维洞道。

**对 TD 的取舍**：最适合作为“已确定流向后的轻量图计算 adapter”或独立 oracle，尤其可对照 donor CSR、累计面积、basin 和 stream order。TD 仍应保留自己的 provenance、开放边界和 failure-prefix 保存协议。

## 按功能横向比较

| 功能 | Landlab | WhiteboxTools | TauDEM | TopoToolbox | RichDEM / pyflwdir | TD 当前判断 |
|---|---|---|---|---|---|---|
| 汇流/流向 | D8/D∞ 与组件化网格 | 多种栅格算法 | D8/D∞、并行 | FlowObject/graph | 高性能栅格/flow graph | 不重写通用内核；保留 TD graph、Q 账和边界语义 |
| 洼地处理 | depression finder/router | fill、breach、保留/分析 sinks | pit removal、平坦区处理 | DEM/流向处理 | priority-flood 等 | 复用算法思想/外部 oracle；TD 自研湖盆分类、鞍点和审计 |
| 河网提取 | channel profiler、network | stream raster/network 工具 | stream definition/order/network | stream network、纵剖面 | stream/watershed graph | 外部结果只做候选；TD 自研河段实体、谷地中心线、断面和材质 |
| 降雨产流 | runoff/overland-flow 组件 | 零散水文分析，不是统一产流框架 | 主要 DEM 派生 | 主要地貌分析 | 无完整产流框架 | TD 已有两库 forcing；可用 Landlab 做参考，不替换 TD ledger |
| 1D 河道水动力 | 组件可组合，非专用全网河道产品 | 无主水动力求解器 | 无主水动力求解器 | 无主水动力求解器 | 无 | TD 的 1D storage/Manning 仍需自研与验收，但不应宣称完整 Saint-Venant |
| 2D 地表水 | OverlandFlow/KinWave 等 | 无完整 2D 浅水核心 | 无 | 无 | 无 | TD 仍需自研多域、交换、边界和守恒发布；方程可对照 Landlab/专用库 |
| 侵蚀/泥沙 | stream-power、SPACE 等 | 地形分析/部分 erosion 工具 | 非核心 | 河流地貌分析 | 非核心 | TD 的 Exner、材料所有权、床变后重耦合仍需自研 |
| 跨尺度/大栅格 | 网格/field，可组合 | 大量栅格工具 | MPI/分块强 | 依赖 MATLAB 工作流 | 高性能栅格 | TD 的跨 tile/精度守恒交换、source pins 和失败门禁不可外包 |
| 三维几何 | 网格场，不是实体 CAD | GIS/TIN/点云 | 栅格 | 地形对象 | 栅格 | TD VDM/Boolean/覆岩/材料账需自研或调用通用几何库 |
| 地下水 | Dupuit 近似组件 | 非核心 | 非核心 | 非核心 | 无 | 多孔介质用 MODFLOW 6/FloPy adapter；TD 负责边界/耦合语义 |
| 洞道几何 | 无专门洞穴工作流 | 无专门洞穴工作流 | 无 | 无 | 无 | 测量表达用 Therion/CaveWhere；自然洞道发现、实体接回和水力需自研 |

## 地下水与洞道候选工具

### MODFLOW 6 与 FloPy

- [MODFLOW 6 官方仓库](https://github.com/MODFLOW-ORG/modflow6)
- [MODFLOW 6 官方文档](https://modflow6.readthedocs.io/)
- [USGS MODFLOW 软件页](https://www.usgs.gov/software/modflow-6-usgs-modular-hydrologic-model)
- [FloPy 官方仓库](https://github.com/modflowpy/flopy)
- [FloPy 官方文档](https://flopy.readthedocs.io/)

MODFLOW 6 提供模块化地下水流、输运和耦合模型；FloPy 是 Python 建模、输入生成、结果读取和后处理接口。它们适合 TD 的含水层、压力水头、补给、排泄、河流/排水边界等多孔介质问题。TD 不应重新实现地下水 PDE；应自研一个隔离 adapter，把 TD 的 source/CRS/水文域、地表河网和洞道交换边界映射为 MODFLOW package，并把时间步、单位、网格和残差作为保存身份。

限制很关键：MODFLOW 的规则/非结构化地下介质网格不是“洞道几何生成器”，默认河流包也不是自由液面洞穴明渠或压力管完整模型；若把洞道等效为高导通单元，必须明确这是模型化近似，并单独验证与地表接回的质量守恒。

### Therion、CaveWhere 与 OpenPNM

- [Therion 官方仓库](https://github.com/therion/therion)
- [Therion 官方站点与文档](https://therion.speleo.sk/)
- [CaveWhere 官方仓库](https://github.com/Cavewhere/Cavewhere)
- [CaveWhere 官方站点](https://cavewhere.org/)
- [OpenPNM 官方仓库](https://github.com/PMEAL/OpenPNM)
- [OpenPNM 官方文档](https://openpnm.org/)

Therion/CaveWhere 的价值是洞穴测量数据、站点/中心线、断面和三维可视化/制图；它们可作为 TD 洞道 survey import/export 或人工校验格式，不会从 TD 地形自动发现自然洞道，也不负责水量和地下水力。OpenPNM 解决孔隙网络介质中的几何/传输抽象，适合微观渗流研究，不适合直接表示百米尺度、有洞顶/洞底/开口的 TD gallery。

三者的合理接法是：TD 保留 typed surface–sink–conduit–spring 图和实体材料账；Therion/CaveWhere 作为测量/审查交换；MODFLOW 6/FloPy 作为多孔介质地下水后端；洞道内的自由面、压力管、溢流和地表交换仍由 TD 的专门 1D/2D conduit model 负责。不要以导入一条测量中心线冒充完整地下水系。

## 哪些功能应直接借用、哪些必须自研

### 建议借用或只读适配

- **静态 DEM 水文派生**：选一个主 reference（建议 pyflwdir/RichDEM 或 TauDEM），用 WhiteboxTools/TopoToolbox/Landlab 做交叉验证；保存算法、版本、参数、CRS、nodata、边界和输入 SHA。
- **洼地基础算法**：优先使用成熟 fill/breach/priority-flood 实现或以其结果做 oracle；TD 只实现策略层：原床、填洼、破洼、保留闭合盆地、人工/自然出口和拒绝条件。
- **通用地下水 PDE**：用 MODFLOW 6/FloPy，不在 TD 内另造通用含水层求解器。
- **洞穴测量交换**：支持 Therion/CaveWhere 的中心线/站点/断面导入导出，用于审查和人工输入；不把外部中心线直接发布为 TD 水系。
- **通用网格/布尔/空间索引**：可以依赖成熟库，但必须把网格版本、容差、实体角色、源采样和材料账锁进 TD artifact；不能只以 mesh 相交成功作为连通证明。

### 仍需 Terragenesis 自研

- **TD 来源契约**：Terrain Diffusion identity、坐标轴/单位/CRS pending 语义、原始数据不可变、派生包身份、跨 tile owner 和 shared node。
- **流域与河网产品层**：从外部 flow graph 到 TD 的不可变节点/河段/湖泊/边界图，维护 local Q、accumulated Q、terminal cut、开放边界和失败前缀。
- **湖泊与河槽几何**：天然盆地合并、最低鞍点、多出口、共同水面、回水、谷地中心线、曲率/坡度、真实断面和河床实体；不能用 stream raster 或显示平滑代替。
- **动态水量与水动力发布**：产流—坡面—河道—湖泊—地下交换的时间语义、守恒 ledger、有限 1D/2D 求解、细化/资源预算、边界和冷读审计。若要完整 2D 浅水或 Saint-Venant，应先明确方程、稳健性、干湿界面、回水和发布门槛，不能将现有简化模块改名。
- **泥沙与形态反馈**：侵蚀、沉积、Exner、固体/孔隙/岩石库存、床变后的几何和水力重耦合，以及局部/全域材料所有权。
- **跨尺度/拼接调度**：共享面、halo、网格细化与粗化、跨 tile 传输、不同精度时间交换、重复库存消除、Q/水/泥沙守恒和失败恢复。普通 raster mosaic 只能处理数组拼接，不能承担这些物理语义。
- **地下暗河闭环**：洞口自动候选、地层/覆岩/断层约束、路线搜索、分叉汇合、多层拓扑、表面—洞道—复出端口、洞内水力、地下水交换和自然出口认证。
- **三维交付与 Minecraft 适配**：VDM、Boolean 实体、覆岩、空气/水域、切岩和材料账的绑定，以及物理米制到方块坐标的显式消费；前端只读 artifact，不在显示层推导水面或连通性。

## 推荐的最小集成路线

1. **建立 reference suite**：固定小型解析 DEM、真实 TD 窗口和一个闭合盆地；分别用 pyflwdir/RichDEM、TauDEM、WhiteboxTools、TopoToolbox、Landlab 输出流向、面积、盆地和河网，记录差异而不篡改 TD。
2. **收敛 TD 的静态策略**：明确哪些结果是原床、fill、breach、spill network、湖泊候选；外部库只产生 derived artifact，不能跳过 TD 的 provenance 和 acceptance gate。
3. **先完成跨域守恒再扩大方程**：M7 多精度交换、共享边界、湖河回水和全域河槽优先于接入更多算法库；外部工具不解决这些产品级契约。
4. **地下分层集成**：先以 MODFLOW/FloPy 做多孔介质基线，以 Therion/CaveWhere 做几何交换，再定义洞道内 1D/2D conduit model 和 surface exchange；固定洞道 V1 不升级为地下水完成。
5. **把外部库当 oracle，不当发布标志**：所有比较结果保存版本/参数/输入 SHA 和单位；只有 TD 自己的连续性、守恒、跨尺度、几何、资源和冷读门槛通过，才提升 `hydraulic_ready`、`natural_outlet_verified` 或 `publishable`。

## 来源与证据说明

- 外部能力判断均指向上述项目的官方仓库、官方文档或论文原文；访问日期为 2026-10-09。
- 当前 TD 判断来自工程内已保存文档和接口命名，尤其是 `docs/td-river-milestones-1-2-20261008.md`、`docs/td-river-m3-m4-coupling-20261008.md`、`docs/td-river-m5-m6-20261008.md`、`docs/underground-river-v1.md`、`docs/surface-fine-mosaic-v1.md` 与 `docs/hybrid-river-network.md`。
- 本报告没有把“存在源码入口”当成“能力通过”；对 TD 仍开放、失败或标记为 `false` 的项目能力保持原状态。
