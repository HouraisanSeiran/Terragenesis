# 工程 TODO

## 2026-10-09 河网主线分类与形态事件

- [x] 建立主线/legacy/adapter/audit/presentation/consumer模块登记，冻结新算法只进入metric主线。
- [x] 建立统一`MorphologyEvent`契约，绑定父图/几何、水沙转移、材料账和重验声明。
- [x] 实现`delta_growth`河口三角洲V1：沉积足迹、有限分汊候选和固体/孔隙/未解析账；保存产品冷读通过。
- [x] 实现`cutoff`截弯取直V1：河颈检测、捷径、退役曲流和牛轭湖候选。
- [x] 实现`bank_migration`外弯冲刷/内弯点坝候选及有限`bifurcation`辫状分汊候选。
- [x] 实现`alluvial_fan`冲积扇和`floodplain_inundation`洪泛平原候选，保留storage proxy语义。
- [x] 已生成真实TD256局部优先级1–6候选集 `verification/td-morphology-candidates/td256-20261010-01/`；来源、父图和局部解释身份已保存。
- [x] 独立冷审通过：`verification/td-morphology-candidates/td256-20261010-01-audit-05/audit.json`；拓扑写回仍待后续门禁。
- [ ] 完成两个真实TD局部案例的保存后冷审，再接入共同水面/床变主线。

分类登记见 `docs/architecture/river-module-classification-20261009.md`，事件规格见 `.scratch/river-morphology/issues/01-delta-cutoff.md`。Minecraft保持后续消费子项目。

## 2026-10-09 成熟库复用

- [x] 接入固定 `pyflwdir==0.5.12` 的TD图分析：成熟库计算汇水面积、终端贡献域、Strahler等级；保留receiver和closed/unknown/规定边界语义。
- [x] 新CLI实际消费TD256保存图，65,536格流向/贡献域/面积差异均0，450个闭合终端候选保留；9项针对性测试与标准包保存/冷读通过。
- [ ] 后续按新增需求逐步调用后端，替换DEM路由前先匹配unknown、出口、格距及平地政策；不把独立外部填洼政策直接替换旧固定包。
- [ ] 水动力/侵蚀内核继续专项评估成熟后端；Minecraft保留为后续消费子项目，本阶段不开发。

使用和范围见 [成熟后端接口](docs/reference-routing.md)，本地任务 [.scratch/reference-routing/issues/01-pyflwdir-adapter.md](.scratch/reference-routing/issues/01-pyflwdir-adapter.md)。其他智能体在途河槽、湖泊、前端及冻结证据不在本轮写集。

## 长期路线图接入

长期阶段计划见 [`Terragenesis河流地貌长期路线图.md`](Terragenesis河流地貌长期路线图.md)，任务记录见 [.scratch/td-river-blueprint/issues/14-long-term-roadmap-integration.md](.scratch/td-river-blueprint/issues/14-long-term-roadmap-integration.md)。该路线图现在作为阶段依赖、状态命名和验收门槛的上位计划：阶段0–1对应 M0–M2，阶段2–3对应 M3–M4，阶段5对应 M6/12 的有界反馈，阶段9对应 Terraindiffusion 条件地形，阶段10对应 M7 多分辨率交换与发布审查。

- [x] 接入长期路线图，保留其对主线冻结、真实调用链、单位/时间语义、未知边界和渲染层限制的约束。
- [ ] 完成 13 全域几何后，按路线图阶段10启动 M7；阶段4一般分流、阶段6–8曲流/三角洲/局部三维岩体仍排在后续路线。

## 2026-10-08 M3–M6补充接续进行中

- [ ] 继续补充[11天然湖盆/回水](.scratch/td-river-blueprint/issues/11-natural-lake-merging-and-backwater.md)：TD256 2/.5 秒失败包保留；`.5/.125` 真实共同水面细化已通过固定1mm门槛，但仍限六叶瞬时平衡范围。
- [x] 11 的 `.5/.125` 真实共同水面细化已通过固定 1mm 门槛，stage 差 0.539420mm；仅接受 TD256 六叶有限瞬时平衡范围，issue 仍开放。
- [ ] 继续补充[13全域谷地河槽](.scratch/td-river-blueprint/issues/13-global-valley-channel-geometry.md)：45/45组件和623/673边已通过 tiled 冷审；50边全部因 owner divide 拒绝，27条中心线本身跨 owner、23条最小合法半径仍跨 owner，failure-prefix 保留，必须通过合法重路由或明确 scope exclusion。
- [x] [12床变几何/水力重耦合](.scratch/td-river-blueprint/issues/12-morphology-recoupling.md)受限无湖范围验收完成；含湖、全域和拓扑变化仍依赖11/13。
- [ ] 上述11/13实际验收后再开始[09 M7多精度交换](.scratch/td-river-blueprint/issues/09-resolution-exchange.md)。旧M3–M6限定验收有效，但本轮补充未完成项不能被旧证据覆盖。

## 2026-10-08 Claude 蓝图 M5 / M6 限定基线完成

- [x] [07 M5局部原床中心线/河床几何](.scratch/td-river-blueprint/issues/07-channel-geometry.md)与[08 M6单向冻结水流泥沙/Exner](.scratch/td-river-blueprint/issues/08-sediment-erosion.md)验收，见[实现、审查、独立参考与限制](docs/td-river-m5-m6-20261008.md)。共享fan4床面/真实断面、单一切岩账、入湖湿格保护、固体/孔隙/岩石分账及真实失败前缀完成。
- [x] 183项相关回归+3项独立审查通过；禁10生成/求解入口联合冷审通过16份几何、10份泥沙与新几何水流映射，GLB结构及预览已核验。原TD/冻结D4/历史拒绝/Claude前端写集保留，无服务/GPU/游戏/Java启动。
- [x] 真实1024局部弯道最大45度降到33.9011度，空间细化体积差0.006144%；同源256入湖0.25/0.125m差0.646393%。真实90m/900s泥沙事件床变0.02617745mm、粗细床差0.0000171231mm、出口差0.0228232%、固体残差-1.9984e-15m³。
- [ ] 下一主线[09 M7多精度守恒交换](.scratch/td-river-blueprint/issues/09-resolution-exchange.md)。[11天然湖盆/回水](.scratch/td-river-blueprint/issues/11-natural-lake-merging-and-backwater.md)、[12床变后几何与水力重耦合](.scratch/td-river-blueprint/issues/12-morphology-recoupling.md)、[13全域谷地河槽扩展](.scratch/td-river-blueprint/issues/13-global-valley-channel-geometry.md)仍开放，共同阻塞10发布。局部形态改善不是全1024河网已自然化，冻结水流回放不认证变化床面的水力，全部认证标志false；前端仍为诊断标注、不代表细网格瞬时水面。

## 2026-10-08 Claude 蓝图 M3 接续 / M4 有限湖盆耦合完成

- [x] [06有限湖盆耦合基线](.scratch/td-river-blueprint/issues/06-lake-boundary-coupling.md)验收，见[实现、独立参考及限制](docs/td-river-m3-m4-coupling-20261008.md)。原床V(h)/反函数、多出口、共同步湖河交换、open/closed/unknown/stage/discharge边界、逐节点账及真实失败前缀完成；M3无湖行为兼容。
- [x] 143项相关回归通过；三个细步独立参考误差0.0348894%、0.0950233%、0.0728230%。最终禁7生成/求解入口冷审通过11份保存产品，包含实际2s停止的容量失败前缀和独立边界案例。
- [x] 同源真实256² TD与冻结D4映射：5格湖泊支撑和70格贡献域分开。900s事件水位细化差0.000960688mm、累计出口差0.284804%、残差-3.07e-12m³；密集/稀疏输出积分一致。初始储水为显式近溢流预置，首鞍点以上为固定直壁池近似；已有1024² M3证据保留。
- [x] 此处历史下一主线[07谷地中心线/河床几何](.scratch/td-river-blueprint/issues/07-channel-geometry.md)的限定基线已在上节完成；全域直线/直角及天然湖盆仍为13/11开放任务。水力/自然出口/发布标志保持false，不将有限池推成天然湖岸或细网格瞬时水面。

## 2026-10-08 Claude 蓝图 M3 与河线路径审查

- [x] [M3限定河道储量/运动波基线](.scratch/td-river-blueprint/issues/05-channel-storage.md)完成，见[交付报告](docs/td-river-channel-m3-20261008.md)。显式物理矩形断面、Manning、CFL、逐节点账、真实失败前缀、求解后采样与独立冷读；单支流/Y解析与ODE参考通过，10m峰值失败保留，5m细化通过。
- [x] 真实1024²来源上的96节点/3153.381m河段运行900s，局部水量17.903751m³逐格一次输入；2s/0.5s细化深差0.002519mm、累计出口差0.278665%，密集/稀疏末态与水量一致。只消费已有源/产流，无全域新求解、GPU或服务。
- [x] 只读定位直线/直角：填洼D8等高边67,728条、最长等高直线4.03km，D4直角边对约20.98%。[任务07](.scratch/td-river-blueprint/issues/07-channel-geometry.md)增加谷地、盆地、曲率与拓扑约束，不把显示平滑作为修复。
- [x] 119项相关新旧回归通过；最后资源检查修改后17项M3聚焦测试通过，最终禁8入口冷审验证8份轨迹与4份采样输出，原始TD文件和局部Q绑定通过。
- [x] [M4湖泊储量/溢流及边界耦合](.scratch/td-river-blueprint/issues/06-lake-boundary-coupling.md)限定基线已在上节完成；下一项M5中心线/河床几何。水力/自然出口/发布标志仍false，不代表全流域天然断面或细网格瞬时水面；Claude前端在途改动保留。

## 2026-10-08 Claude 蓝图 M1 / M2 完成

- [x] 完成 M0 来源/tile 前提、M1 静态诊断排水与 M2 时间变产流，见[交付与真实TD验收](docs/td-river-milestones-1-2-20261008.md)。原床D8/独立泛洪D8/新边界适配D4、donors CSR、来源登记、跨tile空间降雨、独立密集/稀疏输出包；103项相关新旧测试通过。
- [x] 真实1024²、30m TD原生地形联合验收与禁16个生成/求解入口的独立冷审通过；P=2,359,296m³，本地释放221,980.874475m³，联合残差−3.96e−9m³，密集/稀疏末状态和累计量一致。256固定来源同时通过；旧source/算法/D4包哈希不变，三张诊断预览已保存。
- [x] [M3 河道储量与简化水动力](.scratch/td-river-blueprint/issues/05-channel-storage.md)已在上节完成限定基线，下一项M4。原床3333个闭合候选不代表实际湖面；泛洪最大114.14m仅改变工作面。CRS继续pending，水力/自然出口/发布标志保持false。服务、GPU、Java和游戏未重启，Claude前端写集保留。

## 2026-10-07 按 Claude TD 河网实施建议接续

- [x] 按[用户指定实施蓝图](Terraindiffusion河网算法完整实施建议.md)完成第一轮 A-F，见[报告与真实TD证据](docs/td-river-blueprint-first-round-20261007.md)：四契约、原床D8、边界/产流适配、保存冷读及68项新旧测试通过；全域输入147456m³，残差−2.51e−10m³。450个闭合候选保留，不作为湖面或河道水力；三个诊断预览已生成。
- [ ] 按[阶段规格与依赖任务](.scratch/td-river-blueprint/spec.md)继续M7-M8；来源/tile、排水政策/forcing及M3-M6限定基线已在10月8日完成，之后为多精度、天然湖盆/回水、床变反馈与全域几何扩展。水力/自然口/发布标志保持false，CRS缺失保持pending_provenance。主协调负责审查、发布与验收；用户已指定GPT-6 Sol实施、同时最多3智能体含主协调。既有地下接回工作保留为独立任务。

## 2026-10-07 河网算法主线接续

- [ ] 按[接续规格与具体任务](.scratch/river-continuation-20261007/spec.md)补齐新洞道独立审计、完整地表接回端口及后续 face/必要水动力。主协调审查与集成，最多3智能体含主协调；用户本轮指定可用6luna，首次分派因账户不支持该模型失败。
- [ ] 确认 Claude 最新修改/建议位置；当前已定位地下暗河 V1 和其后续文档，不将旧静态小沟包测试等同于完成河网主线。
- [x] 完成[新洞道保存证据独立审计](.scratch/river-continuation-20261007/issues/01-saved-gallery-audit.md)：seed17实际TD包的四实体/材料、固定端点、VDM与空气路径通过，6项篡改/拒绝回归通过；完整端口、连续覆岩与水力仍待完成。

## 2026-10-07 动态河网渲染后续审查

- [ ] 按[动态河网渲染审查任务](.scratch/frontend-review/issues/03-dynamic-river-renderer-review.md)核对模块职责、`signedEdgeQ` 与箭头端点方向、初始状态与保存区间语义、三维诊断叠加限制、`window.surfaceRenderer.flowInterval()` 与点选兼容性，并评估二维网格/河网绘制/选择投影是否需要进一步拆分。
- [x] 基于固定 Terrain Diffusion 地形生成静态自然河网候选并完成独立只读审计；交付目录为 `verification/natural-river-network/td-claude-review-20261007-01/`。当前仅有小沟候选，全部河段需细化，水力、自然出口和发布标志保持 false。

## 2026-10-06 地下暗河 V1 与前端交付

