# 三维水系首例交付摘要：2026-10-06

本轮交付是连续地表片段、源约束细床和一对真实端口的地下几何，不是所有河网complete。必要水力未通过，未接受时序禁止前端消费。原TD/source、旧冻结包与默认Minecraft世界不修改；本摘要不声称本轮前端已改。

GitHub首批代码commit `44374f8`已实际上传；后续增量由Main最后核验并发布，不能把本地新增文档当作已push回执。仓库为source-only，不包含模型、运行环境、凭据、`.scratch/`或大型`verification/`数据。仅clone源码可运行有界tiny/help；真实首例复现需要完整本地父链和匹配pins，见[快速开始](hybrid-river-quickstart.md)及[算法接口](hybrid-river-network.md)。

## 已通过的限定成果

| 层级 | 实际量化结果 | 接受范围与限制 |
| --- | --- | --- |
| 原生地形输入 | TD生成山地256×256，原生30m间距 | 生成地形，不是现实测绘或实测地质 |
| 连续地表床 | 尝试128节点，120接受、118接回弧、18分叉、2334面；最长1230m，2分量 | 独立几何passed；仍有开放端和真实拒绝，非全主域连通 |
| 0.175m细床 | 333,374唯一格、436 tiles、8,366 fans | 原native bilinear减保存affine cut；覆盖/来源/唯一格独立passed |
| 精确细床材料 | 切岩并全外运3,041.031556m³ | fan∩finecell多边形积分，不用格心depth乘整格替代材料账 |
| Typed graph | 122节点、121弧；118条surface context弧与3条sample_route弧 | 图/动态水状态分离；实际半臂接入/地下/接出，沿程累计Q不重复注入；不认证水流 |
| 首例洞道/VDM | 两实际端口，17个gallery站+2地表半臂，站间125.246807m | geometry03独立passed；gallery:4..12九站封闭核心，其余敞口坡道 |
| 实际局部Boolean | 1m近似顶面7,535样点；双地形坡道开口、16段空域路线、1个连通切出体；独立Boolean差0 | Mesh64+local origin；不是仅管壁相交，也不夸整个平面端口全开孔 |
| 洞道切岩 | 全外运1,834.143489m³，signed残差约9.1e-12m³ | 采样实体方量，不能与原生fan精确积分混作同精度认证 |

VDM保存reference+displacement=derived，端口/洞底固定；新多chart形态不冒充旧metric_vdm接受。埋深8m是显式生成条件，不是地质测量；保留6m覆岩拒绝和02.partial，不降低0.5m覆岩门槛。源到洞道的位移与chart形态位移分开。

## 输入与证据 Pins

下表路径均相对本地`verification/natural-river-network/`，不是GitHub随附文件。SHA256为文件字节pin，不等于内容identity；读取还须匹配所有原生输入/父链、代码和独立审计。

| 文件 | SHA256 |
| --- | --- |
| `shared-port-channel-20261006-01/index.json` | `d4b2e125b54137de40d4ecfab4cc72f1252afb4f96c82858eafa9298d04e1d68` |
| 同包`independent-audit-v1.json`，passed | `54e7577d6c3e0c75836003c9092e5e5dc70f6a96872238c4d1eb7f2f216845d5` |
| `shared-channel-fine-20261006-01/index.json` | `90783f602c50eb1f39f18316fbfcbe4724c682e5d07608e3b7c9db756941a48a` |
| 同包`independent-audit-v1.json`，passed | `a612499a8341df266229aae07ce25b805ced0e68b3f990c6176b2bf56a9c5894` |
| `hybrid-river-graph-20261006-01/graph.json` | `279d632e6f471c2629a37d7d6954adbcb734be19278e009eb352c9852593846a` |
| `hybrid-cave-geometry-20261006-03/geometry.json` | `3ba55abbb06f6f4cd8ac5a65dba2de362df958acf48843adcef2351bd465f593` |
| 同包`independent-audit-v2.json`，passed | `703d457eb93afa0a74ab9fc5a7bae7149cbe45d492a89202b484948a434c3364` |

固定sink/spring为`receiver:59076:59332 → receiver:60099:60355`。geometry绑定原graph及14/15的实际端口、半臂、源函数和审计，不改原来源。

## 必要水力：严格未接受

工程事件为900s，pulse供水6m³/s×450s=2,700m³，reverse另有显式工程尾水；不是自然出口认证。1D diffusive storage/Manning模型不是3D Navier-Stokes。实际断面库容、越岸工程竖壁和pressure-slot compliance须分开解释；Boolean切岩量不是水量。

