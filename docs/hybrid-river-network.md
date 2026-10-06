# 地表与地下三维水系

## 架构

二维河网保留为水文与来源骨架，三维typed图表达地表河段、地下洞道、潜入节点和复出节点。不可变拓扑与动态水状态分开。地表床、洞底、洞顶、水面和压力水头分别命名，全部采用模型米制XYZ。

几何先建立洞道及洞口拓扑，再施加VDM位移。局部岩体与洞道实体布尔用于真实开孔；仅中心线相连或网格相交不能证明地表与地下贯通。地下路径与岩层参数初期为显式生成规则，不冒称实测地质。

有限水力消费最终变形断面，地表扣量与地下加量使用同一次交换；累计Q先验不能在沿途反复注入。首例以明确工程边界的一维蓄量/通量模型验证收支、传播与反流，不冒称三维Navier-Stokes或完整自然河网认证。

## 当前固定成果

共享中点地表床的真实独立检查已通过：128节点尝试、120接受、118接回弧、18分叉、2334面；两个实际连通分量，最长1230m。保存输入为本地`verification/natural-river-network/shared-port-channel-20261006-01/`。来源TD原生256×256/30m，是生成山地，不是现实地点测绘。

统一细床亦已完成实际生成和独立冷读：0.175m格线、333,374唯一格、436 tiles、8,366 source-minus-affine-cut fans。原生bilinear源床不修改。精确fan与fine格相交面积积分切岩/全外运3,041.031556m³；格心depth乘整格的3,041.173871m³仅作不同语义的诊断量，不代替材料账。生成RSS185,192,448B、独立审计RSS121,794,560B，均低于1GiB。

固定包为`verification/natural-river-network/shared-channel-fine-20261006-01/`。index SHA256=`90783f602c50eb1f39f18316fbfcbe4724c682e5d07608e3b7c9db756941a48a`；`independent-audit-v1.json` SHA256=`a612499a8341df266229aae07ce25b805ced0e68b3f990c6176b2bf56a9c5894`，status=passed。这只认证已接受片段的来源、覆盖、唯一格和材料，不认证全主流域、新床水力或自然海口。

## 算法入口

| 入口 | 职责与范围 |
| --- | --- |
| `terrain_pipeline/td_shared_channel_fine.py` | 接受节点source减affine cut的统一fine与相交积分材料账 |
| `tools/prepare_td_shared_channel_fine.py` | 显式准备，固定父包；不启动水力 |
| `tools/audit_td_shared_channel_fine.py` | 原生DEM、保存fans、唯一格与精确积分的独立冷读 |
| `terrain_pipeline/hybrid_river_graph.py` | 不可变surface/sink/underground/spring typed图，与动态状态分离 |
| `terrain_pipeline/hybrid_cave_geometry.py` | 局部采样岩体、洞道chart与VDM位移、真实Boolean、实际水力断面 |
| `tools/prepare_hybrid_cave_geometry.py` | 绑定真实地表/细床/图，另存局部岩体和洞道候选 |
| `tools/audit_hybrid_cave_geometry_v2.py` | 绑定Python-bool修正版，独立核对实体、真实双口、空域通路与敞口/封闭断面 |
| `tools/export_hybrid_cave_review.py` | 保存网格、剖面、3D科学图和caseartifact，不修改网页UI |
| `terrain_pipeline/hybrid_river_hydraulics.py` | 有限一维diffusive storage/Manning/Radau，非动量求解 |
| `tools/prepare_hybrid_river_hydraulics.py` | graph/experiments/run三种显式操作；几何独立通过后才准水力 |
| `terrain_pipeline/hybrid_river_sections_v2.py` | FastSection按实际断面高程分段缓存面积/湿周及反演；不是新床或新forcing |
| `tools/prepare_hybrid_river_hydraulics_v2.py` | 复用原水力核，每个完整case原子保存checkpoint；真实首场未通过 |
| `terrain_pipeline/hybrid_river_hydraulics_v3.py` | 显式Jacobian的独立版本；log-volume数值列与tracer解析列，保留原物理RHS |
| `tools/prepare_hybrid_river_hydraulics_v3.py` | 绑定原五文件和v2依赖，另存v3 case/index；真实首场未通过 |
| `terrain_pipeline/hybrid_river_hydraulics_v4.py` / `tools/prepare_hybrid_river_hydraulics_v4.py` | 显式屋顶摩阻接触过渡及accepted/trial诊断；原实际断面A/P/反演/pressure slot保留，04/05未通过 |
| `terrain_pipeline/hybrid_river_hydraulics_v5.py` / `tools/prepare_hybrid_river_hydraulics_v5.py` | 三来源直接库存、观察时刻Radau端点、严格负库存拒步及累计重试预算；06部分case已保存，整组验收pending |
| `terrain_pipeline/hybrid_river_hydraulics_v7.py` / `tools/prepare_hybrid_river_hydraulics_v7.py` | BDF严格精度版本；08已failed_partial，两个pulse完整但时间精度拒绝，根因分析pending |
| `terrain_pipeline/hybrid_river_hydraulics_v8.py` / `tools/prepare_hybrid_river_hydraulics_v8.py` | 共同local datum适配器，委托冻结v6 Radau、不复制kernel；09零完整case、预算停止，未接受 |
| `tools/audit_hybrid_river_hydraulics_v8.py` | 冷读重建共同local数组、参数身份与global/local映射，再检查实际面积/Q/三库存/账及细化；实现不等于09passed |
| `tools/audit_hybrid_river_hydraulics.py` | 无求解冷读逐断面库存、配对水/双tracer账与实际时间细化 |
| `tools/export_hybrid_river_hydraulics_review.py` | 独立通过后导出真实断面时序，不伪造连续三维水面 |