- [x] 实现固定真实山地窗口的种子洞道生成：侧向路径、宽度、洞顶 VDM 变化，固定两端；实际生成 cutter/rock_after/removed，不修改来源。
- [x] 默认新包几何检查通过：125.323254m、切岩1885.050525m³、材料残差7.73e-12m³、9个覆岩核心断面；保存完整覆岩/空气路线/实际开口见证。
- [x] 接入本工作区网页「河网算法 → 地下暗河 · 第一版生成」：2D/3D、透明岩体、剖切、站点、参数生成与审查导出；实际seed18新成果与旧包不变检查通过。
- [ ] 自动洞口选址/地质约束路线发现、分叉汇合及多层地下水系。
- [ ] 完整地表接回端口独立认证与必要水动力；保留composition03和07/08/09拒绝，不以几何生成冒称水力通过。

接口与边界见 [地下暗河 V1](docs/underground-river-v1.md)。本版为固定125m样例的有界构造生成，非自动自然洞道发现；新参数成果尚未独立审计。`water=null`，水力/完整河网/自然出口标志均false。前端修改为用户本轮明确授权；原source、Java/JAR、默认世界不改。下方历史“网页未接入”不适用于本V1入口，其他未认证事项保持开放。

## 2026-10-06 本轮新增交付

- [x] 增加严格保存切片消费器：保留外环/孔洞、空域和正面积 sliver；拒绝有理非零但显示为零的多边形、非有限坐标、越界孔洞和重叠组件。
- [x] 增加 composition03 只读切片消费审计；结果为 `candidate_consumer_only`，不改变 composition 的 `refused` 状态。
- [x] 增加 VDM/三维几何纯 IO 导出：`td-vdm-geometry-io-review-v1`，绑定 geometry03/review/graph/geometry audit，保留17站、19断面、4实体和所有能力 false 标志；不导出水面。
- [ ] 修复 composition03 sink 端口有理非零/GEOS 零面积诊断三角形，并重新完成独立全端口审计；禁止删面、snap、移动切面或放宽门槛。
- [ ] 只有全端口独立审计通过后，才运行 faces-v2；之后重新定义并实现必要水动力，保留旧07/08/09拒绝证据。

## 2026-10-06 地表与地下闭环最新状态

本节优先于历史。共享地表床已实际接受120节点/118接回弧/18分叉、最长1230m；统一0.175m细床333374唯一格/436tiles与3041.031556m³精确切岩账独立冷读通过。三维typed图已保存122节点/121弧；125.246807m潜入/洞道/复出样例经实际岩体Boolean打通，VDM多chart与19真实断面独立通过，1834.143489m³局部采样实体切岩另计。见[公开架构与接口](docs/hybrid-river-network.md)、[本轮证据/失败记录](.scratch/hybrid-river-network/round-20261006.md)。

必要水力尚未通过：07/08实际退出并保留时间精度/预算拒绝；08两个完整900s pulse的实际断面和逐cell账通过，但全历史head差1.871692mm、V差0.089751m³、配对link差0.226888m³未过门槛。09共同local datum在548.696942s触发RHS200001，0完整case。不能继续以收紧容差或换solver代替模型审查。实际18共享face的首包已冷审，14通过、洞口附近4拒绝；正在[新版本地表半臂实体接回](.scratch/hybrid-river-network/issues/02-surface-solid-composition.md)中修正采样岩顶与原生床线差异，保留真实polygon/三角壁角色，不删除cap冒充通过。无水力求解在途，不改26冻结依赖或放宽1mm/1%、1e-4m³、600s/1GiB。当前状态见[唯一检查点](.scratch/hybrid-river-network/checkpoint.md)。源码首批已实际上传GitHub，增量待完成。只读几何和18face审查图已导出，网页导航未改。自然海口、全主流域细槽/漫滩水力、独立跨精度、多洞道与完整三维产品仍开放；原source、Java/JAR、默认世界不改。

## 2026-10-06 接续轮最新状态

本节优先于下方历史。缺失0.005s细级240s已完成，原0.01s粗级零重算；最大深差0.008121mm、累计净通量相对L1差3.04424e-6，原1mm/1%通过。完整50帧无损review仅授权该来源隔离局部脉冲消费。源岸面v3已独立冷读：12接受/2拒绝，36,437格原子替换、29原填方拒绝恢复、7保留，signed切岩/外运各0.00460185533m³。没有在途水力求解，不恢复历史PID。

连续性普查发现06床条带仍有238个整断面连通分量；07的195个汇流原型没有真实四点边界端口，不能按已合成连续河床发布。正在执行[12实际端口汇流与条带接回](.scratch/natural-river-network/issues/12-ported-junction-and-strip-composition.md)：保留最高Q锚点冲突，先在合法三臂hub尝试真实共享端口，再推进成片组合。详见[本轮工作记录](.scratch/natural-river-network/round-20261006-network-completion.md)。自然海口、全主流域fine/同床水力、跨精度、VDM完整三维和地下暗河仍开放；Claude前端、Java/JAR和原source不修改。

## 2026-10-06 当前轮：11阶段交付，仍未完成

先读[11交付](.scratch/natural-river-network/delivery-entry-propagation-and-source-banks-20261006.md)。源隔离240s事件的完整粗级已冷读通过：原Q供水0.831124m³、边界输入严格0，跨60m净输运0.581392m³、湿支持区最大0.490406m³，单级前沿87.2875m。主机重启导致细级与原最终index丢失；粗级完整恢复、不重算，时间细化仍false。25帧/27数组无损诊断review已导出，正式网页接入pending。

源约束岸面v2与多节点支撑弧接口已实现，实际新包峰752,451,584B<1GiB；17,788三角/43,297旧细格的14组件全部因邻接绝对面不兼容或未闭合非零切深边界拒绝。替换与材料差额均0、36填方拒绝保留。独立保存/拒绝协议审查已通过，不宣称岸面组件修复通过；全部14边界见证已保存，代表性完整床函数差最大25.037mm，实际是一次项不匹配而非全为二次曲率。[11任务](.scratch/natural-river-network/issues/11-entry-propagation-and-source-conforming-banks.md)保持claimed；下一步补可恢复细级与原生结点完整接口匹配，不重跑旧全天或原四场。

下方10及更早记录为历史，不覆盖本节；自然海口、完整主河廊fine、水动力、VDM三维/地下河与独立多域仍开放。

## 2026-10-05 本轮状态

**2026-10-06 最新接续**：[10分片与同床浅水交付](.scratch/natural-river-network/delivery-shards-and-same-bed-shallow-water-20261006.md)已完成限定范围。80,792个唯一细格、346.9624m³原岩切出/外运账独立冷读通过；15个完整局部入口、14个pending、47个父级拒绝，36个填方格保留。90m真实TD床的供水/退水与受控尾水各粗细两级实际HLL/SSPRK2事件通过逐格质量/动量与1mm/1%时间细化，耗时1172.77s，不重跑旧水文。普通20s脉冲在60s时前沿26.5625m，未跨30/60m；尾水回流确已跨60m，不能混称供水贯通入湖。4.84MB只读前端包已导出，UI未修改。下一项[11传播与源岸面](.scratch/natural-river-network/issues/11-entry-propagation-and-source-conforming-banks.md)，全主流域fine、自然口、VDM三维/地下河与独立多域仍开放。

以下是09历史交付，不能覆盖上面的10最新状态。

最新[真实源交付](.scratch/natural-river-network/delivery-native-lake-entry-fine-20261005.md)优先于历史：旧fine源床为断面IDW，矩形减深不能验收真实TD改床。09已完成限定诊断：29/76入口渐变、47父几何拒绝；0.175m真实源派生细床64,059格/64,041候选/18无来源填方拒绝，切出原岩291.19m³全记外运，独立审查通过。整体局部入口门禁10通过/19pending，不等于完整河廊。下一项[10分片与同床浅水](.scratch/natural-river-network/issues/10-entry-shards-and-same-bed-shallow-water.md)；连续全域fine、新床浅水传播/尾水、自然口仍开放。两名6.1sol medium代理已关闭，无在途新求解。

- [ ] 完成真实源床的全主流域 fine 与材料账；旧 `fine-bed-material-20261005-02` 仅端口插值算术诊断，不输入自然细槽水力。
- [x] 实现真实 DEM 的有限陆地入湖床深渐变：`verification/natural-river-network/lake-entry-taper-20261005-02/`，29/76几何候选通过源采样/横向几何/湿区保护冷读，47项拒绝；尚非全河廊接受。
- [x] 保存有界真实源三角覆盖细床及切出原岩外运账：`fine-bed-raster-lake-entry-20261005-01`；10入口完整局部保存格诊断，19预算/填方pending，独立raw DEM审查通过。
- [ ] 实现连续新床的真实浅水传播与尾水；旧 `td_fine_bed_hydraulics.py` 仅3×3导通原型，不能代替此项。
- [x] 固定自然海口三证据门禁：`verification/natural-river-network/natural-outlet-certification-20261005-02/certification.json`；当前 `pending`，三项门禁全 false。
- [ ] 补齐剩余缺端口/汇流湖入口与源约束断面；内部湖接口使用本模型原始 TD 米制证据，不等待现实海岸测绘。
- [ ] 将新床水动力扩展到已接受的连续 fine 河廊，加入真实尾水/回水边界并独立审计。
- [ ] 之后再开展基于 VDM 的三维河网、地下暗河、跨域跨精度动态水力；本轮不提前宣称完成。

## 当前优先级

2026-10-05 [目标审计](.scratch/natural-river-network/goal-audit-20261005.md)已完成：用户六阶段统一N1至N6，当前N2盆地/出口不等待N5跨域、地下河、侵蚀或Mod。有限初始填洼/切穿与单事件侵蚀分开，旧门槛和失败原样保留；不重复既有通过验证。

[最新几何交付](.scratch/natural-river-network/delivery-watershed-geometry-20261005.md)：已从2.9169km²/35保留盆地主分量生成1,776条真实陆地receiver候选，1,096条已形成共享床岸网格、6,576三角形；680条因汇流补片/锚点衔接/转角等明确拒绝。4项新测试与独立冷读v2通过，25文件核验、零水文求解；原审计器契约错误诊断保留。fine请求1,999,859格，不是已有fine DEM；原床未改。

06/07/09限定诊断已交付，08完整主流域fine与材料账仍开放，当前下一项为10。07最终1,383个补片候选、178个拒绝；09只覆盖显式湖入口邻域，不授予完整三维或水力认证。N2自然海口、N4细槽传播/尾水、N5跨域跨精度及地下暗河开放。正式网页接入pending。详见[长期工作表](.scratch/terrain-framework/long-term-workboard-20261004.md)。

## 历史记录

**2026-10-05 最新交付**：真实 VDM 岩壁的局部走滑断层已接入本工程前端，入口 `http://127.0.0.1:8765/?workspace=fault`。v2 修复旧算法丢失 VDM 变形的问题，并换到真实变形选区；前后对照、参数预览、默认关闭缝线和桌面/手机/宽屏实际浏览器通过。见[断层交付](.scratch/metric-vdm/fault-frontend-delivery-20261005.md)。自然主线新增土壤/快速/慢速产流到地表库存、全域空间雨与退水、限定地表积分器时间细化及独立四库存冷读账；503 条真实 D4 溢流路径请求已保存，首批 8 个候选因厚度/水量材料潜力拒绝。见[主线交付](.scratch/natural-river-network/delivery-runoff-and-paths-20261005.md)与[当前任务](.scratch/natural-river-network/issues/03-runoff-and-stable-spill-paths.md)。45 项联合回归及 5 个新增独立审计测试通过。第二阶段整体仍开放：产流完整时间细化、尾水、合法新床联算、永久主干/连续 fine、自然口待完成；旧基线不重算、不放宽门槛。

**当前候选阻碍**：全量预算冷读已确认 1006 份请求全部未过旧水量/材料势门槛，排序不能解决。保留蓄水基线，暂停追加无效生成；下一步诊断路径与单事件侵蚀预算适用性，独立设计局部地形处理/有限填洼及材料来源，不降低原验收门槛。实际报告见本批交付的 `feasibility-audit.json` 引用。

**2026-10-05 P0 数值往返振荡修复（优先于下方历史）**：已定位显式300s更新越过水头平衡点；独立Radau v5正权重共享面积分保留真实反流，完成完整24h/6h两场两级时间细化及独立冷读审计。方向抵消由79.1066%/68.4127%降至0.433156%/0.362465%，水位差0.041121mm/0.076944mm、累计净通量相对L1差3.58959e-6/1.88228e-6，严格1mm/1%通过。固定新入口 `verification/natural-river-network/radau-overflow-20261005-03/index.json`，SHA `2bdf20aaee1d3f22d4e22ed94f26c66c761896a613afa1abb6338a658ad36618`；详见[本轮交付](.scratch/natural-river-network/delivery-stable-overflow-20261005.md)。下一步补四库/受控尾水和各候选同模型事件，接收关系只作事件诊断，不直接升级永久主干/连续fine河廊；自然河网P0整体仍开放。

**同轮下游接收交付**：`verification/natural-river-network/stable-reception-20261005-01/index.json` 已固定，44.73MB逐面/逐盆地接收诊断保存并禁求解冷读通过；两场989/1039面满足保守事件稳定关系，139/119活动面仍保留诊断。最终107项联合回归通过，所有本轮runner和两名子代理已结束。见[前端接入契约](.scratch/natural-river-network/stable-overflow-frontend-contract-20261005.md)，本轮未改Claude前端或Mod。