| 实际包 | 结果与拒绝原因 |
| --- | --- |
| 07 | `failed_partial`；三个完整case，pulse head差0.142606mm/相对差0.000521807通过，但V/tracer差0.0047851m³、link差0.0120924m³未过1e-4m³；reverse-refined在528.71458s、RHS200001预算停止 |
| 08，严格BDF精度v7 | `failed_partial`；两pulse完整900s，但head差1.87169mm、volume差0.0897506m³、link差0.226888m³拒绝；reverse-base工作上限停止，refined未启动，不重跑 |

Main对08两pulse的面积/Q/三来源库存及逐cell账独立冷读通过，仅是保存诊断检查，不代表时间精度通过。转压力强瞬变仍在根因分析中，不能写成已解决；没有四case接受或正式水力消费包。

v8唯一09实际零完整case，物理548.6969417s、RHS200001/link3952019、墙钟107.141s预算停止，水力未接受。`hybrid_river_hydraulics_v8.py`/对应prepare使用共同local datum委托冻结v6 Radau，不复制kernel、不改geometry/law/forcing/预算/门槛；保存local数组与参数身份，由`tools/audit_hybrid_river_hydraulics_v8.py`冷读。26pins未改，worker两tiny1.404s/Main两coldtiny1.063s通过仅是有界测试，不重复真实运行。

调查观察到08逆向global head近1367±1e-12m的量化与窄slot刚性；pulse625..645s近干receiver的minK自湿释放不能归为645s roof-band根因。local datum未证单一根因或已解决；保留08正式拒绝及09失败，Main先补实际face几何，水力门禁不放行。

| 08拒绝证据：同目录`hybrid-river-hydraulics-20261006-08/` | SHA256 |
| --- | --- |
| `saved-diagnostic-v1.json` | `f69e44bb7c70839e36ab8907d5b2a17a17f2a0649f22e9d9da8a2022c6e80c80` |
| `index.json`，failed_partial | `011c088ec5ce6878676f8dae63a5ea54b21d95baa6258fbc6b1b947fd6b500de` |
| `independent-audit-v1.json`，正式拒绝 | `55df33ea215649710df18fa0630e54f4642c09877e10f8d20411faf32263e9b7` |

## 已保存只读审查

18个实际link face的首包已冷审：14局部几何通过、4洞口相关拒绝；整包refused。独立audit SHA256=`5bc3593e5c30fc079a2af9b38b0fb5993eb75688fce0d574f9bd4b9cc5e84c37`。`hybrid-river-faces-review-20261006-01/faces.png`显示剩余岩、切出材料、cutter和真实湿壁，没有水。该补证表明geometry03既有“真实地形坡道洞口”认证不能扩大为canonical整平面通水认证。

- 地表：`shared-port-channel-review-20261006-01/review.json`；地下：`hybrid-cave-review-20261006-01/review.json`与`caseartifact.json`，均位于上述本地verification根目录。
- 地下配套`overview.png`、`profile.png`、`oblique-3d.png`已按实际网格审查；review核对matched/passed和geometry/mesh/VDM pins。`caseartifact.mesh.water=null`，removed/cutter实体不是水。
- 世界XYZ米制、Y向上，先减local_origin再转float32；透明岩体只是观察手段，不作开孔证明。区分canonical端口控制点、实际顶面开口与覆岩核心边界。
- 前端可只读消费已接受几何JSON/mesh/PNG；不得动画化07/08未接受时序，不把离散压力水头拼成已认证三维水面。本轮未改UI，前端正式接入另行验收。

## 地表半臂实体接回：补证

新版本沿既有半臂来源构造52个三角棱柱，与洞道切出体组合；原mesh、端口、VDM、fine15和主Boolean阶段均保持不可变。composition03复用composition02的完整保存实体，主Boolean重算0次、水力solver0次，生成耗时1.86s、峰RSS81,395,712B。

原CrossSection把顶边量化约2.66nm，沿数米边积成超过门槛的伪缺口。新切片保留rational XYZ/UV、原edge身份、有向环/孔洞与浮点投影上界；不同精确节点即使在float显示中重合，也不合并原身份。极小正面积面与真正零面积面分别处理，全部原三角保留。

composition03的独立恢复审查已通过原生半臂来源与材料Boolean：原洞道切岩1834.1434894m³、额外切岩1.2278756m³、总采样切岩1835.3713650m³，原/额外重叠0、填方0。该账仍是采样实体方量，不替代fine15的3041.031556m³原生精确材料账，也不直接与之相加。

**整个接回包仍未接受。** producer不再报告端口缺口，但独立审查在sink/spring的原实体三维占据见证处拒绝；未把producer两侧连接标记当证书。因此faces-v2虽已实现，尚未运行真实准备，也未放行新水力或水量动画。

