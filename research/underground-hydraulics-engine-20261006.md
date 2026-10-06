# 实际洞道 mixed-flow 引擎窄研究

日期：2026-10-06。范围：EPA SWMM 官方 C 源码与 PySWMM 官方包装接口。只读研究，未安装、运行引擎或改动现有物理/库容；不将研究视为实际 18 face、19 cell 或双口连接验收。其他引擎本次未作主源核查，不作比较性推荐。

## 结论

**SWMM Dynamic Wave 值得作为一个明确新身份的工程模型转换候选，但不是现有 cell V(H) + 双 head actual-face A/P 的即插即用积分器。** 它包含 conduit 动量方程、节点连续性、明满流切换和逆流；CUSTOM 断面输入、管段库存和 surcharge 本构均有自己的语义。PySWMM 提供运行/观察接口，并不自动把这些语义变成本项目冻结模型。[S1][S2][S3][S4][P1]

若后续授权，最小准备工作是先做**不求解的模型转换误差表与全域库存归属表**，而不是再开启 900s 事件。尤其不得把 19 个既有 cell 的完整库容放进 storage nodes 后，又让连接它们的 conduits 存储同一段洞道水；源码确实同时统计 node 与 link 库存。[S2][S5][S6] 这是源代码所示行为导出的工程约束，不是 SWMM 已保证我们的空间分区正确。

## 主源与版本

本次通过 GitHub 官方 API 读取以下固定 revision 的源文件内容；raw 域名连接失败后使用 API 的 base64 内容读取，未依赖搜索摘要。EPA 仓库读取 revision 为 `07c371f8a0d477da1d9d4e7c0d75719664f62fec`；PySWMM 为 `97cb36ff7820ba23ed6c09d9a38551aa619ea88a`。它们是本次检查的 revision，不宣称是本地已安装版本或永久最新 release。