**2026-10-05 P0 原床账本与候选比较交付**：已补齐共享面净通量和逐盆地收支，独立冷读审计通过；推荐固定入口为 `verification/natural-river-network/original-bed-overflow-20261005-06/index.json`。11 个既有候选已核对实际保存文件，继续选择 baseline，不重跑旧全天水文。普通/强雨累计交换中方向抵消约 79%/68%，守恒不等于数值稳定；下批优先时间步敏感性、稳定溢流与实际下游接收，然后才建主干/连续细廊。详见[本批交付](.scratch/natural-river-network/delivery-overflow-accounting-20261005.md)；[P0 任务](.scratch/natural-river-network/issues/02-spill-and-same-bed.md)保持未完成。

**2026-10-05 当前有效状态（优先于下方历史条目）**：工程已经具备可审查的地形输入、有限单域三维地表水力、VDM 岩壁形态和第一版走滑断层模块；尚未完成“自然山地—合格干流—自然海口—跨域连续河网—地下暗河”的完整产品链。当前最优先任务是 `.scratch/natural-river-network/issues/02-spill-and-same-bed.md`：在 Terrain Diffusion 原生山地上完成原床蓄水溢流基线、精确共享面交换、同床普通/强雨事件和有限填洼/切穿候选比较。所有自然海口、自然河网发布、跨精度动态、地下暗河和完整三维认证标志继续保持 false。

**当前成果速览**：

- 单域有限工程水力已验收：原生 30m/双向 24h/50 帧与局部 240m×240m AMR/120s/35 帧，保存、冷读、独立收支、三维消费和搬移审查均有固定证据；这不等于自然河网完成。
- 自然河网已有静态候选、稳定原床溢流和事件接收：完整 256×256、30m TD 域、1085 盆地、2921 面；Radau v5 时间细化和事件接收通过限定门槛，新产流四库存账及空间雨/退水亦通过限定独立审计。503 条鞍点路径请求不是永久主干；细床水力和自然口未通过。
- 域间工程已完成首批保存几何：四域、halo、唯一共享面、混合精度切线、域账归因和 1024² 合成拓扑审查；独立多域推进、连续 fine 河廊和跨精度动态水力仍未完成。
- VDM 已有六种参数化岩壁形态；当前断层 v2 在实际变形岩壁上局部切割，132 个移动顶点、最大 4m 位移、68 条缝边，已可前端审查。旧 v1 丢失 VDM 变形的成果只作历史诊断；自交、稳定性、侧壁/实体、地下和水力耦合仍未通过。
- `web-preview/` 已交付“地形输入 / VDM 算法 / 河网算法”、2D/3D、来源绑定、保存包与真实断层预览。新自然事件/廊道包仍需前端整合，前端展示不等于算法接受。

**下一批完成条件**：先完成盆地连接与同床事件，再集中运行保存/冷读/独立账本/资源和前端合同审查；只有实际下游接收、连续床面和同床水力通过，才能把静态候选升级为自然河网候选。不得以工程开放边界替代自然海口，不得把潜在逃逸链或假想储量画成已发生河流。

**2026-10-05 第一版走滑断层交付**：已实现独立 `metric-vdm-fault-v1`，采用局部 VDM 岩层、竖直切面、水平走向平移、过渡带和开放断层缝；固定入口 `verification/metric-vdm-fault/run-20261005-04/index.json`。8 项断层测试和 16 项 VDM 回归通过，候选产生 138 个移动顶点、最大4m位移、814条缝边、零跨缝三角。保留旧 VDM 不变；当前仍未认证自交、地质稳定性、断层侧壁、封闭实体、水力和前端接入。

**2026-10-05 第一版走滑断层已确认并开始实现**：按用户确认的既有思路，采用局部 VDM 岩层、竖直切面、水平走向平移、外围过渡带、开放表面断层缝。新建独立 `metric-vdm-fault-v1`，不得修改旧 VDM 拓扑；核心、测试和审查工具正在分工实现。断层第一版不生成封闭实体、洞穴、地下暗河或水力响应。

**2026-10-05 QA 第二轮本批交付（静态候选，整体未完成）**：[交付报告](.scratch/natural-river-network/delivery-20261005.md)与[前端消费契约](.scratch/natural-river-network/frontend-contract.md)已固定。完成多场景先验、自动主流域评分/筛选/下游闭合、共享床节点、中心线实际改床、细化请求及只读保存链。核心61项和收尾17项定向测试分别通过，15项独立静态审计、25项原源/代码/成果pin核对通过；不重跑旧全天水文。原生1085个局部汇流分区选中661格/0.5949km²、323条边/92河段，全部支沟，没有合格干流；1m细床仍有361需细化/124截边节点。新增19面潜在工程出口链诊断，假想储量1291.66m³仅针对选中盆地，非动态溢流。最终纯IO补充入口 `verification/natural-river-network/round2-review-20261005-03/index.json` 明确诊断失败及几何门禁，旧02审查保留但不再推荐。永久床形identity已与完整事件包身份分开；前端由Claude接入pending。下一项[盆地连接与同床事件](.scratch/natural-river-network/issues/02-spill-and-same-bed.md)优先，Q4/Q10/Q14/Q17、自然口、跨精度、地下暗河和完整三维仍未完成。

**2026-10-05 QA 第二轮自然河网实现**：Q23—Q26 已按用户“直接按 QA 表执行”采用推荐 A，进入[自然河网主线任务](.scratch/natural-river-network/issues/01-second-round.md)。优先实现完整 TD 域的主流域评分、多普通雨场景筛选、共享节点/中心线真实改床、细化请求和只读审查包；不将旧人工槽或本轮静态几何当作自然海口/新床水力完成。规格见[第二轮规格](.scratch/natural-river-network/spec.md)。

**河网算法调查新增决策**：稳定河网继续使用多个固定普通降雨场景进行当前验收；后续加入由 Perlin 噪声模拟区域降雨强度、并结合地形因素的空间连续降雨场。该降雨场用于代表性产流与区域差异，不让单场暴雨直接重建永久河床；具体噪声尺度、地形增雨/雨影关系和参数身份待下一阶段定稿。详见[河流概念调查](.scratch/river-concept-audit/report-20261004.md)与[讨论地图](.scratch/river-concept-audit/map.md)。

**河网示范范围决策**：首个自然河网主展示采用完整约 `7.68km × 7.68km` 的 `256×256` 原生 TD 域，局部细化嵌入主域而不是单独冒称完整河网。精度不足的河道拒绝发布并标记需细化；自然成果与工程水力测试分为两个前端工作区。详见[调查讨论地图](.scratch/river-concept-audit/map.md)。

**河网细化决策**：全域先展示稳定河网和流域证据，再按河流等级、汇水量、汇流节点、坡降/曲率、出口/盆地与保护区建立重点细化河廊；主展示选一个完整主流域，其他流域不伪造连通。Perlin 空间降雨暂列独立 forcing 版本，固定普通雨/强雨先完成主链。粗网格无法表达的河段标记未发布，不自动加宽。

**2026-10-04 河流概念对照调查**：已整理[详细报告](.scratch/river-concept-audit/report-20261004.md)及两份源码证据附录。原目标的自然山地—支流—干流—合法出口产品链尚未贯通；现有第一阶段完成仅指有限工程水力与保存验收，不能替代自然河网产品完成。早期D8/米制宽深/实际中心线和TD河段候选有复用能力，尚未全部接入最新人工槽AMR链。调查保留既有验收与失败，本轮不改算法、不重算。下一步优先级、跨区域语义及河道形态/事件水量关系进入[grilling讨论](.scratch/river-concept-audit/map.md)，用户确认前不变更长期顺序。

**2026-10-04 VDM 位移图层**：黄色长线确认为参考面到派生岩壁的位移连线，不是拓扑/流向。新增独立「VDM 位移向量」开关，默认关闭，不再共用河网边状态；来源与几何不变，导出保留图层状态。浏览器默认/开启/关闭恢复检查、导航/相机/来源回归与桌面/手机画布检查通过，证据为 `verification/frontend-review/vdm-overlay-20261004-02/report.json`。任务见[位移连线显示](.scratch/frontend-review/issues/02-vdm-displacement-overlay.md)。长期工作表当前状态已同步为第二阶段，地下暗河和 VDM 质量门仍未完成。

**2026-10-04 前端分类与相机整理完成**：主类别按用户确认改为「地形输入」「VDM 算法」「河网算法」，不限定基础输入必须是 TD。最新 AMR 为河网默认；盆地/出口/共享边界归河网，断层草案归 VDM，历史 TD 输入与河网工程案例分开。AMR 两轴拖拽方向修正、三维右键平移/下方观察与类别导出已实现。Spec/Standards 只读审查完成，来源身份、加载时导出与过期预览错误已修复；最终导航检查、保存包桌面/手机检查、历史 16 案例回归和 5 项导出测试通过。任务见[前端审查整理](.scratch/frontend-review/issues/01-classification-camera.md)，证据见[交付记录](.scratch/frontend-review/delivery-20261004.md)。本轮没有重新求解水文或修改冻结证据。

**2026-10-04 第二阶段首批测试与正式前端接入**：最新 AMR/原生/uniform 三类固定保存包已接入 `web-preview/`，实际三维、叶间距、时间播放和来源导出通过桌面/手机浏览器检查。35 帧真实保存四域 mosaic 的 halo/唯一共享面/床水接缝/蓄水覆盖通过，新增实际 1/2/4m 混合切线与原保存 epoch 正反向域账归因；1024² 合成拓扑和定向回归通过。完整第二阶段仍开放，尚未实现独立多域 HLL/RK 调度与动态跨精度水力。事实与固定证据见[第二阶段首批交付](.scratch/fine-domain-mosaic/delivery-20261004.md)，规格见[共享边界任务](.scratch/fine-domain-mosaic/spec.md)。下方“阶段 2 未启动/正式前端未接入”均为之前历史状态，冻结第一阶段证据不修改。

**2026-10-04 第一阶段完成（有限工程验收）**：[最终交付](.scratch/single-domain-fine/delivery-final-20261004.md)和唯一 `verification/single-domain-stage/acceptance-20261004-03/acceptance-index.json` 已固定，SHA256 `74f4b419f7341990e254c216cd2d37798f587abbabde6bc44ed507e92629971c`；18 项外部证据核对通过。原生 30m/双向各 24h/50 帧与局部 240m/AMR 4/2/1m/120s/35 帧分别验收。七例全窗最大深差 0.02299mm、相对体积差 1.93e-8、零源静湖漂移零，独立物理审计/全历史冷读/35 帧来源与三维 fan/搬移 HTTP/PNG 实际审查完成，72 项联合测试通过。正式运行 1722.891s、RSS352391168B、同时磁盘峰1956806886B、最大暂存段128MiB；两次存储失败及 uniform 4.91cm/7.79cm 失败保留，门槛未放宽，后期全窗 1m 不称持续粗化效率。正式前端和 Mod 未接入，自然/水力/发布标志仍 false。本轮结束于阶段 1，阶段 2（共享边界与连续 fine mosaic）未启动。下方同日期“claimed/执行中”条目均为历史，以本条和唯一验收为准。

**2026-10-04 第一阶段完整 v7 验收与 AMR 接续**：原定 120s 七案例、35 帧、28 区间/首次 RK 见证、独立审计和禁执行 cold 全部完成，1293.375s/RSS442392576/private402714624B/输出473941019B；时间细化实际改变子步，深差 0.02299mm 通过，尾水响应通过，均匀空间深差 4.91cm/7.79cm 仍失败。静湖历史案例是默认湿土持续产流，不是无源静湖，新测试显式零供水且门槛不变。fine 可搬移诊断消费包59 NPZ/35帧已导出，禁止原来源文件访问后搬移/HTTP验证通过。单域 AMR 真实2s对独立1m全窗对照通过1cm/1%，约5.04万leaf，仅12.4%自由度节省，仍需完整120s及独立历史几何/区间审计；原uniform coarse失败不改名接受。详见[最新诊断](.scratch/single-domain-fine/diagnosis-20261004.md)和[AMR任务](.scratch/single-domain-fine/issues/04-adaptive-single-domain.md)。第一阶段仍 claimed，后续阶段不启动。

**2026-10-04 第一阶段数值复核接续**：canonical 保护掩膜、fan 床积分和初态守恒聚合已修复，子单元 V(stage) 保持粗网格半湿静湖。v3 固定真实 2s 包、独立 HLL/RK/CFL/收支审计与禁求解器 cold 读取完成；2m/1m、4m/2m 最大深差 0.050563m/0.087346m，体积差 0.007149%/0.049276%，水深门槛未过。旧 `.1/.05s` 两组实际子步相同，时间通过声明撤回，改为 `.025/.0125s` 并核对子步。源码快照 SHA/路径绑定和目录链接逃逸反例通过，70 项联合回归通过。两名 GPT-6.1 Sol medium 继续定位开放边界半湿前沿与粗网格摩阻积分；详见[本轮诊断](.scratch/single-domain-fine/diagnosis-20261004.md)。门槛保持 1cm/1%、静水 1e-9m，第一阶段仍开放。