v4/v5接口已经版本化冻结，v5绑定此前冻结依赖共17个代码pins，两项tiny通过（0.465s）。代码冻结、tiny或一个完整case均不等于两场工程事件及细化全部通过。

## 保存接口与门禁

实际link切面的首包已完成一次准备及独立冷读：18面中14局部几何通过、face:0/1/16/17拒绝，整个`hybrid-river-faces-20261006-01`仍refused。两个canonical平面保留实际岩盖，另外两个斜切床域不能压成连续高度函数；材料removed分片不等于fluid分片。原生床函数与1m采样岩顶的接回差异需要新实体版本处理，不能删cap或放松容差继承接受。18面图在本地`hybrid-river-faces-review-20261006-01/faces.png`，无水体或流量。

新增接口：`terrain_pipeline/hybrid_river_faces.py` / `tools/prepare_hybrid_river_faces.py`准备真实Mesh64切片；`tools/audit_hybrid_river_faces.py`核对原三角、完整边界和湿壁；`tools/export_hybrid_river_faces_review.py`只读取保存切片出图。闭顶口域不被storage slot扩大，真实湿岩壁、开放边、工程墙和人工cap分开；原link长度及n=0.035只绑定来源，`additional_step_loss=null`不是零损失。即使局部几何通过，也不认证整link最高控制槛或新水力本构。

准备器与只读审计/导出分开。父文件采用绝对`path`与文件`sha256`绑定，内容另有`identity_sha256`；二者不能互换。修改路径、参数、代码版本或文件字节后，应另存新包并重新审计，不能仅补写passed标记。冻结旧代码不被新版本替换或运行时重绑定。

| 保存接口 | 内容与消费边界 |
| --- | --- |
| `td-shared-channel-fine-preparation-v1` / `td-shared-channel-fine-v1` | index/manifest绑定14父包、独立审计、compact_fans、material和逐tile pins；`candidate_unverified`须与真实passed审计配对 |
| `td-hybrid-river-graph-v1` | surface/sink/spring nodes、surface/underground/portal_attachment arcs；原source_xyz与派生bed_xyz分离，context_only不重复供水 |
| `td-hybrid-river-geometry-v1` | `inputs`、`mesh_pins`、`vdm_pin`、`source_sampling_pin`、`surface_attachments_pin`、实际`hydraulic_cells`/`hydraulic_links`及覆岩/开孔见证 |
| `td-hybrid-multichart-vdm-v1` | 每站reference/displacement/derived ring、station-major展开的cutter triangles与不可移动端口；不是旧metric_vdm固定chart接口 |
| `td-hybrid-cave-geometry-independent-audit-v1` | v2审计实现支持Python-bool修正版，绑定实际文件SHA；`actual_portal_connections_verified`与`actual_hydraulic_sections_verified`仅认证几何证据 |
| `td-hybrid-river-engineering-experiments-v1` | 显式预湿、脉冲、尾水、时刻、容差和工作预算；配置文件不是水力结果 |
| `td-hybrid-river-hydraulics-preparation-v2` / `-v3` | 各版本独立index/checkpoint，只有完整case才保存结果；不自动resume，不把partial当完成 |
| `td-hybrid-river-hydraulics-preparation-v4` / `-v5` | 另存`hydraulic-model.json`和版本化结果/诊断；模型摩阻参数、inventory policy、代码/forcing pins与实际work一并绑定 |
| `td-hybrid-river-hydraulics-preparation-v7` | 独立BDF结果/checkpoint，记录原输入参数身份及base/refined严格精度政策；不是07失败包的接受标记 |
| `td-hybrid-river-hydraulics-preparation-v8` / `td-hybrid-river-local-vertical-frame-v8` | 保存共同datum、local head/尾水/solver参数及身份；global head=datum+local head，原geometry不变 |

