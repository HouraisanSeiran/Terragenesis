# 路径约束 VDM 流水侵蚀：物理依据与工程边界

日期：2026-09-28。性质：研究设计，非现有模组效果或实现声明。

## 结论与表示分层

沿预设路径扫出的三维管状区域可以作为**作用域**：给河道、岩壁和河岸提供有限支撑的权重 M(p)，并规定入流、出口和待处理岩层。它不是水流速度、压力或剪应力的解。将管半径、距中心线距离直接当作侵蚀率，最多是美术规则。较严谨的组合是：路径与流域确定边界条件；水力模型求水深、流速和边界剪应力；基岩与松散沉积物分别求侵蚀、搬运和沉积；最后把允许保持拓扑的几何变化写入 VDM。管状蒙版可乘在材料可蚀系数或过程速率上，并在边缘逐渐归零，不能代替守恒方程。

## 可借用的成熟方程

**明渠浅水流。** Saint-Venant 方程是对水深积分的质量、动量守恒；平面形式可写为 `∂h/∂t + ∇·(h u)=r`，`∂(h u)/∂t + ∇·(h u⊗u + 1/2 g h² I)= -g h∇b + friction`。这里 h 是水深，u 是深度平均水平速度，b 是河床高程。Clawpack 官方浅水方程章节给出这一类水深积分模型 [1]。在普通坡面或河床上可使用局部二维近似；在竖直壁、悬挑底面或强曲率三维表面上，直接套用平面 XZ 网格及竖直水深会失真。

**泥沙和基岩分账。** 若只求总输沙且忽略水体内悬沙库存变化，经典 Exner 形式可写为 `(1-λp)∂z_b/∂t + ∇·q_s = 0`，其中 λp 是床层孔隙率，q_s 是总固体体积通量。若显式模拟悬沙，则需分开库存：`(1-λp)∂η/∂t + ∇·q_b = D-E_s`，`∂(h c)/∂t + ∇·(h c u) = E_s-D`；这里 η 是可动床层厚度，q_b 仅为床载通量，c 为水中固体体积分数，E_s 与 D 是床层和悬沙间等量交换。两式相加后交换项抵消；基岩退缩 `E_r` 须另记供沙源，不能把岩石磨蚀直接当成已存在的悬沙。SPACE 原论文把基岩侵蚀、沉积层侵蚀、输运和沉积作为耦合但不同的库存/通量 [2]。这些式子是工程记账框架，符号及床面运动需随选用求解器统一。

**侵蚀驱动。** 大尺度地貌演化可参考 stream-power 形式 `E=K A^m S^n`（有阈值及河宽变体）；它用汇水面积/流量与坡度估计长期下切，不给出岩壁局部三维压力场。对缓变、近似均匀明渠，平均床面剪应力可近似 `τ_b≈ρ g R S_f`，R 是水力半径，S_f 是能量坡度；不能把这个公式不加修正地施到垂直壁、急弯、落水或自由射流。局部经验基岩退缩可设 `E_r=M k_e max(τ_b-τ_c,0)`，若 E_r 单位为长度/时间，则 k_e 的单位必须为长度/(时间·压强)，M 无量纲。τ_c 与 k_e 应按岩性、节理、磨蚀物供给标定；沉积物起动、岩石磨蚀和化学溶蚀不能共享一个无定义的 E。此处 `τ_b` 关系与阈值律是可检验的工程近似，不是这几篇图形学论文替本项目推导出的定律。

## 贴壁水、三维几何与 VDM

若沿变形后的表面 `P(u,v)` 做局部薄水层，必须以真实切向、边长和面积计算通量，而非把 `(u,v)` 当等距平面。度量 `g_ij=∂iP·∂jP` 决定面积元 `sqrt(det g) du dv`；切向重力 `g_t=g-(g·n)n` 决定重力沿面分量。曲率、接触、表面张力和流体惯性会影响是否贴附。首版若用沿面下坡分流，须明说其为简化输水模型，不能声称求解了曲面 Saint-Venant 方程。

接触门控尤其重要：在凸缘/悬挑处无法维持接触时，水应离壁自由落下；撞击下方表面后才重新计入贴壁水。开口明渠和薄膜有自由表面；充满洞穴管道的受压流需压力求解及不同边界条件，不能用同一“沿面水深”表示。地下河还可能在两种状态间转换，本设计暂不提供该转换模型。

