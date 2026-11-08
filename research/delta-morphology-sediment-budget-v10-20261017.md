# 三角洲形态与泥沙收支：v10 算法对照笔记

**日期：2026-10-17**　**范围：**为 Terragenesis v10（风格化陆侧河口湿地）整理现实三角洲形态、分汊和泥沙供给的高可信来源。文中“来源事实”来自所列官方资料或原始论文；“对 v10 的建议”是本项目推论，不是来源原文结论。

## 来源与可核验事实

1. **河流主导、波浪主导、潮汐主导的形态分类。** Galloway 的经典三端元图把三角洲按河流、波浪、潮汐相对作用区分：河流主导常见鸟足状/细长分汊；波浪主导沿岸再分配形成平滑弧形岸线；潮汐主导形成潮汐沟槽、潮汐沙脊和较宽的潮汐通道。该分类及形态示例由原始论文给出（Galloway, 1975, *Geological Society of America Bulletin*, DOI: [10.1130/0016-7606(1975)86<651:SED>2.0.CO;2](https://doi.org/10.1130/0016-7606(1975)86%3C651:SED%3E2.0.CO;2)）。
   - **对 v10 的建议：**把“河流主导”作为当前默认情景；潮汐/波浪应是显式边界模式，未输入潮差、沿岸流或波浪能时不要自动生成潮汐沟槽或平滑沿岸沙脊。三端元可映射为参数，而不是固定几何模板。

2. **河口沙坝会控制分汊网络。** Edmonds & Slingerland 以河口射流、河口沙坝和通道分流为核心，指出沙坝的形成与破坏能触发分汊、改变通道长度与水沙分配；其摘要明确将 mouth-bar mechanics 与 distributary-network morphodynamics 联系起来（Edmonds & Slingerland, 2007, *JGR Earth Surface*, DOI: [10.1029/2006JF000574](https://doi.org/10.1029/2006JF000574)，出版社记录可核验于 [Crossref](https://api.crossref.org/works/10.1029/2006JF000574)）。
   - **对 v10 的建议：**分汊不应只由预设 50/30/20 比例或三条射线产生。至少需要“入口通量 → 沙坝/浅滩沉积 → 局部阻力上升 → 邻支重分流”的事件链，并在每步重新计算可达湿路径。

3. **河流、波浪和潮汐共同决定三角洲平面及沉积收支。** NOAA 的 National Centers for Environmental Information 提供全球河流流量、悬沙和地形/海岸数据产品入口；其河流与海岸观测说明河流携带的泥沙在河口因流速降低沉降，并受波浪、潮汐和沿岸流再搬运（NOAA NCEI 数据与说明入口：[https://www.ncei.noaa.gov/products](https://www.ncei.noaa.gov/products)；海岸与海洋观测专题：[https://www.noaa.gov/oceans-coasts](https://www.noaa.gov/oceans-coasts)）。这些是边界数据来源，不等于某一具体三角洲的校准值。
   - **对 v10 的建议：**输入接口应显式区分流量、固体来沙量/粒级、海平面、潮差和波浪（可先设为关闭）。没有固体来沙预算时，不能把构造填方体积当作“自然沉积”。

4. **全球三角洲正在经历沉降、海平面上升和人类拦沙的复合影响。** NASA Earth Observatory 对全球三角洲变化的遥感综述指出，三角洲地表高程变化取决于沉积补给、压实/沉降、海平面变化及人类工程；卫星时序可用于岸线和地表变化监测（NASA Earth Observatory, “Deltas at Risk”, [https://earthobservatory.nasa.gov/features/Deltas](https://earthobservatory.nasa.gov/features/Deltas)）。
   - **对 v10 的建议：**把“海岸线扩张”与“陆地高程增加”分开记账；未来加入沉降或海平面情景时，应允许同样来沙量得到退缩、淹没或沿岸迁移，而不是单调向海增长。

5. **泥沙收支必须保留开放边界和粒级差异。** USGS 的沉积物输运资料将悬沙浓度、颗粒粒径、流量和河床/河岸条件作为输沙估算的基本观测量；USGS Coastal and Marine Geology 资料也把三角洲视为陆海沉积物交换界面（USGS Water Resources sediment transport 入口：[https://www.usgs.gov/mission-areas/water-resources/science/sediment-transport](https://www.usgs.gov/mission-areas/water-resources/science/sediment-transport)；USGS Coastal and Marine Geology：[https://www.usgs.gov/centers/whcmsc](https://www.usgs.gov/centers/whcmsc)）。
   - **对 v10 的建议：**每个时间窗至少输出：入口固体体积、陆地沉积、再悬移/移动库存、海侧外排、未输送余量和体积残差；细泥与沙应有不同沉降/扩散参数。当前 v10 的大范围构造挖填账与实际供沙账分开是正确方向，应继续保持。

6. **Reduced-complexity DeltaRCM 的一手机制。** Liang, Voller & Paola 的 Part 1 使用水面坡和惯性方向路由水沙，分别处理砂与泥，沉积/侵蚀后更新水深和速度；Part 2 评估流路由与层序结果（Part 1: [10.5194/esurf-3-67-2015](https://doi.org/10.5194/esurf-3-67-2015)；Part 2: [10.5194/esurf-3-87-2015](https://doi.org/10.5194/esurf-3-87-2015)）。该模型是过程近似，不是 v10 现实预测的验证。
   - **对 v10 的建议：**沿用“水面坡优先于单纯地形坡、每步更新湿路径和水深、沉积受有限库存约束”的结构；不要把 DeltaRCM 的参数直接当作自然三角洲标定值。

## 当前 v10 与现实机制的差距

- v10 验收记录显示场景 09 的 16 km 大范围平原主要由显式地形构造生成，构造挖填与实际输沙分账；这适合风格化展示，但不能解释为由已输入来沙量自然长成的完整三角洲（见 [`docs/delta-landward-v10-20261017.md`](../docs/delta-landward-v10-20261017.md)）。
- 该记录明确 `hydraulic_ready=false`，使用静态设计水位；因此尚未表达回水、潮汐、波浪或水面—床面双向反馈。按上述来源，分汊和岸线类型对这些边界条件敏感。
- 已验收的同源供沙案例有有限固体收支，但覆盖范围较小；不能把它外推为公里级平原的自然沉积量。应将“供沙案例”和“风格化构造场景”继续作为两个版本身份。

## 建议的 v10 后续最小对照

1. 增加一个**河流主导基线模式**：关闭潮汐/波浪，使用真实入口流量与固体来沙，分汊由沙坝阻力反馈触发；输出逐窗收支。
2. 用同一入口和来沙量做三组边界对照：无海动力、波浪再分配、潮汐往复；只改变海动力参数，比较分汊数、岸线粗糙度、陆地净沉积和外排量。
3. 对每个模式保存 `sediment_budget`（入口、沉积、再悬移、外排、余量、残差）及 `construction_budget`，并在报告中明确哪部分来自过程演化、哪部分来自风格化构造。

上述建议用于下一版实验设计；本笔记没有修改算法、默认世界或场景文件。
