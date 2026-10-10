# 现实河流形态、侵蚀沉积与地下暗河资料研究

- 访问日期：2026-10-09
- 范围：现实资料研究与对Terragenesis的建模建议；不修改算法、前端或测试代码。
- 证据原则：优先采用USGS、USACE、NOAA、NASA/ESA、UNESCO、政府数据集和原始论文。现实案例用于约束可观测现象，不把扩散生成山地或游戏地形认证为现实地点。

## 1. 平面形态

### 1.1 形态分类与可观测量

USGS的经典报告把冲积河道归纳为直流、曲流和辫状三类，并以坡降、流量、河床材料、河岸稳定性和河道宽深比解释形态转变；因此分类不应只按平面图上的“弯不弯”判断。[Leopold & Wolman, USGS Professional Paper 282-B](https://pubs.usgs.gov/pp/0282b/report.pdf)

- 直流：常见于受基岩、工程岸线或坡降较稳定的河段；应量化中心线曲率、河宽、河岸约束和纵坡，而不是把像素直线直接等同于自然直河。[USGS PP 282-B](https://pubs.usgs.gov/pp/0282b/report.pdf)
- 曲流：外弯为cutbank（冲刷岸），内弯为point bar（点坝）；中心线曲率、弯曲度、波长/河宽、迁移速率、截弯取直次数和废弃河道面积是可复测指标。[USGS PP 282-B](https://pubs.usgs.gov/pp/0282b/report.pdf)；[Hickin & Nanson, 1984, DOI:10.1016/0022-1694(84)90063-9](https://doi.org/10.1016/0022-1694(84)90063-9)
- 辫状：多个同时活动的汊道由沙洲分隔，汊道会分流、再汇合、封堵和重开；应记录活动水面占比、汊道数、分汊/汇流节点、沙洲面积、主流量分配和时间尺度。[USGS PP 282-B](https://pubs.usgs.gov/pp/0282b/report.pdf)
- 分汊、冲积扇、三角洲和河口：分汊可由河床沉积或岸线/构造约束形成；冲积扇是山口出流后坡降降低造成的扇状沉积体系；三角洲是河流向静水体输入泥沙后形成的前缘、分流河道和潮汐/波浪改造体系。三者都必须显式表达出口边界、沉积体积和分流拓扑。[USGS PP 282-B](https://pubs.usgs.gov/pp/0282b/report.pdf)；[NOAA National Estuarine Research Reserve System](https://coast.noaa.gov/nerrs/)

### 1.2 具体案例

| 案例 | 形态与量化观测 | 对模型的意义 |
|---|---|---|
| 密西西比—阿查法拉亚系统 | USACE说明Old River Control用于维持密西西比河与阿查法拉亚河的分流格局，并把进入阿查法拉亚的流量控制在约30%；这是真实的河流捕获风险、分流和人为约束共存案例。[USACE, Old River Control](https://www.mvn.usace.army.mil/Missions/Engineering/Old-River-Control/)| 分汊比例必须是有边界的水沙分配，不应每个格点独立选最大坡降；分流比例还会受工程控制和洪水状态影响。 |
| 黄石河 | USGS长期河流走廊研究使用重复航片、断面和洪水资料跟踪河岸迁移；2011年大洪水后，部分河段出现明显河岸侵蚀、河道重组和侧向迁移。[USGS Yellowstone River Corridor](https://www.usgs.gov/centers/northern-rockies-science-center/science/yellowstone-river-corridor) | 洪水事件应能一次性改变多个断面和汊道，而非只按平均年流量平滑磨损；应保存洪水前后河岸线和物质收支。 |
| 恒河—雅鲁藏布江—Jamuna | 原始遥感研究将Jamuna描述为宽阔、多汊、强烈侧向迁移的辫状河；Landsat时间序列可按年度提取水面、沙洲和岸线变化。[Ashmore et al., 2011, DOI:10.1016/j.geomorph.2011.03.013](https://doi.org/10.1016/j.geomorph.2011.03.013) | 分汊网络需要“活动汊道生命周期”：形成、扩宽、封堵、再汇合；静态Voronoi或固定河槽不能代表该过程。 |
| 科罗拉多河三角洲 | 2014年环境脉冲流把水重新送入干涸的三角洲河道；NASA记录脉冲流持续约8周，并使水流到达加利福尼亚湾，遥感观察到植被和水面恢复。[NASA Earth Observatory, Colorado River Delta](https://earthobservatory.nasa.gov/images/83567/a-pulse-of-water-in-the-colorado-river-delta) | 三角洲事件可简化为有持续时间的入流、沉积前缘和植被/湿地占据变化；不应把一次水面恢复当成长期天然河口平衡。 |
| 多瑙河三角洲 | UNESCO记载多瑙河在三角洲处分成三条主要分支，并形成湖泊、芦苇湿地、沙洲和河口海岸环境；其世界遗产资料提供了分流—湿地—黑海出口的空间证据。[UNESCO Danube Delta](https://whc.unesco.org/en/list/588/) | 三角洲需允许分支、湿地库容、湖泊和海岸边界共同存在；“一条河线到海”是明显的低阶近似。 |
| 牛轭湖与截弯取直 | USGS地学资料把曲流颈部缩短、洪水切穿和旧河段隔离列为牛轭湖形成机制；工程截弯取直则把弯道变为废弃水体，改变坡降、流速和下游输沙。[USGS, Oxbow lakes](https://www.usgs.gov/media/images/oxbow-lake)；[USACE, Channel improvement](https://www.publications.usace.army.mil/) | `cutoff`应是拓扑事件：新捷径、旧弯道、入口/出口封闭状态和库水体，而不只是平面曲线拉直。 |
| 河流袭夺、决口改道 | USGS把河流袭夺定义为一个流域的河流通过侵蚀或构造过程夺取邻近流域上游水量；决口改道则常在洪水越过天然堤或冲破河岸后发生，需由分水岭、河岸高程和洪峰事件共同触发。[USGS, Stream piracy](https://www.usgs.gov/centers/whcmsc/science/stream-capture)；[USGS, Avulsion](https://www.usgs.gov/centers/whcmsc/science/avulsion) | 这是流域拓扑改变，不适合用局部高度平滑代替；低阶实现应先做受约束的候选事件和审计输出。 |

## 2. 侵蚀与沉积

### 2.1 过程链

1. **下切与洪水冲刷**：流量、坡降、床面剪切应力和可蚀性共同决定河床是否下切；洪水可以短时增加床面冲刷、岸脚淘刷和河岸坍塌。[USGS PP 282-B](https://pubs.usgs.gov/pp/0282b/report.pdf)；[USGS, Streambed scour](https://www.usgs.gov/mission-areas/water-resources/science/streambed-scour)
2. **侧蚀、cutbank与point bar**：弯道外侧速度和近岸剪切增强，内侧发生沉积；点坝会随洪水和低流量交替生长、再搬运，不能把单次剖面沉积当作永久填高。[Hickin & Nanson, 1984](https://doi.org/10.1016/0022-1694(84)90063-9)；[USGS PP 282-B](https://pubs.usgs.gov/pp/0282b/report.pdf)
3. **河岸坍塌**：河岸失稳不只由水流剪切造成，还受岸高、土体黏聚力、植被根系、孔隙水压力和地下水出逸影响；坍塌会把块体或细颗粒一次性加入输沙账。[USGS, Bank erosion](https://www.usgs.gov/centers/upper-midwest-environmental-sciences-center/science/riverbank-erosion)
4. **泥沙分选与床面装甲**：洪水优先搬运细颗粒，粗颗粒残留会形成装甲层；粒径级配、临界起动、沉降速度和床面交换层至少要分级记录，否则“侵蚀量”无法对应出口泥沙量。[USGS, Sediment transport](https://www.usgs.gov/mission-areas/water-resources/science/sediment-transport)；[Parker, 1990, University of Minnesota report](https://hdl.handle.net/11299/108731)
5. **三角洲前缘推进与河口改造**：河流输入的泥沙在口门附近沉积，随后由潮汐、波浪和沿岸流重分配；河口不是静止的三角形，必须区分河流主导、潮汐主导和波浪主导的输运方向。[NOAA Estuarine Research Reserve System](https://coast.noaa.gov/nerrs/)；[NOAA Digital Coast](https://coast.noaa.gov/digitalcoast/)

### 2.2 适合米制事件的过程

**可立即简化**：

- 以米、秒、立方米、千克为单位，做单向河段的下切/侧蚀/沉积事件；输入洪水持续时间、流量、坡降、河宽、床面粒径和可蚀性，输出床面高程、岸线、固体泥沙、孔隙体积和外运量。
- 做局部cutbank—point bar成对事件；用弯道内外侧的有符号横向通量近似，不把整个弯道直接平滑。
- 做床面分级库存和装甲阈值；至少分细、中、粗三类，保留每类入流、沉积、再悬移和出口账。
- 做三角洲边界事件：有限沉积前缘推进、有限分汊和开放海洋外运；沉积体积、孔隙率和可用体素余量必须分账。

**需要真实数据才能启用**：河岸坍塌概率、潮汐/波浪再分配、河口回水、泥沙级配参数、植被根系稳定、洪水冲刷系数和三维床面装甲。没有断面、粒径、流量和时间序列时，最多做可审计的形态原型，不应声称预测现实演化。[USGS Sediment Transport](https://www.usgs.gov/mission-areas/water-resources/science/sediment-transport)

## 3. 地下暗河与喀斯特

### 3.1 三个具体系统

| 系统 | 官方资料支持的过程 | 可计算与不可直接计算的部分 |
|---|---|---|
| 菲律宾Puerto Princesa Underground River | UNESCO记载地下河位于石灰岩喀斯特，河流直接流入南海，洞穴段约8.2 km，包含潮汐影响的洞穴—河口环境。[UNESCO Puerto-Princesa Subterranean River National Park](https://whc.unesco.org/en/list/652/) | 可把入口汇水、洞内河段、潮汐出口和季节性入流建成有向网络；8.2 km洞穴长度和洞穴地图不能单独给出断面、糙率、渗漏或压力水头。 |
| 斯洛文尼亚Škocjan Caves—Reka | UNESCO记载Reka河在喀斯特高原落水洞进入地下，穿越大型地下峡谷系统，并在地下继续流向喀斯特泉域；该系统体现地表河、落水洞、地下河和泉口之间的连接。[UNESCO Škocjan Caves](https://whc.unesco.org/en/list/390/) | 可表达“地表入流—ponor—地下河—泉口”拓扑和事件性洪水；洞穴厅、峡谷和通道几何需测绘，不能从DEM水流方向推断。 |
| 美国Mammoth Cave—Green River喀斯特 | NPS说明Mammoth Cave区域存在溶蚀形成的多层洞穴、下沉溪流、地下水通道和泉流，Green River是区域主要地表水体；洞穴水文会随降雨、河水位和季节变化。[NPS, Mammoth Cave Hydrology](https://www.nps.gov/maca/learn/nature/hydrology.htm) | 可用降雨、河水位、泉流量和示踪/渗漏资料做地表—地下交换；“已测洞穴长度”或旅游线路图不等于完整含水层模型。 |

### 3.2 建模边界

- **入渗**：由降雨、土壤/裂隙、非饱和带和岩溶通道共同决定；建议先做有效入渗通量和迟滞库，而不是直接把全部降雨送入地下河。[USGS, Karst groundwater](https://www.usgs.gov/mission-areas/water-resources/science/karst-groundwater)
- **落水洞与地下河**：落水洞是拓扑汇入口，地下河段可采用明渠或有压管两种边界；二者不能共用同一个地表河槽公式。[USGS Karst groundwater](https://www.usgs.gov/mission-areas/water-resources/science/karst-groundwater)
- **泉口复出**：泉口是地下水向地表的边界节点，应允许季节性流量、溢流和回水；没有泉流量时间序列时只能做参数化出口，不应宣称真实泉口位置或流量。[USGS National Water Information System](https://waterdata.usgs.gov/nwis)
- **地表—地下交换**：岩溶系统有快速通道和慢速基质储水并存；可用双库模型表达“快速峰值+缓慢退水”，但参数必须由示踪、泉流量或水位数据校准。[USGS Karst groundwater](https://www.usgs.gov/mission-areas/water-resources/science/karst-groundwater)
- **资料区分**：洞穴测绘资料回答“通道在哪里、几何多大”；水文资料回答“何时有多少水、压力和交换量如何变化”。前者可生成洞体几何，后者才可支撑水量、流速、交换和季节事件计算。二者缺一不可。

## 4. 公开数据与适用边界

| 数据 | 空间/时间特征与许可 | 适合用途 |
|---|---|---|
| USGS 3DEP | 提供美国区域的DEM产品，分辨率按产品和区域从约1 m、约3 m到约10 m不等；USGS公开数据通常可免费使用，但应保留来源、版本和垂直基准。[USGS 3DEP](https://www.usgs.gov/3d-elevation-program) | 河岸、谷地、扇体、局部断面和高程基准；不代表全球覆盖。 |
| Landsat Collection 2 | NASA/USGS Landsat长期多光谱观测，常用地表反射率像元30 m，热红外另有分辨率；USGS说明数据公开可下载和使用。[USGS Landsat](https://www.usgs.gov/landsat-missions/landsat-collection-2) | 年际河道、沙洲、牛轭湖、三角洲岸线和植被变化；小于像元尺度的河岸位置需标注不确定度。 |
| Sentinel-2 | Copernicus多光谱卫星，部分可见光/近红外波段10 m，重访周期取决于纬度和星座；Copernicus数据按其公开使用条款提供。[Copernicus Sentinel data](https://scihub.copernicus.eu/userguide/) | 10 m级活动河面、分汊、沙洲、河口湿地和洪水前后比较；云、浑水和潮位必须筛选。 |
| SWOT | NASA/CNES等合作的宽幅水面高度任务，可观测河流、湖泊和洪泛水体的水面高程、宽度和坡度；误差与水体宽度、观测几何和处理产品有关。[NASA SWOT](https://swot.jpl.nasa.gov/) | 中大型河流的水面高程、坡降、洪泛范围和模型校验；不替代米级河床DEM或洞穴测量。 |
| USGS NWIS gauge | 提供美国水位、流量、降水和部分水质/泥沙站点时间序列，站点、变量和时间范围必须逐项记录。[USGS NWIS](https://waterdata.usgs.gov/nwis) | 流量边界、洪水事件、季节性、模型校准和事件回放；站点代表的是测站断面，不是整个流域平均值。 |
| HydroSHEDS | 基于SRTM等资料加工的全球水文栅格与河网，常见3 arc-sec约90 m产品；官方站点列出产品、版本和使用条款。[HydroSHEDS](https://www.hydrosheds.org/) | 全球流域、河网拓扑、汇水区和大尺度出口先验；不适合直接生成真实河岸、床面或洞穴。 |
| MERIT Hydro | 基于高分辨率DEM校正的全球水文数据，常见约3 arc-sec约90 m网格；作者页面提供数据和许可说明，应随下载版本保存元数据。[MERIT Hydro](https://hydro.iis.u-tokyo.ac.jp/~yamadai/MERIT_Hydro/) | 全球河网、流向、汇水面积和跨瓦片连接；不应把90 m流向当成米级河槽。 |
| 洞穴测量与水文资料 | 洞穴线测、激光扫描、断面、落水洞/泉口坐标、示踪、泉流量和水位来自公园、地质调查机构或洞穴测量组织；每个系统许可和覆盖范围不同。[NPS Mammoth Cave](https://www.nps.gov/maca/learn/nature/hydrology.htm)；[USGS Karst groundwater](https://www.usgs.gov/mission-areas/water-resources/science/karst-groundwater) | 线测/扫描用于几何和拓扑；流量、水位、示踪和降雨用于交换与储量。缺少公开原始数据时只保留来源索引，不反推虚假断面。 |

## 5. 对Terragenesis的分级建议

### 可立即做

1. 保持米制、秒制、立方米和质量账本分离；在现有单向河段上加入有界下切、cutbank—point bar、三类粒径库存、洪水冲刷和沉积前缘事件。
2. 把`cutoff`实现成显式拓扑事件：新河段、旧弯道/牛轭湖、封闭时间、两端水量和固体泥沙转移均可审计。
3. 把直流、曲流、辫状、分汊、三角洲和地下河分别作为形态标签/拓扑，不用显示平滑伪造自然度。
4. 为公开数据建立只读来源登记：URL、访问日期、许可、版本、CRS、水平/垂直分辨率、时间范围和适用边界。
5. 用Landsat/Sentinel水面时序和USGS站点做“现象回放”对照；对比的是迁移、分汊、面积和流量指标，不宣称地点复刻。

### 需要真实数据才能做

1. 河口潮汐/波浪耦合、三角洲前缘长期推进、潮汐汊道和回水；至少需要潮位、波浪、河流流量、泥沙浓度、断面和多时相岸线。
2. 真实河岸坍塌、床面装甲和粒径分选；需要断面、材料级配、河岸土性/植被、洪水过程和输沙观测。
3. 地下暗河水文；需要落水洞—泉口拓扑、降雨、泉流量/水位、示踪或交换观测，以及许可明确的洞穴测绘资料。
4. 现实地点校准；需要固定坐标、DEM垂直基准、遥感时间戳、潮位/水位状态和误差预算，不能只凭一张卫星图。

### 暂不应做

1. 不把90 m全球水文产品或扩散生成高程直接当作米级天然河床、河岸或洞穴几何。
2. 不在没有水沙观测的情况下声称真实河流的侵蚀率、沉积率、三角洲年龄或地下河季节流量。
3. 不把现实资料直接当作TD山地“真实地貌认证”；TD输出仍是扩散生成山地，现实数据只能作为形态约束、对照样本或独立实测地形来源。
4. 不先做全域三维岩溶洞穴、潮汐河口或自动袭夺；这些过程会改变拓扑和边界，必须先建立来源、误差、守恒和失败状态。
5. 不将洞穴旅游线路图、宣传图或洞穴总长度替代水文断面、压力水头、流量和交换资料。

## 6. 来源索引

1. [Leopold & Wolman, 1957, River Channel Patterns: Braided, Meandering, and Straight, USGS PP 282-B](https://pubs.usgs.gov/pp/0282b/report.pdf)
2. [Hickin & Nanson, 1984, Lateral migration rates of river bends, Journal of Hydrology](https://doi.org/10.1016/0022-1694(84)90063-9)
3. [USACE Old River Control](https://www.mvn.usace.army.mil/Missions/Engineering/Old-River-Control/)
4. [USGS Yellowstone River Corridor](https://www.usgs.gov/centers/northern-rockies-science-center/science/yellowstone-river-corridor)
5. [Ashmore et al., 2011, Brahmaputra-Jamuna channel change, Geomorphology](https://doi.org/10.1016/j.geomorph.2011.03.013)
6. [NASA Earth Observatory, A Pulse of Water in the Colorado River Delta](https://earthobservatory.nasa.gov/images/83567/a-pulse-of-water-in-the-colorado-river-delta)
7. [UNESCO Danube Delta](https://whc.unesco.org/en/list/588/)
8. [UNESCO Puerto-Princesa Subterranean River National Park](https://whc.unesco.org/en/list/652/)
9. [UNESCO Škocjan Caves](https://whc.unesco.org/en/list/390/)
10. [NPS Mammoth Cave Hydrology](https://www.nps.gov/maca/learn/nature/hydrology.htm)
11. [USGS 3DEP](https://www.usgs.gov/3d-elevation-program)
12. [USGS Landsat Collection 2](https://www.usgs.gov/landsat-missions/landsat-collection-2)
13. [Copernicus Sentinel data](https://scihub.copernicus.eu/userguide/)
14. [NASA/CNES SWOT](https://swot.jpl.nasa.gov/)
15. [USGS NWIS](https://waterdata.usgs.gov/nwis)
16. [HydroSHEDS](https://www.hydrosheds.org/)
17. [MERIT Hydro](https://hydro.iis.u-tokyo.ac.jp/~yamadai/MERIT_Hydro/)
18. [USGS Karst Groundwater](https://www.usgs.gov/mission-areas/water-resources/science/karst-groundwater)
19. [USGS Sediment Transport](https://www.usgs.gov/mission-areas/water-resources/science/sediment-transport)
20. [NOAA National Estuarine Research Reserve System](https://coast.noaa.gov/nerrs/)
