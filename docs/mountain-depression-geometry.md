# 山地洼地几何：固定接口与预算

任务39 / 实施B，实验版本 mountain-depression-geometry-v1。仅CPU，不修改冻结模块、源地形或Sonnet。

## 数值试验前声明（2026-10-01）

复用 `tools.verify_mountain_rainfall.load_source` 的完整487×487、30m旧TD `height_m`。保留历史游戏限高、13格halo裁剪及海面基准平移标记。H0不是priority-flood工作面。

新实验改变边界条件：整个有限计算窗口的每个边缘格都是 `external_open_boundary`，表示截断外部流出，不是天然海口，也不是CONTEXT定义的完整水文规划域。旧单人工出口结果另存作对照。外部进入窗口的未知入流不被假设为已知；窗口内全部面积唯一归属一个截断出口，展示子域不裁掉内部上游贡献。

固定上限（每山地）：250000格、512MiB、4000000次邻接访问；谷面切深1m，H0至床面累计切深2m，累计切体积200000m³；禁止填高及修改保护区。浅切目标0.25m；河线按完整上游面积≥1000000m²识别。禁止试验后抬高预算。湖位使用原H0的最小逃逸高程，湖盆与spill不为通过而改高程。优先保湖，不强制全部洼地开挖。

新几何用4邻接priority-flood与4连通湖盆，避免D8角接触冒充有宽度的湖。旧D8单出口/全边界比较单列，不将两种邻接方式混为算法改善。工作面仅为最小逃逸水位与拓扑证据，不是填筑谷面或干河床。

## A/B接口

`prepare_mountain_geometry(height_m, *, spacing_m, origin_m_xz, source_binding, boundary_mask, protected_mask, budget)` 返回 `{arrays, metadata}`。

- `H0_m / H1_m / H2_m`：原地形 / 谷面 / 床面。谷面不需改变时H1=H0；湖内H2=H0。
- `escape_level_m / lake_id / lake_mask`：几何水位容量与4连通盆地，非实际存水。湖内receiver表示汇流拓扑，不是干河床。
- `receiver / order`：完整网格扁平索引；receiver=-1仅在显式边界；order下游先于上游。
- `outlet_owner / outlet_cells / outlet_area_m2 / outlet_type`：每格唯一出口归属，类型固定external_open_boundary。
- `flowline_mask / dry_channel_mask / accepted_mask / rejection_code`：河线、干河道、完整接受范围与逐格拒绝证据。
- `spill_lake_id / spill_inside / spill_outside / spill_stage_m / spill_width_m`：原地形上4邻接跨岸接口，宽度一个完整格边30m，不是修改单点制造出口。
- `lake_stage_m / lake_capacity_m3 / lake_area_m2 / lake_downstream_id`：湖盆层级；V(h)=900×Σmax(h-H0,0)，容量不是实际存水。
- `cut_depth_m / cell_cut_volume_m3`：每格实际修改及唯一累计体积。
- `section_cells / section_offset_m / section_H0_m / section_H1_m / section_H2_m`：基于整格有限体积断面，不宣称亚格精细河床或水深。

A必须从新拓扑重算首次下游归属与HRU相交面积，不复用旧累计Q。湖泊独立蓄水，不把湖内拓扑路径当普通干河段重复记水。只读加载必须提供可信H0/源绑定并检查静态语义，不调用prepare、路由或推进。

## 已确认根因

协调只读D8对照：normal正fill格33092→10458，最大fill54.325→7.612m，几何容量420482381→4307375m³；pressure正fill格194316→11311，最大fill228.283→14.012m，几何容量30113822930→9058219m³。旧单出口约束制造的大量潜在蓄水与长直线，主要不是必须切穿的自然内陆盆地。这些不是实际水量。新4邻接结果将独立计算，不借用此统计作为本模块通过证据。

## 冻结候选能力与严格范围

`certify_no_cut_groups` 与施工选择分开：原床无需切也可静态合法。完整D4贡献组不因为无施工而失去几何证书，但静态合法不等于动态单池可解。