**2026-10-04 第一阶段整轮接续**：用户要求尽量一轮完成一个阶段，继续由主协调与两名 GPT-6.1 Sol medium（总数 3）推进[连续 fine 几何/同床水力规格](.scratch/single-domain-fine/spec.md)。固定真实 TD 含汇流 240m×240m 窗口，以 1m 新床运行、2m/4m 对照，补四库独立释放、受控尾水、保存纯 IO 与消费证据；不得把局部窗口或平底近似标成整个原生域 fine/自然认证完成。正式前端仍按既有分工由指定 Claude 接入。

**2026-10-04 第一阶段接续首轮结果（历史基线）**：[fine 交付报告](.scratch/single-domain-fine/delivery-20261004.md)已完成 7 个真实窗口案例、独立审计与纯 IO 冷读。历史时间细化与几何接受声明已由上方复核纠正；受控尾水有响应，空间水深失败。第一阶段保持 claimed，不推进阶段 2。

**2026-10-04 第 1 阶段首批交付**：[单域同源三维保存链](.scratch/single-domain-surface/delivery-20261004.md)完成限定验收，主协调与两名 GPT-6.1 Sol（medium）共 3 名智能体。42 项统一测试、原生 TD 固定床面/共享节点、两个方向各 24h 共 50 帧导出、构建禁用冷读及独立逐格/整期审计通过，湿格零遗漏；导出峰 RSS 242913280B/private225751040B，索引 `verification/single-domain-surface/native-same-bed-20261004-02/index.json` 已固定。默认线程内存失败保留，线程=1 后在原预算内通过。[前端消费契约](.scratch/single-domain-surface/frontend-contract.md)已交付，正式接入 pending。下一批继续连续细槽/岸线/水面、同床 fine 水力与受控回水案例；第 1 阶段整体仍未完成，不推进第 2 阶段。

**2026-10-04 下一阶段顺序固定**：按单域有限区域三维地表河网闭环 → 域间共享边界与连续 fine mosaic → 地下暗河与地表地下耦合 → VDM 陡崖悬挑几何质量门 → 侵蚀、溶蚀和风蚀推进。阶段任务与完成标准以[长期工作表](.scratch/terrain-framework/long-term-workboard-20261004.md)为准；当前执行阶段为第 1 阶段。

**2026-10-04 工程分层与长期路线**：当前工作区已建立算法层与 Minecraft Mod 层的逻辑边界，暂不直接搬移源码，以免破坏根目录相对路径、固定 verification 身份、前端入口和 Gradle 构建。分层说明见 [`docs/architecture/workspace-layout-20261004.md`](docs/architecture/workspace-layout-20261004.md)，算法清单见 [`algorithm/manifest.json`](algorithm/manifest.json)，Mod 清单见 [`minecraft-mod/manifest.json`](minecraft-mod/manifest.json)。长期工作表见 [`.scratch/terrain-framework/long-term-workboard-20261004.md`](.scratch/terrain-framework/long-term-workboard-20261004.md)，下一智能体交接见 [`.scratch/terrain-framework/handoff-next-agent-20261004.md`](.scratch/terrain-framework/handoff-next-agent-20261004.md)，完整提示词见 [`.scratch/terrain-framework/next-agent-prompt-20261004.md`](.scratch/terrain-framework/next-agent-prompt-20261004.md)。当前主目标是米制三维地表河网、地下暗河、陡崖悬挑；侵蚀和风蚀列为长期阶段。

**2026-10-03 VDM走滑断层准备**：[局部切面/水平平移规格](.scratch/metric-vdm/issues/04-strike-slip-fault.md)已记录。建议竖直切面、沿走向正负位移、内区刚体/外缘剪切过渡；真实切割改变拓扑，需独立fault mesh版本，现有VDM固定chart接口不可冒充。算法尚未实现；Opus提示词仅预留明确待接入的设计面板。

**2026-10-03 前端交接准备**：[进度/算法接口清单](.scratch/terrain-framework/frontend-algorithm-inventory-20261003.md)、[Opus 5.5繁体完整提示词](.scratch/terrain-framework/opus55-river-vdm-frontend-prompt-20261003.md)、固定JSON来源快照已整理。核对7份验收引用JSON均一致，细步两方向各24保存页；现有13前端案例保留，新VDM参数HTTP接口尚待Opus实现。本轮只做只读检查和文档，未重跑水文或修改前端。

**2026-10-03 VDM几何控制**：[曲面/端差/走向](.scratch/metric-vdm/geometry-controls.md)已实现，可独立叠加六形态；非默认控制写v2，旧六份v1身份复现一致。18项定向测试和六例TD单变量导出通过；最终入口 `verification/metric-vdm-controls/final-20261003T131348175Z/review.html`。端差指内侧完整岩壁段新增中心高程差，外围仍平滑接回原床；不代表自交/水力验收。

**2026-10-03 VDM多形态**：[六种岩壁交付](.scratch/metric-vdm/forms-delivery.md)完成层状岩棚、凹蚀岩厦、纵向槽脊、阶梯崖壁、弯曲崖带、厚顶悬挑的米制参数化几何及TD河床保护接入；11项定向测试、六例真实导出/回读通过。四份NPS原文与来源清单已保存。资料路径更正为实际存在的 `D:/geography`，此前仓库相对 `d/geography` 缺失不代表地理资料缺失。仍需自然化、自交检测、贴壁侵蚀与水力耦合；当前并非地质重建或完整三维河网完成。

**2026-10-03 VDM独立化**：[首批交付](.scratch/metric-vdm/delivery.md)已迁出旧岩壁骨架为米制XYZ处理层，接入既有TD河床，导出NPZ/OBJ/审查JSON及对照图；7项定向测试和实际保存回读通过。旧Java消费链不切换，Voronoi/贴壁流水侵蚀迁移与完整水力接入仍待做，不能把首批迁出称为全部VDM独立化。

**2026-10-03 阶段推进**：复用既有候选包生成三方案只读比较 `verification/td-basin-treatment-comparison/run-20261003T-next-01/comparison.json`，未重算水文、未写入地形。保留蓄水基线、有限切穿和有限填洼/沉积均列出扰动量、固体账、敏感性和拒绝原因；当前选择仍为 baseline，候选敏感性/细槽水力/自然出口均未通过。当前工作区没有实际 `d/geography` 目录，已有地理清单明确缺少可认证的独立海岸连接，因此不伪造地理认证。

**2026-10-03 下一阶段启动**：新增 `terrain_pipeline/natural_outlet_certification.py`，要求显式海岸掩膜、有效高程、D4连续下坡路径、receiver链到达海岸、海平面约束、保护区/未知区排除和独立观测证据；缺任一项只输出拒绝原因，不把边界或nodata当海口。新增2项契约测试，并与盆地逃逸、切穿、真实DEM出口分类联合44项unittest通过。真实自然海口尚未认证；下一步将把该报告接入地理资料审查页，并对有限填洼/切穿候选生成独立比较报告。

**2026-10-03 07:36最终接续**：07:25:46新0.625s双方向24h共48页及独立审计完成。相对原完整1.25s，东最大水深差0.660266799mm、西0.873420876mm，receiver相对L1分别0.0003407459622、0.0003212066308，均通过1mm/1%；四库账、逐面/checkpoint链、完整雨、IO与两次独立执行资源审计通过。新峰RSS271015936B/private234291200B，未放宽1GiB。最终verification/td-weather-refinement/independent-final-20261002T232545211593Z/acceptance-index.json，SHA c7da55e59be8d9d91fc81c45f17a0c6421848b06fafe215fc268608b1b00a24f，最终及7项引用文件SHA复核通过。原baseline失败结论保留，形态候选未执行；所有已知runner/worker/auditor及其子进程已退出。本轮两流程交付，暂停heartbeat，不为凑10小时重算。仅证明该256原生TD场景保存时刻时间细化达标；自然海口认证、细槽空间水力、域间跨精度、1024全天动态与完整三维仍未完成。

**2026-10-03 05:33接续**：完整基线96页及独立账本/IO/资源/审查完成，东1.303779mm、西1.723217mm均未过1mm，因此停止形态候选。自动串行0.625s两方向48页已启动，东11页保存，完整细化验收待完成；不重复重算、不放宽门槛。最新进程与证据见[唯一检查点](.scratch/terrain-framework/td-basin-long-round-checkpoint-20261002.md)。自然口、细槽水力、域间跨精度和完整三维仍开放。

**2026-10-03 04:30接续**：本实现批次收口55项统一回归、另1项完整索引绑定通过；11份固定交付及56+6冻结复核。原双向数值04:28已保存83/96，watcher5192等待完整原验收失败/PID终止才串行0.625s新增48页。两名gpt-6-sol medium子代理完成关闭，无重复求解；[交付文档顶节](.scratch/terrain-framework/surface-implementation-delivery-20261003-0422.md)、[最高检查点](.scratch/terrain-framework/td-basin-long-round-checkpoint-20261002.md)。仍未认证完整地表/三维，保持12:53硬截止。

**2026-10-03 04:22接续**：原生水面/覆盖诊断、不可变分块halo、连续视觉链v2安全证明、少步同步共享面输运和真实TD2s独立参考有限完成；同一次55项测试13.563s通过。完整基线东1.3038mm仍失败，西向细档在途；watcher5192等待完整原验收后串行同物理0.625s双向新增48页→独立验收，不改56+6冻结，不放宽1mm/1%。[真实交付与审查入口](.scratch/terrain-framework/surface-implementation-delivery-20261003-0422.md)、[最高检查点](.scratch/terrain-framework/td-basin-long-round-checkpoint-20261002.md)。全地表/三维未完成，硬12:53截止。

**2026-10-03 03:50接续**：75原生保存水面和覆盖诊断图、76大域拓扑/不可变halo、77独立连续曲线证明确认有限完成；独立审查发现并修复走廊判据/快照可变漏洞。baseline东向前18h深差约1.2735mm仍超1mm，完整96页/资源审计继续，不降低标准；[78定位](.scratch/terrain-framework/issues/78-td-v10-refinement-attribution.md)主要共享面输运。[79同步输运](.scratch/terrain-framework/issues/79-td-partition-synchronous-transport.md)、[80原物理更细步长](.scratch/terrain-framework/issues/80-td-v10-finer-time-step.md)准备推进，80先等完整原baseline与进程退出才能串行。全地表/三维河网仍未完成。

**2026-10-03 03:25接续**：02:53十小时流水线仍运行，未重启；真实床面WebGL审查已修复并通过浏览器检查，受限视觉曲线/旧31页恢复IO/大域预算已完成有限验收。新批次[75原生水面](.scratch/terrain-framework/issues/75-td-native-water-surface.md)、[76分块halo基础](.scratch/terrain-framework/issues/76-td-native-domain-partition.md)、[77连续路径审计](.scratch/terrain-framework/issues/77-td-visual-path-continuous-audit.md)已开始；不改冻结依赖。候选合并审查已知超旧512MiB，若完整选择通过则用预声明768MiB纯IO工具接续，禁止重算掩盖失败。详见[计划新增批次](.scratch/terrain-framework/long-round-plan-20261003-10h.md)。全工程未完成。

**2026-10-03 02:53当前**：十小时流水线PID24468已启动，最晚12:53截止；完整原床96pages独立raw/final通过才执行两个新床候选192pages。旧31小时前缀cold通过但缺资源，不拼接认证。两名用户授权gpt-6-sol medium推进三维床面/受限路径与1024动态预算。本批23tests及真实65025顶点129032三角独立床审计通过，实际Edge发现审查页JS冲突正在修复。[执行计划](.scratch/terrain-framework/long-round-plan-20261003-10h.md)、[最新检查点](.scratch/terrain-framework/td-basin-long-round-checkpoint-20261002.md)。全工程未完成。

**2026-10-03 00:40当前**：共同初值因果隔离与旧v9最终只读审计实际完成；厘米级细化失败涉及早期状态继承和湿格雨绕过入渗跳变。新v10统一入渗/分库账/小时续算已实现，forcing独立闭式参考通过，完整双向×双步24h在途；[唯一检查点首节](.scratch/terrain-framework/td-basin-long-round-checkpoint-20261002.md)。按用户要求分批实现后统一验证。整个地表河网未完成。

**2026-10-03继续实现**：69已完成实际移动雨双向×两steps共96hour；独立原雨/四库/checkpoint累计链和水账通过，但东向49.153mm/西向19.461mm时间细化失败，保持claimed。原job已结束，正在共同初值因果隔离与新严格IO验收；详见[唯一检查点首节](.scratch/terrain-framework/td-basin-long-round-checkpoint-20261002.md)。新床重联算、有限填洼/显式鞍部切穿、自然口认证、米级三维河槽、一般跨精度仍开放。

**2026-10-02 22:12本轮收口**：62/63/64/65/66/67/68/70有限验收完成；完整TD均匀两雨24h原水账与步长门槛通过，400MB原生审查数据/原生天气/真实水沙候选及新盆地图已保存，Sonnet未接入。[本轮结果与下一步](.scratch/terrain-framework/surface-round-result-20261002-2208.md)；[唯一检查点](.scratch/terrain-framework/td-basin-long-round-checkpoint-20261002.md)首节含全部真实pins。69已有输入模块及tiny测试但真实空间雨水文待完成；新床水文、自然口、一般跨精度、真实米级三维河槽仍开放，无在途heavy。

**2026-10-02 21:44最新**：TD均匀两雨/两步完整24h全部保存，资源峰值≤1GiB；自报1mm/1%通过，协调final独立接受session12987仍在途。接着唯一64逐帧/逐小时含flux导出、66水沙候选、65实际执行等价和68/70独立审计。[唯一检查点首节](.scratch/terrain-framework/td-basin-long-round-checkpoint-20261002.md)优先于下方历史。

