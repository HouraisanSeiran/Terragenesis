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
| `tools/audit_hybrid_river_hydraulics.py` | 无求解冷读逐断面库存、配对水/双tracer账与实际时间细化 |
| `tools/export_hybrid_river_hydraulics_review.py` | 独立通过后导出真实断面时序，不伪造连续三维水面 |

## 首个地下样例

固定typed图：`hybrid-river-graph-20261006-01/graph.json`，122节点、121弧；保留118条地表context弧，实际新增3条可遍历的地表半臂接入/地下/地表半臂接出边。6条原地表弧保留为旁路来源；不是把二维网整体下移，也没有反复注入沿程累计Q。

首例使用已审查的`receiver:59076:59332 → receiver:60099:60355`端口。`hybrid-cave-geometry-20261006-03/geometry.json`已生成并通过`independent-audit-v2.json`独立冷读。实际站间长度125.246807m，17个gallery断面加2个地表半臂库存，共19个水力断面；gallery:4至12具完整岩体封闭，其余按敞口坡道处理。潜入/复出为真实地形坡道洞口，不夸称整个端口平面及全河岸均完整开孔。

VDM保存reference、displacement、derived三个独立身份；洞底与两端端口不移动，洞顶及横向局部位移施于新多chart形式，不更改旧固定chart VDM。原生源到派生洞道的位移另存，不与chart形态位移混为一谈。

局部岩体采用1m采样顶面的闭合网格近似，7535个顶面采样；Mesh64与局部origin避免大世界坐标float32误差。独立Boolean重建差为0、切出空域1个连通体、两口及16段空域路线通过。新增局部切岩/全外运1,834.143489m³，体积残差9.1e-12m³；它是采样实体方量，不与上面的原生fan精确方量混作同精度认证。

6m埋深旧候选保留覆岩不足拒绝；按真实源采样推导的最小所需埋深约7.12377m，新样例显式取8m，未下调0.5m覆岩门槛。`02.partial`为序列化失败未成品，不消费。原source、旧fine和默认Minecraft世界均未修改。

固定geometry SHA256=`3ba55abbb06f6f4cd8ac5a65dba2de362df958acf48843adcef2351bd465f593`；独立audit SHA256=`703d457eb93afa0a74ab9fc5a7bae7149cbe45d492a89202b484948a434c3364`。只读审查包在`verification/natural-river-network/hybrid-cave-review-20261006-01/`，含实际网格、来源与原生山地区位、剖面、3D图和`caseartifact.json`；不是已有水面或正式网页导航。

## 本轮执行

连续fine、三维typed图、潜入/洞道/复出真实几何与VDM形态已完成首例限定交付。两场900s有限水动力及实际时间细化正在执行；不能用配置和计划替代验收。

自然海口、全主流域细床与水力、独立跨域跨精度、复杂多层暗河及侵蚀/风蚀保持后续目标。当前局部闭环不依赖这些目标全部完成，也不能升级为它们的认证。