| 本地文件 | SHA256 / 状态 |
| --- | --- |
| `hybrid-surface-composition-20261006-03/index.json` | `549ebe84dab9252107c8ab06985a0fc47574c13839c78261c7886ca57533434a`，candidate_unverified |
| 同包`composition.json` | `88ed045a0589d130a2622cba3b4ace4a139b6513ebca2616a1bae67bdda0e4b6` |
| 同包`independent-audit-v1.json` | `4ea6f5700735395e3591a744a25d22ab520a6ae486d4c5c2d3a201c83d01a977`，旧rich pin接口拒绝，已保存15个mesh检查 |
| 同包`independent-audit-v2.json` | `82aad9f51e59b4a9718b69d8c7a2b85e501e847d7f976cadadb1bb84ebdfb2a0`，来源/材料通过、整端口占据拒绝 |
| 同包`independent-audit-v3.json` | `ba3da3e65c41db558b52fd2fb046d89f571f06f4fd41cd572fcdeb309f80e245`，v5 pin遍历实现错误 |
| 同包`independent-audit-v4.json` | `b55fa5edf1df71a0e4a8c4588f7ab48f82233d219fded4db8719bfc1fce6e2e7`，7/7区间占据查询通过，但合法带孔切片消费拒绝 |

恢复审查4.437s、峰RSS108,441,600B，继承原15个完整mesh证据、未重算其exact验证；新的来源/材料/端口检查单独记账。原拒绝报告和源码字节均保留。

最终区间核验使用固定`mpmath 1.3.0`纯Python interval backend，7个query、41,910次三角区间评估，25.391s、峰RSS94,244,864B，区间证书全部通过原始1e-7目标。随后旧v3端口消费器在sink带孔slice处拒绝；这说明占据核和端口slice表示已分离，仍不能认证整个端口。新的孔洞消费适配应继续要求外环、孔洞所有权、面积和实际实体侧一致，不能删除孔洞或把多域合并。

后续先解决原实体占据见证，不靠扩大容差、移动切面或忽略正面积小域放行。随后核验18个实际face、整link控制槛/损失和唯一库存，再定义新水力模型。任务边界见[下一水力任务](hybrid-river-next-hydraulics.md)，成熟引擎可行性见`research/underground-hydraulics-engine-20261006.md`。本轮没有安装/运行SWMM，不能把研究报告写成已接入。

## 本轮收尾增量

本轮增加了两个纯只读边界。`tools/hybrid_saved_slice_geometry_adapter.py` 严格消费保存的 polygon/holes，使用原始 binary64 的有理鞋带面积检查和显示几何检查；`tools/audit_hybrid_saved_slice_geometry.py` 对 composition03 的实体切片做独立消费审计，结果为 `candidate_consumer_only`。它没有改变 `independent-audit-v4` 的拒绝状态，也没有把 zero-area diagnostic contact 当成实体流域。

`tools/export_vdm_geometry_io_review.py` 已生成 `verification/natural-river-network/vdm-geometry-io-review-20261006-01/`。manifest 绑定固定 geometry03、review、graph 和 geometry audit，导出局部岩体/切割体/移除体、VDM reference/displacement/derived、17 个站点、19 个断面和 surface attachments。导出包明确 `water=null`，四个能力标志均为 false，适合作为前端只读几何审查输入。

本轮集中测试 14 项通过，纯 Python 编译通过。composition sink 的有理非零退化诊断三角形仍是拒绝项，spring 区间端口已通过；没有启动旧水动力求解，也没有修改 Terrain Diffusion、Java/JAR、前端或 verification 冻结输入。

## 尚未完成的产品范围

| 目标 | 当前状态与所需证据 |
| --- | --- |
| 必要工程水力 | 未接受；先解决实际时间精度/强瞬变与预算，保留严格四case及独立验收 |
| 自然出口 | 未认证；需真实边界与供水证据，工程尾水不替代自然口 |
| 全主域细床/水力 | 未完成；局部120节点和两个分量不代表全河网完成 |
| 漫滩/越岸 | 未建成真实地表漫溢模型；工程竖壁库存不认证无洪泛 |
| 独立跨域/跨精度 | 未认证；局部源函数/Boolean检查不替代独立多尺度验证 |
| 多洞道、多层暗河/侵蚀 | 后续目标；首例生成地质条件与单洞道不代表普适接受 |

`natural_outlet_certified`、`full_network_verified`、`three_dimensional_flow_solved`继续false。本摘要仅新增公开文档，不运行真实求解；TODO、checkpoint、handoff与最后发布由Main负责。