**2026-10-02 21:23最新**：67固定TD每原生格移动降雨两方向独立全域积分通过，已有[可靠雨图](verification/td-native-storm-forcing/figure-20261002T131215682321Z/native-moving-rainfall.png)，天气尚未解水文。68逐小时共享边界审计5专测通过，等完整final。ordinaryfine实际17h、强雨两档/ordinary粗24h完成；下一步final独立接受→64含flux/66geometry发布→65实际等价与候选重建。[唯一检查点](.scratch/terrain-framework/td-basin-long-round-checkpoint-20261002.md)首节为准确入口。

**2026-10-02 20:57最新**：TD强雨2.5/1.25完整24h原水账/库存链/1mm及1%独立通过，最大差0.01647mm；[完整强雨图](verification/td-basin-generation/independent-continuation-figure-20261002T123326689731Z/td-continuation-review.png)。普通雨粗24h完成，细3h，唯一求解继续。66真实水账→水沙候选入口非零专测通过，协调新增原生binary与完整固体配额审计、接受后显式发布入口，等full final后正式导出。67原格点移动降雨并行准备，65实际TD等价/性能仍待当前求解结束。详细事实见[唯一检查点](.scratch/terrain-framework/td-basin-long-round-checkpoint-20261002.md)，完整河槽/自然口/一般跨精度仍开放。

**2026-10-02 20:01最新**：强雨粗完整24h独立水账残差1.3e-8m³、真实跨盆地净交换/25帧wet连通验收通过；细档前12h最大0.01647mm，仍待24h及ordinary。新可靠[实际水图](verification/td-basin-generation/independent-native-state-figure-20261002T115123715401Z/actual-native-water.png)可审查。63/64最终索引接受+v2 binary逐时导出23专测通过但真实final未导；65完整编译执行准备/小等价已过，实际TD性能与非法门禁待验。完整河槽/自然口/跨精度仍未完成，详见检查点。

**2026-10-02 19:23最新**：62有界v8小时续算已实现；首包private commit超1GiB保留拒绝，同公式单线程新包`A-storage-continuation-20261002T110815168692Z`正在strong2.5→1.25、ordinary串行24h。v7首小时细档已通过，不升全程；63独立最终索引/forcing/库存链冷读接受层并行。主协调流读独立数值审计正在验证，53/62仍未完整验收；具体事实见[唯一检查点](.scratch/terrain-framework/td-basin-long-round-checkpoint-20261002.md)。

**2026-10-02 18:56增量**：61已固定三场景/25帧/1085独占汇水区动态审查数据，入口`verification/td-catchment-dynamic-review/run-20261002T105245491130Z/index.json`；每case368900值独立复算与9项专测通过，ordinary-v6预算失败明确显示。新前端接入说明`td-catchment-dynamic-review-integration-20261002.md`待同步新pins。v6四解结束仍强雨4.01mm/普通fine预算未过；v7首小时四步实验在途，准备有界分段续算，继续动态53，未宣称完整水力或三维河槽完成。

**2026-10-02 18:40增量**：60纯IO版本分派和edges/reaches/spill/review接入有限resolved，协调73项相关回归及实际v2/v6双pin冷读通过。v6 strong5/2.5独立最大差降至0.00401367m、receiver L1 0.00006621，仍未过1mm；原生误差图`verification/td-basin-generation/independent-refinement-figure-20261002T103927374734Z/td-refinement-review.png`。v7补偿forcing修复隔离水账并通过制造解，首小时四档实验准备，后续须全时段验证；独占汇水区动态审查导出并行开发，不将potential/V假设或面整轮积分画成实际瞬时河流。

**2026-10-02 18:22接续**：58/59静态已有限完成；动态53继续。v5强雨独立冷读仍3.61cm失败，普通2.5s又被微小累计水账门槛拒绝，保留拒绝并定位。v6全域同时面SSP-RK2串行在`A-storage-v6-full-20261002T101625224506Z`运行，9项专测通过，未提前认证；[60纯IO版本接入](.scratch/terrain-framework/issues/60-td-pure-io-version-dispatch.md)并行准备。最新进程/证据见[唯一检查点](.scratch/terrain-framework/td-basin-long-round-checkpoint-20261002.md)。

**2026-10-02 连接层与数值根因推进**：真实TD河段已接57分片盆地面证据、1085独占汇水分区/2921潜在连接，完整独立逐面/分区水账与1GiB资源验收通过，入口`verification/td-basin-spill-network/run-20261002T095052584723Z/index.json`。继续[59潜在溢流出口规划](.scratch/terrain-framework/issues/59-td-potential-basin-escape-forest.md)。v4完整全域证实强雨旧3.53cm门槛失败，新v5完整强迫对称重解正在强雨优先串行运行；不得提前升全域水力认证。

**2026-10-02 河段/水量继续实现（优先于下方历史）**：新增 TD 全256²/30m、58.9824km²的面积阈值河段层，0.05/0.1/0.25km²分别370/143/19河段。独立完整面积、D4非增坡、唯一边覆盖及保存双向面通量核对通过；固定审查索引 `verification/td-surface-reaches/run-20261002T091814997493Z/index.json`。内部盆地保留，不隐藏碎片，继续[58盆地溢流连接](.scratch/terrain-framework/issues/58-td-reaches-and-basin-spill-network.md)。旧v3阈值公式被独立ODE反例否定，不能继续称正确修复；v4恢复已认证pair law，普通雨全域5/2.5通过，强雨细化仍在途。对称半步降雨强迫的小型受控实验恢复二阶趋势，新版完整水账实施中，不把局部证明或网页线图称完整水力/三维河槽完成。

**2026-10-02 TD跨域冷读接入**：`audit_td_partition` 消费 Gibbs versioned D4 face records，固定 `verification/surface-cross-domain/td-20261002T090748097544Z/` 含 report.json 与外部 pins.json。15项专测通过；256个真实非零单向面两侧外法向抵消为0，完整观察时长86400s。仅 named-cut flux evidence 完整，整体 edge_evidence_complete/hydraulic_ready/natural_outlet_verified=false；跨精度仅合成拆段门禁，未制造细网格或新水面。v3旧步长趋势不作pair correctness。

**2026-10-02 13:55 TD长轮增量**：自然海口审计已修复为优先使用 `PyPDF2`、缺失时回退仓库固定 `.scratch/terrain-framework/pdf-runtime` 的 `pypdfium2`，独立审计包 `verification/td-basin-generation/independent-mouth-audit-20261002T-final/` 可执行；结论仍为具名入海关系有证据、精确口门和原/观测连续连接未认证。v3 蓄水求解器已版本化修正完整初始水头差的过鞍事件公式，代表198格 5/2.5/1.25s 深度差约 `8.75324e-05m`，不能推广为全域收敛；执行冻结包 `A-execution-code-20261002T000000Z/`，候选执行 provenance `A-candidate-execution-20261002T000500Z/`。最终只读审查包 `B-review-v2-final-20261002T0540374988004Z/` hash 完整，普通/强雨与11候选导航可审查。三维前置适配器 7 项、导出 11 项、出口分类 14 项、页面 13 项专测通过，但现有几何仍是共享节点/共享边界的说明性 ribbon，`hydraulic_ready=false`、`natural_outlet_verified=false`、`publishable=false`；真实三维河网门禁未解除。

**2026-10-02 04:35 TD长轮阶段收口**：全域5s→2.5s独立细化审计已完成：ordinary通过（最大深差0.0000759m、receiver L1 0.000488），strong receiver L1通过但最大深差0.0352561m，超过0.001m门槛，因此53仍保持未收敛。真实TD候选11条已完成新床→新源→新盆地图→两雨重联算并通过独立coupling audit；8条鞍部候选零改动拒绝，valley/source候选自身细化未认证，选择安全回退baseline。56新strong审查页、11候选导航和13项review专测已完成。natural_outlet_verified、hydraulic_ready、publishable仍为false；三维河网门禁尚未解除。详见[最新检查点](.scratch/terrain-framework/td-basin-long-round-checkpoint-20261002.md)。

**2026-10-02 03:45 TD长轮增量**：51/52已独立接受；53已修正强雨限流数值根因，新5s主TD四场景全水账通过，2.5s全域收敛检验运行。54/55水沙、显式鞍部与候选重建联算代码已实现，等待真实候选全域验收；56只读山地床水网页可审查，正式Sonnet页面不动。官方PDF附图已提取，海口精确位置/观测连续连接仍未认证。实时路径与session见[唯一检查点](.scratch/terrain-framework/td-basin-long-round-checkpoint-20261002.md)。

**2026-10-02 TD长轮已启动**：两名6.1 Sol medium（Gibbs/Peirce）实施；51完整盆地层级与52连续材料已独立接受，真实256²/30m原床有1085叶、1077合并及7多叉。53嵌套动态与54显式鞍部/水沙继续；海口原件支持具名关系，但两旧位置候选相距13.74km，精确位置/连接未认证。进度以[检查点](.scratch/terrain-framework/td-basin-long-round-checkpoint-20261002.md)为准，下方“未启动”为历史。

**2026-10-02下一长轮准备完成**：用户已确认TD盆地/自然海口规格。已核对冻结成果与源身份，准备任务51—57；预计10—12小时推进TD盆地层级、嵌套蓄水溢流、连续材料、水沙切填、候选重建联算与只读2D/3D验收，海口证据独立穿插。见[执行计划](.scratch/terrain-framework/td-basin-long-round-plan-20261002.md)和[唯一检查点](.scratch/terrain-framework/td-basin-long-round-checkpoint-20261002.md)。目前仅完成准备，未启动实施；需新建两名GPT-6.1 Sol medium子代理，主对话可继续。

**2026-10-02长期轮收口**：从阶段A推进到E有限床面三维原型，任务45—50在各票范围resolved。真实平坦连通14371→3983终点，10388新边且不改高程；全有效格三场景24h水账、只读审查与5390节点4667边92汇流三维原型保存/冷读/独立审查通过。15模块203项联合回归0失败错误跳过，实施者停写关闭。完整成果和下一轮入口见[长期轮结果](.scratch/terrain-framework/long-round-result-20261002.md)。自然海口、内部盆地/细河床水面、全域回水、一般跨精度/跨区、Sonnet实际网页接入及Minecraft成品仍未完成，TD生成山地主线不变；以下“正在进行”为历史。

**长期轮 C/D 已保存**：全261866有效格三场景24h分批降雨+一步一边线性库完成保存/独立水账，最大逐步残差2.0078e-8m³；[阶段C](.scratch/terrain-framework/stage-c-rainfall-result.md)。只读审查包5390河网展示节点、完整DEM/风险、遗漏量和25状态时间，保留未知孔洞，不生成假水面；[阶段D](.scratch/terrain-framework/stage-d-review-result.md)。受影响15模块203项联合回归通过187.550秒。真实三维床面原型初验5390节点/4667边/92汇流/9334三角形，正式gate与冷读进行中；未改Sonnet正式页面，工程尚非完整水动力/自然出口成品。

**平坦连通已验收**：任务 [47](.scratch/terrain-framework/issues/47-real-dem-flat-routing.md) resolved，终点14371→3983，原高程不变；整组件风险630未知/149边界/3204内部，20项联合专测与独立全图连通/距离/贡献复核通过。真实四节点独立抬尾水基准保存897个负边通量，不称全域回水。固定审查图与数据见 [连通验收](.scratch/terrain-framework/stage-b-flat-result.md)。任务48分批降雨核心13项专测通过，正式全域产物准备中。

**长期轮阶段 B 分块基准完成**：任务 [46](.scratch/terrain-framework/issues/46-real-dem-tiled-routing.md) resolved，六真实 tile/顺序配置与冻结原图五数组一致，20 项专测与正式包冷读通过。见 [阶段 B 结果](.scratch/terrain-framework/stage-b-tiled-result.md)。平坦区任务47初测终点14371→3983且不改高程，固定发布待验收；任务48开始分批降雨与单向蓄量传播，不将其称双向回水。

**长期轮阶段 A 完成**：实测 DEM 14371 个终点完成分类，3427 个距 HydroRIVERS 线段不超过 180 m；13 来源保持不变，89 项回归通过，全终点与 26 距离抽样独立验收通过。任务 [45](.scratch/terrain-framework/issues/45-real-dem-outlet-classification.md) resolved，正式包、GeoJSON 和审查图见 [阶段 A 结果](.scratch/terrain-framework/stage-a-outlet-result.md)。下一阶段为真实 DEM tile + halo 适配与平坦区/内部终点连通。Terrain Diffusion 生成山地仍是主研发输入，实测海口认证独立保留。

**当前授权（2026-10-01，单区域第一阶段）**：同时推进完整区域河网、区域内水位/回水、超岸处理、连续三维和场景/精度验收。[计划与验收](.scratch/terrain-framework/single-region-surface-plan.md)，任务41/42 claimed。固定新TD256²/30m全区域58.9824km²；跨区为第二阶段，不以天然海口/无限规划阻塞，但30m模型不冒称精细子格河槽已完成。此前176项为上一轮结果，不覆盖本轮新模块。