`mountain_pool_network` 只处理逐所有原高程事件都单池连通、无未建模等高出口的完整贡献组。min_cells=4是展示筛选；新增min_cells=1表示30m离散蓄水格，不称解析自然湖。按完整窗口面积降序，固定最多10候选试验，保存每个拒绝。每个池局地产流按完整首次入湖归属和HRU真实相交面积分配；上游释放只注入一次。无湖直接支路明确在终端记账，无河道驻留时间，非传播过程线。

堰公式 `Q=1.7*b*head^1.5`，系数单位m^0.5/s，b=30m整格边。head上限是min(1m,其他原始岸线高差的一半)，不是调参找通过。逐步与冷加载拒绝接收池水位高于上游spill的free-weir假设失效。使用后向Euler、每池绝对体积容差1e-6m³与相对1e-10，64次迭代；静态校验逐池与联合水账，不只看总残差。这个量级与A的更严格求解器不同，不能混同A的1e-9结果。`mountain_lake_experiment` 中leaf末库只保留诊断草稿，不进入接受耦合主报告。

`mountain_fine_geometry` 独立替代粗网格方案：固定1m采样、10m宽、最多64次候选、16段/候选、250000 fine格；不与coarse重叠体积重复累计。当前正例是同源90m连续3段，共享节点与真实双线性H0断面，首尾显式局部几何接收面；非整片fine forest。`validate_fine_chain` 静态检查源坐标、H0、cosine切床、全条带保护mask、预算、真实共享断面。

`mountain_fine_storage` 独立局部工程V(h)/conductance实验，复用冻结模块的volume/_invert数学核，不伪造forest。固定K=0.01m²/s、dt<=10s、4096步、200万work。控制区支撑是源1m格点与唯一梯形积分权重；逐有效岸下高程事件单池门禁。接口crest是相邻1m行最低床的较高值，明确离散D4，不宣称连续半格物理界面。高于静水的床保持干，湿连接sill gating，有符号通量可倒灌，空donor限幅不得负存水；限幅后逐节点水账。每节点水位受两岸最低值约束，超岸保存提交前缀及失败。测试部分湿静水、干初始、尾水倒灌、局地脉冲、超岸拒绝与10/5秒对照。

真实90m上游在完整新receiver中含大量未解湖，裸局地产流总和不能直接当已路由入口。上游映射完整保存并明确 `requires_upstream_lake_outflow_binding`；人工边界fine实验与完整贡献组降雨案例分开。

`mountain_fine_mesh.export_fine_mesh` 仅只读消费已验证chain和saved storage。不准备、不推进。床每格固定对角线两三角且共享断面用同vertex id；水用湿support点/加权小柱，不画插值假连续水面，逐保存状态展示水体积与V(h)差。局部米制原点显式保存，垂直夸张在页面控件标出。失败只展示提交状态，T状态/T-1有符号流对齐。

## A/B来源绑定差异

B geometry source_binding为固定mountain、river/raw/provenance哈希和历史conditioning标记。A绑定另含source_identity。两者是不同契约，B包不能直接作为A API输入。B pool forcing另绑定已冻结36产流包哈希，并在报告保存其source_identity。接入时必须通过明确adapter验证H0/spacing/origin/源哈希一致，不做字段名称猜测。

## 验证与只读入口

`D:/anaconda/python.exe -X utf8 -m unittest tests.test_mountain_depression_geometry tests.test_mountain_pool_network tests.test_mountain_fine_geometry tests.test_mountain_fine_storage tests.test_mountain_fine_mesh -v`

`D:/anaconda/python.exe -X utf8 -u tools/verify_mountain_depression_geometry.py`

验证器创建唯一新目录，不覆盖旧包，保存27冻结源运行前后哈希及全部B源码身份。D8单出口与全开放、新D4均给1km²同阈值对照，旧source flowline单列为约5km²阈值，不把降低阈值当路线改善。图报告为review.html；同源三维湿support回放为fine-3d-review.html。开发run不等于协调最终认证，不修改TODO/issues/CONTEXT或Sonnet。

## 2026-10-01阶段固定交付

唯一当前固定包：`verification/mountain-depression-geometry/frozen-20261001T070426687355Z/`。`static-freeze-manifest.json`记录源代码、全部13个改动路径、27冻结源前后哈希、只读重导出身份。该包从065431保存的几何与水动力静态读取重导出，不重新搜索候选或推进。旧065431床三角朝向向下，不能认证；新固定包统一正Y法向。report.json保留原运行记录，当前源码身份以static-freeze-manifest为准，不能混同。

