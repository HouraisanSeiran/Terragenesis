**2026-11-08 三角洲当前进展另存独立检查点。** 第一阶段形态、代码、同址图集和物理续算已打包，798 个文件逐项校验通过；原 v5 基线保持不变。[存档与回执](.scratch/delta-archives/README.md) · [接下来的自然度优化顺序](.scratch/delta-naturalness-20261108/checkpoint-next-steps.md)。本次仅存档和记录方案。

**2026-11-08 三角洲自然度第一阶段已验证。** 保留独立 v5 归档，冻结同一主要河网后改善河形、低地绕行与连续断面；100／30 m 同节点同路径，12 口／5 环保持，保护高丘切动和中心线阻塞均为 0。100 m 最新剖面完成 600 秒水沙、账差 0 和冷读逐位续算，89 项相关测试通过；100 m 宽平原数组保持原值。完整多尺度平原、漫滩微地形、差异填湾、潮汐、新旧河道和新版百公里案例仍待推进。[本轮验收](.scratch/delta-naturalness-20261108/phase1-review.md) · [同址图集](验收图片/三角洲自然度-河形与断面-20261108/README.md) · [下一项](.scratch/delta-naturalness-20261108/issues/02-plain-relief.md)。

**2026-11-08 三角洲有限域链已交付：参考图纠偏形态＋水沙续算＋百公里平原。** 已取消数圆拼接和强制口外沙洲，以真实低地/水深和有限地质库存构造宽阔平原，保留湾汊与山丘；基准连续平原267.03 km²、原口左右宽7.15／3.25 km。相同算法百公里内部跨度100.3 km（口门跨度24.57 km）；两例均完成600秒、固体账差0、冷读续算逐位一致，65项相关回归通过。潮流反转、长期漫滩/迁汊未接，30 m诊断有岸边切山及拓扑变化，多尺度未通过。用户反馈本版明显改善，已存为[独立归档基线](.scratch/delta-archives/README.md)；下一轮按[自然度方案](.scratch/delta-naturalness-20261108/plan.md)逐步比较。[图集](验收图片/地形约束三角洲v5-水沙与百公里-20261108/README.md) · [验收及后续边界](.scratch/delta-completion-20261107/final-review.md) · [形成过程与参考图修正](research/三角洲形成过程与参考图修正-20261108.md)。

**2026-11-07 世界过程集成实施中。** 用户批准将水力/侵蚀沉积、500Ma事件地质历史和季节环境并入默认世界任务；2km粗预览先发布、重点TD区域续算，新增CPU目标180秒。规格与分工见[本轮任务](.scratch/world-process-integration-20261107/spec.md)，完成状态以实测与验收记录为准。

2026-11-08最新复验：v2基础1600km/2km世界已按原门槛实跑，墙钟162.71秒、CPU142.64秒、峰值2.89GB；独立水沙账、实际地图读取、查询顺序及真实round08分支冷恢复一致。环境仍partial-or-pending。地下水、冻融、冰川、生态化学、潮浪等13项进入[完整接入任务](.scratch/world-environment-integration-20261108/spec.md)，逐项按[消费者与收支矩阵](.scratch/world-environment-integration-20261108/acceptance-matrix.md)验收；不把基础世界通过当作环境链完成。[二阶段完善程度](.scratch/world-process-integration-20261107/closure-20261108/stage2-readiness.md)。

新增环境接入当前受资源阻塞：默认v3、完整状态/年度续算、根系/Manning消费者和地图后台已实现；暖/冷真实TD六类库存账、45项冷恢复数组及水盐/生物量反馈通过。季节地冰最大85.293mm水当量，非多年冻土认证；预热湖水初始数组及分阶段出流修复后，真实TD默认一年预热、一年输出、冷读再续算一年及保存数组水量账通过。整1600km、最终候选冰川/潮浪同源精算、全域成本和图件未验。连续三轮资源拒绝，最新attempt04可用2.155GB＜要求3.991GB，原生TD主机/GPU也拒绝；未启动，没有在途生成。目标标blocked、不标完成，资源可用后继续原来源。[元素表](.scratch/world-environment-integration-20261108/integration-status.md) · [局部证据](.scratch/world-environment-integration-20261108/continuation-lake-acceptance.json) · [阻塞及恢复审计](.scratch/world-environment-integration-20261108/resource-blocked-audit.json)。