**本轮收口（2026-10-01 20:42北京时间）**：单区域第一阶段的正式索引为`verification/regional-hydraulics/B-final-index-v3.json`，冻结artifact index为`verification/regional-hydraulics/regional-round-artifact-index-v3.json`。全域来源、三场景72h产流、1221段静态河网、72h干态/湿土无雨和60m暴雨快照已保存；30m湿土72h通过完整水账、只读mesh、2D/3D和诊断页验收。主暴雨和抬尾水均在17.8235h触及20m安全上限并保存一致拒绝前缀；半CFL只有未发布前缀，不能称时间收敛。尾水同雨比较通过：约13.5h起9个D4相连格受影响、最远120m、最大正水深差10.0468m、边界入流5411224.832m³。正式联合回归两次各113项唯一测试，0失败/0错误/0跳过。该轮完成的是可审查的有限区域全格水动力原型与证据链；30m不解析米级细槽，静态网络520条逆坡边未解决，边界不是天然出口，跨区河网及多层/地下三维继续属于后续阶段。当前检查点见[single-region-checkpoint.md](.scratch/terrain-framework/single-region-checkpoint.md)。

**当前阶段收口（2026-10-01 16:18北京时间）**：[3小时核心流程](.scratch/terrain-framework/next-round-mountain-3h-plan.md)的主要目标已完成，[实时检查点](.scratch/terrain-framework/mountain-3h-checkpoint.md)记录固定路径。实际30m Terrain Diffusion内陆源、group960两湖三场景72h降雨、Manning局部三维、100m强迫追加及176项唯一联合回归均已独立接受有限范围。完整天然出口、全域双向回水、跨窗口无缝mosaic及全网三维仍未完成，不将本轮有限窗口当作全工程完成。

**最新交付（2026-10-01，37/38有限完成）**：双山地六场景已加入29/12河段储水传播、唯一局地分配与14天时间滑块；现实尺度配置/独立Y64预设实现。协调水账/Edge通过，联合79项78通过1旧可选依赖跳过。[成果及下一步](.scratch/terrain-framework/mountain-propagation-result-20261001.md)。新GPU推理未运行，下一主线为现实尺度TD输出及合法山地床面/湖泊/断面闭合。两实施者冻结关闭，下方运行中叙述为历史。

**当前联合推进（2026-10-01）**：[37山地河段传播](.scratch/terrain-framework/issues/37-mountain-channel-propagation.md)与[38现实尺度生成/游戏预设](.scratch/terrain-framework/issues/38-physical-generation-and-game-preset.md)并行实施。本轮目标把降雨实际分配到山地河段并形成出口过程，同时解除新生成配方的游戏高度目标，补Y64导入层显式配置；最终按固定证据交付可审查结果，不把条件图或线性库称完整物理河床/动力波。

**当前增量（2026-10-01，任务36有限完成）**：Terrain Diffusion普通/压力山地各三种降雨情景、土壤/快慢库与14天退水已保存，26项相关测试及独立水账/真实Edge通过。[交付与后续](.scratch/terrain-framework/mountain-rainfall-result-20261001.md)。后续仍以生成山地推进；山地河床/断面水动力耦合、现实尺度新生成配方及Minecraft Y64预设实现仍待完成，不能把局地产流总和称河口洪峰。

**当前方向修订（2026-10-01）**：用户明确后续以Terrain Diffusion生成山地开发河网，现实米制尺度优先；实测DEM/自然口认证用于现实对照，不再阻塞所有生成山地研发。新增[36降雨产流](.scratch/terrain-framework/issues/36-mountain-rainfall-runoff.md)：土壤/快慢库、退水与两份山地可视结果。1024/Y64归Minecraft导入预设，旧Y62缓存/Java格式另保留，详见[更新米制约定](.scratch/terrain-framework/metric-standard.md)。上一轮464项为原工程基线，不覆盖本轮新增能力。

**当前交付（2026-10-01 05:21，优先于以下历史）**：31/32/33/34/35有限范围冻结并独立接受；9800m²双域地表、两连续工程海口、V(h)传播/双向回水已接网页2D/3D，13新案例+3legacy可审查。最终同次31模块464项：462通过、2Windows链接权限跳过、零失败错误；实际Edge16案例通过、零pageerror，99文件起止hash稳定。[交付入口与剩余门槛](.scratch/terrain-framework/overnight-surface-result-20261001.md)。服务http://127.0.0.1:8765/保留，A/B与验收均已结束；真实认证、一般跨精度、完整动力波及地下多层3D未完成，17/22/25/26/27继续claimed。

**当前验收（2026-10-01 05:06，优先于下方历史）**：31/32/33工程切片、34网页与35严格只读校验修复均已独立有限接受且冻结；最终31模块联合回归与Edge回放正在同次运行，目录run-20260930T210555225217Z，不累加旧424或聚焦成绩。9800m²双域地表、两工程出口、V(h)回水与13固定案例可在http://127.0.0.1:8765/审查。[本轮结果与剩余门槛](.scratch/terrain-framework/overnight-surface-result-20261001.md)。A/B均已关闭；完整自然认证和地下/多层3D仍未完成。

**当前长轮收口（2026-10-01 04:39）**：31离散V(h)、32两出口工程联合包、33原9800m²陆地足迹clamped工程解释已有独立有限验收；13固定案例及3legacy实际2D/3D网页回放通过。34严格导出5项中2失败来自旧evaluation隐式H0采样，正在[任务35根因修复](.scratch/terrain-framework/issues/35-static-engineering-validation-repair.md)，不放宽guard、不改原包/旧报告；最后同次联合回归待修复冻结后运行。[当前结果与缺口](.scratch/terrain-framework/overnight-surface-result-20261001.md)、[检查点](.scratch/terrain-framework/overnight-checkpoint.md)。本条优先于下方历史waiting/草稿/前端未接入；地下/多层3D门禁仍未解除。

**当前长轮实施（2026-10-01 03:41）**：用户确认Sonnet前端交付并授权开工；31离散V(h)与32双实际工程海口/全域forest统一包已冻结、协调独立接受有限规格，不累加旧424项。A修复并接入审查页，B实施独立[任务33原land像素足迹](.scratch/terrain-framework/issues/33-engineering-land-pixel-coverage.md)，模型均GPT-6.1 Sol medium。首轮Edge浏览器发现首次画布尺寸错误、3D每帧约1.25s和dynamic标3D实2D，正在修复，不能称页面验收完成。详见[实时检查点](.scratch/terrain-framework/overnight-checkpoint.md)与[最长约10小时计划](.scratch/terrain-framework/next-round-10h-plan.md)。真实认证和地下/多层3D门禁仍未解除。

**当前交付优先级（2026-10-01）**：用户要求先总结并把accepted地表/海口/动态回水/真实DEM缺口接入网页2D/3D审查，前端由Opus实施；[进度与切换](.scratch/terrain-framework/progress-and-visual-review-20261001.md)、[可直接交付的前端提示词](.scratch/terrain-framework/opus-surface-review-prompt.md)。后续子代理GPT-6.1 Sol medium。31/32保留未验收草稿，无新固定证据，基线仍424项（422通过2跳过）；可视化地表不等于地下/多层三维河网完成。

**最新工程接续（2026-10-01）**：同源干燥fine extension已补指定双域节点包络600cells，新增全域动态forest覆盖16nodes/14edges/2独立出口；两切片冻结并独立验收，任务29/30仅有限范围resolved。最终同次27模块424项（422通过、2权限跳过、0失败）292.726秒。[最新结果与三维门槛](.scratch/terrain-framework/surface-continuity-resumption-result.md)。真实认证、完整陆地足迹/一般跨精度、两出口真实海岸端到端drop与断面V(h)仍缺，17/22/25/26/27保持claimed，3D未启动。以下600gap/仅domain1动态图/410项等为历史产物状态，不覆盖新切片范围。

**资料与准备最新状态（2026-09-30）**：已直接核查D:/geography的109文件/265397067字节，完成显式资料清单与五包静态开发准备诊断两切片，主协调独立验收；最终同次25模块410项（408通过、2权限跳过、0失败）238.443秒。[结果及下一步](.scratch/terrain-framework/geography-development-preparation-result.md)。任务28仅有限资料接收/诊断范围resolved；真实认证器与同源端到端仍缺，17/22/25/26/27保持claimed，3D未启动。两实施者已冻结关闭；下方356等为此前历史。

**最终本轮状态（2026-09-30）**：mosaic限定湿接缝/跨精度cells、连续4.2m→0m工程海口几何、动态storage/conductance图与accepted recovery动态图适配四切片均冻结并独立验收。最终同次22模块356项通过161.039秒；[完整结果与缺口](.scratch/terrain-framework/surface-3d-readiness-result.md)。真实DEM33454未知/自然口与datum未认证、旧两域600cells fine gap仍诊断，动态仍常面积线性K；任务17/22/25/26/27不关闭，按用户先后顺序未启动3D。两实施者已关闭，以下活动文字均历史。

最新活动（2026-09-30）：用户要求真实山地/自然出口、跨域fine mosaic/共享边界/跨精度、连续海口drop及动态河道蓄量/传播/双向回水完成后再尝试三维河网。两个互斥实施组推进mosaic/coast及动态slice；真实DEM仍33454未知、独立出口与垂直基准未认证，三维尝试暂不越过门禁。详见[前置计划](.scratch/terrain-framework/surface-3d-readiness-plan.md)、[独立审查](.scratch/terrain-framework/surface-3d-readiness-review.md)。

最新增量：动态常床storage/conductance独立切片已验收，29项聚焦通过；固定`verification/dynamic-surface-hydraulics/run-20260930T121232.238906Z/`有协调JSON。它尚无accepted recovery到动态图adapter，不等于完整河道动力学。mosaic修复与[连续海口drop](.scratch/terrain-framework/surface-coast-drop-plan.md)继续，最终同次联合回归未运行；任务26/27与17/22/25保持打开。

后续增量：mosaic限定湿接缝/共享节点/整数跨精度cells已独立接受，20项聚焦通过10.538秒；run123659含协调JSON。旧双域10m fine gap仍600cells diagnostic，不是完整全域mosaic。连续drop与[源图动态适配](.scratch/terrain-framework/surface-dynamic-prepare-plan.md)继续实施。

后续海口增量：连续4.2m→0m工程source-triangle几何已独立接受，19项聚焦通过7.147秒；run125523含协调JSON。84nodes/120triangles、实际河端全宽附件与cut/Q通过；新海側仍synthetic，不是自然出口认证。源图动态适配和最终同次联合回归继续，四项未齐不建立3D河网。

活动接续（2026-09-30）：用户再次要求完成完整地表河网；本轮完整水文域调度与湖河连续连接几何两个 bounded slices 已完成独立验收，最终联合回归271项通过。详见[本轮计划](.scratch/terrain-framework/surface-domain-connector-plan.md)与[独立审查](.scratch/terrain-framework/surface-domain-connector-review.md)。真实山地、动态回水及跨精度门禁不放宽。

最新验收（2026-09-30）：完整水文域调度与湖河连续连接几何两个 bounded slices 已独立验收；最终固定证据分别为 `verification/surface-domain-prepare/run-20260930T103111870204Z/` 与 `verification/lake-river-connector/run-20260930T105124.463722Z/`。待同次联合回归确认后，仍不宣称完整地表河网完成：真实山地/自然出口、连续fine mosaic与共享边界、连续海口drop、动态回水/跨精度及Java/游戏消费继续开放。

最终同次联合回归：271项通过88.798秒；上述两个固定证据目录均含实施报告和主协调独立审查JSON。仍不宣称完整地表河网完成：真实山地/自然出口、连续fine mosaic与共享边界、连续海口drop、动态回水/跨精度及Java/游戏消费继续开放。

接续结果（2026-09-30最新）：移动中心线完整细准备与同格tiles生命周期两切片已通过固定验证和主协调独立验收，各最终目录有independent-review.json；最终同次16模块221项通过68.264秒，不累加旧176或聚焦运行。详见[接续与独立验收](.scratch/terrain-framework/surface-engineering-resumption-review.md)。任务17/22/25保持打开，以下停写交接段为上一轮历史；本轮不代表完整地表河网完成。

交接状态（2026-09-30最新）：用户要求整理后交给下一智能体，两实施者已停写并关闭。移动中心线完整准备与独立tiles存储留下三个未验收草稿文件，已知锁竞争和样例Q问题待修；未新增已验收测试或固定产物。先读[交接入口](.scratch/terrain-framework/handoff-next-agent.md)和[冻结审查](.scratch/terrain-framework/surface-engineering-review.md)。下文176项为前序已验收基线。

当前主线（2026-09-30）：继续完成完整地表河网。任务24真实低地固定路线闭环、任务25自动谷面/恢复、单池湖泊时序、通用只读交付和单向湖泊出流联算切片已独立验收。最终176项相关测试通过18.684秒；完整真实山地域/自然出口、湖河连续水几何、动态回水与跨精度消费仍未完成，地下保持暂停。详见[工程进度](.scratch/terrain-framework/surface-river-progress.md)与[本轮审查](.scratch/terrain-framework/surface-system-review.md)。

本轮后端补齐：DEM v2精确中心米制候选及HydroRIVERS现有证据审计通过独立切片验收，69项相关测试/4104点源采样一致；真实候选仍33454未知，河口未认证，不发布。前端留给后续Opus，原始资料只读。详见[独立审查](.scratch/terrain-framework/dem-evidence-review.md)与[证据需求](.scratch/terrain-framework/surface-evidence-requirements.md)。