同坐标双山地连续90m床面与湿support三维回放：`fine-3d-review.html`。床H0/H2共用bbox相机；时间不因床面切换重置。Edge headless、禁GPU，双山地5场景34次状态切换无pageerror，尾水末态和脉冲峰值截图/证据在包内。V(h)显示水量误差约1e-12m³；湿support是离散加权表示而非三角水体插值。

pressure1378完整四池组0.6741km²小于固定1km²起河阈值，coarse cut与flowline均为0，不适用既有施工fine selector。新增只读集成可行性诊断 `integration-preflight/` 单列为独立支流研究，未改变起河阈值或A原几何。按已验证上游湖数、完整子树面积和flat id确定90m候选；完整上游面积382500m²，包含2639/2652已解湖，干区344700m²按真实HRU相交面积给入流。入口用两湖实际释放加干区局地产流，而非裸累计Q。固定1m×10m、0.25m独立浅切方案112.5m³，非准备后接受的coarse床。

实际入口峰1.706014m³/s，现有K=0.01m²/s最大出口0.002331m³/s，岸下容量上界39.730224m³。即便全部时段按最大有效出口排水，dry初始在第25时段末23400s（6.5h）已必超岸。因此此集成被预检拒绝，不发布真实降雨→fine成功贯通，不通过放大K或抬岸解决。独立fine人工边界试验与完整四池降雨试验仍分开。

B已运行新模块34项联合测试全通过；最后针对静态防伪与非法forcing补2项并针对geometry/pool20项通过，mesh朝向针对3项通过。不能将这些重复覆盖项相加宣称57项；当前测试集合共36个独立方法，协调最终独立回归另记。

## 独立Manning支流切片

共享 `mountain_depression_geometry.py` 保持SHA256 `6be2f275de2907183a214903f35fc7742d34a7f26141c1757b036cd42e477694` 不变。新模块 `mountain_manning_geometry/storage/binding/mesh` 不修改旧K实验、A或Sonnet。固定pressure1378研究链219142→219145、90m×10m、1m双线性采样、0.25m浅切、独立切量112.5m³；不是原1km²起河证书，1m采样不增加30m源分辨率。

四控制体V(h)，实际折线断面A/P/R，upwind conveyance、shared crest截断水头、后向Euler；n=.035 s/m^(1/3)为预声明情景。无动量，不是Saint-Venant；指定末支撑最低床尾水是工程扩散边界，不称自然自由跌落。固定24h、30/15s相同物理输入对照、6000步、每步64次nfev、3-point四变量最多9次残差/nfev加首尾2次、200万总残差、64MiB；资源耗尽和超岸只保留已提交前缀，不增预算。

A完整湖河保存出流绑定：首node293下游释放为入口（已含首节点河库），后3节点局地量及外部侧支释放只计一次。fine增加额外停留，是离线单向替代研究，不是严格河库替换、不将A重复储量加到fine账、不反向反馈A。末node296完整子树716格644400m²，分区425/1/1/289；不是749格完整组全覆盖。保存node/cell_partition与局部递推、全部A体积列来源证据，静态验证不调用bind或prepare。

旧含湖面直降雨湿暴雨：入口峰2.122m³/s，两步长在10h下一步超岸拒绝；不是此前pool-only约1.706的同一forcing。任意时间区间累计输入减最大可能出流超过39.730m³容量，能证明容量不足；从t0的松必要界null不能解释为可输水。东/西移动雨和无雨统一前24h完整保存。无雨仍有原土库退水，不冒充零输入。

运行：`D:/anaconda/python.exe -X utf8 tools/verify_mountain_depression_geometry.py --manning`。
静态重验/导出：`D:/anaconda/python.exe -X utf8 tools/verify_mountain_depression_geometry.py --manning-freeze verification/mountain-manning-tributary/run-20261001T073045498330Z`。创建新目录、不覆盖073045，禁止solver/prepare/bind；源与产物hash、新旧验证器身份分别保存。`manning-3d-review.html` 只读保存水位湿support点，V(h)权重水量，不伪造连续三角水面；最多98原保存状态含首尾和储量峰。requested/committed输入、外流、储量分账，失败不画拒绝状态。