`route_region`描述图上来源，`cell.kind`描述实际物理断面，两者不能强行等同。gallery敞口坡道仍属于地下route，但其cell为`surface/open_polyline`；真实连续覆岩核心才是`underground/closed_polygon`。`section_geometry_reference`绑定最终ring与横向框架，开放坡道仅引用floor prefix。配对链接按物理cell类型区分`surface_half_arm`、`sink_exchange`、`conduit`、`spring_exchange`，交换位置不冒充canonical midpoint端口位置。

上限为1GiB RSS、64MiB/保存文件；fine不超过2,000,000唯一格，局部岩体顶面采样硬上限300,000。超预算拒绝整包，不靠截取缩成通过；没有默认求解、原source写入或Minecraft世界发布。

## 首个地下样例

固定typed图：`hybrid-river-graph-20261006-01/graph.json`，122节点、121弧；保留118条地表context弧，实际新增3条可遍历的地表半臂接入/地下/地表半臂接出边。6条原地表弧保留为旁路来源；不是把二维网整体下移，也没有反复注入沿程累计Q。

首例使用已审查的`receiver:59076:59332 → receiver:60099:60355`端口。`hybrid-cave-geometry-20261006-03/geometry.json`已生成并通过`independent-audit-v2.json`独立冷读。实际站间长度125.246807m，17个gallery断面加2个地表半臂库存，共19个水力断面；gallery:4至12具完整岩体封闭，其余按敞口坡道处理。潜入/复出为真实地形坡道洞口，不夸称整个端口平面及全河岸均完整开孔。

VDM保存reference、displacement、derived三个独立身份；洞底与两端端口不移动，洞顶及横向局部位移施于新多chart形式，不更改旧固定chart VDM。原生源到派生洞道的位移另存，不与chart形态位移混为一谈。

局部岩体采用1m采样顶面的闭合网格近似，7535个顶面采样；Mesh64与局部origin避免大世界坐标float32误差。独立Boolean重建差为0、切出空域1个连通体、两口及16段空域路线通过。新增局部切岩/全外运1,834.143489m³，体积残差9.1e-12m³；它是采样实体方量，不与上面的原生fan精确方量混作同精度认证。

6m埋深旧候选保留覆岩不足拒绝；按真实源采样推导的最小所需埋深约7.12377m，新样例显式取8m，未下调0.5m覆岩门槛。`02.partial`为序列化失败未成品，不消费。原source、旧fine和默认Minecraft世界均未修改。

固定geometry SHA256=`3ba55abbb06f6f4cd8ac5a65dba2de362df958acf48843adcef2351bd465f593`；独立audit SHA256=`703d457eb93afa0a74ab9fc5a7bae7149cbe45d492a89202b484948a434c3364`。只读审查包在`verification/natural-river-network/hybrid-cave-review-20261006-01/`，含实际网格、来源与原生山地区位、剖面、3D图和`caseartifact.json`；不是已有水面或正式网页导航。

## 库容与水力限制

9个封闭核心单元的合计长度82.740026m，按最终实际断面的一维站库存`Σ L·A(crown)`为1,481.111726m³。它不是Boolean精确空腔体积，不能与1,834.143489m³切岩量互换，更不能作为初始水量。开放单元有显式工程竖壁：水头超过保存bank高程后的额外库存不认证真实地表防漫溢能力。

封闭断面的工程pressure slot宽0.02m，核心合计`Σ L·slot_width = 1.654801m³/m head`。洞顶以上新增库存属于工程compliance，不是额外实体洞腔或实测岩体可压缩性。冷读须从每个实际保存水头计算断面面积、库存、越岸和洞顶以上槽储量，不能仅看solver成功或生成器到达bool。

当前固定工程配置是900s观察、6m³/s脉冲450s（总供水2,700m³）、预湿各floor+0.05m、pulse尾水1360.910608m、reverse尾水1367.0m；时间步上限base/refined为10s/5s，容差另有细化。这些是工程输入，不是测得的自然边界，也不是已接受传播结果。600s是每case墙钟保护，不是900s物理模拟时长。