**2026-11-08 火山岛体量与Voronoi纹理已修正为v5候选。** 按用户反馈拆开紧凑上锥与低缓熔岩裙坡，去除侵蚀型放射硬槽；固定种子、扭曲平滑Voronoi实际改变堆积厚薄、口缘与岛岸，`volcanic_lava_strength`可关闭。主工程148项与织梦31项通过，旧v4精确回放；15张同址新旧/关闭/开启图供用户继续判断自然度，不代表岩浆物理或游戏验收。普通岛仍按>25km²处理。[验收](.scratch/volcanic-islands-refinement-20261108/review.md) · [图集](验收图片/火山岛Voronoi形态修正-20261108/README.md) · [接口](docs/ocean-islands.md#特殊火山岛)。

**2026-11-07 岛屿山系面积条件已放宽。** 默认实际露海面积严格>25km²即可准备山系，无默认腹地宽度门槛；25–100km²岛requested峰高为300m加固定±10%波动，较大岛沿用原300–3000m面积曲线。普通世界生成已接线，CPU任务pending，显式GPU任务复用既有TD链；两遍整岛raw统计/共同scale保护海岸与区块接缝。真实TD单块及最终世界消费已验证，完整真实岛峰高仍因内存门槛未验。[当前规则](docs/island-mountains-current.md) · [放宽记录与统计](.scratch/ocean-islands-20261106/area25-relaxation/review.md) · [原模型验收](.scratch/ocean-islands-20261106/area100-world-system-v3/review.md)。

**2026-11-07 海洋岛屿与岛链v3有限域已验证。** GPT-6.1 Sol实现、主端审查：分层米制噪波、无四向强制谷切、有界海底平滑拼接；正式64万格及全部局部冷读通过，固定交线坡跳0.481184→0.000373m/m、无新增陆桥。织梦实际公开CLI生成和加强审计通过，修复闭合负床误变陆；45.80秒、抽样RSS约440.21MiB。大型岛显式TD资格与派生链已实现，默认面积≥2000km²且3km岸缓冲后连续腹地内接圆直径≥20km；真实主源最大323km²，未触发模型。完整无限源及真实TD山形响应另验。[调用说明](docs/ocean-islands.md) · [大型岛TD](docs/island-mountains.md) · [审查](.scratch/ocean-islands-20261106/review.md) · [图集](验收图片/板块海洋岛链-20261106/README.md)。

**2026-11-05 历史交接（已由当前状态修正）。** 评估、河网统一及输沙调查曾暂停；之后复杂三角洲形态已推进到v4，并有三组DEM和图包，不能再称代码/形态尚未开始。v4尚未耦合实际水沙、海侧沉积和库存续算。当前以[2026-11-07完成任务](.scratch/delta-completion-20261107/spec.md)为准；历史交接保留供追溯。

**2026-11-04 三角洲45°转折/90°禁行已验。** 共用不规则路径接入倒数转向代价，动态分汊/挂接检查入出边与重汇接续；原两处急转作登记局部重建，保留四口和三组分合。169节点/171边/173种真实转接最大87.404°、≥90°为0。相关38项测试有通过记录，主端600秒/22项独立检查及三态冷读通过，泥沙账差0、无漫岸；扇面不裁剪沉积或洲体。仍属构造初态及短事件。[新图包](验收图片/三角洲转向约束与局部分合-20261104/README.md) · [验收](.scratch/delta-braided-acceptance-20261104/angle-acceptance.md)。

**2026-11-04 四口三角洲已补三组局部分合。** 在已验洲体上新增实际分开—重汇河槽，保留原四海口；171节点/173唯一边，新增3个独立环。600秒末态新臂Q约100–130m³/s、有效宽49–91m，全网无漫岸；施工挖方单列储备、固体账差0，相关24项回归与主端冷读通过。扇面仅用于河流方向，未裁剪地质/海洋沉积域或洲体形状。属于显式初始构造，长期自组织辫状河与百公里仍未完成。[用户图包](验收图片/三角洲多分汊与局部分合-20261104/README.md) · [主端验收](.scratch/delta-braided-acceptance-20261104/acceptance.md)。

**2026-11-04 四口三角洲形态重新验收已交付。** 复用现有地质沉积、分级河网/河宽和实际边图，真实TD32km/100m窗形成28.62km²连岸低平洲体，沿岸8.8km、向海约4km，三处分叉含child、四独立湿流海口。正常Q1500无漫岸，600s事件库存/源/冷读重算全部通过；属于显式地质构造初态与短事件，复杂潮沟洲岛/长期自发及百公里保持未完成。[用户图包](验收图片/四口三角洲形态验收-20261104/README.md) · [主端验收](.scratch/delta-morphology-acceptance-20261104/acceptance.md)。

**2026-11-04 山体方向更新及世界粗山系候选已交付。** 当前为大陆基底→世界粗山系→TD局部山地与特殊形态；历史独立局部试验不再作为TD替代主线。GPT-6.1 Sol双代理完成核心/导出，主端审查修正C0跳变并独立冷读。真实1600×1280km大陆、5km预览/2km正式、16bit灰度与浮点数组已保存；2km512000格prepare2.123秒、采样RSS158.24MiB，18项相关检查及全部格心/源身份/灰度/快照核验通过。粗布局可读，串珠/模板感保留，5/2km栅格不能直接混接；TD局部接线、水文、无限增量及默认替换未做。[主端E1–E9](.scratch/world-mountain-belts-20261104/review.md) · [图集](验收图片/大陆基底与世界粗山系-20261104/README.md) · [规格](.scratch/world-mountain-belts-20261104/spec.md)。Terra可用性探针仍503。

**2026-11-04 动态分汊接线及未触发对照已验。** GPT-6.1 Sol开发，主端加两子代理共最多3活跃。显式登记、真实双臂Q/湿深/有效宽、有限候选与床升消费接通；有限库存机制两次沉积触发新汊与再分叉。主端22项回归通过；真实TD14km/100m半年+25h四态库存/重算通过，但section淤高未达.1m、未增新汊，成熟三角洲保持未完成。[主端验收](.scratch/delta-reference-shapes-20261104/main-dynamic-e-review.md) · [新图包](验收图片/三角洲动态分汊接线与未触发对照-20261104/README.md) · [后续局地输沙24](.scratch/delta-reference-shapes-20261104/issues/24-hydraulic-sediment-capacity.md)。

**2026-11-04 已交付：分级山脊骨架与可变截面试验。** Terra渠道503后经用户授权由主端实现与审查；两级弯曲主支脊、三种同几何截面与低幅背景/Advanced组合完成。七组401²60m、16bit灰度/float64阶段、关闭细节峰体及剖面已保存，65项相关检查与冷读通过，512²近/远10.66/9.89秒。三向分叉模板与沿脊细线保留，源间峰—鞍连接、真实次峰与谷线为后续方向；自然度/水文/默认替换未完成。[主端审查](.scratch/mountain-skeleton/review.md) · [图集](验收图片/分级山脊骨架与可变截面-20261104/README.md) · [规格](.scratch/mountain-skeleton/spec.md)。

**2026-11-04 局部两组分合与水沙演化已验收、形态仍partial。** Terra实测503，按用户授权由GPT-6.1 Sol完成物理边图接线、有限拓岸/实际成形Q及显式年度容量平衡。真实TD 14km/100m两组分合、半年冲淤+25h潮汐保持Q1500，四态库存/湿路/冷读通过；第一环是原陆地、第二环仍水下，远海边界沉积浓集与新生多汊待改，不能称成熟三角洲。[图包](验收图片/三角洲两组分合与水沙演化-20261104/README.md) · [主端范围](.scratch/delta-reference-shapes-20261104/main-c-review.md) · [远海沉积22](.scratch/delta-reference-shapes-20261104/issues/22-marine-boundary-deposition.md) · [动态新汊23](.scratch/delta-reference-shapes-20261104/issues/23-dynamic-bars-and-multibranch.md)。

**2026-11-04 河宽复用反馈已验收。** GPT-6.1 Terra完成固定占地multicell链：复用现有断面与材料参数，事件侵蚀/年度沉积反馈下一步设计宽，实际宽受占地约束，保存同态水力；年度输沙显式限容量并保留超额库存。主端30项测试及真实TD100m、2s案例8项独立检查通过。主动拓岸、实际水文成形Q和连续复杂分合未完成。[主端验收](.scratch/delta-reference-shapes-20261104/main-width-review.md) · [具体任务](.scratch/delta-reference-shapes-20261104/issues/10-existing-width-feedback.md)。

**2026-11-04 恢复开发：按参考图验证复杂分汊、分后汇合和沙洲。** 局部优先100m，世界概览约1km并保留主要水系；先修多格占地/共同水头分流，再接分合水沙与同源沙洲演化，最终完成百公里案例。GPT-6.1 Terra实施，主端验收，pyDeltaRCM仅参考。[最新规格与顺序](.scratch/delta-reference-shapes-20261104/spec.md) · [验收清单](.scratch/delta-reference-shapes-20261104/acceptance.md) · [当前派工](.scratch/delta-reference-shapes-20261104/progress.md)。

**2026-11-04 已交付：局部胞状体量叠加与深沟壑试验、图形学方法研究。** 保留原宏观，只截局部体量乘原山体后叠加；负雕刻最大由约131m加深至315m，近零坡度淡入。五组401²灰度/剖面、48项回归和独立解码通过，512²近远11.46/11.69秒；自然度和水文仍未通过。[主端审查](.scratch/mountain-local-volume/review.md) · [灰度图集](验收图片/局部Voronoi体量与深沟壑-20261104/README.md) · [10类图形学方法筛选](research/图形学地形生成方法筛选-20261104.md)。后续优先研究分级曲线骨架和可变截面，不将研究建议视作已实现。

**2026-11-04 已交付：连续山脊乘胞状体量的灰度山脉试验。** 固定种子20260903，先组合宏观再驱动Advanced；主窗alpha0/0.65/1与负窗四组401²、60m的16bit灰度高度图、8bit预览及float64数组已发布。54项相关测试和主端独立解码通过，512²近远5.34/5.31秒；平滑后胞边界伪影减轻，部分沿脊细线及宽缓峰形仍保留，水文未接入。[主端审查](.scratch/mountain-product/review.md) · [灰度图集](验收图片/连续山脊乘Voronoi-20261104/README.md) · [规格](.scratch/mountain-product/spec.md)。自然度未通过，默认来源不变。

**2026-11-04 已交付：独立山体直脊柔化与局部破缺功能候选。** GPT-6.1 Terra实现，主端独立冷读与图审；世界锚定高斯、结构弯曲、正脊切低及小幅岩面噪波完成，75项相关测试通过。512²近远生成18.04/17.82秒，四组数值与优化前逐值一致；蜂窝组织和碎山仍明显，参考山自然度及真实河网保护未通过。[主端E1–E9审查](.scratch/mountain-ridge-breakup/review.md) · [图集](验收图片/山脊柔化与破缺-20261104/README.md) · [规格](.scratch/mountain-ridge-breakup/spec.md)。默认世界来源未切换。

**2026-11-03 活动目标：百公里扇区分级河网通过完整25h，继续接沉积触发新汊。** 真实路径加入顶点/扇面、层深3/单河侧汊2/口门8上限及折返/绕行限制，实际5口。主端14项回归和独立事件检查通过，低均高潮五口湿路成立；厚沉积体106.23×50.73km。初始网形仍由规划形成，长期自发分汊未完成。[本轮报告与图集](.scratch/delta-hundred-km-20261103/fan-event-review.md) · [进行中反馈任务](.scratch/delta-hundred-km-20261103/multicell-feedback-task.md) · [规格](.scratch/delta-hundred-km-20261103/spec.md)。pyDeltaRCM仅参考。

**2026-11-03 当前完成：三角洲构造算法有限域交付。** 已继承原床面与库存，复用非规则河道、标准阈值动态分汊及共享水沙链；后续2等效年与25h潮浪形成两个主要水下叶瓣，三口实际移动约703/308/376m。111项相关测试及四阶段冷读8项通过，最终存档副本已校验并重载。[约5.3MB图集与存档](验收图片/三角洲沉积叶瓣与口门演化-20261103/README.md) · [逐要求主端验收](.scratch/delta-material-lobes-20261103/main-completion-review.md) · [接口](.scratch/delta-material-lobes-20261103/implementation-guide.md)。演化200m，100km仅为来源图幅；最终低潮一口、均潮两口、高潮三口通流，粗网格出口规则仍需改进。当前构造目标已关闭，成熟平原/岛洲潮沟及百公里案例继续由[09后续任务](.scratch/coast-marine-reorganization-20261102/issues/09-morphology-and-multibranch.md)跟踪，用户自然形态验收保留。以下为历史阶段记录。

**2026-11-03 阶段交付：三角洲非规则河网与五年海洋输运。** 已共享既有谷线寻路内核，真实坐标/河段长度接入水力、输沙、库存及有限切沙延口；标准阈值下单主路实际新增两汊，形成三个通海口门。年度与事件海洋输运现共享真实口门流量/方向，不重复供沙；新增事件逐口过沙记录。整合108项测试通过；年度显式海侧交付及同源0.05年续算另验通过；额外五年海洋续算及末态25h潮浪通过主端来源、沿线床水面、共享流量和水沙账冷读。第一口前移200m；出现连续近海沉积，但独立叶瓣及成熟自然形态尚未通过，完整目标保持开放。[约5MB图集与末存档](验收图片/三角洲非规则河网与五年沉积-20261103/README.md) · [完整范围](.scratch/delta-irregular-reuse-20261103/spec.md) · [主端审查](.scratch/delta-irregular-reuse-20261103/main-current-review.md)。

**2026-11-03 用户验收候选：100km区域三角洲图已交付，形态尚未通过。** 100×100km视域、200m网格、原生TD30m，3个实际活动口门及水沙/共同断面/保存冷读通过；主要连续出露块约15×7km，口门集中且有明显直角，不称百公里大型三角洲。2年阶段为河道/漫滩，低阈值情景启用新汊后另算25h潮浪，未完成多年海洋搬运。[候选图集与约17MB数据](验收图片/大区域三角洲候选-100km-20261103/README.md) · [主端审查](.scratch/delta-large-acceptance-20261103/main-review.md)。

**2026-11-03 当前交付：三角洲连续演化工程初版。** 45km窗口、100m计算、同源TD30m与历史库存守恒迁移；实际断面/水沙→分流→有限漫滩/冲淤→潮浪/口门追岸→新汊反馈和保存续算已闭环。5等效年后新增一条实际通水分汊，再完成两次25h事件；主端来源/床面/水面/预算独立检查通过，83个不同相关测试通过。Q150为情景，末态只通过16.819m³/s，其余留账。自然形态仍有D4直角与长直段，多级分汊/稳定平原尚未全验：[交付与接口](.scratch/coast-marine-reorganization-20261102/main-full-delivery.md) · [约21MB图集与存档](验收图片/三角洲连续演化工程初版-20261103/README.md) · [已验08](.scratch/coast-marine-reorganization-20261102/issues/08-evolution-integration.md) · [剩余形态09](.scratch/coast-marine-reorganization-20261102/issues/09-morphology-and-multibranch.md)。百公里、默认世界、前端与500km未启动；冰川先讨论。

**2026-11-03 历史进度：统计潮滩与分汊河流水面接线已验收，继续实际断面和漫滩。** 本轮主端34项相关测试通过（潮滩/长期11项、水面/分汊23项）；已修同址湿干库存、河流海位误判及嵌套分流。最终25小时末五支有水，但假定3m上游水头下总接收仅109.631m³/s，3000m³/s输入的大部分明确待交付，完整三角洲仍未完成。[最新河网/水面图集](验收图片/分汊河流水面接线-20261103/README.md) · [潮滩机制图集](验收图片/统计潮滩与分汊复核-20261103/README.md) · [下一步07实际断面与漫滩](.scratch/coast-marine-reorganization-20261102/issues/07-upstream-sections-floodplain.md) → [05稳定平原](.scratch/coast-marine-reorganization-20261102/issues/05-emergent-delta-plain.md)。06机制已resolved；百公里暂缓，冰川先讨论，500km不恢复。

**2026-11-02 河宽与三角洲原任务。** 河宽生产接线先行，三角洲依赖上述新海岸前置任务。[任务规格](.scratch/river-width-delta-20261102/spec.md) · [进行中审查](.scratch/river-width-delta-20261102/main-feedback.md)。

当前进展：河宽生产接线及同断面下一水沙步骤已通过[01 验收](.scratch/river-width-delta-20261102/issues/01-width.md)。V7 修复虚假海路阻断，库存与潮汐时钟续算接口已发布；三角洲多轮共同床面反馈仍在集成。用户已选择新增独立浅大陆架情景用于百公里例，保留原 TD/全部陆地；[底图契约](.scratch/river-width-delta-20261102/shelf-contract.md)与[主端核查](.scratch/river-width-delta-20261102/main-shelf-v2-check.json)。不把地质底图调整计作河流沉积，未宣称新大型三角洲已完成。

**2026-11-02 已交付：约45/114/255 km 三组真实 TD 沿岸复合三角洲初版 DEM 与分汊河网。** 77页来源完成，主端核查来源、保存床面、连通和流量/沉积预算通过。沿岸细长形态及深盆地填积为明确限制；三尺度已有各自冻结几何的25小时地理潮汐证据，大型局部岸顶超高5.22m和时间步敏感性尚未通过，不宣称完整动态三角洲算法完成。[中文对比与来源](验收图片/多尺度三角洲-20261102/README.md) · [主端验收](.scratch/delta-scale-suite-20261102/main-review.md) · [后续动力学修复](.scratch/delta-scale-suite-20261102/issues/04-tidal-quality.md)。

**2026-11-02 已交付：三角洲潮汐、波浪与有限冲淤工程闭环。** 同源 30 天无潮/潮汐/潮汐加波浪三组完成，100 段河槽、3 个口门接双向水沙、河岸交换和床面反馈；主端修正过高水位并独立验收，25 项相关测试通过。规则矩形湿区来自 300 m 常水位投影，保守重建后明显减轻，波浪情景仍有网格痕迹。原生 DEM 30 m、海岸水动力 300 m，不称自发长成大型多汊三角洲或完整 30 m 水动力。[主端验收](.scratch/delta-tides-bars-20261102/main-review.md) · [图片与产品](验收图片/三角洲潮汐冲淤v6-20261102/README.md) · [实施任务](.scratch/delta-tides-bars-20261102/spec.md)。默认世界接线、细潮沟和长期自然拓扑演化仍后续；冰川先讨论，500 km 不自动恢复。

**2026-11-02 已交付：约25km沿岸三角洲地貌初版。** 同源原生TD上形成124.16km²连续新生低地，接入两级分叉、3个活动入海口与30天已知水沙情景；主端已核查实际床面、水位、来源与库存并检查图片。地质形成初态不冒充30天增长，活动河网只覆盖其中一侧；潮沟、周期潮汐、沙洲持续演化及默认世界消费者接线仍留后续。[图片与数据](验收图片/大三角洲活动河网v12-20261101/README.md) · [主端验收](.scratch/large-delta-20261101/main-review.md)。冰川先讨论，500km不自动恢复。

**2026-11-01 一阶段新大陆河网工程版已交付，形态待审阅。** 同一50km总图与多处分汊细图已发布；原生30m水量、湖泊连接、低地规则、稳定归属和修正产品只读接口已验收，7条小流量缺陷明确保留。见[最终交付与范围](.scratch/river-upgrade-20261101/stage1-delivery.md)、[图片](验收图片/原生河湖三角洲50km遥感合成-20261101-final/README.md)。二阶段按04起继续，冰川先讨论。以下为历史记录。

**2026-11-01 当前：50km初版河网已生成并接回低地规则；完整一阶段与三角洲继续推进。** [主端进度](.scratch/river-upgrade-20261101/main-progress.md) · [最新河网图](.scratch/river-upgrade-20261101/game-grade-lowland/river-map.png) · [工程顺序](.scratch/river-upgrade-20261101/spec.md)。已复用16页真实TD，122.88km支持域按90m求汇流、50km窗口展示30m床面；低地河线减少约15%，汇水总量不变，上游主河连续。实际流量/季节河分类、湖泊湿连通和三角洲仍待接线，不把候选河线或潜在湖面称为完整动态水文。按用户要求放宽游戏用途精度验收；[万公里粗DEM跑团用途预评估](.scratch/rpg-world-dem-20261101/assessment.md)已完成，全球尚未实测，美学另行负责。GPT-6.1 Terra实现、主端验收；冰川到时先讨论，500km原高精度验收及自然袭夺仍暂停。

**2026-11-01 已交付：按用户Coastal v1参考图完成轻量细化，并已阅读工程交接。** 保留同一64.08km旧TD山脉/平原/湾岬，仅恢复近岸被压制的TD细节，不叠独立噪波。1.32%格点发生微调，变化格点绝对床变中位4.6cm，幅度≤6m，可解析岛屿6→6；岸线距离P95 30m，独立子窗差0，主端34项测试通过。[验收与图片](.scratch/coastal-v1-refine-20261101/main-review.md) · [交接阅读](.scratch/coastal-v1-refine-20261101/handoff-reading.md)。新板块TD的任务02仍claimed，旧参考微调不代替新世界验收；500km保持暂停。

**2026-11-01 当前：新板块条件真实TD已生成；海岸形态被否决，任务02继续claimed。** 129页与913源窗生成、冷读成功，同页复跑逐位一致；跨请求大小重叠仍有最大9.77mm差异。强度1独立噪波改写过大且偏离TD风格，用户否决；已保存零噪波同源诊断，进一步发现宏观二次合成抹平TD原有湾谷。下一步保留TD局部地形，约束宏观纠偏，禁止以噪波堆岛。[最新复核](.scratch/plate-td-source-20261101/real-inference-review.md) · [原始TD对照](验收图片/板块条件TD接线-20261101/README.md)。此前联合39项、主端来源25项测试通过。一二阶段[任务补充矩阵](.scratch/world-generation-sequence-20261101/phase12-task-additions.md)已并入02—08，500km仍暂停。

**2026-11-01 当前：区域性海岸与群岛工程已完成主端验收。** Terra 实现、主端修订与独立验收；选定 regional-relief-v3 强度 1.0，同一 64.08 km 窗口可解析岛屿 6→25，总面积 1.4706→2.3445 km²，保留平静岸段。14 项相关测试通过，全幅及独立子窗重算差 0 m。[验收报告](.scratch/coastal-archipelago-20261101/main-review.md) · [全图和细节](验收图片/海岸群岛改进-20261101/README.md)。当前为旧保存 TD 上的初始地形塑形；新 Voronoi 大陆条件 TD、河流消费者接线、沉积与潮汐尚未完成。全深海核心对照通过，单独 v3 对照产品因内存预检未发布。已在海岸收尾后核对工程文档及实际河流链：[七项改进与来源接线评审](.scratch/coastal-archipelago-20261101/river-source-chain-review.md)，优先接通冻结板块条件 TD，再统一床面、河床连通、跨区边界、湖泊、季节多口及来沙；本轮未修改河流代码。

**2026-11-01 当前：海岸初版离线算法已完成。** GPT-6.1 Terra medium实现，主端独立验收：连续近岸合成、最终床面统一海洋分类、prepare/冷读及真实TD同址对照；10项海岸测试与23项相关回归通过，真实TD接缝误差0m，冷读失败不发布，同输入重跑身份一致。[主端验收](.scratch/plate-formation-coast-20261101/coast-main-review.md) · [64km与海岸细节图](验收图片/海岸初版-20261101/README.md)。最新多形状板块v4同址适配已实跑，该窗口全深海，不能冒称新板块海岸TD。现有河流算法已完成只读审查与主端复核，[六项优先改进](.scratch/plate-formation-coast-20261101/river-algorithm-review.md)涵盖同源床面、河床连通、跨区边界、湖泊水账、季节河口和来沙；河网重算/消费者接线、沉积与潮汐演化、新板块条件TD推理、大型三角洲和500km扩域后置。

**2026-11-01 历史：实施与生成全面暂停，先确认待办。** 用户明确参考图为恒河三角洲，要求扩大三角洲影响范围，先讨论大陆、海岸、三角洲和现有缺陷的优先级。[待办事项栏（讨论稿）](.scratch/tectonic-coastal-base-20261101/backlog.md)。当时只整理任务；已有研究和64 km成果保留，500 km不执行。

**2026-11-01 500 km 生成暂停，优先修正大陆与海岸来源。** 用户要求大陆由板块构造驱动，Voronoi 只作初始板块分区，宏观界面展示计算后的大陆；当前板块演化尚未实现。[当前范围](.scratch/world-scale-acceptance-20261031/spec.md) · [海岸与三角洲研究](research/海岸岛链生成与三角洲耦合-20261101.md)。季节积雪已改为 35% 不透明度的地理遮罩，[同源三图](验收图片/64km季节积雪遮罩-20261101/README.md)另存；本模拟年全年残留候选为 0，不冒称永久雪或冰川。宏观基底待按新方向重做；TD、汇流/盆地、河湖/高程已有 64 km 实跑证据，500 km 不继续执行，旧基底形态未通过验收。以下为历史记录。

**2026-11-01 64 km 同源世界样图交付，待用户审阅。** 独立单大陆布局，90 m 全域、30 m 河口；真实 TD、气候降水、现行不规则河网、湖泊、土壤植被、积雪与河口水沙已联合实跑，交付 10 张遥感式/专题图（含一张仅宏观规划定位图）。[用户图片](验收图片/64km世界联合验收-20261101/README.md) · [实测与待查项](.scratch/world-acceptance-64km-20261031/acceptance.md) · [后续计划](.scratch/world-scale-acceptance-20261031/spec.md)。宏观基底→TD合成→汇流/盆地→河湖/派生高程在本窗口均已执行；500 km 等用户审阅后扩展。一次土壤守恒异常未复现，完整重算通过但原因未确认，不标为全面验收通过；袭夺仍暂停。

**2026-10-31 三角洲顺流方向与潮道组织改进已交付。** 按用户纠正取消同岸大U，原4条主分汊向海，32条可解析潮路径中8条贯穿切岛；独立主向逆向长度为0。潮坪可达储量约束断面，湾岸与平台共同构造；明确选择有文献依据的3m理想潮差。46项联合测试、同源年度48子步、两潮周期水盐、全尺寸冷读/续算通过。[正式四图及实测](.scratch/delta-process-natural-20261031/acceptance.md) · [文献与独立形态比较](.scratch/delta-process-natural-20261031/research.md) · [使用说明](docs/delta-engineering.md)。实现收口，形态交用户验收；曲折度改善有限、两个断面有设计限幅，未称真实DEM标定或通用科学自然度认证。宏观基底→TD沿用保存来源；汇流与盆地分析复用上游与水力树；河湖及必要高程调整完成本轮方向/潮坪改进和实测；袭夺暂停。以下保留历史进度。

**2026-10-31 三角洲工程版开发完成：密集潮沟与破碎岸线。** 新增49处根沟口、164条三级潮沟，实际写入床面；原4个主出口全年48子步通海。37项联合测试、两实际潮周期水盐收支、全尺寸冷读及追加1小时恢复通过。交付[四张实测图与验收记录](.scratch/delta-tidal-finish-20261031/acceptance.md)、[使用说明](docs/delta-engineering.md)，[任务](.scratch/delta-tidal-finish-20261031/spec.md)已resolved。宏观基底→TD地形合成沿用保存来源；汇流与盆地分析复用上游及连续分汊水力树；河湖及必要高程调整完成本工程版三角洲收口。构造初始地形、年度水沙与简化潮汐交换分别记账；视觉自然度交用户验收，自发长期多汊、高沙挑战与真实DEM标定未转通过；袭夺暂停。以下保留历史进度。

**2026-10-31 三角洲自然形态改进已交付。** 修正逆折/回接海口，采用固定种子错站分叉、受约束弯曲与相邻河槽控制洲体；新增650m有限近岸槽床过渡，初始水下挖方单列。四个实际出口同源同年度水沙48子步全连通，24项相关测试和主端材料/海床/几何冷读通过。[同尺度新旧图与验收](.scratch/delta-natural-shape-20261031/acceptance.md)。形态仍偏平滑，交用户验收；自然长期演化和高沙挑战未转通过。宏观基底→TD沿用；汇流/盆地沿用上游并更新分汊几何；河湖及必要高程调整完成本轮形态与年度计算，袭夺暂停。

**2026-10-31 完整构造版三角洲已交付，形态待用户验收。** 按用户允许初始分汊构造的决定，复用既有16km场景与多级水力水沙；800×800、20m保存栅格，5出口含1次级分汊，48子步沿程通水并连通海边界。45项相关回归通过，主端全尺寸冷读及追加一小时续算通过，只发新水沙包。[成品、实测图与使用](.scratch/complete-delta-20261031/acceptance.md)。初始填挖和有限泥沙分别记账；分汊偏直、继承基底有拼接痕迹，高沙挑战失败，未称自然长期多汊完成。宏观基底→TD地形合成沿用并重采样；汇流与盆地分析保持既有上游并接多出口水力树；河湖及必要高程调整完成本构造版年度水沙和恢复；袭夺暂停。

**2026-10-31 大范围三角洲工程试验完成。** 固定种子、原生30m、128×128（3.84km×3.84km）域已完成单主槽→泛滥平原→浅海坡的二维水沙增长，第四面板改为实际面通量绝对值。12h账本闭合，但仍只有单主槽出口弧形沙体，未形成自然连续多汊；0.6m有限海床已触底。TD细节尚未接入，现实DEM仅作机制与窗口参考。[验收记录](.scratch/large-delta-trial-20261031/acceptance.md) · [现实三角洲资料与DEM](D:/geography/11-现实三角洲DEM与算法/研究报告与索引.md)。宏观基底→TD地形合成→汇流与盆地分析→河湖及必要高程调整：分别为已扩展、接口输入、二维FV、有限床变完成；自然多汊保持未认证。

**2026-10-31 五组河口条件形态实测完成。** 新增向海缓坡、150m宽口门、0.3m潮汐与0.3m入射波四例24h供沙，并复用平床基线，输出五张真实床面/水深/床变/潮汐图。[结果与图片](.scratch/delta-forms-20261031/acceptance.md)。10项相关测试通过，水沙预算闭合；仍为水下口门沙体，不认证成熟多汊。宏观基底→TD沿用，汇流/盆地保持新版图，河湖及必要高程调整扩展本轮有限形态对照；袭夺暂停。

**2026-10-31 三角洲48h实测与六张验收图已交付。** 固定种子、原生30m、有限可蚀海床，完成平床/微扰两组24h供沙及连续清水涨落水至48h；新6项测试通过。两组出现水下沙体两侧实际输水，但沿程连续槽形仍不足，48h完整沙洲保持指标未通过（两侧路径仍连通）。[实测、图片与使用](.scratch/delta-distributary-20261031/acceptance.md)，待用户形态验收；原总体自然多汊任务未关闭。宏观基底→TD沿用，汇流/盆地沿用新不规则图，河湖及必要高程调整完成本轮局部实测，袭夺暂停。

**2026-10-31 三角洲入口与二维水沙计算已交付，持续自然分汊未通过。** 已解除真实源图的八邻格入口限制，接通保存世界河口、二维床水反馈、潮浪响应、保存与冷续算；37项测试及8个子测试通过。12h有限供沙形成水下口门沙体，退水至7200s仍未形成可验的持续自然分汊；预设障碍岛绕流只作为机制控制。[交付与使用](.scratch/delta-development-20261030/acceptance.md)、[形态验证及未完成项](.scratch/delta-development-20261030/morphology-validation.md)、[现实案例资料](D:/geography/10-现实三角洲案例/研究报告与索引.md)。宏观基底→TD沿用，汇流/盆地沿用新版不规则图，河湖及必要高程调整增加动态三角洲；河流袭夺继续暂停。以下为历史记录。

**2026-10-30 二阶段有限工程版已完成（最新）。** 按用户放宽后的验收口径，补齐G6土壤/根区水→覆盖→实际生长、环境出口→既有Manning/Exner水沙床变、相邻独立河段保存/只消费一次/冷续算，以及同世界河口→既有三角洲沉积/海盆水热。[交付与使用说明](.scratch/stage2-finish-20261030/acceptance.md)；[世界接线01–04](.scratch/stage2-world-integration/spec.md)与[G9–G20](.scratch/stage2-g9-g20/spec.md)按工程范围resolved。最终联合选择13项测试通过，复用既有案例证据，不累计重叠测试数。宏观基底→TD沿用；新汇流/盆地保持；河湖及必要高程调整完成有限工程接线。世界级动态覆盖、完整逆坡/回水、长期自然地貌和真实物性标定另列后续；河流袭夺继续暂停。资料整理到[D:/geography/09-二阶段环境水文接线](D:/geography/09-二阶段环境水文接线/)。以下为历史记录。

**2026-10-30 重构与随后季节接线已验收。** 公共存储、环境职责和旧Java准备/只读查询完成[重构](.scratch/codebase-refactor-20261030/spec.md)，旧行为基线保持。随后接通G2→G9材料、G3/G4→G7→G5→保存河网及逐格ET次步回收，[联合验收134/134](.scratch/stage2-world-integration/seasonal-validation.md)通过。宏观基底→TD沿用，新汇流/盆地保持，河湖增加有限季节供水；64×64固定域不代表世界动态覆盖。默认下渗结果与零交换交接对照分别保存。下一步补G6母质/覆盖、实际水动力及独立域持久交接，见[任务卡](.scratch/stage2-world-integration/spec.md)；河流袭夺暂停。

**2026-10-30 G9–G20有状态联合首版完成。** 十二项有限机制已接成可保存、冷读、续算的环境产品，固定内陆/海岸TD样例验证物质与能量收支、实际消费者及来源不变。[逐G验收与剩余任务](.scratch/stage2-g9-g20/acceptance.md)。宏观基底→TD沿用；汇流/盆地增加局部床变后归属提交；河湖/高程增加多过程反馈。接下来依次补同世界季节驱动、完整水动力/动态侵蚀消费、跨区域持久状态及长期地貌案例；原G9–G20完整目标和二阶段整体未全部完成。

**2026-10-30 新河网下游模块补验。** 已盘点157个直接/间接相关生产模块，补查水沙、降雨传播、河槽、跨域动态及冷读，修复真实边长、原点传递和旧成品只读兼容等遗漏。[联合验收与剩余边界](.scratch/river-generation-review/module-validation.md)。低流量细支流隐藏但保留累计来水；42km实源证据继续有效；完整水动力连通、新世界动态侵蚀仍未完成，G9–G20本轮局部共同联动见上条。

**2026-10-30 活动D8替换范围验收与河网显示筛选完成。** 新不规则图已在42×42 km、196万格同源TD上实算，928个湿湖、71条普通河段和18个完整盆地跨请求接缝，原始源未改。[实测与河网图](.scratch/river-generation-review/real-source-acceptance.md) · [退役审计](.scratch/river-generation-review/d8-retirement-audit.md) · [显示阈值](.scratch/river-generation-review/display-filter-spec.md)。旧D8证据仅作历史；G9–G20按[任务卡](.scratch/stage2-g9-g20/spec.md)继续，未自动标完。

**2026-10-30 42km跨区域水文交接完成，二阶段计划已复核。** 宏观基底沿用；TD分块合成196万格；汇流/盆地与河湖/高程在磁盘模式统一计算，37条完整河道边、17个完整盆地跨原请求界，独立水量账与冷读通过，78.77秒/600.91MiB。[任务08](.scratch/large-world-first-pass/issues/08-disk-region-handoff.md) · [四阶段实测](.scratch/large-world-first-pass/disk-region-handoff-validation.md)。世界级稳定域边界/永久归属与增量调度仍由[任务06](.scratch/large-world-first-pass/issues/06-demand-connected-world.md)跟踪。双风格地图[Claude实施交接](.scratch/world-atlas/CLAUDE-HANDOFF.md)已就绪，UI未实施；二阶段已标有限完成，后续按[同世界环境→雨影产流→雪冰入河→海岸交换](.scratch/stage2-world-integration/spec.md)推进。

**2026-10-20 石柱群真三维程序化生成 + VDM 柱壁雕刻原型已跑通（用户明确要求：不做二维高度场，用 VDM 在柱壁上雕刻）。** 用户先问「石柱群底座应该是圆的吗」，再定方向。诊断成立：现路线是高度场（[`metric_special_terrain_forms.py`](terrain_pipeline/metric_special_terrain_forms.py) 位移场 → [`metric_special_terrain_surface.py`](terrain_pipeline/metric_special_terrain_surface.py) 规则网格），每个 `(row, col)` 只有一个 `z`，所以**截面只能是等高线**（代码里 `rx == rz`，就是那个圆盘），**竖直柱壁 / 铁帽外凸 / 凹龛根本表达不了**。改为**真三维闭合实体**：复用仓内 [`hybrid_rock_boolean.py`](terrain_pipeline/hybrid_rock_boolean.py) + [`hybrid_cave_geometry.py`](terrain_pipeline/hybrid_cave_geometry.py)（不新内核）——节理网络用抖动栅格 Voronoi 胞给每个柱一个**不规则多边形截面**，内缩 3 m 出真节理缝，然后每顶点沿外法线横向位移（`taper` 上细下粗 / 两级 `striation` 节理横纹 / 两级 `flute` 纵向凹槽 / 顶部 30 m `cap` 铁帽外凸），`combine` 成一体。**三个真实根因（都是先出结论、被探针推翻，均勿重犯）**：①**报 `no consistent winding found` 的其实是容差不是绕向**——手搓 double 体积与 MESH64 差 ~1.7e-6 相对量（MESH64 会重焊近重合顶点），仓内 `_volume_gate` 的 1e-9 是给 `to_mesh64()` 往返记录用的，改用仓内 `save_manifold` 导出即从构造上对齐；②**墙三角化按 CCW 环走 → 法线朝内**，MESH64 的 `volume()` **带符号**，`volume() > 0` 把唯一合法盖组合漏掉了（盖 4 种翻转须**各配一次全局反转**）；③**`taper` 一开始用「到世界原点的距离」当径向**，它沿周长任意变化、还随柱子在场地里的位置变，把壁面整段拉折——改为**绕自身质心的精确相似收缩**（正相似变换把简单多边形映成简单多边形，**可证不折**），满深度柱 8/16 → **14/16**。另有：mitre 角局部曲率半径≈0，内缩超过它就折（不平滑时 15/16 柱在离底 4–16 m 折掉）→ 环须 `resample(1.5 m)` + `smooth(4 遍)`；环顶点 ~12 m 而凹槽波长 11 m 会**混叠**（呼应 `SAMPLES_PER_FEATURE = 4`）。**实测**（candidate，仅原型）：plain 16 柱 / 3 755 顶点 / 11 985 720.22 m³；carved 16 柱 / 97 981 顶点 / 11 378 293.13 m³ / 满深度 14/16 / `components = 1` / 闭合实体门 passed / 逐水平截面均简单；两分支 exit 0。**资料**：张家界石英砂岩峰林硬事实（多组垂直节理控制形态、棱角平直、金鞭岩「四棱分明」/ 御笔峰「方正如削·上细下粗」、铁帽 ~30 m、演化四阶段）已逐项标等级并入文。**文档** [`docs/special-terrain-pillars-3d-20261020.md`](docs/special-terrain-pillars-3d-20261020.md) · [对比图](.scratch/special-terrain/pillars3d-20261020/pillars3d-prototype.png) · 原型与数组 `.scratch/special-terrain/pillars3d-20261020/`（三脚本已从归档位置重跑验证）。**已落仓（用户答「可以」后执行）**：新模块 [`terrain_pipeline/special_terrain_pillars3d.py`](terrain_pipeline/special_terrain_pillars3d.py)（1127 行，`td-special-terrain-l1-pillars3d-v1` / `…-report-v1`、`ALGORITHM=joint-controlled-sandstone-pillar-field-with-vdm-carved-vertical-walls-v1`、`SUPERSEDES` 声明 **`sandstone_pillar_field` 旧高度场值作废**并指名 `metric-special-terrain-v1` + `-surface-v2`；`status=candidate`、六能力位全 False；**被 pin 的 `metric_*`/`diffusion/*` 零改动，`verification/` 零写入**）。产物 `.scratch/special-terrain/l1-preview-20261020/pillars3d/`：`report.json` sha256 `e00b359f…82269`、`carved.npz` `2efaa000…d2b0`、`plain.npz` `51f2737b…5dd9`、identity `a44932dd…5477`，数字与归档原型**逐位吻合**（plain 3755/7506/11985720.215367893 m³；carved 97981/195958/11378293.132742487 m³ / 满深度 14/16 / `carve_scales=[1,1,.5,1,1,1,1,1,.7,1,1,1,1,1,1,1]` / components 1 / 七个见证全 true）。报告顶层另带 `pillar_footprints`（16 项节理胞环 + 面积）、`level_schedule`、`plateau_ring_xz_m`。**已接进 `web-preview` 真三维展示**（第四项地形输入工作区「石柱群 · 真三维闭合实体」）：只读适配器 [`web-preview/pillars3d.py`](web-preview/pillars3d.py)（报告按 sha256+identity、两份 npz 按 digest **四重硬 pin**，被改动即拒读）、[`web-preview/pillars3d.js`](web-preview/pillars3d.js)（三层：雕刻实体 / 未雕刻棱柱线框对照 / 柱顶节理胞轮廓；二维平面画**多边形节理胞而非圆盘**，着色可切「柱高 / 雕刻深度 step」，两根未满深柱以锈色跳出）、`bridge.py` 三条 `/api/pillars3d/*` 路由 + 静态白名单、`index.html`/`app.js` 五处挂接。**验收**：契约单测 [`tests/test_pillars3d_preview.py`](tests/test_pillars3d_preview.py) **15/15 OK**；真浏览器验收（CDP + node 内置 WebSocket，不依赖 playwright）[`tools/verify_pillars3d_browser.mjs`](tools/verify_pillars3d_browser.mjs) **17/17**，含「只留雕刻层仍 rasterise（lit 823095）」「平面 lit 208942」「切雕刻着色出现锈色像素 172995」「`full_depth==14`/`components==1`/见证全 true」「supersedes 指名旧 schema」。**落仓时新发现的两个真缺陷（勿重犯）**：①**截面简单性门是假阴性**——共享竖边上的交点被相邻两个三角各算一遍、二者差 ~1e-11 m，而 shapely `polygonize` 要求端点**精确相等**，于是**笔直棱柱**也返回 0 个多边形（plain 报 208/256「折」）；**真因是容差不是几何**，修法是缝合前把端点吸附到 1e-6 m（修后 plain/carved 均 **256/0**），该容差说明已随产物写进见证的 `method_note`；②**`overlap_removed_m3` 恰为 0 是对的**——节理缝让 16 柱互不相交、基座整体在 y<0，输入互不重叠则并集不减材料；真正可测的是 `carved_removed_m3 = 607427.08 m³`。另：柱环面积比 15.7（角部 0.82 m² vs 内部 12936 m²）是 **Voronoi 边界胞被裁剪的真几何**，不是缺陷。**仍未认证（必须如实说）**：**自交专项检查未做**（`self_intersection_verified` 保持 False；只保证**逐水平截面**简单 256/0，**不保证整体三角网无自交**）；未做规模/性能验收（16 柱 vs 真实 3000+ 柱 / 369 km²）；柱径 / 柱间距 / 节理间距 / 高宽比分布**仍全部是显式假设**（台账 §3 硬缺口）；未做 Minecraft 导出。

**2026-10-20 特殊地形 3D 审查工作区已交付（用户明确要求：用已有 `web-preview/` 前端以 3D 展示）。** 未新起前端工程、未改算法。新增 [`web-preview/special_surface.py`](web-preview/special_surface.py)（只读适配器：清单本身 SHA256 硬 pin `d1f12249…`，四个 bundle 再按 sha256+identity 双重校验，路径必须在工程根内；`catalog()` / `descriptor(kind)` / `binary(kind,name)`；**收敛声明由读取端复算**——用 `relaxation_maximum_excess_m <= relaxation_tolerance_m` 重新推导，与台账布尔不符即 raise，这就是 v2 验收器拦下的那类缺陷在读取侧的堵法）、[`web-preview/special-surface.js`](web-preview/special-surface.js)（Three.js 轨道相机 + 全分辨率保存地表 + 解析参考面线框 + 侵蚀变化顶点色发散色带 + 保护区点云 + 二维变化/高程图 + `Raycaster` 与反投影双路点选 + 审查导出；四个能力位硬编码 false）、[`tests/test_special_surface_preview.py`](tests/test_special_surface_preview.py)（**11/11 OK**）。后端 [`bridge.py`](web-preview/bridge.py) 加三条 GET：`/api/special/catalog`、`/api/special/frame/<kind>`、`/api/special/array/<kind>/<name>`（后者 `application/octet-stream`），三条均拒 query；`special-surface.js` 入静态白名单（不然 403）。前端 [`index.html`](web-preview/index.html)（面板 `#specialControls` + `script`）/ [`app.js`](web-preview/app.js)（`reviewCategories` 归入「地形输入」、「setWorkspace」分支、`reset`、`reviewRecord`、`getSelection` 五处）/ [`style.css`](web-preview/style.css)（`.special-canvas`）挂接。**二进制沿用 `saved_surface` 范式**：JSON descriptor 带 `arrays[name]={dtype,shape,bytes,url}`（顶点减 AABB 最小、`<f4`/`<u4`/`<u1`），数组另走 octet-stream；**拓扑复用不重建**（`surface_triangles` 即存储 `triangles`，`(2(r-1)(c-1),3)`）——既省一次三角化，也让「显示的是保存几何」在代码层成立。**实测**：catalog 4 forms/candidate；四 kind（inselberg 276×476@8 m、karst 491²@1 m、sandstone 321²@0.5 m、volcanic_plug 411²@1 m）的 `frame` + 20 个数组 URL 全 200 且长度与声明逐一相符；带 query frame → 400、未知 kind → 500、`/api/special/frame` 形状不匹配 → 404、`/special-surface-nope.js` → 403。**回归 40/40 OK**（underground/fault/river-results/l1-cave 四个桥接测试）；`py_compile`、两个 JS `node --check`、HTML id 无缺失无重复均通过。**真浏览器验收 14/14**：本机无 playwright，但 Edge headless 可用 → 新写自包含验收器 [`tools/verify_special_surface_browser.mjs`](tools/verify_special_surface_browser.mjs)（**CDP + node 内置 WebSocket，不依赖 playwright**；自起桥接与无头浏览器，从页面内 `readPixels` 数非空像素），报告 `.scratch/special-surface-browser-report.json`。**一个只有浏览器实测才能抓到的真缺陷（勿重犯）**：`view3d` 点击后 canvas 仍 `hidden`、非空像素 **0**——`saved-surface.js:157` 的共享控件自我订阅（`['view2d','view3d','verticalScale']`）**漏抄**，而 `app.js` 的 `renderWorkspace()` 只调 `surfaceRenderer.render()`、不驱动本模块，所以三维从未显示；补上后 `lit` 0 → **780416**。教训：照抄模板时「不显眼的那几行」往往就是接通的那一根线。**文档** [`docs/special-terrain-3d-preview-20261020.md`](docs/special-terrain-3d-preview-20261020.md) · [`web-preview/README.md`](web-preview/README.md) 已加节。入口 `http://127.0.0.1:8765/?workspace=special`。**未做**：工作区未登记进 `fixed_catalog()["workspaces"]`（展示登记，前端导航不读它）。

**2026-10-20 离线地形图渲染器已交付：遥感图 / 地形图两种版式（用户方向 A）。** 针对用户「预览要按照遥感图和地形图的格式来做」的明确要求（B 实时无限预览用户定为**可选开关、默认关**，C/D 本轮不做）。新增 [`terrain_pipeline/terrain_map_style.py`](terrain_pipeline/terrain_map_style.py)（**全仓唯一样式层**：六段 relief 色带此前有 3 份逐字副本、陆/海色带 9 份，故不再抄第 4 份）、[`tools/render_terrain_map.py`](tools/render_terrain_map.py)（`remote` 连续色带+物理 hillshade+常流实线/非常流虚线；`topo` 离散分级+每条带边等值线+公里网格+比例尺+指北针）、[`tests/test_terrain_map_style.py`](tests/test_terrain_map_style.py)（**25/25 OK**）。**三处此前真空白**：①分级等高色带全仓**不存在**（此前一律连续 `Normalize`）→ `banded_relief_rgb` + `validate_band_edges`（首边须=海平面、严格递增）+ 颜色数==边数-1；②经纬网全仓 **0 处** → **分两层**：默认米制坐标框，**可选**声明式经纬网（`--declare-metres-per-degree-east/north` + origin，缺一即拒、拒绝猜测换算，产物 stamp `declared_graticule_not_a_projection` 且标签标 `*`）——因为本工程地形在**无限瓦片像素坐标**上，`geography_v*.py` 的 `latitude = 22*np.sin(z/96)` **不是真实地理纬度**，直接照画就是伪造地理信息；③比例尺此前仅 1 个脚本有。**两处被自己实测拦下的真缺陷（勿重犯）**：①`colour_range_m` 把大 TD 的冻结区间 `(0.609,536.184)` 当**全局默认**，使 208 m 的喀斯特图被拉到 536 m 量程、色带被压成 2.6 倍宽，而报告并列 `plotted_max_m=208` 会让人以为色带是对的 → 改为**默认取该图幅自身范围**，只对 `DEFAULT_SOURCE` 保留冻结对以与既有 `verification/` 图并置；②默认 `graticule_step_km=10` 在 0.16 km 图上**零根线**，报告却写 `planar_kilometre_grid` → 改为按跨度推导 `nice_graticule_step_km`，且 `draw_metre_graticule` **返回实际画了几根线**，报告改写这个记录而非重复请求值。**实测**：五组场景（1280²@30 m=38.37 km 大 TD；四类特殊地形 0.16–3.80 km）+ 一个经纬网变体，全部 exit 0；各图色带保留自身范围（karst 0..208、sandstone 0..158、inselberg 0..369、volcanic_plug 0..285），网格按跨度（38 km 图 5 km/x8·y7，0.16 km 图 20 m/x9·y9）；**两条拒绝路径实测触发**（无溯源 bundle、篡改 sha256）；`guard_output` 拒绝写 `verification/`。**坑（已记）**：图幅 y 轴**倒置**（z 向南增大），家具必须用**有符号** y 跨度定位，故 `screen_frame` 返回 signed span；北箭头指向 z 减小方向；验箭头**不能**用 `FancyArrowPatch.get_path().vertices`（那是 patch 私有坐标系），要用 `Annotation.xy/get_position()`。**文档** [`docs/terrain-map-renderer-20261020.md`](docs/terrain-map-renderer-20261020.md) · 产物 `.scratch/terrain-map-preview-20261020/<场景>/{*-remote.png,*-topo.png,report.json}`。**未认证**：产物 `status=candidate`、四能力位全 False；被 pin 的 `metric_*`/`diffusion/*` **零改动**（`fixed_hillshade` 等旧副本**故意保留字节不变**，因其 PNG 在 `verification/` 作为证据）；色带断点/颜色/hillshade 权重**均属声明式风格（显式假设）**。**未做**：B 实时无限预览、群系图（需先给米制气候补纬度）、尺度提升到参考图的 ~500 km（差 ~13 倍，需多分辨率金字塔）、海深扩容到 −6000 m。

**2026-10-20 特殊地形表面 v2 已交付：加面粗糙度 + 水力侵蚀（复用仓内内核）。** 针对用户「形态太规整，为什么不用噪波」「再加水力侵蚀，多复用已有算法」两点。新模块 [`terrain_pipeline/metric_special_terrain_surface.py`](terrain_pipeline/metric_special_terrain_surface.py)（`metric-special-terrain-surface-v2` / `special-terrain-facet-noise-hydraulic-dissection-v2`，`SUPERSEDES_ALGORITHM=…-v1`）消费 L0 四类父 bundle：面粗糙度调 `diffusion/geographic_noise.field`，水力切割调 `route_diagnostic` + `accumulate_local_discharge` + `conservative_diffusion_step` + `relax_mobile_slopes` + `phase_record`（全部只 import，五个内核 sha256 写进 metadata `kernel_revisions`，既有 `metric_*` / `diffusion/*` 零改动）。**验收**：单测 11/11 OK；独立冷读验收器 [`tools/audit_special_terrain_surface.py`](tools/audit_special_terrain_surface.py) 不 import 生成器、自实现噪波内核与岩石下限、重放 target 足迹、从磁盘重算五内核哈希。**三条实测语义**（前两条是初稿判断被自己的探针推翻，第三条是验收器拦下的真缺陷，均勿重犯）：①「整面铺松散壳再松弛到休止角」会毁地形（搬 1.8e7 m³ vs 切 5.2e3 m³，塔损失 36.5 m，喀斯特反被抬高 104 m）→ 正确做法是仓内原生 `mobile_base` 语义（只在途柱、3.9e5 m³）；②切割必须由**声明的岩石下限**约束而非活动柱；③**`relaxation_converged` 曾被独立验收器当成必须为 True 的门槛**——但 `relax_mobile_slopes` 的契约本就允许返回「未收敛的有限停步态」，真问题在 `surface_preset` 里 `tolerance_m=1e-6 / max_sweeps=8` 这两个**从未实测过**的常量。改为：把判据的每个操作数记进台账、验收器**复算**该布尔而非相信它；预算按实测定值（`tolerance_m=1e-3`、`max_sweeps=512`）。实测 20000 扫下四类 12 步全收敛（最大 2031 扫），证明残差是预算问题而非结构性下限。**文档** [`docs/special-terrain-surface-20261020.md`](docs/special-terrain-surface-20261020.md) · 参数台账 [`.scratch/special-terrain/parameters-and-sources.md`](.scratch/special-terrain/parameters-and-sources.md) §5.1/§5.2 · 产物 `.scratch/special-terrain/surface-20261020/`（bundle + 独立审计）与 `surface-preview-20261020/`（三栏对照 + 剖面 + 侵蚀变化图）。**未认证**：四能力位全 False（`hydraulic_ready` 仍 False——本轮切割是**声明式**水流功率项，不是水文合法性证明）；`simulate_fluvial_morphodynamics` 需 pyDeltaRCM 未装故未用；TD 真实 1 m 床上的 v2 端到端、Java 接入、`TGMCMT01` 新版本均未做。参数除「继承父模块 / 原生语义 / 内核对内惯例」外**全为显式假设**（无公开资料给出这四类地形的表面微起伏量级）。

**2026-10-19 特殊地形离线几何与预览已交付（独立于三角洲主线）。** 六类特殊地形分两路实现：L0 四类（魔鬼塔/乌鲁鲁主体/张家界石柱群/喀斯特峰林）走新模块 `terrain_pipeline/metric_special_terrain_forms.py`（`metric-special-terrain-v1` 场式位移）并在真实 TD 1 m 床上薄适配；L1 四项（天坑竖井+坑底暗河+天窗、溶洞—天窗—天生桥、魔鬼岩石蛋堆、Uluru flared slope）走 `hybrid_rock_boolean` 体积路线，四个新模块 `terrain_pipeline/special_terrain_l1_*.py`。[交付文档](docs/special-terrain-offline-20261019.md) · [盘点](docs/special-terrain-recon-20261019.md) · [规格](.scratch/special-terrain/spec.md)。**验收**：L0 独立冷读 4/4 pass（`max_replay_difference_m=0.0`、perimeter 四边 0）、L1 主代理侧独立冷读 54 条探针 + 29 条 record + 全部布尔见证通过、产物 figures sha256 与紧凑性校验通过；合计 86 用例 OK（L0/适配 32 + L1 54）。**未认证**：Java 9 步接入、`TGMCMT01` 新版本、天坑水文三项前置本轮均未做；所有产物 `status=candidate`、能力位全 False；形态参数多数无来源（显式假设，非实测）。冻结基线 `hybrid_cave_geometry.py`/`hybrid_rock_boolean.py` 哈希未变，既有 `metric_*` 身份常量零改动。

**2026-10-19 最新实现：床沙再悬浮、剪切相关沉降、湿岸侧移与薄水床载修复已完成。** v3同父96秒严格匹配对照通过；v4修复微米过岸水层触发的超量床载，31项测试及连续1200秒压缩潮位周期独立水沙/载流检查通过，有限新供沙已耗尽并自动转清水。全部保存状态新增干露仍0、未形成持续分汊，陆侧平原和完整自然形态尚未通过。全部计算结束。[实现、结果与末检查点](docs/delta-finite-exchange-v3-20261019.md)。下方为历史记录。

**2026-10-19 下一阶段更新：** 扩大域独立来河初态与8步沉积短验已完成，7项测试通过；定位了原生水面与流速截顶不一致，暂不进行长程生长。600秒同床FV及20区间水/动量独立核对通过，下一步接入有限供沙沉积的水流输入。实际新陆干露仍0，完整三角洲未完成。[结果与下一步](docs/delta-natural-deposition-progress-20261018.md)。

# 工程 TODO

**2026-10-30 宏观基底→TD合成→盆地汇流→河湖链路完成有限页验收。** [任务05](.scratch/large-world-first-pass/issues/05-base-td-water-chain.md) · [实测与使用](.scratch/large-world-first-pass/terrain-water-chain-validation.md)。千岛及大陆共用全域海洋规划，千湖先陆地再按来水形成湖泊；14项新增测试通过，真实TD源三种局部路径跑通。千湖形成356.69 m有限小积水面，海岸2096河道格；实际切深保持海陆约束。Terra实现、主端审查；本轮未运行GPU。跨页完整流域、溢流湖链与全幅30 m仍未完成，海岸运行峰值RSS749.66 MiB超出512 MiB软观测目标。

**2026-10-29 新布局单页TD实跑已完成，湖岸目标未通过。** 用户批准兼容监测后仅运行一次：RTX2080s、54.08s、生成器显存3.06GiB、RSS2.95GiB。真实页已保存，但8278个设计湖格全部高于0m水位，不能按设计掩膜冒真实湖运行河槽。[高程对照与完整结果](.scratch/large-world-first-pass/natural-layout-validation.md)。未换页、未改水位、未再次GPU推理；下一项为条件控制与实际水体识别一致性。

**2026-10-29 可控大世界自然布局修正已通过CPU验收，实际TD待运行。** 规则格子改为具有疏密和大小差异的连续场，补连续湖盆与岸坡条件，57项本轮测试通过。独立16km采样得1120湖类分量、983陆岛分量，水比误差<0.015个百分点。[新版图、实测与固定页](.scratch/large-world-first-pass/natural-layout-validation.md)。Terra实现、主端审查；这仍是布局/条件图，待确认allocator监测范围后单次实际TD验证。

**2026-10-29 大世界首轮部分交付，GPU实跑受阻。** [使用说明](.scratch/large-world-first-pass/README.md) · [实测](.scratch/large-world-first-pass/validation.md)。12,288km三模式布局概览、岩性＋代表Q→河槽宽深与冷读已实现；60项针对性测试通过，旧真实TD样本3665河道格、重叠8986共同complete格Q/硬度/宽深差0。新布局单页GPU尝试因WDDM无法测PID显存停止，未生成新页、不自动重试；未宣大世界端到端或无限河网完成。

**2026-10-29 用户恢复可控大世界首轮实现。** [当前规格与任务](.scratch/large-world-first-pass/spec.md)：超过10,000 km×10,000 km有限世界，千湖/千岛/大陆布局，内部按需30 m地形/河网，复用岩性＋代表流量→河槽宽深；动态侵蚀单列验证。GPT-6.1 Terra编码，主端发布任务、审查验收。下面18:23暂停为历史记录，本次只恢复上述范围，不自动重开其他工作。

**2026-10-29 18:23 用户要求暂时停止工程，当前已暂停。** [暂停交接与恢复入口](.scratch/stage2-g1-g9/HANDOFF-PAUSED-20261029.md)。本轮计划13/20任务完成（非算法完成率）；所有在途代理已结束/中断，本会话后台命令0，未运行新GPU源页。河线正式lossless模式尚未主跑，G1布局/条件适配仍有失败与中断半成品；旧成果和失败现场均保留。等待用户明确恢复后才继续测试、实现、推理与catalog更新。下方2026-10-28「尚未编码或验收」为当时记录，当前进度以本交接和acceptance.md为准。

**2026-10-28 最新批准：五代理并发河网预计算与G1–G9**：[共享规格与首卡入口](.scratch/stage2-g1-g9/spec.md)。按依赖多波完成G1地形、G2物性、G3温度、G4风雨影、G5水分、G6土壤覆盖、G7雪冰融水、G8海洋海岸、G9风化成土；河流生产prepare/query及保真可先交。当前五线核复用/白名单，尚未编码或验收，不宣九项完成。G10–G20、Java及冻结源修改不因本批准自动放行。下列旧顺序/执行树编号为历史，现以本入口和当前计划树为准。

**2026-10-28 二阶段已启动（用户指令）**：[协调入口](.scratch/stage2-coordination-20261028.md)。按四阶段路线进入Python地理环境/气候/材料/生态首批同坐标环境链；VMH DeepSeek实现、主端审查报告。并行保留有限水系扩域实算，及“主干/重要支流预计算—走廊依赖索引—小支流按需细算”的复用与最小原型准备；不是宣称无限河网或G1–G20候选全量完成/全量开工。

**2026-10-28 有限样本已交付（M1–M4通过）**：[使用说明](artifacts/finite-river-sample-v1-README.md) · [正式包](artifacts/finite-river-sample-v1-delivery.zip) · [M4主端验收](.scratch/finite-river-sample/m4-default-v1/DELIVERY-M4.md)。3951格真实完整汇水/89格河道、有限事件接收湖、降雨soil真实供水、2/4块与新进程恢复、现Python默认query均已验。仅所交6h安全库存范围内有限产品完成，不宣全无限世界/瞬变水动力/Java。旧失败与后续R/S路线保留，不阻塞本次交付。

**2026-10-28 当前交付目标（用户最新决定）**：[有限闭合河网样本](.scratch/finite-river-sample/spec.md)。阶段一按M1静态河网与合法终点、M2真实产流供水、M3实际跨块与冷恢复、M4 Python默认消费分里程碑交付；每项通过单独承认，M4通过即交付本次有限产品，不等待R1–R9/S1–S6全部通过。旧W1失败与世界目录扩展保留，25tile不再是主线前锁；全量认证仍是长期范围，不冒已完成。唯一当前执行树p10。

**2026-10-27 最新批准全量收官**：[无限世界河网收官](.scratch/infinite-river-completion/plan.md)与[G01–G24缺口矩阵](.scratch/infinite-river-completion/acceptance.md)。包含高地源区、稳定区域主河、合法终点、降雨冰雪/湖动态、回水洪泛、水沙床变反馈、依赖加载/恢复及R1–R9/S1–S6认证；通过后精简。当前接续源区安全准备与D/H验收，55项P0及重封攻击过不等整体完成。下方旧路线保留历史。

**2026-10-26 最新批准路线**：[固定高地源区与区域主河](.scratch/highland-mainstem-world/plan.md)。先冻结高地源区和区域主河，再按相交走廊与依赖加载/显示；低地降雨沿地形补给，计算范围按预算选择，不固定50km。当前阶段A核来源一致性与规格，尚未实现新源区链。下列旧整合计划保留历史成果，不结转未通过门。

**2026-10-26 已批准续作（历史顺序，已由上方路线替代）**：[河湖与无限世界整合](.scratch/river-lake-world-integration/plan.md)。先整合当前成果并完成河湖/跨块联合验收，后精简代码；当前规格已审，下一项为结构域候选及主干实现。M1余项并入整合验收，不视为已完成；冻结源码修改仍须专项批准。

**2026-10-26 阶段一现行入口（本表只留总览，细节看新文件）**：一阶段的「已实现有界能力 / 未闭合主要问题 / M1 工程收口 / 待讨论建议」集中在 [阶段一当前状态与问题导航](.scratch/river-stage1-completion/current-status.md)。它只是**导航与核对快照**，不覆盖契约与原始证据，也不改旧报告。
下方总览表保留作总览；本文件**按日期保留历史**（六门读数来自不同日期、不同基底，**不得全表定性为 10 km，也不得把 30 m 局部 pass 外推**），现行判定须与 [30 m 重判](.scratch/fine-terrain-40km/acceptance-matrix-30m.md)、[continuation 矩阵](.scratch/river-stage1-completion/continuation-matrix.md) 与 [final gate](.scratch/river-stage1-completion/final-stage1-gate-20261025-v1.md) 联读。阶段一仍**未完成**，单测数与局部 pass 不相加成完成度。

**2026-10-24 河流算法增量**：已实现有限联合receiver图诊断汇流和未知上游传播（不是继续调制图）。13项新单测+33项跨页回归通过；4049²真实TD联合图16,297,369格完整处理，水量相对残差6.22e-17；旧分块保留区29个差异格经独立上游子树核算验证。未认证无限世界、动态水力/Qs/床变和默认消费接线。见[实现与验收记录](.scratch/river-network-accumulation/report.md)。DeepSeek本次调用401无产出，由主端完成实现与验算。


**2026-10-21 四阶段详细规划表确认**：用户确认 [.scratch/terrain-four-stage-review-20261021/algorithm-components-review.md](.scratch/terrain-four-stage-review-20261021/algorithm-components-review.md) 是四阶段详细组成依据（R1–R9/G1–G20/V1–V8，审阅稿，非全量实施批准）；详细边界见 [四阶段路线](docs/terrain-diffusion-four-stage-roadmap.md)。旧阶段 0–5 总规划已弃用并归档于 [deprecated-plans/](deprecated-plans/README.md)。

**四阶段任务总览**：权威路线与详细证据分别见 [四阶段路线](docs/terrain-diffusion-four-stage-roadmap.md)、[算法组成审阅稿](.scratch/terrain-four-stage-review-20261021/algorithm-components-review.md)（R/G/V 组成分类是审阅参考，不是全量实现授权）。本表只记录当前阶段和主要节点状态；旧专题编号不换算为四阶段完成率。

| 阶段 | 当前状态 | 主要节点与进度 | 当前待办 / 边界 |
|---|---|---|---|
| **1. 无限世界河网（Python）** | **进行中，端到端未完成** | **2026-10-23 基底已改为 TD 直接生成的 30 m 原生网格**（用户拍板，旧 10 km 插值面不再作开发/验收基准）。40 km @30 m 三项验收：**选区已完成**（43.4124 km² 闭合盆地、盆底 50.4492 m、鞍口 120.7850 m、窗口原点米 [1265190, 1286220]、覆盖 40.08 km、29 tests OK）；**湖盆已完成**（9.5571 km²、盆底 982.4127 m、鞍口 1268.5966 m、A(h)/V(h) 与独立复算差 0、35 tests OK）；**跨区域已完成**（重叠 1024×2049 差异 2042 格 0.097% 全在最外一列，距边≥6 格的 206 万格逐位相同、33 tests OK）。**河段已完成**（汇水 10.3797 km²/4515.3 m，43 结点 Manning 断面中位 0.104 m，三本账全闭：水 2.5e-16/固 4.8e-15/Exner 1.23e-10；限制：均匀 Q、stride=3、床变量级未验）；**微洼地溢流门已定稿**（61 tests OK；门后 131、截断另计 208、改判 12409；**单格 6392 → 0**；恒等式两条都闭）；**跨区流路/出口/累积量已完成**（D8 301476 格零分歧、2000 条流路真实分歧 0、累积计数干净格 100% 相同）。R1–R4：基础地形、海陆、域归属和有界拓扑已有实现；几何/归属/出口接缝有局部证据。R5：水量、泥沙与耦合账本已有；水量相关风化源可选、默认关闭且未标定。R6：有限域河道几何适配层已实现，尚未认证或由R7消费。R7：原床运动波候选适配 v2 已交付，18 项定向测试通过；固定顺序累计已修复跨 NumPy 版本的覆盖摘要差异，旧失败产品保留；动态回水与守恒洪泛仍缺。R8：均摊增床反馈已进入候选包；侵蚀写入、沿程分布和水力重验仍缺。R9：`publish_domain_bundle.py` 已由用户指定并登记为**未验证的默认消费者入口**（仅显式调用，不自动调度/无限生成）；有限tile（core+margin）闭合门在写入前验证点选域；未选域按C方案保留为未验证附带数据，索引明确数量与whole_tile_certified=false，79项回归通过。所有产品 `hydraulic_ready/natural_outlet_verified/publishable` 仍为false，role不代表产品认证。 | 待完成：**① Q/Qs 的物理量跨瓦片一致（本轮只比了格计数）；② 30 m 目标尺度拒绝率普查；③ 30 m 产物接入默认消费链；④ 河段：R5/R6 物理/几何独立验收、动态回水、床变量级标定；⑤ R7 回水/洪泛/床变重算**。旧六门矩阵（2026-10-22，基于 10 km 基底）见 [阶段一验收矩阵](.scratch/river-stage1-acceptance-20261022/acceptance-matrix.md)：条件1–5 partial、第6项 blocked；该矩阵**需在 30 m 面上重判**，新判定见 [30 m 六门重判](.scratch/fine-terrain-40km/acceptance-matrix-30m.md)（条件1/2 基本成立、条件3 partial、条件4/5/6 partial）。详见 [河网计划与契约](.scratch/river-infinite-world/plan.md)、[40 km 验收规格](.scratch/river-infinite-world/fine-terrain-40km-spec.md)、[R5 水沙耦合契约](.scratch/river-infinite-world/domain-coupled-spec.md)。 |

| **2. 地理环境与地表表现（Python）** | **局部原型存在；统一环境链未完成** | G1：合成地形/海陆背景有局部实现；G2：合成材料场有，完整岩性/层序未完成；G3–G5：合成气候、风、地形增雨/雨影及局部水文模块有；G6：土壤代理与温雨—地貌分类规则有；G7：冻结高程诊断有；G8：有限海岸原型有。G9–G20：候选审阅项。 | 先按 [地理依赖矩阵](docs/terrain-geography-dependency-matrix.md) 逐项确认范围和接线；尚未形成同坐标环境—生态完整链。G9–G20、板块、洋流、冰川、地下水等不因列入审阅稿而自动开工。 |
| **3. 非高度场三维地貌（Python）** | **离线原型存在；无限世界集成未完成** | V1–V7：洞穴、天坑、天然桥、石柱、悬挑等局部几何/预览原型；部分有局部体积或见证点记录。V8：统一交付和消费者接线尚未完成。 | 按 [非高度场地貌目录](docs/terrain-non-heightfield-landforms-inventory.md) 建立统一 TD 拼接、跨瓦片、拓扑、水路和消费者契约；离线原型不能作为无限世界联合结果。 |
| **4. Java / Minecraft Mod** | **按计划尚未启动** | 等阶段 1–3 的算法、产物身份、跨窗口行为和目标表现成熟后启动。 | Java 只负责转换 Python 产物、资源映射和游戏交付；当前未接线不是算法缺陷。 |

**总览口径**：生产默认入口 role=`production_default_consumer_unvalidated` 只表示用户指定入口；只在显式提供坐标和输出目录时运行，不能自动生成无限世界。所有认证claims保持false。R5/R6初次交付未运行测试；本轮R7–R9证据限定见 [候选接线记录](.scratch/river-infinite-world/r7-r9-candidate-integration.md)；阶段一仍未完成。

**2026-10-19 本轮验收已收口：完整自然三角洲未通过。** [验收结论与证据](docs/delta-natural-acceptance-20261019.md)。有限供沙、状态继承及已运行的水床反馈检查通过；实际露陆、未截断扇缘、陆侧平原和最终新床潮浪联合形态未通过或未验证。任务13仍实施中，扩大域仅为几何准备。

**2026-10-19 续算验收更新：** [任务13](.scratch/delta-completion/issues/13-natural-deposition-delta.md)仍未完成。新增有限27.11万m³固体的341包续生长已结束；海平面以上床面9,675m²、几何连陆5,275m²，但新床1,500秒平均海位FV检查实际干露仍0。左边界已截断沉积叶瓣，需扩大计算范围并处理新旧床接缝。旧床完整44,714秒潮期及300秒波开/关反馈对照已完成独立核对；波浪造成最大床差2.5mm，不能称成熟岸线塑形。正式预览和逐格证据见[当前记录](docs/delta-natural-deposition-progress-20261018.md)。

**2026-10-19 当前三角洲主任务：自然沉积与涌现分汊，实施中。** 用户指出构造平原、长直河槽和预设分汊不接近现实，已转回[任务13](.scratch/delta-completion/issues/13-natural-deposition-delta.md)，[输入、规模与实施记录](docs/delta-natural-deposition-progress-20261018.md)。TD原近岸完整自然沉积与同源零供沙对照已完成，出现水下脊槽但原生水场实际干露仍0；真实有限体积潮汐、波动员与双向床变正在独立计算和审查。单次声明追加9m有限上游岩层的来源账已核对，原生检查点续生长已启动，不重复年度沙或重置基底库存。原年度有限供沙31,101.986m³固体最多约47,849m³含孔隙沉积，不能冒充可在一年生成广阔平原。下方任务12完成只指构造地形上的顺序耦合实验，不能作为自然沉积三角洲完成证据。唯一GPT-6.1 Sol编码，主协调审查运行，原始资料与旧正式失败链保留。

**2026-10-18 A-P0 已完成：中心线搜索取消「以参考路径为上限」的自指接受规则，身份 v6→v7。** [决策记录](docs/adr/0002-centerline-entry-independent-turn-ceiling.md) · [实施状态与证据](docs/river-algorithm-improvement-list-20261018.md) · [v6 证书作废声明](verification/td-terrain-generated-rivers/CENTERLINE-V6-SUPERSEDED.md)。旧接受判据是「候选的 ordinary/junction 的 max 与 p95 四个转角数不得超过参考路径自身对应值」，而参考路径就是搜索起点：上限自指、入口决定结果（实测同算法同参数仅改传不传 `reference_points`，转角能量差 27 倍）、且四数全局互斥。现改为**入口无关的三层上限**：声明式解析上限 `ANALYTIC_TURN_BOUND_DEGREES = 90°/90°` 只做严格程度封顶；有效上限 `turn_ceiling(baseline) = max(声明上限, 基线 movable 转角最大值)`（不看参考路径，又给脏基线留下降余量——一次性硬墙实测会把搜索堵死、接受 0 步）；只约束**可移动节点**，锚点宽转角转记 `anchor_turn_exemption` 诊断字段。起点归一：`reference_points` 不再充当搜索起点，只做验收对齐诊断。三处副本同源化；6 个新 policy 诊断字段。**验收**：三入口（传原始台阶参考/不传参考/传扰动参考）最终路径逐节点完全相同（偏移 0）。**回归**：24 个受影响模块 22 OK；`test_metric_td_generated_rivers`/`test_audit_td_generated_rivers` 各 3 error 与改动前基线逐条一致（既有 HiGHS 技术债，非本次引入）。**未做**：A-P1 静默拒绝补账、A-P3 走廊三分类、A-P2 依赖与台账比对修复；v7 生产尺寸证据尚未重新生成（既有 v6 证据不得继续引用为其接受依据）。

**2026-10-18 三角洲最新交付：16km TD派生分汊—潮汐—波浪集成实验已验收。** [结果与限制](docs/delta-integrated-td-coastal-20261018.md) · [任务12](.scratch/delta-completion/issues/12-integrated-td-coastal-delta.md)。最终`verification/fluvial-delta/td-coastal-delta-20261018-02/`保留五终端/真实二级分支，实际有限潮浪输运、三潮位水面和四组对照；低潮无开挖表面排水至首个连通海水，修复正来水河口算干。52项测试、123条独立数组检查、198数组精确冷重放通过。潮间淹没范围差9.4964km²，净床变−0.230008至+0.611497m，源到海固体账残差5.44e−10m³。构造土方、有限既有地质活动层和30961.761041m³年度终端供沙分别记账，不称自然一年长成；海岸与河流顺序耦合、规定流量准稳态水面，尚非完整双向二维水动力。旧[任务11报告](docs/delta-terrain-diffusion-tide-wave-20261018.md)已撤销不一致TD海陆掩膜和静态条纹的集成证据。原始TD、scene15、年度基准、默认世界与游戏保持不变。

**2026-10-17 已完成本轮修正：支汊首次入海终止与岸陆变化。** [验收与结果](docs/delta-coast-bounded-acceptance-20261017.md) · [任务09](.scratch/delta-completion/issues/09-coast-bounded-distributaries.md)。新版独立scene02展宽主干/三支至200/170/145/120m，增加连续低脊、浅湾与不均匀岸缘；三支在首次入海处停止，旧跨海岛槽1428格全部恢复。34项独立测试、实际图审、5倍来水一年、故意失效默认场景的精确冷重放和主协调数组检查通过。海域零河槽切方、年度零储沙/床变；年供沙31101.986m³、留存8509.043m³、外排22592.943m³，无实际新增干地。施工地形独立记账，海侧羽流未建模；下方旧scene09及03/增流量结果保留为历史，未通过本轮首次入海约束。Terrain Diffusion地形演算仍为后续阶段。

**2026-10-17 已完成：增流量三角洲对照。** 原情景2/5/10倍来水已分别重算有限上游侵蚀供沙与三角洲反馈；[报告](docs/delta-discharge-scenarios-20261017.md) · [任务08](.scratch/delta-completion/issues/08-discharge-scenarios.md)。25项聚焦测试、三档精确冷重放和独立数组检查通过，原始输入及03基准保持。年供沙受同一份耗尽库存限制，均约31102m³固体；5倍档陆侧至少1mm淤积面积从0.0376增至0.2204km²，但增流量档陆侧均未达到1cm沉积，无实际新增干地。更大流量增加外排，10倍档约92.9%泥沙入海。算法成熟后，再基于Terrain Diffusion生成地形的河网、坡度、汇水与材料输入进行演算；该阶段尚未实施。

**2026-10-17 当前完成：16km风格化三角洲统一算法。** [完成与验收报告](docs/delta-integrated-completion-20261017.md) · [任务07](.scratch/delta-completion/issues/07-integrated-16km.md)。已将有限上游供沙、实际床变、动态水位/分流和陆侧沉积接入同一800×800场景，最终结果为`verification/fluvial-delta/integrated-16km-20261017-03/`。101项测试、11个子测试通过，冷重放与来源保持通过。实际年供沙31101.986m³、净留存27598.190m³；三支接海，清水不改床。采用准稳态河道树近似，构造土方独立记账，未接入游戏。以下v10及局部模型分开、三角洲未完成等描述为历史检查点；本条为当前状态。

**2026-10-17 最新完成：风格化陆侧三角洲v10已集成主工程。** [结果与验收报告](docs/delta-landward-v10-20261017.md) · [已完成任务](.scratch/delta-completion/issues/02-complete-stylized-landward-delta.md)。16km场景09已生成，原陆地旧槽带外改造5.0076km²，三支陆侧分汊连海；主工程6项测试、37份来源hash和精确重放通过。有限供沙反馈02继续有效；大场景挖填独立记账，静态设计水位，尚非供沙自然长成的完整水动力三角洲，未发布默认世界。下方停止、v7失败和待实施描述为历史记录，以本条和报告为准。

**2026-10-17 最新动态供沙验收：** [修复与同源空间反馈报告](docs/delta-dynamic-outlet-acceptance-20261017.md)完成。DeepSeek编码、主协调审查集成；修正沉积/外排颠倒及零水外排，移除分支编号偏置，空间对照复用已有有限水沙内核。80项测试与11个子测试通过；2.88km同源全年供沙重放精确一致，单个海侧出口分配变化最高5.91个百分点，清水对照不变；原陆地沉积4500m²，原海洋内新增出露0。四份输入hash及v10三个实现文件/场景09存档保持一致；实际图审与逐数组独立冷读通过。16km构造场景与局部供沙模型尚未统一，不标完整水动力三角洲完成。

旧[非空间对照](docs/delta-river-dominant-comparison-20261017.md)与[空间对照](docs/delta-spatial-river-dominant-20261017.md)的2项/16项测试记录属于修复前历史，未覆盖后来发现的问题，不能作为物理正确性的证据；以本次验收为准。

**2026-10-17 恢复实施前验收历史：三角洲仍未完成，现保存进度。** 详见[验收与接续记录](docs/delta-acceptance-handoff-20261017.md)。Claude 工作树中的06场景已生成，v6保存结果自身检查有效但形态未通过；当时v7代码聚焦测试3通过、2失败，存在未定义变量和上游不连海，无法重放06。当时未合并或发布。本条覆盖下方“06尚未生成”的历史状态。

**2026-10-16 最新交接：用户要求停止，由 Claude 接续。** 见[Claude 三角洲接续文档](docs/claude-delta-handoff-20261016.md)。上游供沙与逐日反馈有限案例已验收；16km场景05形态仍被用户要求修正，06代码修改未验证、尚未生成。编程子智能体已中断，相关计算进程已结束；保留全部代码和归档，不再自动继续。

研究工具接入：[SRHarness/MDB 本地验证](research/srharness-mdbench-local-integration-20261016.md)与[任务12](.scratch/deepseek-harness/issues/12-srharness-mdbench-bridge.md)。已跑通 DeepSeek 三轮公式搜索→冻结候选→MDB 独立评分；合成沉降速度与净受力探针在训练/ID/OOD均通过数值及符号等价。三角洲供沙与陆侧平原仍按下述任务推进，工具接通不算地形验收完成。

当前状态与接续入口：[河口三角洲最新进度（2026-10-16）](docs/delta-progress-handoff-20261016.md)。已验收有限同源供沙与逐日床变/正常流反馈：84节点、365日，实际交付67932.416m³固体，原陆地净沉积146.054m³/4500m²；59项测试和14个子测试通过。此例只延入陆侧约99m，大范围陆侧设计平原任务10仍在实施，不能凭小范围沉积标完成。唯一GPT-6.1-Sol编程、主协调审查；不再使用DeepSeek。结果、准稳态限制与原档入口见进度文档，原16km场景和旧演化结果保留。

湖泊可作为入湖河段终点及出湖河段起点，简化河→湖→河已支持；鄱阳湖式完整干流侧接、顶托倒灌与湖内泥沙尚未接通。入湖口、汇流、冲积扇、宽谷、沙洲等复用评估见[河湖与泥沙评估](docs/lake-sediment-reuse-and-topology-review-20261016.md)。下列旧三角洲运行段落保留历史记录，以最新进度为准。

工程地图：[交互总览](docs/river-engineering-map.html) · [可编辑源文档](docs/river-engineering-map.md)。Markmap 已安装为工程本地工具，修改源文档后按[使用说明](tools/markmap/README.md)重新生成。

当前对话移交：[成果与设计方向可视化记录（2026-10-15）](docs/river-visual-overview-handoff-20261015.md)。包含现有成果入口、二维/三维顺序及 Markmap 安装接续说明。

当前验收：v6水路由修复已通过连续4步/2+2恢复证明，并从冻结v5/4096正式续至4224后正常退出。材料/原床通过；本批lost约3.22e−6m³，但几何连陆750m²、岸进25m、持续双支false，实际连续干露连陆0，整体三角洲尚未完成。本128步全海域净增31121m³，同时固定参考近海平面带净冲刷6454m³，需据实际区域变化与原始论文决定下一对照，不自动延长运行或更改门槛。证据见[任务17](.scratch/hydrological-planning-domain/issues/17-water-routing-continuous-evolution.md)。

DeepSeek已完成[4步扩散消融](.scratch/deepseek-harness/issues/04-delta-diffusion-ablation.md)及[128步独立对照](.scratch/deepseek-harness/issues/05-delta-diffusion-128-step.md)。同4224父点至4352，开启/关闭扩散的固定近SL区域净变化分别为−6514.86/−3156.83m³，几何连陆775/750m²，实际连续干露连陆均0、持续分汊均false。材料检查通过，但关闭扩散未解决形态。所有诊断另存且不可恢复，正式链保持4224；[已有实体河床采样](.scratch/deepseek-harness/issues/06-saved-bed-grid.md)29项检查通过，[真实接海定位](.scratch/deepseek-harness/issues/07-saved-bed-mouth.md)已读出14.14km中心线，14153点无未知：实际床约8.242km过零，约8.323km进入父30m海洋标签。同plan单河来水提取结果如下。只保留一名子智能体负责DeepSeek派发、机械集成和运行，主协调审查。

[同源单河来水提取](.scratch/deepseek-harness/issues/08-saved-river-seasonal-supply.md)已实现并验收，9项检查通过。8470上游25格/2500km²，365天Q范围31.06至109.90m³/s、均值62.54m³/s；该河段占8600海口全年水量35.22%，其余支流独立记账。七口逐日核账最大差2.24e−8m³，月界土壤差0，源文件未变。数据在`.scratch/hydrological-planning-domain/saved-river-seasonal-supply-20261016-01/`。下一步核对实际8m断面与近岸水位，接入保留河床的初始化，并补同源输沙；尚未完成水沙耦合或16km连续三角洲。

用户最新允许夸张三角洲/湿地，[风格化连续河口湿地](.scratch/deepseek-harness/issues/09-stylized-river-mouth-wetland.md)已完成首版并通过主协调实际图审：16km×16km、20m、800×800，真实河口/保存河床纵剖/同源季节Q为基础，主河展宽并构造三支水道、不规则浅湾和岛洲。最终成果在`.scratch/hydrological-planning-domain/stylized-mouth-16km-20261016-02/`，含实际床面、水面、水深、总图、细节及前后对照。3项聚焦测试通过，上游接海及三支内部D4连通通过，36条源hash未变。平台内核92.03%为连通水，识别出5个独立干岛，属于浅水岛湾风格；挖填独立记账，不称为旧自然演化验收通过。DeepSeek编写，唯一子智能体集成运行，主协调审查并查看三张实际图。

用户进一步指出三角洲应包含原河口陆地；[陆侧三角洲平原任务10](.scratch/deepseek-harness/issues/10-landward-delta-plain.md)已完成只读库存、尚未实现。口前2km旧床171.94m而场景base26.16m，需先协调高程、保留上游参考并明确过渡段，再将分汊和低平原延入陆地。此前海侧01/02保留，无scene03。DeepSeek编写，唯一子智能体集成运行，主协调审查。

[统一上游供沙任务11](.scratch/deepseek-harness/issues/11-upstream-sediment-supply.md)已登记、尚未实现：硬度/可蚀材料和水流共同确定侵蚀与输沙，沿程沉积滞留单独记账，河口仅消费实际出口交付。优先库存同源材料、水力及现有输沙模块的接口，避免把Q或河槽挖方直接当作河口泥沙；低供沙可无明显三角洲。湖口、汇流和内陆复用以及未来袭夺的拓扑/域边界更新已写入进度快照，尚未派发这些扩展。

2026-10-16用户要求实施[三角洲完成路线](docs/delta-completion-plan-20261016.md)：先完成[水路由修复与连续演化（任务17）](.scratch/hydrological-planning-domain/issues/17-water-routing-continuous-evolution.md)，再解决连陆生长、稳定分汊并建设连续16km河口场景。此前16km范围示意图不满足用户请求，不算三角洲交付。

- [x] 完成[河流主导三角洲有限机制首版](.scratch/hydrological-planning-domain/issues/13-fluvial-delta.md)：TD海口32阶段水沙与床面反馈通过；真实TD仍为水下沉积，合成浅水例验证出露。尚非成熟细河槽三角洲，见[结果与预览](docs/td-fluvial-delta-20261015.md)。
- [x] 实现[局部细化与覆盖层再侵蚀](docs/td-fluvial-remobilization-20261015.md)：TD 海口 5 m 栅格、16 阶段水沙与库存冷读通过，累计再侵蚀735.637 m³，清水最大净降床0.8 m；合成淤堵失败保留。
- [x] 完成[实际连续分汊床与有界近岸衔接](.scratch/hydrological-planning-domain/issues/15-fluvial-distributary-bed.md)有限验收：合成/TD各96阶段，TD主槽30m、两支670/700m，连续3阶段真实床面与材料冷读通过；33项关键回归全过。[报告与图集](docs/td-fluvial-distributary-20261015.md)。近岸供材单独计账，旧覆盖层gate仍false。
- [ ] 实施[河流主导二维水沙演化与连片沉积体](.scratch/hydrological-planning-domain/issues/16-fluvial-delta-morphodynamics.md)：v3已修新增陡崖，v5已修实际交换舍入并跑完4096；几何连陆1100m²、岸进40m、持续双支仍未过，现定位末期路由预算耗尽与水场异常。旧失败保留。[报告与图集](docs/td-fluvial-morphodynamics-20261015.md)。用户要求继续完成三角洲、不限时间。
- [ ] 三角洲潮汐下一版：河流主导版验收后先与用户讨论，再实施潮汐及其水沙交换。
- [ ] 三角洲波浪作用：后续加入波浪搬运、沿岸输沙及岸线重塑；当前河流主导版不实施。
- [ ] 接入 DeepSeek 任务派发：已通过用户配置的阿里云 deepseek-v4.1-flash 真实派发并集成[首个三角洲代码任务](.scratch/deepseek-harness/issues/02-delta-inlet-weights.md)，相关12项测试通过；[任务、回复、返工与验收记录](.scratch/deepseek-harness/tasks/delta-inlet-weights-20261016-01/conversation.md)已落盘。已有[本地配置窗口](.scratch/deepseek-harness/README.md#本地配置窗口)。MCP 注册、统一历史界面与自主代码执行尚未完成；现由协调方审查、落盘和测试。

- [x] 实现[汇流流量、岩性与河槽宽深](.scratch/hydrological-planning-domain/issues/12-discharge-rock-channel-geometry.md)：同源38.4km产物13项检查通过，209处汇流增流、204处展宽、207处加深；[断面、粗栅格限制及三角洲讨论起点](docs/td-discharge-rock-channel-geometry-20261015.md)。

- [x] 完成[季节背景与短时强降雨联动](.scratch/hydrological-planning-domain/issues/11-seasonal-storm-response.md)：同源38.4km TD地形72小时强雨情景及22项产物检查通过，季节河道虚线展示；[结果与剩余问题](docs/td-lowland-runoff-20261014.md)。

- [x] 实现[低地径流承接与可见河道分离](.scratch/hydrological-planning-domain/issues/10-lowland-runoff-receivers.md)：同一38.4km TD大图低地河道密度含季节性下降43.30%，保留完整产流水量和主干连续性，非河道承接对象同等沿地形接纳；11项关键测试及31项冷读检查通过。[本轮报告](docs/td-lowland-runoff-20261014.md)保留未校准、未达周期稳定和未解终点限制。

- [x] 修复[38.4km大图粗标签矩形截河](.scratch/hydrological-planning-domain/issues/09-remove-coarse-label-walls.md)：原生TD汇水重规划移除64个内部人工端口，64/64个问题位置均有300m内继续下游路径；汇流400、最长连续路径66.142km。产物与图审见[原生重规划报告](docs/td-large-map-native-replan-20261014.md)。仍保留窗口外未知和5个深洼，不代表完整水文域、自然河床或无限地图完成。

2026-10-13 已完成本轮河槽修复增量与六源关键验收，未重复全套测试；见[最终报告](docs/td-river-shape-repair-20261013-final.md)。恢复、失败和参考采用历史保留。

- [ ] 实施用户已确认的[水文规划域首版](.scratch/hydrological-planning-domain/spec.md)：共享山脊的海岸/内流双域，全域粗规划、局部TD细化、12月水账及算法可视化验收；Minecraft接入后置。
- [x] 完成[有限规划与归属查询](.scratch/hydrological-planning-domain/issues/02-bounded-planning.md)：35个成功支持区、14个明确拒绝，固定依赖清册与实际排水检查；不代表全世界覆盖。
- [x] 完成[首例季节水量循环](.scratch/hydrological-planning-domain/issues/03-seasonal-water.md)：日/半日周期轨迹与冷审通过；保留旧候选水量失败。
- [ ] 完成[真实TD细化与图审](.scratch/hydrological-planning-domain/issues/04-td-detail-review.md)：现行v5开发样例的完整10km普通河段20片、14.142km海口29片、4.888km三臂联合床面及实际细粗接口已通过；459个已归属粗单元通向合法终点，粗纵剖面连续。v5局部混合湖的周期与190个临界水位连通通过。固定12槽多种子审查已确认地形条带、矩形平整区和部分真实约束拒绝，自然度不通过，不能授予成熟发布。执行结果与开发候选冻结见[河网本体完成任务](.scratch/hydrological-planning-domain/issues/05-algorithm-completion.md)和[实施记录](docs/hydrological-planning-domain-progress.md)；保持低资源，Minecraft后置。
- [ ] 后续研究[严格条件下的跨水文域地下连接](.scratch/hydrological-planning-domain/issues/01-future-cross-domain-underground.md)。用户已要求登记；当前仍禁止跨域，暗河后续先限域内。跨域条件须明确水量交换、有限依赖及独立性变化，不能把已连通域继续称为完全独立。
- [ ] 接续[固定 TD 自然度与床面失败修复](.scratch/hydrological-planning-domain/issues/06-td-naturalness-improvement.md)：调和边界位移目标与采样横断面包络已实现，固定 seed29 普通河段宏观改写量下降约35%；原失败位置60m及同一完整窗口4.04km、9/9段细床和接缝已实际生成并冷审通过。残留条带处理见[本轮同源报告](docs/td-hydrology-naturalness-improvement-20261014.md)。自然度仍未通过，旧冻结候选不升级发布。

## 2026-10-12 先修实际河槽形态

- [x] 完成本轮实际河槽修复增量及六源同源生成、独立冷读和78张固定图审查；22569条接受边完整保留，普通折角及底部整体改善。见[本轮任务](.scratch/td-river-shape-repair/spec.md)。
- [ ] 继续处理残余汇流折角、局部不对称/谷侧偏位和形态单一，补宽深参数与现实尺度参考；本轮增量完成不表示所有形态问题清零。
- [x] 本轮河槽修复后已开始水文规划域；设计基线保留在 CONTEXT.md，当前实施状态见顶部任务。

## 2026-10-11 基于 TD 地形实际生成

- [x] 贯通全部六份固定原始 TD 地形、噪波降雨、河网与实际河槽；22569/27336 条候选河段生成，4767 条真实超预算拒绝，最终全六独立冷读通过。见[实际生成记录](docs/td-terrain-generated-rivers-20261011.md)。
- [x] 保存原地形/生成网/床面变化及来源，完成全六独立检查与固定视角审查；[最终图集](verification/td-terrain-generated-rivers/generated-20261011-04/render/index.html)保留实际折角、窄槽和拒绝区域，具体分工及验收见[本轮任务](.scratch/td-terrain-generated-rivers/spec.md)。
- [ ] 本轮已降低实际几何的普通折角并改善底部；仍需改善汇流与局部形态，补足超预算洼地的湖泊/溢流和匹配尺度的现实参考验证。六源数值审核通过尚不等于贴近现实的河流生成目标完成。

## 2026-10-11 TD 自然河网阶段 0–5

- [x] 阶段 0–5 本轮有限实现、独立审查、评价证伪与只读交付完成；见[最终报告](docs/td-natural-river-stages-0-5-20261011-final.md)及[验收矩阵](.scratch/td-natural-river-stages/spec.md)。主协调审查，三名 GPT-6.1 Sol 编写。
- [x] 按用户建议接入噪波气候与天气强度场，月序列派生 BIO，实际贯通原生降雨—土壤—河湖水账；12 个正式气候检查通过。
- [x] 509 块真实参考与两独立种子正式留出：12 窗口 10 通过/2 拒绝，6 组 5 通过/1 拒绝；不按结果调门槛，保留真实失败。
- [x] 原活动泥沙完整 900 秒空间/时间验收：128/256 级通过；最终 2048 节点正常 worker 536.16 秒、318 MiB，通过 600 秒/1 GiB，旧粗网格和恢复链资源失败保留。
- [x] 最终 14 份补充报告绑定只读页，桌面/手机的交互、完整导出、失效清理与布局通过。
- [ ] 全域自然可信与发布认证仍未授予；形态保持候选，独立留出拒绝区域不在已通过观测覆盖内。一般动态拓扑、含湖床反馈与 Minecraft 消费不属于本轮已认证能力。

历史阶段报告保留：[阶段 0–2](docs/td-natural-river-stages-0-2-20261011.md)、[阶段 3–5 原批次](docs/td-natural-river-stages-3-5-20261011.md)、[阶段 4 旧剩余项](docs/td-natural-river-stage4-remainder-20261011.md)。旧失败不由新状态覆盖。

## 2026-10-11 河网 P1 修复

- [x] 明确河道床高、几何距离和坡度关系，同时修复构造、冷读与相关调用；65 项河道回归和旧版同源几何读取通过。
- [x] 新审查发布包直接消费依赖自包含，支持离开原仓库后读取，保留旧版证据与既有前端入口；新包位于 `verification/td-river-release/portable-p1-20261011-01/`。

范围与验收见 [.scratch/river-p1-correctness/spec.md](.scratch/river-p1-correctness/spec.md)。本轮仅修复物理身份和交付依赖，不提升自然出口或全域水力认证状态。

## 2026-10-10 河网成果闭环与自然路径

- [x] 默认验收展示真实 TD 河槽、原床/加工床/切深对比、断面及同源侵蚀沉积时间记录，保留 M7 诊断入口。
- [x] 将原床约束中心线接入实际共享河床生成，保存真实 TD 前后结果并接入成果页；全域 50 条 owner-divide 拒绝继续单列。

任务与验收见 [.scratch/river-results-loop/spec.md](.scratch/river-results-loop/spec.md)。本节区分可见成果交付与此前 M8 审查包完成状态。

## 2026-10-10 河网验收默认输入

- [x] 前端河网验收默认使用已保存的 Terrain Diffusion 原始地形及同源 M7/M8 成果，显示实际来源；保留旧工程对照和显式页面链接。

范围与验证见 [.scratch/td-river-default/spec.md](.scratch/td-river-default/spec.md)。本项只修改默认入口和来源展示，不改变算法或既有验收状态。

## 2026-10-10 M7 / M8 接续

- [x] M7 限定实现：同一保存 TD 河段上的原生、均匀及固定一维局部细化，三种精度水沙均完成900s，实际交换、回粗守恒、差异指标与独立冷审通过；空间收敛未决。
- [x] M8 最终审查包：持久化绑定 M5/M6/自然谷地成果，来源与门禁、保存后冷读、前端六案例、断面、900s 水沙、WebGL 和导出均通过；全域发布仍未通过。

本轮按用户最新指示推进，具体范围见 [.scratch/m7-m8/spec.md](.scratch/m7-m8/spec.md)，实测与限制见 [验收记录](docs/td-river-m7-m8-20261010.md)。一维河段细化不等于全域二维 AMR；11/13、含湖床变反馈、CRS 和自然出口未通过的门禁继续保留。

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

历史长期阶段计划已移至 [归档路线图](deprecated-plans/Terragenesis河流地貌长期路线图.md)，原任务记录见 [.scratch/td-river-blueprint/issues/14-long-term-roadmap-integration.md](.scratch/td-river-blueprint/issues/14-long-term-roadmap-integration.md)。下列旧阶段映射只作历史记录，不再作为上位计划；可复用的验收要求见[旧规划提炼与四阶段映射](docs/legacy-river-plan-takeaways-20261022.md)。当前开发仅遵循[四阶段总览](docs/terrain-diffusion-four-stage-roadmap.md)。

- [x] 接入长期路线图，保留其对主线冻结、真实调用链、单位/时间语义、未知边界和渲染层限制的约束。
- [ ] 完成 13 全域几何后，按路线图阶段10启动 M7；阶段4一般分流、阶段6–8曲流/三角洲/局部三维岩体仍排在后续路线。

## 2026-10-08 M3–M6补充接续进行中

- [ ] 继续补充[11天然湖盆/回水](.scratch/td-river-blueprint/issues/11-natural-lake-merging-and-backwater.md)：TD256 2/.5 秒失败包保留；`.5/.125` 真实共同水面细化已通过固定1mm门槛，但仍限六叶瞬时平衡范围。
- [x] 11 的 `.5/.125` 真实共同水面细化已通过固定 1mm 门槛，stage 差 0.539420mm；仅接受 TD256 六叶有限瞬时平衡范围，issue 仍开放。
- [x] [13全域谷地河槽](.scratch/td-river-blueprint/issues/13-global-valley-channel-geometry.md)已完成本轮范围划分并接入前端全域覆盖页：45/45组件和623/673边通过 tiled 冷审；本轮排除既有50条 owner-divide 拒绝边。27条中心线支撑跨 owner，50条在原半径0.1倍诊断下仍跨 owner；重路由未评估，母集仍不完整。原始 failure-prefix 和新 scope-exclusion 证据均保留。
- [ ] 继续补充13的全域覆盖：只有合法重路由或重新声明覆盖集后，才能把623/673提升为完整全域几何；当前发布标志保持 false。
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

- [x] 按[用户指定实施蓝图（现已归档）](deprecated-plans/Terraindiffusion河网算法完整实施建议.md)完成第一轮 A-F，见[报告与真实TD证据](docs/td-river-blueprint-first-round-20261007.md)：四契约、原床D8、边界/产流适配、保存冷读及68项新旧测试通过；全域输入147456m³，残差−2.51e−10m³。450个闭合候选保留，不作为湖面或河道水力；三个诊断预览已生成。
- [ ] 按[阶段规格与依赖任务](.scratch/td-river-blueprint/spec.md)继续M7-M8；来源/tile、排水政策/forcing及M3-M6限定基线已在10月8日完成，之后为多精度、天然湖盆/回水、床变反馈与全域几何扩展。水力/自然口/发布标志保持false，CRS缺失保持pending_provenance。主协调负责审查、发布与验收；用户已指定GPT-6 Sol实施、同时最多3智能体含主协调。既有地下接回工作保留为独立任务。

## 2026-10-07 河网算法主线接续

- [ ] 按[接续规格与具体任务](.scratch/river-continuation-20261007/spec.md)补齐新洞道独立审计、完整地表接回端口及后续 face/必要水动力。主协调审查与集成，最多3智能体含主协调；用户本轮指定可用6luna，首次分派因账户不支持该模型失败。
- [ ] 确认 Claude 最新修改/建议位置；当前已定位地下暗河 V1 和其后续文档，不将旧静态小沟包测试等同于完成河网主线。
- [x] 完成[新洞道保存证据独立审计](.scratch/river-continuation-20261007/issues/01-saved-gallery-audit.md)：seed17实际TD包的四实体/材料、固定端点、VDM与空气路径通过，6项篡改/拒绝回归通过；完整端口、连续覆岩与水力仍待完成。

## 2026-10-07 动态河网渲染后续审查

- [x] 按[动态河网渲染审查任务](.scratch/frontend-review/issues/03-dynamic-river-renderer-review.md)完成六项审查；2026-10-10 M8 桌面/移动端再次验证，修复床面河段点选、无参数 `flowInterval()` 和切换时间后的旧选择，保留诊断限制，不额外拆分模块。
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

2026-11-03 用户补充：基于 Runevision Advanced Terrain Erosion Filter 继续发展有辨识度的山体形态，参考 Yosemite、落基山脉及贡嘎群山，尤其贡嘎主峰。目标包括峰形、岩壁、刃脊、谷地和岩体结构；沟壑滤镜作为组合环节。详见[山体形态规格](.scratch/mountain-morphology/spec.md)与[一手资料研究](research/runevision-erosion-primary-sources-2026-11-03.md)。共用种子引用 [CONTRIBUTING.md](CONTRIBUTING.md#共用世界种子用户更新2026-11-03)；旧冻结产物按原种子复验。

- [ ] 独立山体后端已实现首轮候选：世界坐标噪波 → Advanced底座 → 区域处理噪波，三类及混合场；固定`20260903`，高度图仅为采样输出。继续按[评价标准](无限世界地形生成评价标准.md)审查自然度、性能和世界接线；原始源码/许可已保存在`third_party/runevision_advanced_terrain_erosion/`。详见[实施与验收](.scratch/mountain-morphology/implementation-review.md)，[下一步形态深化](.scratch/mountain-morphology/issues/04-shape-refinement.md)。已按用户批准增加[Voronoi结构与沟槽保护](.scratch/mountain-voronoi/review.md)，提供同址三场、近远基准与路由变化证据；沟槽核心高程保留不等于河网保留，形态仍待深化。有限路由/扩散/冰川复用不等于整山耦合，尚未替换默认TD来源。

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

- Task11 upstream sediment connector: completed artifact same-source-20261016-04; frozen-water approximation and 1.089495 m mouth interface bed mismatch documented in summary.json.

**2026-10-31 世界尺度验收要求纠正，主图未交付。** 已核对10月初TD联合图与既有Nacrea双风格地图入口；13张局部图保留为辅助证据，任务改为partial。后续复用已有渲染器，补世界概览TD来源、粗细尺度水文与同世界环境联算，不能用条件图或放大局部图代替。[历史核对](.scratch/world-scale-acceptance-20261031/history-review.md) · [世界尺度任务及四阶段状态](.scratch/world-scale-acceptance-20261031/spec.md)。宏观基底已有世界范围；TD合成、汇流/盆地、河湖/必要高程调整已有局部成果，世界联合覆盖未完成。本轮未重跑生成或求解。

**2026-10-31 一、二阶段遥感式成果图集交付。** 新增13图：42km TD/组合地形、现行不规则河网与模型湖泊、派生床和未知边界、G3月际温度、实算G4降水、雪/水/土壤/生态与有限过程、最新三角洲及同址G6多算法联合。入口 `tools/render_project_acceptance.py`；3项定向检查通过，两位GPT-6.1 Terra核对来源与覆盖，未知上游遗漏已修正。[用户图集](验收图片/遥感式验收-20261031/README.md) · [任务与证据](.scratch/project-remote-acceptance-20261031/spec.md) · [后续验收规范](docs/remote-sensing-acceptance.md)。所有新验收图需绑定TD生成地形，优先同图联合算法；季节不称长期气候，构造三角洲不称自然自发成形。宏观基底→TD合成→汇流/盆地→河湖/派生高程本轮读取既有结果，另做G4一小时CPU对照；不扩大算法认证，袭夺暂停。