当表面保持顶点对应和拓扑时，岩体朝内退缩可写 `P_new=P_old-Δt E_r n`，再写入 VDM 位移；注意法线方向、位移上限、相邻面片一致性和网格自交。局部表面面积变化意味着体积通量和岩石移除量应按真实面积积分。VDM 只移动对应顶点，不会自动穿孔、分裂岩块或产生新洞穴连通。若侧蚀掏空、拱/洞形成、支撑失稳，需要转入多层高度图、体素/隐式体或重拓扑表示。Nilles 等的多层高度图工作正是利用横向侵蚀与列分裂表现悬挑、拱及部分洞穴，并做支撑检查 [4]；其结果不能归功于单值 VDM。

## 图形学中相近的工作

| 工作 | 已发表的方法 | 与本方案的关系与差别 |
|---|---|---|
| Génevaux 等，*Terrain Generation Using Procedural Models Based on Hydrology* (2013) [3] | 先从几何排水图构建层级河网及流域，再组合程序地形与河道面片，使用融合/刻蚀操作。 | 支持“路径/河网约束地形”的建模层；不等于沿 VDM 三维表面求水力。 |
| Schott 等，*Large-scale Terrain Authoring through Interactive Erosion Simulation* (2023) [5] | 以曲线/点高程约束和抬升域控制地形，结合 stream-power 侵蚀、快速排水与流向路由，融合有水文一致性的地形面片。 | 与“可控路径 + 侵蚀”的创作目标很近，但仍是大尺度地表，不是三维洞穴或 VDM 贴壁水力。 |
| Nilles 等，*3D Real-Time Hydraulic Erosion Simulation using Multi-Layered Heightmaps* (2024) [4] | 扩展高度图和 virtual pipes，水横向侵蚀相邻基岩，可分裂列，形成悬挑、拱和部分洞穴，并检查支撑。 | 与三维侧蚀/拓扑变化最接近；用多层高度图及可变列，不是固定顶点 VDM。 |
| SPACE 1.0 (2017) [2] | 地貌演化中区分基岩、可动沉积物和输沙沉积。 | 提供物质收支结构；原模型是地表尺度，不是竖直崖壁流体求解器。 |

## 可实施的验证顺序

1. 在有界样区固定河网、流量和出口；记录每一步水输入、存储变化、边界输出、沉积物与基岩库存，误差用物理单位报告。
2. 平坦明渠、恒定坡度、弯道和坡度突变分别测试水深/流量/剪应力；曲面网格旋转或重参数化后，通量与总侵蚀量应接近不变。
3. 检查蒙版边缘、区域缓存边界、同一路径跨区接缝；不同窗口及生成顺序不应改变共享内域结果。
4. 在竖壁、悬挑和凸缘样片测试接触/脱离/再撞击；与实验或高分辨率自由表面解对照前，不宣称物理真实。
5. 测试 VDM 顶点对应、法向约定、单步位移上限、网格自交与支撑；穿孔、分裂及塌落必须切换表示并单独验收。

## 已核实来源

1. Clawpack, *The Shallow Water Equations*，官方 Riemann book，2026-09-28 访问返回 HTTP 200；本地快照 `clawpack-shallow-water.html`。https://www.clawpack.org/riemann_book/html/Shallow_water.html
2. Shobe, Tucker & Barnhart (2017), *The SPACE 1.0 model: a Landlab component for 2-D calculation of sediment transport, bedrock erosion, and landscape evolution*, GMD 10, 4577–4604，DOI `10.5194/gmd-10-4577-2017`；出版页 HTTP 200；本地快照 `space-paper.html`。https://gmd.copernicus.org/articles/10/4577/2017/
3. Génevaux, Galin, Guérin, Peytavie & Benes (2013), *Terrain Generation Using Procedural Models Based on Hydrology*, DOI `10.1145/2461912.2461996`；Crossref 元数据及摘要保存于 `hydrology-terrain-crossref.json`。https://doi.org/10.1145/2461912.2461996
4. Nilles, Günther, Wagner & Müller (2024), *3D Real-Time Hydraulic Erosion Simulation using Multi-Layered Heightmaps*, Eurographics VMV，DOI `10.2312/vmv.20241211`；出版社题录/摘要已核，快照见 `../sources/multilayer-hydraulic-erosion-2024.html`。https://diglib.eg.org/items/deefa865-6a25-4463-adcd-d8de2b37507e
5. Schott, Paris, Fournier, Guérin & Galin (2023), *Large-scale Terrain Authoring through Interactive Erosion Simulation*, DOI `10.1145/3592787`；Crossref 题录及摘要核对。https://doi.org/10.1145/3592787

HEC-RAS 文档域名在此次环境中无法解析，未将其列作已核实来源。本文没有找到并核实一个恰好将“管状路径约束 + 曲面水力 + VDM 位移”合成单一成熟算法的来源。