- [EPA 官方产品/手册入口](https://www.epa.gov/water-research/storm-water-management-model-swmm)。本文具体实现判断以以下固定源码为依据，不假定手册中每项概述对应任意安装版本。
- [S1：dwflow.c，conduit momentum、湿断面、slot](https://github.com/USEPA/Stormwater-Management-Model/blob/07c371f8a0d477da1d9d4e7c0d75719664f62fec/src/solver/dwflow.c)
- [S2：dynwave.c，节点连续性、surcharge、步长](https://github.com/USEPA/Stormwater-Management-Model/blob/07c371f8a0d477da1d9d4e7c0d75719664f62fec/src/solver/dynwave.c)
- [S3：shape.c，CUSTOM 宽度曲线到断面几何表](https://github.com/USEPA/Stormwater-Management-Model/blob/07c371f8a0d477da1d9d4e7c0d75719664f62fec/src/solver/shape.c)
- [S4：xsect.c，断面类型及 A/R/W 查询](https://github.com/USEPA/Stormwater-Management-Model/blob/07c371f8a0d477da1d9d4e7c0d75719664f62fec/src/solver/xsect.c)
- [S5：node.c，storage depth/area/volume 与 outfall stage](https://github.com/USEPA/Stormwater-Management-Model/blob/07c371f8a0d477da1d9d4e7c0d75719664f62fec/src/solver/node.c)
- [S6：output.c，报告期输出、node/link 库存、REAL4](https://github.com/USEPA/Stormwater-Management-Model/blob/07c371f8a0d477da1d9d4e7c0d75719664f62fec/src/solver/output.c)
- [S7：qualrout.c，污染物完全混合与反应](https://github.com/USEPA/Stormwater-Management-Model/blob/07c371f8a0d477da1d9d4e7c0d75719664f62fec/src/solver/qualrout.c)
- [S8：routing.c，外来流与 outfall 逆流污染物输入](https://github.com/USEPA/Stormwater-Management-Model/blob/07c371f8a0d477da1d9d4e7c0d75719664f62fec/src/solver/routing.c)
- [S9：massbal.c，全系统水量/污染物收支](https://github.com/USEPA/Stormwater-Management-Model/blob/07c371f8a0d477da1d9d4e7c0d75719664f62fec/src/solver/massbal.c)
- [S10：objects.h，断面表与 node/link 状态](https://github.com/USEPA/Stormwater-Management-Model/blob/07c371f8a0d477da1d9d4e7c0d75719664f62fec/src/solver/objects.h)
- [S11：link.c，flap gate、局部损失及连接](https://github.com/USEPA/Stormwater-Management-Model/blob/07c371f8a0d477da1d9d4e7c0d75719664f62fec/src/solver/link.c)
- [P1：simulation.py，逐 routing step 与 step_advance](https://github.com/pyswmm/pyswmm/blob/97cb36ff7820ba23ed6c09d9a38551aa619ea88a/pyswmm/simulation.py)
- [P2：nodes.py，volume、generated_inflow、quality、outfall_stage](https://github.com/pyswmm/pyswmm/blob/97cb36ff7820ba23ed6c09d9a38551aa619ea88a/pyswmm/nodes.py)
- [P3：links.py，volume、flow、quality、total_loading](https://github.com/pyswmm/pyswmm/blob/97cb36ff7820ba23ed6c09d9a38551aa619ea88a/pyswmm/links.py)
- [P4：output.py，报告期序列读取](https://github.com/pyswmm/pyswmm/blob/97cb36ff7820ba23ed6c09d9a38551aa619ea88a/pyswmm/output.py)

## 几何与 mixed-flow 接口

| 本项目需求 | 官方实现证据 | 可用范围 / 不能直接替换的部分 |
| --- | --- | --- |
| 真实 open polyline | `xsect.c` 的 IRREGULAR 断面走 transect 几何表；CUSTOM 走 shape 表。[S4] | 可作为显式断面转换路线；不是直接提交任意三角网或多个湿域。必须另核 A/P 与本项目实际边界。 |
| 真实 closed polygon | `shape_validate` 接受 width vs height；`computeShapeTables` 转成等高表；`N_SHAPE_TBL=51`。湿周增量是 `2*sqrt(dy²+(dw/2)²)`，顶端加顶宽。[S3:42–59,117–120,156–170,353–368][S10:646–658] | CUSTOM 可表示某些宽度曲线，但任意不对称/非凸 polygon 的实际左右湿壁长度不能仅由总宽度恢复；源码采用两侧对称梯形增量。即使 A 匹配，P 也未必匹配。不得宣称无损实际多边形支持。 |
| 明渠与压力水头 | conduit momentum 有摩阻、head gradient、惯性/阻尼、局部损失项；满管时还有专门阻尼规则。[S1:195–230] | 比纯扩散库容模型多出动量状态；因此是新模型，不是换一个积分器就保持旧 RHS。不是 3D NS，也不是洞道气液压缩认证。 |
| compliance / pressure slot | `getSlotWidth` 在 SLOT 模式按相对水深使用 Sjoberg 公式，较高水头时变为最大宽的 1%；满顶 area 加 `(y-yFull)*wSlot`。[S1:575–618] | 不是当前固定 slot/compliance 的原样参数映射。EXTRAN 与 SLOT 也不是同一个本构；须明确选项、实际新增存量及转换误差，不能把计算 slot 当成真实 face 开口。 |
| cell V(H) | TABULAR storage 使用深度—面积曲线积分成体积；inverse 也调用 storage depth 查表。[S5:846,930–955,997] | 可离散导入 dV/dH，而非直接注册任意 Python 精确 V(H)/inverse 回调。有限表的积分误差、满深上限、压力段/ponding 语义都要单独核验。 |
| face A(Hu,Hd), P(Hu,Hd) | conduit 求两端及中段深度的 xsect A/R，并使用上游加权与动量方程。[S1:124–152,195–225][S4] | 没有本次检到的公共接口可原样接入 actual-face 双 head 截面、two-sided cap 支持或控制 sill 证据。orifice/weir 转换也改变物理类型，不能借名称跳过几何验收。[S11] |

上表行号用于定位固定源码，不代表我们已证明每一种实际 section 均无法转换。**可否转换要逐实际 section 对比**：至少 floor/crown、A(H)、P(H)、dV/dH、压力存量和两端连接长度；任何拒绝 face 仍拒绝，不得用引擎默认断面覆盖未知。

## 19 库容与 link 存量：不能重复计水

Dynamic Wave 会设置 `Link.newVolume = area * actual_length * barrels`；全系统输出同时累加节点和管段库存。[S1:177,289–291][S6:692–693,932–951] 因此两个可研究的转换互不等价：

1. **conduit 为主**：把实际洞道长度/断面划归管段，节点只保留不重叠的 junction/surface 库容。此时原 19 cell V(H) 不再逐 cell 原样存在，必须重建实际几何体积的唯一归属与转换误差。
2. **storage 为主**：保留 19 storage 库容，但连接件本身可能仍持有存量；必须找到经验证的非重复空间分区。不能将真实长度设为零或任意极小以消除重复而不报告动量/损失变化。

这两个方案是工程推论，依据为 [S1][S5][S6]；**本文不推荐其中任何一个作为现有模型的等价表示**。没有全链 control-sill、有效长度、粗糙度与局部损失证据时，只能标 needs-info；明确的理想工程 n/L/loss 可以组成新身份，但不能提升为自然洞道参数。

## 三来源示踪与双向尾水

- SWMM 对多个污染物分别路由。`qualrout.c` 在 node/link 使用完全混合浓度并可加一阶反应；湿初态使用每个污染物的 `initConcen`。[S7:63–95,146–174,298–351,451–472] 因而三个无衰减、无处理、无额外损失的示踪物可作为来源编码候选；必须明确浓度单位及浓度乘体积到来源水量的转换。**它不是直接积分三个来源体积并令 V=sum 的结构保证**；源码还有浓度上界/混合限制和干小库存处理，不能据此承诺当前 positivity/composition0 门槛。[S7]
- FIXED/TIDAL/TIMESERIES outfall 支持外部 stage；flap gate 可禁止逆流，关闭该限制时负流采用反向 donor。[S5:1413–1458][S11:643–668][S7:195–202] 这可以研究工程 tailwater 双向事件，不能称自然出口。
- 逆流 outfall 的污染物输入不是自动有“尾水来源”。`routing.c` 将旧步 outfall 逆流加入外来流 q，再把配置的浓度乘 q 计入污染物外来质量。[S8:473–493] 因此尾水标签必须显式绑定 outfall 浓度输入并核查时序/一步延迟；只设置 stage 不足以证明尾水 tracer 返回首地表。
- PySWMM 提供实时 volume/quality/stage 访问，也提供设置当前质量状态的接口。[P2][P3] **不能把每步强设库存浓度当成守恒示踪**；那会引入未经配对的质量更新。这是基于 setter 语义的审计要求，不是官方库自动拒绝这种操作。

## 守恒、时间细化与可冷读导出

SWMM 有水量和污染物系统质量平衡统计；Dynamic Wave 的变步长使用 conduit Courant 与 node depth-change 条件。[S9][S2:799–866] 它们支持独立细化实验，但全系统百分比误差不能代替本项目逐 cell/逐 link 的全历史 `1e-4 m³` 门槛。

PySWMM `Simulation.__next__` 可逐 routing step 返回控制；`step_advance(seconds)` **只改变 Python 获得控制的间隔，不改变 solver routing step**。[P1:170,315–322] 真正时间细化须改并保存引擎 routing 参数、版本与实际步长，不能把采样加密叫 solver refinement。

标准二进制输出是报告期序列，包含 node head/volume、link flow/volume 和 pollutant concentration；使用 `REAL4` 状态输出及插值/可选平均。[S6:74–76,147–153,481–483][P4] 因而不能仅靠 `.out` 文件承诺毫米精度和累计账的绝对误差门槛。需要另外保存双精度逐内部步状态/通量和积分区间，并核验公共 API 实际给出的量与时刻。[P1][P2][P3]

`Links.total_loading` 能读 link 累计污染物 loading，但本次未证明它是按正负方向拆分、逐来源成对且与每个 node 账完全对齐的接口。[P3:901][S7][S9] 所以应把以下列为**尚待验证的导出缺口**，而非声称包装器已有完整证明：每内部步 signed water flux、正反向 donor 浓度、配对三来源累计通量、outfall 正反向三来源账、所有 node/link 库存和全部精度参数。自行用粗报告期 Q*C 梯形积分不够。

## 最小可辩护下一步（仅条件建议，未授权执行）

1. 待全部实际 face / two-sided port 独审接受；当前拒绝项不能因 SWMM 支持 mixed-flow 而放行。
2. 单独版本化转换器规范：实际 station/polygon 到 SWMM transect/CUSTOM/storage，明确不可表示的 P、slot、控制 sill 和损失。给逐高程误差表与 node/link 不重叠体积映射，不改原 geometry。
3. 明确是一个新 dynamic-wave 工程模型：引擎 revision、surcharge/inertial-damping、粗糙度/损失、单位、initial filling、stage 与 tracer 边界均形成新身份，不宣称与旧 v5 扩散模型逐字节相同。
4. 只有接口与库存映射达标后才考虑一个有界双向工程样例；先确认双精度逐步导出与来源守恒能被独立冷读。时间细化与失败预算仍保留，不因成熟引擎免除现有门槛。

上述建议由已核主源 [S1–S11][P1–P4] 推导，**不是完成实现/求解/认证的报告**。最重要的节省不是立即换 solver，而是避免继续把“有 pressure/逆流功能”误等同于“无损消费我们的实际库容与双 head face”。