v4显式引入屋顶摩阻接触过渡，不应描述为与旧摩阻定律完全相同。`--crown-friction-transition-m`范围0至0.05m；0只允许配合短诊断停止复现旧law，正宽度也可短诊断。首例05/06使用0.02m（2cm）工程过渡；它改变有效屋顶接触摩阻，而不改变实际断面面积A、湿周P、A的反演或0.02m压力槽库容。`hydraulic-model.json`与相应代码pins记录该区别，不能仅据旧geometry审计授予新law接受。

v5的三个来源库存为`untraced`、`source`、`tailwater`，水量V定义为三者直接求和，不再分别积分V后允许source超V。900s的181个观察时刻对应180个积分区间，保存状态必须是Radau实际端点，不用dense插值库存冒充正性认证。接受端点的任何负来源库存严格拒绝整个步并减半重试，无clamp、事后归一或负值容差；Newton trial可有有限带符号来源值，但总水量必须正，trial不等于accepted。所有重试累计在同一原forcing/work/wall/RSS预算内，不重置预算或改供水事件。是否最终通过仍由完整保存时序、细化和独立冷读决定。

v7改用BDF，base采用原配置相对/绝对容差各除64、最大步长除4；refined各容差除256、最大步长除8。对本例原10s步长，上限分别为2.5s/1.25s。forcing和900s事件不改，三来源库存、严格负库存拒步、端点观察与累计预算仍需完整检查；不能用更严格的参数配置替代实际细化通过。08未复用07的旧精度case，但实际仅两个pulse完成，reverse-base预算停止、reverse-refined未启动。

v8是最小数值坐标改进：从实际断面最低floor取整数datum，统一平移断面高程、初始head与尾水，在共同local frame先计算inverse、摩阻、Q和Jacobian，然后恢复global输出。它显式委托冻结v6 Radau，不复制kernel，不改geometry、law、forcing、预算或接受门槛，也不增加微小通量deadband。26个代码pins冻结；worker两项source-only tiny通过（1.404s），Main两项cold-frame tiny通过（1.063s），仅为有界测试证据。

## 本轮执行

截至2026-10-06本次文档更新，连续fine、三维typed图、潜入/洞道/复出真实几何与VDM形态已完成首例限定交付。水力尚未通过，不能用配置、tiny或版本加速替代验收：

| 版本/实际包 | 状态 |
| --- | --- |
| 原水力核v1 | 首场触发墙钟保护，无已接受水力成品；原五文件冻结 |
| v2 / `hybrid-river-hydraulics-20261006-02` | `failed_partial`，`completed_cases=[]`；首场`array must not contain infs or NaNs`，不是有效时序 |
| v3 / `hybrid-river-hydraulics-20261006-03` | `failed_partial`，`completed_cases=[]`；约57.39s触发`independent 1D work/time bound exceeded`，不是物理事件完成 |
| v4 / `hybrid-river-hydraulics-20261006-04` | 旧law短诊断在物理时间约110.30s、gallery:9精确crown附近停滞；诊断不是完整900s事件 |
| v4 / `hybrid-river-hydraulics-20261006-05` | 2cm摩阻过渡使900s事件推进完毕（墙钟约45.656s），但source库存超V约2.607e-6m³，严格composition检查拒绝；不是通过结果 |
| v5 / `hybrid-river-hydraulics-20261006-06` | pulse-base已完整保存并由07复用；单case不授予整组接受 |
| `hybrid-river-hydraulics-20261006-07` | 已`failed_partial`退出；三个完整case为复用06的pulse-base、07的pulse-refined及reverse-base，reverse-refined未完成；pulse细化亦未全部通过 |
| v7 / `hybrid-river-hydraulics-20261006-08` | 已`failed_partial`退出；两个pulse BDF精度case完整900s但时间精度拒绝，reverse-base工作上限停止，reverse-refined未启动；不重跑，根因分析pending |
| v8 / `hybrid-river-hydraulics-20261006-09` | 零完整case；物理548.6969417s、RHS200001/link3952019、墙钟107.141s预算停止；26pins未改，水力未接受 |

06的已保存pulse-base快照：墙钟75.094s、169,471次RHS、RSS113,000,448B；source出口累计7.980095m³，最后100s出口source量3.101984m³，阈值到达时间575s。上述是单个base case的实际保存证据，阈值tracer到达不代表有限速度波前，也不授予独立水力接受。