- [ ] [任务25地表实际恢复接入](.scratch/terrain-framework/issues/25-surface-recovery-integration.md)：自动恢复、累计谷床预算、单池时序及单向出流联算和非游戏只读交付切片通过，最终176项相关测试通过。真实两山地仍超谷深且人工出口；完整山地、湖河连接器/回水与跨精度未验收。[独立审查](.scratch/terrain-framework/surface-system-review.md)。

- [x] 移动中心线细准备与同格tiles存储切片：流量守恒、实际移动床/湿面、语义重放与诊断隔离；排他锁、取消/resume、lazy只读、精确接缝与唯一节点积分通过。[本轮验收](.scratch/terrain-framework/surface-engineering-resumption-review.md)。方块跨度与矩形查询不等于跨精度；无游戏部署。

- [ ] 地下暗河首轮候选规划：地表河网 + 灰度入渗/侵蚀参考 + 岩性/渗透性参考层，综合评分筛选入口，规划可分叉地下明渠至地表/海底出口；验证覆岩、断面、连通、跨域和网页双视图，首轮不修改岩体。
- [ ] 地下暗河后续几何：在首轮路径验收后加入多层柱/实体拓扑与有限 VDM 侵蚀；洞口、洞顶、坍塌和地下湖独立记账。
- [ ] 地下湖第二轮：加入库容—水位、入流/出流/渗漏/蒸发账本，允许地下河接入地下湖及海底出口。

- [ ] 地表河谷完成后再做地下暗河原型：以 VDM/灰度图提供受约束输入，以独立三维实体/拓扑表达通道；验证米制映射、表里连接、支撑/开孔和水量/体积收支。不得提前接入 Minecraft 或把 VDM 单独当作洞穴拓扑。

- [ ] [任务22：受预算约束河谷塑形与失败回退](.scratch/terrain-framework/issues/22-valley-budget-recovery.md)：旧切片仅预算诊断，后续任务25已实现自动谷面/累计预算、失败驱动改线恢复及单池湖泊时序；完整山地和湖河连续水几何仍未完成。任务保持打开，[最新审查](.scratch/terrain-framework/surface-system-review.md)；[旧诊断复核](.scratch/terrain-framework/valley-budget-review.md)保留历史。

- [x] [任务21：共同水位、连通淹水与联合验收](.scratch/terrain-framework/issues/21-stage-bank-joint.md)：三项接入完成，56项回归通过；合成双支流及槽外淹水静态通过，真实域仍失败。[验收与河网主线位置](.scratch/terrain-framework/channel-joint-review.md)。下一步处理完整真实域、河谷塑形与改线/湖泊。

- [x] [任务20：受限中心线平滑](.scratch/terrain-framework/issues/20-channel-centerline-smoothing.md)：固定锚点、偏移/交叉检查、平滑后床坡与局部诊断完成，50项测试通过；[验收](.scratch/terrain-framework/channel-centerline-review.md)。水位/岸线联合检查仍待完成。

- [x] [任务19：局部河槽断面](.scratch/terrain-framework/issues/19-local-channel-sections.md)：米制扫掠、预算/保护、分块一致性与边界诊断完成；[验收](.scratch/terrain-framework/local-channel-sections-review.md)。自然弯道、完整粗细衔接、水面与河谷主体仍待完成。

- [x] [任务18：米制河槽规划](.scratch/terrain-framework/issues/18-metric-channel-plan.md)：独立宽深参数、按距离纵坡、预算与精度不足诊断完成；[验收](.scratch/terrain-framework/metric-channel-plan-review.md)。旧v4回归通过；局部断面、水面、河谷塑形、真实标定及任务17仍待完成。

- [ ] 河网原因诊断与完整域规划：[任务17](.scratch/terrain-framework/issues/17-river-feasibility-diagnostics.md)诊断和29项回归完成，一次扩域找到低地辅例，完整山地双支流/出口与预算仍缺。见[阶段验收](.scratch/terrain-framework/river-feasibility-review.md)。

- [x] 河网离线验收执行：22项回归通过，真实两山地核心河道仍全部未解决，未发布；须修复域/出口与洼地规划、床水连续性和河宽分辨率耦合。见[本轮验收](.scratch/terrain-framework/metric-rivers-review.md)。

- [x] 用户放宽高度标准：Y800软目标，允许少量峰但低于1024，导出保留1022安全表面上限。已有13份v5重评全部高度安全，31项回归通过；见[任务15](.scratch/terrain-framework/issues/15-soft-800-hard-build-limit.md)。此前Y800失败结论为历史标准。

- [x] v5高基底平滑压缩输入：13次推理、39项回归完成；普通山地起伏部分恢复但压力峰仍超限，未改默认、未跑河网。见[验收与限制](.scratch/terrain-framework/soft-knee-review.md)。

- [x] 河网前固定参数复验6窗：5窗高度通过，已知压力窗仍Y851.73且逐点复现；河网启动条件未满足，见[复验结果](.scratch/terrain-framework/height-confirmation-review.md)。

- [x] v4独立基底/起伏/海深与最多3次统一批次重试；20次真实推理，8份留出快照完成。压力窗仍Y851.73、普通山地起伏降低，参数未推广默认，见[验收与缺口](.scratch/terrain-framework/separated-budgets-review.md)。

- [x] 多种子高度实测：18次真实推理；12基线窗中1窗超Y800、2窗低于Y-64，SNR配对未解决最差窗。默认参数未改，见[数据与建议](.scratch/terrain-framework/height-benchmark-review.md)。

- [ ] 剩余迁移按[五轮路线](.scratch/terrain-framework/remaining-rounds.md)推进：高度发布检查 → 有限世界分块 → 地表水文 → XYZ/洞穴实体 → 集成清理。当前先实施[任务10](.scratch/terrain-framework/issues/10-height-publication-gate.md)，各轮独立验收。

- [x] 新生成输入适配Y800目标：geographic_v3两份真实高原/高山样本完成加工和导出，最高Y763.085/Y716.509；旧原始样本保留，1米/方块不变。新种子仍需逐成果验证，见 [高度验收](.scratch/terrain-framework/height-budget-review.md)。

- [x] RegionProcessor首阶段米制配方定稿及默认processed Java只读切换：54项Python测试、Java全编译回归通过；Java新路径仅导入/方块适配与群系，不生成地貌。详见 [最终验收与工程进度](.scratch/terrain-framework/final-cutover-review.md)。完整多块世界、水文、洞穴和实际软件/游戏验收仍未完成。

- [ ] 后续Python米制算法迁移：RegionProcessor首阶段、30米配方及Java默认processed只读切换已完成；河网、VDM、洞穴及其它旧算法仍待迁移。核心默认海面126米，Minecraft固定Y62，1米=1方块；见 [最新验收](.scratch/terrain-framework/final-cutover-review.md)。

## 当前优先级（2026-09-28，框架审查后）

- [x] 通用数据契约独立首版：米制参考表面／位移、身份、表面水及显式保存重载，由 GPT-6 Sol 实施、主协调审查；6 项契约测试及 24 项旧流程回归通过。范围与未完成项见 [验收记录](.scratch/terrain-framework/contract-review.md)，不等于框架迁移或消费者验收完成。
- [x] 已有分区成果接入通用双包：用户已确认[任务 06](.scratch/terrain-framework/issues/06-legacy-region-integration.md)，GPT-6 Sol 实施，主协调验收；只读取已保存真实成果，不改算法，以显式准备和程序化只读消费为本轮终点。状态与证据见[接入记录](.scratch/terrain-framework/legacy-integration-review.md)。

- 2026-09-29 最新顺序：先确认跨领域框架准备规格并治理契约与模块边界，再验收地表支流汇合主线。第一轮独立小样例验证内流湖，第二轮在主展示中加入完整内流域；辫状水系和三角洲仍独立改进，接入及移植后排。代码、资料索引与验证成果均留在本工作区。
- [ ] 跨领域框架准备规格整体确认：见 [.scratch/terrain-framework/spec.md](.scratch/terrain-framework/spec.md)，包含已确认要求、模块保留／迁移／隔离清单与分轮验收；具体任务由 [路线图](.scratch/terrain-framework/map.md) 索引。
- 外部资料统一目录：`D:/geography`（用户指定，包含后续资料和既往相关对话）。工程保存来源索引与验证产物；不自行搬移或删除旧资料目录。首次核对时新目录为空，迁入后更新来源索引。
- [x] 地表汇流首版离线流程：显式出口、保守汇水、共享汇流格、流量控制宽度、有限下切、水面与四邻连接、派生 NPZ/垂直位移保存。合成 Y 型场景与 17 项主线测试通过；见 `research/river-erosion/地表汇流本轮验收.md`。
- [ ] 真实模型样窗的河床连续性：当前人工出口样窗仍有未解决河道/侧岸，最长剖面失败；完善全流域边界、湖泊与受限切穿后再验收，禁止把诊断数据当成导入成品。
- [ ] 成果转移到其他程序：待本地算法验收后，明确目标程序、许可、数据格式、坐标/单位、算法版本、性能预算及适配测试；本轮不部署或移植，不把独立实验自动加入主线。
- [x] 独立分流与输沙首轮改进：显式水力能力取代固定 70:30、共享河段流量汇总、湿路径输沙与沉积/移动库存/开放边界收支；27 项本轮相关测试通过，未接入主线。依据与限制见 `research/river-erosion/资料改造依据.md`。
- [ ] 辫状河道半成品独立改造：分流/再汇合、走廊限制、流量分配与失效回退；先测试和自然度验收，暂不接入地表河流主线。
- [ ] 三角洲半成品独立改造：真实河口与海洋连通、切向沉积、泥沙体积/孔隙率/导出余量；先独立验证，暂不接入地表河流主线。

- 用户最新优先级：先提升长期可维护性，暂停向默认生成路线扩展新侵蚀功能。按 `CONTRIBUTING.md` 分阶段重构；结构调整和算法参数变化分开验收。
- [x] 样本网页预览首版：读取 Java 处理器保存的三个真实模型样本，提供三维旋转缩放、二维查询、原始/派生高度切换、连续权重和垂直位移图层。启动说明见 `web-preview/README.md`；与 Minecraft 方块画面分开验收。
- [ ] 网页后续：读取任意游戏区域成品、剖面比较、跨区域拼接；水体、洞穴和多层 VDM 需要独立网格/体积导出协议。
- 旧地形测试存档已获用户授权清理；开发阶段不要求历史存档兼容，稳定版本后再设计迁移。其它 Mod 的存档保留。
- [x] 新默认路线取消 Java 导入阶段的整体三倍放大，独立定义游戏海平面 Y=62、世界上限 1024 和模型单位映射；真实 GPU 样本已有，但游戏画面与区块仍待验收。
- [ ] 以模型地理条件和推理参数控制山体尺度、起伏及间断程度；Y=700–800 是世界最高一批峰的真实样本目标，不要求每座山达到该高度。按 `research/高度与地形区域设计.md` 对照平原、高原、高山的绝对高度与相对起伏，分清扩散前意图和扩散后实测标签；派生实测分区已实现，但扩散前地貌意图尚未实现，不逐区域归一化。
- [ ] 原始扩散输出与派生结果已分配独立配方缓存；侵蚀、崖壁 VDM、洞穴保持可选且基础模式默认关闭，继续完成真实游戏验收。
- [ ] 按 `research/工程框架审查-2026-09-28.md` 分离区域准备、只读查询和 Minecraft 写入，统一地貌规划与数据契约。
- [ ] 长期维护：将 source/recipe/scale 合法组合收拢到单一版本化模式定义，UI、预检及运行时共享；统一格式化并拆分旧河网的布局、状态和空间查询。开发阶段暂不承担旧存档迁移，历史实验模式单独隔离。
- [ ] 已完成 6 次真实 `geographic_v2` GPU 推理与参数对照，第二种子样本最高峰 Y751.41；平原候选仍偏丘陵。继续完成真实 Minecraft 区块保存重载、接缝/水面与客户端画面验收；模型样窗不能代替游戏观感。
- [ ] 区分平原与丘陵的意图及实测标签；候选 `R128<60` 不足以单独判定平原，还需低坡连通面积和多尺度起伏。
- [x] 首版实测高度/起伏/坡度连续权重及派生平滑：保护海岸和局部山峰，25 样本 halo 保持窗口一致，原始模型数据独立保存。大尺度丘陵整平、河道识别与保护仍待后续算法。
- [ ] 统一高度数据契约命名：当前服务 `GenerationConfig.sea_level` / RMD2 中间基准仍为 72，Java `TerrainScale.RAW_MODEL` 映射到游戏海面 Y=62；现有样本无海面抬高问题，后续消除命名歧义时须版本化身份。

项目名称：**Terragenesis（山川形意）**。内部 `remotemountains` 标识暂时保留，以兼容现有存档。

- [ ] 修复山海流域汇流处悬空水：统一支流水面与最终 VDM 水陆边界；保留扩展服务端河岸扫描失败作为回归证据（种子 20260927，世界 X1890 Z-48）。

## 本轮范围与后续分工（2026-09-28）

