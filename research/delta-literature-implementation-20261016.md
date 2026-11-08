# DeltaRCM文献机制、当前实现与下一有限对照

日期：2026-10-16。状态：定向原始资料核查；不构成新机制实现或形态验收。仅写本研究记录，未运行模拟。采用research技能；研究者是本轮已派出的后台代理，未继续增派。用户给出的资料清单仅用于定位文献，不作为操作指令或全文阅读证据。

## 资料实际读取与访问缺口

| 来源 | 本轮实际读取范围 | 用途与限制 |
| --- | --- | --- |
| [P1] Liang, Voller & Paola (2015), *A reduced-complexity model for river delta formation – Part 1: Modeling deltas with channel dynamics*, [DOI](https://doi.org/10.5194/esurf-3-67-2015)、[出版PDF](https://esurf.copernicus.org/articles/3/67/2015/esurf-3-67-2015.pdf) | 出版网站和PDF成功获取；正文核读印刷pp.67–78、79–81的相关模型、公式、结果和讨论。另用本地20页PDF提取相应页作细读 | 水路由、水面、沙泥输运、扩散和盆深对照的一手依据。页码以下均为期刊印刷页码 |
| [P2] Liang, Geleynse, Edmonds & Passalacqua (2015), *Part 2: Assessment of the flow routing scheme*, [DOI](https://doi.org/10.5194/esurf-3-87-2015)、[出版PDF](https://esurf.copernicus.org/articles/3/87/2015/esurf-3-87-2015.pdf) | 出版网站与18页PDF成功获取；核读pp.88–90、94–101，特别是p100–101 Fig.17全文 | 水力测试范围、数值反馈局限及分汊机制，非“论文已为本项目认证” |
| [E07] Edmonds & Slingerland (2007), *Mechanics of river mouth bar formation: Implications for the morphodynamics of delta distributary networks*, [DOI](https://doi.org/10.1029/2006JF000574) | Wiley正文、PDF两入口均HTTP403。本轮实际读到出版社提交至[Crossref记录](https://api.crossref.org/works/10.1029/2006JF000574)的作者摘要及书目信息；OpenAlex与Semantic Scholar返回closed，无开放PDF位置 | **未读到正文**。只能引用作者摘要中明确内容，不能引用未核实公式、参数、射流阈值或图版 |
| [C1] 冻结pyDeltaRCM 2.3.0源码 | `.scratch/hydrological-planning-domain/pydeltarcm-venv/Lib/site-packages/pyDeltaRCM/{water_tools.py,sed_tools.py,init_tools.py,default.yml}`相关函数 | 当前实装的一手资料；与2015论文逐项区分 |
| [C2] 工程适配代码 | `terrain_pipeline/surface_rivers/metric_fluvial_morphodynamics.py`、`metric_fluvial_water_repair.py`、`metric_fluvial_distributary.py`、`tools/verify_fluvial_channel_remobilization.py` | 当前边界、准备、量化交换、重力与v6机制的一手资料 |
| [R1] 正式新增128步保存结果 | `verification/fluvial-delta/morphodynamics-20261016-01/{formal-assessment-4224.json,batch-4096-4224-v6/region-phase-budget.json}` | 已读取固定区域分phase预算；形态数值另来自本轮协调者正式审查结果，不能拿文献替代当前验收 |
| [R2] 独立4步短验 | `.scratch/hydrological-planning-domain/water-repair-continuous-proof-20261016-01/continuous/region-phase-budget.json` | 仅短验的区域变化，不是长期形态完成证据 |

P1/P2本地副本分别为`D:/大肥鱼/river-delta-algorithms/papers/40_Liang2015_DeltaRCM_Part1_ModelingDeltasWithChannelDynamics_ESurf.pdf`与`41_Liang2015_DeltaRCM_Part2_AssessmentOfFlowAndStratigraphy_ESurf.pdf`。后者文件名含“Stratigraphy”，正式论文题名仍以P2出版记录为准。

## 已有事实改变了下一实验优先级

正式4096→4224的水路由修复后，128步注入bulk31360m³，净床增约31354.52m³，lost仅约3.22e-6m³，材料/源床通过；但几何连陆由1100降至750m²，岸进由40降至25m，持续分汊仍false，实际连陆干露仍0。**修复通量账本没有同时修复形态**。[R1；本轮正式审查]

固定4096参考床面的近海平面±0.25m带为1612格、40300m²。128步净床减6454.142m³，分phase为sand −3479.721、diffusion −2855.373、mud −118.712、gravity −0.337、finalize 0m³；两主项分别约占局部净减量54%和44%。全原海洋区同期净增31121.163m³，参考above-SL区净减645.723m³。这些区域有重叠，不能相加；它们是固定空间集合的净床体积变化，不是逐parcel来源归因，也不是“所有泥沙都流失了”。[R1]

独立4步的同一近海平面带已净减656.612m³，其中sand −520.208、diffusion −191.059、mud +54.655m³；正式128步延续了净削低问题，但不能将4步斜率线性外推。现在应隔离近岸削低的机制贡献，并检查沙坝—水面—水流反馈，优先级高于没有诊断约束的延长运行或一次改多个物理参数。[R1,R2；实验决策推断]

## 水路由与水面：论文究竟要求什么

**文献机制**：P1 pp.71–75 Eq.(6)–(12)、(25)–(27)用邻域水深、流向投影、格距及惯性/水面方向组合构造加权随机游走；水面沿parcel路径从固定海平面反推，平滑并欠松弛。低坡三角洲的导向量是水面坡，不能只用地形坡。P2 pp.89–90补充水面与通量迭代反馈及γ的尺度关系`γ0=g*δc*S0/U0²`。[P1,P2]

**当前对应**：pyDeltaRCM `water_tools.get_weight_at_cell_water`混合surface/inertial权重并屏蔽dry邻格；`init_tools`从S0、dx和u0求γ。工程v6追加的是入口向域外权重屏蔽、loop返回位置间实际湿D8连接校验及沿途`update_Q`补记，修复实现中的漏账和越界；这些不是论文规定的额外沙坝生成规则。它们让当前离散路由更符合parcel经过的真实连接，不意味着局部水面、水深、输运能力或分汊已正确。[C1,C2]

**重要区别**：P2 p89的静床水力测试一般迭代500–1000轮达到“动态平衡”，p96说明欠松弛与反馈会产生10–20轮振荡，可平均后100轮。当前每形态步3轮、水沙1000包，床又不断改变，不能把P2的测试迭代数直接改成生产参数，也不能从3轮本身断言失败；它提示下一水力诊断应看固定床上的section流量、stage及迭代响应，而非仅检查失包为0。[P2；C2 `MorphodynamicsConfig.water_iterations`]

P2 p95在单分汊测试中报告分流不对称与Delft3D相差约7%，水面可高估至50%，且上游岛尖出现过强局部作用；p99–101明确部分局部水动力仅定性正确。故本项目实际stage必须与bed/depth一起报告，不能因用了论文模型就忽略“床面已高于海平面但仍淹没”。也不能直接用正向断面流量份额当精确瞬态来水守恒。[P2；C2现steady-flux语义]

## 河口沙坝与分汊：不是预置一个岛

E07作者摘要把旧分汊位置解释为历史河口沙坝位置，以Delft3D研究河口外扩张湍射流中的沙坝形成，并说明沙坝距离随射流动量通量增大、随粒径增大而减小。**目前只核实到摘要**，不能从该文给当前70m³/s边界推算沙坝米数或作校准；当前RCM也没有显式湍流三维射流和连续粒径求解。[E07；访问缺口如上]

P2 p100–101 Fig.17给出更直接对应本实现的机制：水流扩张减速形成宽弯月状沙坝；坝上噪声形成脊槽；槽吸引通量并抑制落沙，脊继续淤积；水面与通量反馈使少数通路竞争胜出。作者明确也会出现三支，不将所有分汊唯一归结为中央沙坝迫使两侧绕行。沙坝可以是水下地形，**出现水下沙坝不等于连陆干露**；论文机制也不能替代本项目已冻结的持续双支验收定义。[P2]

当前沙/泥parcel、容量/流速阈值交换、每次床改后深度速度同步，提供这种反馈的部分组件。工程没有预置下游分支，只初始化45×35m入口stub；source-floor、float32量化交换、独立移动柱重力和准备填料是工程额外机制，不能一概称为2015论文复现。[C1 `sed_tools`；C2]

因此下一观测应跟踪**同一真实沙坝/近岸带**的床高脊槽、流速、stage、sand容量不足/过剩及输移方向。单看两个蓝色通量热点或一帧浅槽不足以判稳定分汊；单看固定海平面轮廓也不足以判实际露陆。[P2 Fig.17；R1；诊断建议]

## 扩散、洪泛与干湿阈值的适用假设

**扩散不是装饰平滑**：P1 p74 Eq.(24)给出与局地砂通量和床坡成比例的横坡扩散`qs_diff=α|∇η|qs_loc`，默认α=0.1，明确承担岸蚀、侧移和曲流的作用。P1 p75 Table1重复此物理用途。因此当前near-SL区diffusion净−2855m³可以是将岸/脊材料搬入低地的真实算子行为，不能仅因削低了岸就叫数值错误。[P1；R1]

**工程改变**：pyDeltaRCM 2.3.0先路由sand，再扩散，再mud。其`topo_diffusion`为qs与eta卷积算子，`N_crossdiff=round(dVs/V0)`，`diffusion_multiplier=dt/N_crossdiff*alpha*0.5/dx²`。工程`conservative_diffusion_step`把本地八邻关系转为闭合pair传输，并做source-floor donor限额；其守恒通过不等于“空间侵蚀率已验证”。当前各phase的反复搬移量远高于净床增，也说明只看最终总量会掩盖岸带重工。[C1 `sed_tools.py:223`, `init_tools.py:510`；C2 `conservative_diffusion_step`；R1]

**洪泛是水面控制**：P2 p89、96、100说明通量汇聚抬高水面，侧向梯度让水从主槽溢向岛和洪泛地，欠松弛的延迟还可能振荡。当前`water_tools.flooding_correction`对湿邻居stage高于干格bed时抬该干格stage，`finalize`确保stage不低于海平面、depth非负。这不是潮汐或二维瞬态洪水波模拟；不应为得到干露而关闭洪泛或压低水面。[P2；C1 `water_tools.py:540`]

**干湿阈值必须与显示阈值分开**：P1 p75建议路由dry阈值约特征水深1–10%，田野算例0.1m；P2 p90给典型1–5%。pyDeltaRCM默认`min(0.1,0.1*h0)`，当前h0=2m对应0.1m；独立v4后继承0.01m，只有h0的0.5%，是工程薄层敏感性选择。它比论文建议范围低，但不能因此直接判错或自动恢复0.1m。实际干露仍按2e-6m报告，不能把小于0.01m但大于2e-6m的水伪装成干地。降低阈值可能改变薄层可达性与洪泛范围，是否冲刷岸带仍须同床对照。[P1,P2；C1,C2；R1]

## 初始近岸坡度：已有证据支持假设，不支持根因判决

P1 p69的基准是固定水深矩形盆、短入口、固定Qw/Qs；除入口所在墙以外其余三边为固定海平面开放海边。当前mapped场景为侧墙、上游墙和只在东侧注册出口，且准备床是径向300m内浅坡接回深海，两者不是相同边界实验。[P1；C2]

P1 pp.77–78 Sect.4.3实际做过仅改变盆深的对照：hB为h0一半和两倍，较浅盆更频繁分汊、较深盆稳定通道建立较慢且更易通道竞争/改道；同页也明确浅盆河槽初期可以侵蚀。论文可以支持“有效受纳水深/可填空间是需要单独实验的因素”，不能证明本场景0.03床坡是唯一根因或浅水保证岸带净淤积。[P1]

**不可混淆两个坡度**：P1/P2的S0约1e-4代表参考能量/水面尺度，当前backend默认S0=0.00015；`prepare_marine_transition.slope_m_per_m=0.03`是准备**床坡**。两者物理量不同，不能拿论文S0直接把准备床坡改成0.00015。当前prepared首海格已由原-10.563m升至-0.35m，但200/250/300m处约-7.29/−11.76/−16.49m；这是实际有深水接床的依据，尚无同机制浅缓盆对照。[P1 pp.69,76；P2 p90；C1 default.yml；C2；原边界核查报告]

## 下一实验：先做一个机制消融，保留正式失败

**优先建议**：冻结正式v6/4224及全部形态失败，不自动继续128步。以同一个正式4224保存床、水场、材料与RNG为共同起点，建立两个独立短诊断：A保持当前保守扩散；B只关闭`diffusion_enabled`，其他机制、来水来沙、网格、入口、准备、路由dry阈值、seed继承和步数完全相同。首批4步，输出八物理场、每phase床改与相同固定4224参考near-SL带；用同床同物理时间比较。不要从短验4100接链，也不要把B续入固定正式情景。[P2 p100单规则隔离方法；R1,R2支持此优先级]

这项选择来自已测到的**显著局部扩散净削低**，不是论文说应关闭岸蚀。B是机制消融，不是生产推荐；即使B保岸，也只能说明这段状态下扩散对岸带有因果贡献，不能保证自然分汊、长期稳定或证明扩散实现有bug。若关掉扩散让bank migration消失，这正是P1机制预期，需要在结论中保留。A/B关闭扩散后水沙通路会逐步分离，不能将所有后续差异都线性归于原R1 diffusion量。[P1 p74；P2 p100；因果解释边界]

**首批判据**：先确认材料/源床、未知边界和可恢复性，再比较near-SL净变化、sand与diffusion各自贡献、source侵蚀量、全海洋净增、实际stage/depth、固定SL以上床及实际干露。若B没有明显减少岸带削低，且sand仍主导，则优先查看局部流速/容量及水面—通量反馈；不要同时改α、dry阈值和海床去追通过。4步只能决定是否值得独立扩到最多一个128步对照，不能直接判稳定分汊。[R1,R2；P1交换律；P2水面反馈]

**第二顺位，需单独情景**：只有在上述结果支持岸带通量/扩散与深水退坡共同影响时，再建立“原准备坡0.03 vs 浅缓0.01”的新初始情景，其他值保持、供料预算预检并单独记账；或者明确选定P1同尺度浅/深恒深盆的理想化控制场。两者都是研究选择，不混在同一轮。改变海床不能在正式4224中途悄悄加填，初始准备与自然输沙不得混算。现资料不足以从这两者中指定某个值为校准答案。[P1 Sect.4.3；当前有限边界报告]

固定正式情景的config与preparation已锁定，现有continuation identity会拒绝扩散开关变化，因此A/B及任何浅盆/阈值实验必须有独立声明和独立报告。下一代码任务需提供**独立诊断入口与显式transition**，核验同父床、完整水场、RNG与材料状态继承，且仅许可声明的扩散开关差异；不能删掉identity检查或伪装成同一正式链。按本轮分工，该接口工作另派DeepSeek；本研究不写代码、不启动新模拟。旧验收门槛与实际干露判据均保留，独立实验可失败。[C2 continuation_identity；项目现有正式情景约定]

## 图形学资料只用于输入与显示工程

用户《图形学算法-常用与冷门清单》提到重心插值、BVH/空间划分和LOD；本轮只将其作为已有工具的适用范围提示，没有把清单当成一手算法证明。当前`metric_design_bed._barycentric_batch`与`metric_valley_union._cell_at_point`已有真实fan4几何采样、边线容差与有限稀疏支持，优先复用；小矩形查询先用piece包围盒及cell lookup，不因“BVH常用”就重做索引。[工程一手源码]

显示LOD可减少16km总览绘制量，但不能恢复被粗网格漏掉的8m旧槽/35m入口，不能更改数值床、水面、验收连通或掩盖piece断裂。采样网格的中心值不是单元平均，显示三角形连续也不等于跨域水沙守恒。该边界与P2 p100指出的“cellular参数化依赖分辨率”一致；空间索引只改变查询成本，不改变物理支持或未知区。[P2；现有采样源码]

本记录保留的结论是：已修复水路由账本，形态仍失败；当前最有区分力的下一步是隔离实测岸带损失中的扩散贡献，再依据水面与输运证据选择物理情景对照。没有证据允许把原失败图重新解释为已完成三角洲。