07的pulse细化中，最大head差0.142606mm及相对体积差0.000521807分别通过1mm/1%门槛，但V/tracer差约0.0047851m³、配对link积分差约0.0120924m³均未达到1e-4m³绝对门槛，因此pulse细化整体未通过。reverse-refined在物理时间528.71458s、RHS计数200001触发预算停止，不能用reverse-base代替缺失细化case。07没有四case接受或正式前端水力交付。

08的两个完整pulse case对照：最大head差1.87169mm、体积差0.0897506m³、配对link积分差0.226888m³，分别未过1mm及1e-4m³绝对门槛。Main对这两个pulse独立冷读的实际断面面积、Q、三来源库存与逐cell账检查通过，但这不代表时间精度通过或整组水力接受。当前与另外两位代理分析转压力阶段的强瞬变；根因尚待确认，不提前把该假设写成已解决。08不重跑，未接受时序仍禁止前端消费，几何交付状态不受其影响。

最小调查事实：08逆向接近平衡时global head在1367±1e-12m附近量化，窄pressure slot使库存/head耦合刚性明显；共同local datum是改善数值条件的候选，不是唯一根因证明。pulse约625..645s的近干receiver涉及minK自湿释放，不能归因为645s roof-band触发。09仍预算失败，无已解决或唯一根因结论；Main转向补充真实face几何，不因此授予求解接受。

水力发布需两场各base/refined共四个完整case、实际时间细化、配对水/双tracer账及独立冷读全部通过。几何审计的`actual_hydraulic_sections_verified=true`不表示`hydraulic_solved=true`。未通过包与checkpoint只供诊断，不供前端水量动画；失败不能通过放宽物理、forcing或认证门槛改称通过。

## 源码与只读消费

GitHub交付为source-only：模型、原生数组、运行环境、凭据、`.scratch/`与`verification/`大型包不随代码上传。源码可安装依赖并运行tiny/help；固定真实样例还必须取得完整原生来源、14/15及其审计和父链文件。不能声称只clone代码即可复现该真实包。具体命令与本地pins要求见[快速开始](hybrid-river-quickstart.md)。GitHub提交/push是否完成须另看主协调回执。

前端契约来源为本地`.scratch/hybrid-river-network/frontend-consumption-contract.md`，其未上传内容的必要消费规则同步如下：

- 已通过地表片段读`shared-port-channel-review-20261006-01/review.json`；typed图读`hybrid-river-graph-20261006-01/graph.json`；地下几何读`hybrid-cave-review-20261006-01/review.json`与`caseartifact.json`。这些路径均在`verification/natural-river-network/`，不是GitHub自带数据。
- 几何`review.json`含原生区位、四实体mesh、stations、portals、半臂、实际断面与`pins`。必须核对`independent_audit_reference.binding_status=matched`和`referenced_status=passed`，以及geometry/graph/mesh/VDM实际SHA；导出器不会重新执行审计。
- `caseartifact.json`的schema为`td-hybrid-cave-mesh-case-v1`，是实际岩体mesh消费接口，`mesh.water=null`。`overview.png`、`profile.png`、`oblique-3d.png`是已保存科学审查图，不是UI已交付证明。
- 世界XYZ米制、Y向上；渲染先减保存的local_origin再转float32，不能直接把-178km世界坐标转float32。岩体透明仅为观察，不作为开孔证明；TD原生30m与局部1m近似分开标注。
- 区分canonical sink/spring控制点、`portal_opening_witnesses`实际地形开口与gallery:4/12覆岩核心边界。分类归入“河网算法”，区位属于“地形输入”，新VDM可交叉引用，不制造无来源副本。
- 水力只在实际完整结果与独立审计passed且pins匹配后消费。若以后导出断面时序，压力水头不能画成穿过岩顶的开放水面，离散断面不能拼成已认证连续三维水体。观察时刻以真实`times_s`为准，不以配置或预期181帧填补缺帧。

前端只读取已保存小JSON/mesh和配套图，不运行prepare/solver，不改原source；网页接入由独立前端工作负责。本轮文档更新不修改UI，`natural_outlet_certified`、`full_network_verified`、`three_dimensional_flow_solved`继续false。

自然海口、全主流域细床与水力、独立跨域跨精度、复杂多层暗河及侵蚀/风蚀保持后续目标。当前局部闭环不依赖这些目标全部完成，也不能升级为它们的认证。