- 当前优先：随机种子地理条件已接入现有 Terrain Diffusion，首版分区派生处理与导入已完成离线验证；下一步验收真实新世界画面、跨区水面和保存重载。基础模型暂不替换。
- 后续代码实现由 GPT-6 Sol 承担，主协调负责方案、接口审查、集成和结果验收。
- [ ] 后续全域基础地形开发：自研可替换的全域基础高程生成器，覆盖海陆、大陆尺度起伏、山脉布局、跨区域河网和侵蚀；复用统一高程/VDM 数据与 Minecraft 导入接口。作为后续工作，不阻塞当前 Terrain Diffusion 版本。
- [ ] 用相同尺度、种子集合与地貌指标对照自研后端和 Terrain Diffusion，评估自然度、运行成本、跨区域一致性后决定默认方案。

## 当前路线

原始 Terrain Diffusion → 连续地貌分区权重 → 独立保存派生 height/垂直 VDM → 导入 Minecraft 方块。首版代码与离线验证已完成；真实新世界画面、保存重载和水面仍待验收。旧演示模块属于另一条路线。

- [x] 首版完成分区权重、边界 halo、派生包身份与只读导入；原始模型缓存保持独立，离线构建和验证通过。
- [ ] 在真实 Minecraft 新世界验收区域派生预设的画面、跨区水面与保存重载；离线预览不能代替此项。
- [ ] 独立河网原型：以世界坐标 XYZ 节点/河段表达地表河、地下明渠和湖泊出口；先验证汇流共节点水位、无环流向、水沙收支及无出口湖泊库容，再尝试受浸润床岸侵蚀。默认区域派生预设暂不接入，方案见 `research/长期维护与三维河网设计.md`。
- [ ] 以河网中心线扫描可变截面管状影响域，使用平滑掩码限定支持；仅在连通浸润的河床与河岸表面、受水面约束的位置塑形，避免盲目侵蚀地下半柱。区分路径切向、实际流速与岩壁法向；侵蚀可采用 `E=M K max(tau-tauc,0)^p` 并接入泥沙守恒。先由高度场上的一维 stream-power / 二维浅水模型推进，再扩展曲面薄层流，地下明渠和有压流分别处理；床岸 VDM 更新与体积拓扑改动分开。本项仅为后续规划。
- [ ] 后续流水：全域流域与跨区入口/出口、连续水面纵剖面、地上地下连接；水沙守恒后再做侧蚀与沉积。VDM 负责既有曲面的崖壁/洞壁塑形，穿孔和崩塌由体积拓扑负责。
- [ ] 按 `research/river-erosion/三维河网与Minecraft落地设计.md` 逐步实现多层柱邻接通量、横向侵蚀损伤、柱分裂与支撑检查；不得将路径掩码和经验退缩原型视为已复现 2024 多层高度图论文。
- [ ] 沉积优先验证三角洲，兼顾内弯沙洲和地下湖底：输运、已沉积及导出方块分账，保存小数余量与孔隙率；从地下湖库容—水位关系、河口输沙和体素连通检查推进到真实游戏验收。
- [ ] 后续风化与风蚀分开：岩层耐蚀差异、风场、输沙和遮蔽先形成守恒约束；局部 VDM 处理表面退缩，崩塌拓扑另行处理。
- [ ] 后续美化：地形细节、河岸/崖脚沉积、植被与原版方块材质过渡；以游戏性、跨区连续与性能验收。参考研究见 `research/farseek/参考评估与后续路线.md`。

当前优先用 Terrain Diffusion 跑通基础地形及塑形前后预览。基础地形不要求由模型直接输出 XYZ 位移；已有直接 VDM 扩散实验保留为研究代码。

## 区域地形数据后续工作

- [x] 独立区域路线首版：按多个区块准备并持久化基础高程、水、气候、地貌标签及完整 XYZ VDM；支持有限矩形预生成、磁盘优先读取和按需生成。
- [x] 版本化随机形状逻辑地貌区布局与存储格网分离，区域包保存地貌标签；其过渡权重尚未驱动基础高度和岩壁位置。
- [ ] 在真实 Minecraft 区块中验收新预设的生成、保存、重载和客户端画面。
- [ ] 为同一数据集并发预生成增加跨进程锁和冲突处理。
- [ ] 跨区域水系先统一流域出口、河道水面和泥沙通量，再处理区域交界；区域缓存本身不生成连续的全域河网。
- [ ] `surface_cross_domain` 只读跨域/跨精度 seam 适配器已完成小型 fixture 门禁；真实全域共享边界、跨精度水文与自然海口仍待外部输入和独立验收。
- [ ] `surface_cross_domain.adapt_saved_mosaics` 已接入保存的 domain/fine mosaic 冷读审计；保存包未提供完整河网边证据时保留 `edge_evidence_complete=false`，不从网格邻接伪造水文。
- [ ] 基于相邻区域共享的高度、水、气候和地貌条件，加入版本化的交界侵蚀与噪波融合；明确其对最终 VDM 的作用及边界验收。预留处理模式不能算已完成侵蚀。
- [ ] 让地貌区归属和过渡权重真正约束 Terrain Diffusion 高度轮廓、群系与后续塑形；随机地貌区形状本身不等于山脉形状已受控。
- [ ] 对相同种子、不同区块加载顺序、缓存删除后重建及移动存档做区域身份与结果一致性验收。

## 支持多种基础地形算法

2026-09-28 补充：将 Terrain Diffusion 作为可替换基础高程后端，工程主体负责地理条件、流域校正、侵蚀、VDM 和 Minecraft 导入。优先跑通可靠版本，再增加独立程序化后端对照，不立即从零训练同等级扩散模型。

- [ ] 程序化基础后端：大陆/海陆、山脉骨架、噪声细节与侵蚀输出统一高程数据；和 Terrain Diffusion 使用相同种子/坐标约定及验收指标。
- [x] 地理条件生成器首版：全球坐标连续、种子确定的粗高程、温度、季节性、年降水及降水变异；`geographic_v1` 不读取 WorldClim/ETOPO 栅格或统计缓存，已接入真实模型推理。使用平滑值噪声、海拔降温及简化风向/雨影关系，仍非完整气候模拟。
- [ ] 地理条件到水文：明确年降水单位与模拟步长，计算蒸发/下渗/汇流；避免条件图水汽与演示水沙台账相互脱节。
- [ ] 分发时保留 Terrain Diffusion MIT 版权与许可证、模型来源及版本；重新分发原始 DEM/气候数据时分别核对数据条款。

2026-09-27 用户提出：基础地形也可以使用其他算法生成，加入后续开发计划。

- [ ] 将基础地形生成器设计为可替换模块，沿用并完善 `BaseTerrainSource` 接口；每种算法独立实现。
- [ ] 统一输出约定：世界种子、坐标、采样间隔、高程单位、海平面及可选气候数据，使各生成器共用 VDM 转换与后续塑形流程。
- [ ] 保留 Terrain Diffusion 作为当前实现，评估 Perlin/Simplex 多层噪声、山脊噪声、侵蚀驱动及水系约束等候选算法；先比较效果和成本，再确定实现顺序。
- [ ] 支持通过配置选择基础生成算法，并评估按地貌群系选择或混合算法；处理区域过渡、区块接缝及水系衔接。
- [ ] 将算法名称、版本、参数和种子纳入缓存与存档身份，避免更换生成器后新旧地形不一致。
- [ ] 使用固定种子和同等尺度比较生成速度、内存占用、自然度及与 VDM 塑形的兼容性。

## 当前待完成

- [ ] 优先修复流域汇流处残余悬河：加强的服务器检查在世界 `(1890,-48)` 等处发现最终 VDM/水面不一致；保留失败回归，统一河段交界与体素化后的岸线，不靠隐藏水或抬岸掩盖。

- [x] 接收富春江照片、地形图与卫星影像，核对本地资料和已有粗条件导入接口；记录于 research/fuchun-reference/资料评估与下一步.md。
- [ ] 获取富春江参照范围的带坐标DEM和主要水系，统计谷宽变化、山脊/支谷层级，区分水库与天然河段。
- [ ] 对同种子运行无条件、粗高程条件、条件加水文校正三组真实扩散实验；验证粗条件尺度能否保留宽谷，不能默认锁定细河线。
- [ ] 增加富春江风格的湿润低山宽谷参照，保留平地与局部盆地；Y700–800只作整体最高峰目标，不统一抬高所有山体。
- [x] 补充长江源区、三峡、富春江三段参照方案并审查DEM获取清单，见 research/fuchun-reference/长江源区三峡与富春江分段方案.md。
- [ ] 获取三类典型区域的小样DEM，提取坡度/相对起伏/谷宽/分支指标；标记冰雪质量与库区，使用统一河网与连续纵剖面连接地貌，避免逐段DEM硬拼。

- [x] 新增独立山海流域世界预设，保留旧有限地貌展示；海平面 Y=62、山峰目标 Y=700–800。
- [x] 独立演示使用统一粗河网：源区、支流汇合、河谷、单一入海口；局部 VDM 岩壁接收分配水量并把出流水沙回传下游。
- [ ] 将全域实时扩散地形接入跨区域河网；确定海岸/出口后再生成区块，不能逐区块选择入海口。
- [ ] 用地形驱动的河网或河网条件扩散替换演示世界的预设宏观坡降和三支流布局，进一步改善山脊、支流非对称性及分水岭自然度。
- [ ] 将下游水沙通量反馈到河床演化与河口沉积几何；当前新演示的水沙账本守恒，不等于完整动态地貌演化。

- [x] 新增有限演示地貌测试区和全域实时 Terrain Diffusion 世界预设。
- [x] 将全域固定中心岩壁扩展为按地貌区域选择的多个局部面片（0.5.0）。
- [ ] 将真实模型瓦片共享边界规范为单一确定值；本次相邻推理窗口误差最大约 0.04 方块，尚非逐值一致。

- [x] 完成真实 Terrain Diffusion 基础地形推理，输出基础地形与 VDM 塑形后的对照预览；有效样片见 preview/terrain-pipeline/20260927_-7680_0_513。
- [x] 完成当前固定悬崖的 VDM 格式、几何与区块接缝验证；任意复杂面片的自交/拓扑修复仍待完成。
- [x] 完成打包模组的专用服务器生成与保存重载验证，结果见 verification/diffusion-server/results.json。
- [ ] 完成 Minecraft 客户端选用“长垣 · 地貌世界”后的实际画面确认；不能把预览渲染或服务器验证当成客户端截图。

## 岩壁生成与贴壁流水（2026-09-27）

- [x] 巫峡参考：在原有流域坡面上添加间断岩壁，支持混合角度与统一类型；代码检查覆盖河道保护、面片间隔和VDM体素化，真实服务器记录见实现状态。
- [ ] 将固定尺寸完整面片改为沿山嘴/支沟/岩层分段的自然崖带，变化长度、高度与朝向；建立坡面降雨/支沟到崖顶的入流路径，替换演示比例分配。
- [ ] 将峡谷候选位置从独立演示河段扩展为DEM/扩散地形的谷壁识别，依据坡度、曲率、河距与山嘴/支沟结构选择，不铺满整条河。

设计见 research/岩壁Voronoi与贴壁流水设计.md；局部岩壁实验已实现，完整区域水系和崩塌沉积仍待扩展。

- [x] 为局部岩壁提供独立面片采样、倾角与向内/向外倾斜参数，正确映射回 VDM。
- [x] 用非均匀 Voronoi 定义岩块、节理和耐蚀度，避免等宽蜂窝裂缝；基础地形仍先经过 Terrain Diffusion。
- [x] 实现有世界重力方向的贴壁径流，允许横向汇流、平台积水、离壁下落与重新接触。
- [x] 补充岩壁/沟槽侧向退缩、岩层差异侵蚀，区分水流切向运动与岩石法向退缩。
- [x] 岩壁及缓冲面片采用统一跨区块缓存，最多 12 个面片；淘汰重建保持一致（0.5.0）。
- [ ] 将面片的上游汇水和下游水沙接入区域水系，统一面片间通量。
  - 0.7.0已在独立山海演示中接入单个岩壁面片与统一流域台账；全域多面片互联仍待完成。
- [ ] 对穿孔、失稳、落石、崖脚堆积采用局部体积处理，避免 VDM 顶点位移冒充拓扑变化。
- [ ] 输出垂直、普通斜坡、悬挑三种基准面和侵蚀前后对照，检查守恒、接缝、退化面与可重复性。

## 安装诊断

- [x] 确认 2026-09-27 用户实例中 0.2.0 已加载，但两个存档使用 minecraft:noise；需新建并选择自定义预设。
- [x] 添加工作区内只读安装诊断工具及测试说明，见 verification/installation-20260927。
- [ ] 为首次安装的跨进程文件锁和安装子进程等待设置超时、取消及失败提示；当前派生区域首次采样会同步等待安装，安装卡住时其他区域读取也会停住。
- [ ] 后续增加游戏内生成器状态提示，使“装了模组但使用普通世界”的情况更易识别。

## Long-round surface-network execution

The next 8-10 hour round follows `.scratch/terrain-framework/long-round-surface-network-plan.md` and `.scratch/terrain-framework/long-round-execution-checklist.md`: real DEM outlet classification, tiled topology, rainfall routing, read-only review export, then gated 3D river geometry.
- **2026-10-02 v3 全域普通雨审计**：`A-storage-v3-ordinary-5s-20261002T001500Z` 只有输入索引，没有水力输出；已写 `incomplete.json` 与 `independent-audit.json` 明确拒绝残留冒充完成。v3 全域 ordinary/strong 门禁未通过，所有 `hydraulic_ready/transient_converged/publishable` flags 保持 false。
