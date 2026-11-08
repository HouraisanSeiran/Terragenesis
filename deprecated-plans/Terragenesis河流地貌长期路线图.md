# Terragenesis / Terraindiffusion 河流地貌长期路线图

> 文档用途：作为 Terragenesis 河流地貌系统的长期实施计划、架构约束和 GPT 执行清单。
>
> 计划形式：阶段路线图，不承诺具体日历日期。每个阶段以依赖关系、交付物和验收门槛结束。
>
> 覆盖范围：流域产流、支流—主河输运、湖泊、辫状水系、曲流迁移、截弯取直与牛轭湖、泥沙与侵蚀、三角洲、峡谷、悬挑、洞穴、局部三维岩体、Terraindiffusion 条件生成、AMR、多分辨率、前端审查和发布状态。

---

## 0. 总体判断

当前工程不是从零开始实现河流。代码库已经包含多个层级的河网、湖泊、河道几何、动态水动力、泥沙、真实 DEM、大规模处理和审计测试模块。但这些实现处于不同成熟度，存在并行原型、实验性模块、兼容层和诊断输出。

因此，长期工作的首要任务不是继续平行增加文件，而是把已有能力收敛成一条可验证的主线：

```text
现有模块和测试盘点
→ 真实调用链审计
→ 数据契约、单位和时间语义统一
→ 版本与主线冻结
→ 水量账本和边界语义统一
→ 支流—主河输运
→ 湖泊与多分流
→ 泥沙与河床演化
→ 曲流、截弯和牛轭湖
→ 河口与三角洲
→ 峡谷、悬挑和局部三维岩体
→ AMR、多分辨率和发布包
```

当前必须保留的边界：

- `terrain_pipeline/rainfall_runoff.py` 是独立单元产流模块，不是河道输运 solver；其中 `local_q_m3_s` 的语义不能改写成河道流量。
- `surface_rivers.route → accumulate → carve_channels` 是确定性、有界、离线的排水和通道几何原型，不是完整动态河网。
- `real_dem_rainfall_routing.py` 是单向线性储库延迟路由基线，不是 Saint-Venant、回水或自然出口认证器。
- `mountain_lake_coupling.py` 是有限窗口湖泊—河段耦合原型，不能自动认证自然出口。
- `surface_rivers.branches.py` 和 `hydraulics.py` 已有局部分流原型，但只支持有限的一分支分流，不等于一般多分流、再汇流和辫状水系。
- `surface_rivers.delta.py` 和 `transport.py` 已有带守恒和边界门槛的河口泥沙原型，但不是潮汐、波浪、密度流和真实河口地貌 solver。
- 图形界面上的线条、颜色和线宽不能被当作物理河宽、瞬时水面或已认证自然河网。
- Terraindiffusion 负责地形和条件场生成；水量、水动力、泥沙和几何守恒必须由独立物理模块负责。

---

## 1. 目标架构

最终系统应把地形生成、水文、河道水动力、地貌演化、三维岩体和可视化审查分层。推荐数据流：

```text
TerrainSource / Terraindiffusion
        ↓
TerrainGrid + Provenance + ValidMask + BoundaryGrid
        ↓
Rainfall / Snowmelt / Groundwater / Infiltration
        ↓
HydrologyState：本地产流、储量、交换通量
        ↓
RoutingGraph / ReachNetwork / LakeNetwork
        ↓
SurfaceHydraulics：河道储量、水位、流量、分流、回水
        ↓
SedimentState：泥沙通量、粒径、沉积、侵蚀、河床高程
        ↓
MorphologyState：河道迁移、分汊、截弯、牛轭湖、三角洲
        ↓
GeometryState：二维候选几何、断面、峡谷、悬挑、洞穴、局部三维岩体
        ↓
AMR / NativeGrid / RenderGrid
        ↓
Validation + Evidence + Preview + Publishability
```

每个阶段的产物必须使用明确状态：

| 状态 | 含义 | 是否可称最终自然河网 |
|---|---|---|
| `diagnostic` | 诊断排水方向、失败定位或可视化标注 | 否 |
| `candidate` | 候选中心线、通道、河口或几何 | 否 |
| `bounded` | 在显式有限域、边界和假设下闭合 | 否，除非完成对应认证 |
| `validated` | 通过该阶段的守恒、拓扑、边界和几何测试 | 仅限已验证范围 |
| `publishable` | 来源、数值、几何、时间和前端证据完整 | 仅限声明覆盖范围 |
| `unresolved` | 存在无法闭合的水面、边界、拓扑或几何问题 | 否 |

`validated` 和 `publishable` 不能因为渲染效果良好而自动获得。

---

## 2. 现有代码能力盘点

### 2.1 可作为基础主线的代码

| 现有模块 | 当前价值 | 不能越界宣称 |
|---|---|---|
| `surface_rivers/contracts.py` | 有 `GridInput`、路由、累计和产品契约 | 还不是统一的米制全局水动力契约 |
| `surface_rivers/drainage.py` | 优先泛洪、D8、显式 outlet、下游优先 order、守恒累计 | 单 receiver 结构不能表达一般分流和辫状网络 |
| `surface_rivers/channel.py` | 按流量生成通道、限制下切、标记 unresolved、水面修复 | 不是动态河床演化，也不是稳定水动力 |
| `surface_rivers/pipeline.py` | 将路由、累计、切槽、后验证和保存串联 | 主要是离线有界产品，不是长时间河流模拟 |
| `rainfall_runoff.py` | 独立 cell 产流、入渗、土壤和快慢储库、质量平衡 | `local_q_m3_s` 不是河道传输流量 |
| `real_dem_rainfall_routing.py` | 真实 DEM 批量产流和单边线性储库延迟路由 | 不是 Saint-Venant、回水或自然出口证明 |
| `mountain_lake_coupling.py` | 有限窗口湖泊—河段和边界体积记账 | 不能自动证明湖泊拥有自然出口 |
| `surface_rivers/postvalidate.py` | 对漏水和流线断连进行后验证 | 不能修复错误物理，只能拒绝或标记结果 |

### 2.2 已有但应标记为原型或实验的能力

`surface_rivers/branches.py` 能在给定 corridor 和显式局部水力输入时寻找一条侧槽，并按两个通道的 Manning proxy 分配流量。它适合做“局部分流最小案例”，但目前 `max_branches` 只接受 `0` 或 `1`，分支是路径替换式结构，缺少任意图拓扑、动态分流、再汇流时滞、分流稳定性和泥沙反馈。

`surface_rivers/hydraulics.py` 的 `ChannelHydraulics.conveyance()` 是宽矩形断面 Manning 代理，适合参数单元测试和局部比例分配，不应直接命名为完整河道水动力求解器。

`surface_rivers/delta.py` 在 land-to-connected-ocean mouth 上分配有限沉积体积，并对沉积固体量守恒。它明确是局部 morphology prototype，不包含潮汐、波浪、沿岸漂移或外海水位耦合。

`surface_rivers/transport.py` 在显式湿润海洋网格上进行有限步 8 邻域泥沙转移，能够保留 unresolved inventory，并区分沉积和开放边界输出。它不是完整二维泥沙输运方程，也没有粒径分级、临界起动、波流共同作用或海岸线演化。

### 2.3 现有测试说明了什么

现有测试已经覆盖 Y 型汇流、通道下切上限、水面连通、河床单调性、流量合流、分流比例、河口连接、沉积固体守恒、开放边界输出、湖泊—河流连接、动态水动力和多个 metric 级别模块。

这些测试说明工程已有较好的“局部合同测试”基础，但不能自动证明模块已经被主 pipeline 调用。长期计划必须增加调用链测试、版本矩阵测试和端到端证据包测试。

---

## 3. 阶段路线图

## 阶段 0：现有系统清点与主线冻结

### 目标

在新增算法前，确认每个模块究竟是主线实现、兼容层、实验原型、诊断工具还是未接入代码。

### 工作内容

1. 为 `terrain_pipeline`、`surface_rivers`、`metric_*`、`real_dem_*`、`mountain_*`、`dynamic_*` 和 `lake_*` 模块建立能力登记表。
2. 画出真实 import、函数调用和数据流图，不以文件名推断调用关系。
3. 记录每个模块的输入单位、输出单位、时间语义、边界语义、状态字段和 recipe 版本。
4. 找出重复实现：相同功能只选一个主线接口，其余标记 `legacy`、`experimental` 或 `diagnostic`。
5. 建立测试覆盖矩阵：单元测试、合同测试、集成测试、端到端测试、失败案例。
6. 冻结第一条主线，禁止在主线冻结前继续创建平行 river/lake solver。

### 现有代码基础

以 `surface_rivers/contracts.py`、`drainage.py`、`pipeline.py` 为最小离线基线，以 `rainfall_runoff.py` 为产流基线，以现有 metric channel/lake/dynamic 模块为待整合候选，而不是重新实现同名功能。

### 交付物

- 能力登记表、真实调用图和数据流图。
- 主线、实验、诊断和废弃模块清单。
- 统一 recipe 命名规则和测试覆盖矩阵。
- 主线架构决策记录。

### 验收门槛

- 任何标记为主线的模块至少有一个可重复的调用入口。
- 每个主线字段都有单位和时间语义。
- 对重复功能有明确选择，不允许两个模块同时声称唯一真源。
- 未接入模块不得出现在最终发布路径。

### 阻塞条件

若无法说明一个模块的真实调用者、输入输出契约或测试边界，则只能标记为 `experimental` 或 `diagnostic`，不能作为下一阶段依赖。

---

## 阶段 1：统一地形、来源、边界与时间契约

### 目标

建立所有水文和河流模块共同使用的米制数据契约，消除 block、cell、meter、瞬时率、区间平均量混用。

### 核心契约

至少统一以下对象：

```python
TerrainGrid
BoundaryGrid
RainfallForcing
HydrologyState
RoutingGraph
ReachNetwork
LakeNetwork
SedimentState
GeometryState
EvidenceRecord
```

`TerrainGrid` 应包含高程、有效掩码、世界坐标、网格间距、坐标参考、来源类型、来源哈希、垂直基准和 nodata 语义。

`BoundaryGrid` 不应只有 `outlet_mask`，必须区分 `open_outflow`、`closed_wall`、`prescribed_stage`、`prescribed_discharge` 和 `unknown_boundary`，并记录是否允许入流。

时间序列必须区分：`q_instantaneous`、`q_timestep_average`、`volume_interval`、`stage_end_of_interval` 和 `rainfall_interval_average`。前端不能从字段名猜单位。

### 交付物

- 统一 contracts 模块和版本号。
- 单位转换适配层，明确旧 API 的兼容期限。
- provenance、参数哈希、forcing 哈希和随机种子记录。
- 边界账本和时间语义说明。
- 所有保存产品的 schema 版本。

### 验收测试

- 同一个物理场经米制和兼容 block 输入转换后，守恒误差在预设容差内。
- 不同输出帧间隔不会改变区间累计量总和。
- `open_outflow` 永不产生未经声明的倒灌。
- unknown 区域不会被自动接成可靠下游。
- 保存和读取不改变源地形数组。

### 不得宣称

契约统一本身不等于水动力完成，也不等于自然出口认证。

---

## 阶段 2：流域产流与支流—主河输运主线

### 目标

把“本地产流”和“河道输运”正式分开，用同一个水量账本把雨水、融雪、地下水、支流、主河、湖泊和域外出流连接起来。

### 设计原则

- 降雨、融雪、地下水和侧向交换是源项或储库交换。
- 上游支流进入主河后只计入一次，不能把主河再当作独立的同一份降雨源。
- 河道节点储量和 reach 边界通量必须显式保存。
- 允许内部短子步，输出帧只是抽样；不能把输出帧间隔默认成一秒。
- 先实现单向、无回水的 reach solver 作为基线，再增加回水和二维自由水面。

### 实现顺序

1. 从 `rainfall_runoff.py` 输出标准化产流事件和储库交换量。
2. 把 `real_dem_rainfall_routing.py` 的线性储库路由收敛为可替换的 baseline backend。
3. 建立 `ReachNetwork`，支持多 donors、主河和支流边界通量。
4. 增加 reach storage、travel time、端点流量、侧向入流和开放边界账本。
5. 将现有湖泊模块接入同一账本，而不是另建一套水量定义。
6. 为每条边保存方向约定：正流量从 `edges[index][0]` 到 `edges[index][1]`。

### 交付物与验收

- 流域产流—河道输运端到端最小案例。
- 支流汇入主河的动态水量账本。
- 单向线性储库 backend 与未来 hydraulic backend 的统一接口。
- 峰值到达时间、汇流量和边界输出报告。
- Y 型网络中汇合点流量等于 donor 输入加本地侧向输入。
- 河道总水量 + 域外输出 + 未解析储量 = 初始水量 + 源项。
- 输出帧间隔和支流重复计数测试通过。

### 状态门槛

完成后最多标记为 `bounded_validated`。除非边界和真实下游来源通过认证，不得标记 `natural_outlet_verified` 或 `publishable`。

---

## 阶段 3：河道水动力、湖泊、内流盆地与边界耦合

### 目标

把线性路由逐步替换或补充为具有明确适用范围的河道水动力，并正确保留湖泊和内流盆地。

### 实现层级

1. 基线层：线性储库或运动波，用于回归和大规模粗筛。
2. 一维河段层：Manning 断面、连续性方程、可选扩散波或 Saint-Venant backend。
3. 湖泊层：湖面 stage、库容曲线、入流、出流、溢流和内流盆地保留。
4. 局部二维层：只在河口、分汊、回水、洪泛区或关键节点启用。

### 边界语义

- `open_outflow`：只允许从域内流出。
- `closed_wall`：零通量。
- `prescribed_stage`：由外部水位驱动，可允许入流，但必须标记来源。
- `prescribed_discharge`：外部流量边界。
- `unknown_boundary`：不追踪未知下游，只生成候选域外输出并记账。

没有自然出口的洼地必须保留为湖泊、暂时积水盆地或 unresolved 水体。不能为了让河网连通而强行 breach。

### 验收测试

- 静水湖泊保持水平水面且水量守恒。
- 无外部入流的封闭盆地不会凭空出水。
- 单向自由出流边界无负出口通量。
- 河道水面、断面流量和储量在时间上连续。
- uniform 与局部 AMR 在总水量、出口体积和关键断面上满足误差预算。

### 不得宣称

存在 Manning 公式或一维 solver 不等于已经完成回水、洪泛区或自然河口水动力。

---

## 阶段 4：一般分流、辫状水系与河网拓扑

### 目标

从单 receiver 树结构升级为能够表达多下游分流、再汇流、分流比例随时间变化和局部河道竞争的网络。

当前 `drainage.py` 的单 receiver 图适合诊断排水和树状汇流，但辫状水系需要有向多边图：一个节点可以有多个 downstream edges，一个 edge 可以有独立储量、输沙量和几何状态。

主线应建立 `ReachNode`、`ReachEdge`、`SplitJunction`、`RejoinJunction`、`FloodplainExchange` 和 `BranchAllocation`。分流比例至少受到水位、坡降、断面、糙率、河床高程、局部阻力和泥沙状态影响，而不是只由静态宽度决定。

### 实现顺序

1. 将单主槽和一条侧槽测试提升为一般 edge graph。
2. 为 junction 增加输入、输出、储量和分配规则。
3. 增加多分流、再汇流和分流关闭／重启。
4. 加入河床和泥沙反馈，防止分流仅是视觉复制。
5. 建立 braid index、活跃分汊数、再汇流率和分流稳定性指标。

### 验收测试

- 一个节点三条出口时总出流等于可用入流。
- 分流后再汇流时网络总水量和总泥沙量守恒。
- 关闭一条支汊时其水量不会继续泄漏到失效边。
- 分辨率变化不会凭空增加或消灭总河流量。
- 分流图无非法环；回水环必须由专门水动力 solver 处理。

完成一般分流守恒后可标记 `braided_candidate`；完成动态稳定性、泥沙反馈和几何连贯性后才可标记 `braided_validated`。

---

## 阶段 5：泥沙、侵蚀与河床演化

### 目标

建立独立于可视化的泥沙账本，让河道变化由输水、输沙、沉积和侵蚀共同决定。

### 组成

- 坡面侵蚀与河道侵蚀分开。
- 细颗粒、砂、砾石至少在接口上支持分组；初版可以只实现单粒径。
- 每条 reach 保存上游泥沙输入、本地产沙、沉积量、侵蚀量、输出量和未解析量。
- 河床高程变化使用 Exner 类更新或明确的离散替代，并与水量 solver 时间步协调。
- 沉积体积使用孔隙率转换，固体体积和占据体积不能混用。

`surface_rivers/transport.py` 的守恒、开放边界和 unresolved inventory 测试可作为局部 contract baseline；`delta.py` 的口门沉积容量测试可作为河口几何 baseline。主线必须将两者接入统一 `SedimentState` 和 `SedimentBudget`。

### 验收测试

- 固体泥沙输入 = 沉积 + 域外输出 + 活动库存 + unresolved 库存。
- 孔隙率变化不会破坏固体体积守恒。
- 河床侵蚀不超过材料或几何允许的上限。
- 地形更新、通道水面和河流连通性保持一致。
- 关闭泥沙过程时，水动力结果回归无形态变化基线。

有沉积高度图不等于完成泥沙输运；没有粒径、边界和未解析库存时必须标记为 `morphology_candidate`。

---

## 阶段 6：曲流迁移、截弯取直与牛轭湖

### 目标

把河道平面形态从静态中心线升级为随时间变化的河道迁移和拓扑事件。

曲流迁移是河岸侵蚀、内弯沉积、流量、水位和局部曲率共同作用的结果。截弯取直是拓扑事件，不是简单删除旧中心线。被切断的旧河段应保留为牛轭湖或湿地候选，并拥有自己的 stage、库容、交换通量和沉积状态。

每次截弯必须记录发生时间、触发指标、旧边、新边、被保留湖泊几何和水量转移；河道迁移不能仅通过中心线平滑或随机扰动伪造。

### 实现顺序

1. 静态曲流中心线和断面参数。
2. 曲率相关的外弯侵蚀和内弯沉积。
3. 河岸迁移和洪泛区交换。
4. 由颈部距离、局部高程和流量阈值触发 cutoff / avulsion。
5. 旧河段转为 `oxbow_lake_candidate` 并继续水量、泥沙记账。
6. 事件回放和拓扑版本号。

### 验收测试

- 曲流迁移不破坏水量和泥沙账本。
- 截弯前后的主河连通性正确。
- 旧河段不会被无声删除。
- 牛轭湖关闭、补水、溢流和沉积状态可复现。
- 相同输入和随机种子产生相同事件序列。

规则触发且无物理反馈时标记 `meander_prototype`；完成事件账本和守恒后标记 `oxbow_validated_bounded`。

---

## 阶段 7：河口、三角洲与接收水体耦合

### 目标

建立河流进入海洋、湖泊或大型接收水体时的水动力和泥沙耦合，不把三角洲简化成一团颜色或固定沉积扇。

至少区分陆地与连接的接收水体、口门和多个 distributary mouths、接收水体 stage 和深度、河流输入水量、各粒径泥沙通量、沉积、再悬浮、域外输出、未解析库存以及三角洲前缘和陆地面积变化。

`deposit_delta()` 适合作为“单口门、连接海洋、有限沉积容量”的 contract；`route_sediment()` 适合作为局部运输 contract。主线必须将两者接入动态河口 network，并明确暂时不包含波浪、潮汐、沿岸流和密度流。

### 实现顺序

1. 单口门、静态接收水位和固体守恒。
2. 多分流口门和分流竞争。
3. 接收水体水位变化、潮汐或外部 stage 边界。
4. 沿岸搬运、再悬浮和河口前缘推进。
5. 三角洲叶瓣切换和分汊退化。

### 验收测试

- land 与 ocean mask 不重叠，且口门属于与外部边界连通的接收水体。
- 沉积固体输入 = 局地沉积 + 输出 + 活动库存。
- 内部孤立水体不会被误判为海洋。
- 水位边界改变时，输入、回流和外排语义显式变化。
- 多口门分流不产生凭空泥沙。

只有河流到达 ocean mask 并产生 height delta，不能称为真实三角洲。

---

## 阶段 8：峡谷、悬挑和局部三维岩体

### 目标

将二维地表河网与局部三维岩体几何连接，表达峡谷切割、河岸掏蚀、悬挑、洞口和地下通道，同时避免把高度场伪装成立体洞穴。

### 几何分层

1. 二维地表层：高程、河床、洪泛区和候选中心线。
2. 断面层：沿河断面、岸坡、岩性、稳定性和侵蚀上限。
3. 局部三维层：峡谷壁、悬挑底面、洞顶、洞底、侧壁和入口出口。
4. 封闭体层：用于体积审计、自交检查、开挖和移除体积一致性。

VDM 可以表达表面细节、洞口附近岩壁形变和局部视觉层，但不能单独表达真正洞腔拓扑、悬空内壁或同一水平位置的洞顶与洞底。真正洞穴应使用体素、SDF、局部三维网格或等价封闭体积表示。

### 实现顺序

1. 从河床剖面和岩性场生成峡谷断面候选。
2. 用侵蚀和稳定性规则生成岸壁退缩与悬挑候选。
3. 对悬挑进行支撑、厚度、底面和自交检查。
4. 设计洞穴入口—出口—压力边界和地下水交换接口。
5. 生成闭合三维岩体，审计洞顶、洞底、侧壁、开挖体积和移除体积。
6. 将地表河网、地下通道和入口出口接入统一水量账本，但不强行把地下流路塞入二维 surface receiver graph。

### 验收测试

- 悬挑几何有明确底面、支撑或稳定性状态。
- 三维岩体无自交或被标记为 unresolved。
- 洞穴封闭体积与开挖／移除体积一致。
- 入口出口与地表河网连通关系可追踪。
- 地表水量和地下水量分账后总账仍守恒。
- VDM 只作为 visual/detail layer，不被报告为洞穴拓扑证明。

局部三维网格在通过体积和自交审计前只能标记 `geometry_candidate`；通过后也只对该局部几何范围标记 `validated`，不自动提升整个河网状态。

---

## 阶段 9：Terraindiffusion 条件生成与河流反馈

### 目标

明确 Terraindiffusion 与物理河流模型的职责边界，并建立可重复的条件地形生成—物理验证闭环。

Terraindiffusion 可以生成或修复地形高程、岩性条件场、降雨先验、侵蚀敏感性、河流走廊先验和多尺度地形细节。它不能代替水量守恒、水动力稳定性、泥沙守恒、边界条件或地下几何审计。

推荐闭环：

```text
条件输入
→ Terraindiffusion 生成 terrain candidate
→ 来源与质量检查
→ Hydrology / Hydraulics / Sediment 求解
→ 误差和约束反馈
→ 只更新允许的条件变量
→ 重新求解和比较证据
```

生成地形必须使用 `generated_terrain` 或 `conditioned_terrain`。只有来源链明确来自测绘资料，才使用 `observed_dem`。

### 验收测试

- 相同 seed、模型版本和条件摘要可复现生成结果。
- 生成地形进入水动力前通过有效掩码、坡度、洼地和边界检查。
- 物理求解器可以拒绝不满足边界或守恒的生成结果。
- 生成模型不能通过修改报告字段把 candidate 变成 publishable。
- observed 与 generated 的来源标记在保存、前端和报告中保持一致。

---

## 阶段 10：AMR、多分辨率、前端审查与发布包

### 目标

在物理主线稳定后增加局部高分辨率、跨尺度比较、可视化证据和发布门槛。

### AMR 和原生网格规则

- 原生网格是水体积和全域账本基准。
- AMR 是局部高精度对照，不自动是真值。
- uniform 结果保留为失败对照和数值偏差基线。
- AMR 必须报告细化区域、细化比、限制器、边界通量和与原生网格的体积差。
- 视觉水面重构必须保存原生水量、重构水量、差值和守恒修正状态。

### 前端图层语义

当前 `river-renderer.js` 的分层方向应继续保持：诊断排水拓扑、候选河流中心线、有界诊断河床几何、保存水面／水位、湿润层（若保存）、unknown／孔洞和来源 footprint。

拓扑边必须绘制在床面投影上，不能伪装成细网格瞬时水面。线宽只表示显示样式，不能默认为物理河宽。`signedEdgeQ` 必须使用 payload 明确的单位和时间语义，不能默认写成 `m3/s`。

### 发布包必须包含

- 输入地形和来源登记。
- forcing、参数和随机种子哈希。
- 物理时间、solver 子步和输出帧时间。
- 水量、泥沙、边界和 unresolved 账本。
- 河网拓扑版本和几何版本。
- uniform / AMR 对照结果。
- 验收测试摘要。
- diagnostic、candidate、bounded、validated、publishable 状态。
- 前端 review record 和图层语义。

以下任一项失败，结果都不能标记 `publishable`：来源不明、时间语义不明、边界倒灌、质量不守恒、泥沙库存丢失、unknown 被伪装成已知下游、三维几何自交、保存水面无法解释或前端层级混淆。

---

## 4. 跨阶段验收矩阵

| 类别 | 最低验收问题 |
|---|---|
| 来源 | 输入是 generated、conditioned 还是 observed？哈希和坐标是否可追溯？ |
| 水量 | 初始量 + 源项 = 储量 + 出流 + 未解析量吗？ |
| 泥沙 | 固体输入 = 沉积 + 输出 + 活动库存 + unresolved 吗？ |
| 边界 | open outflow 是否禁止倒灌？unknown 是否没有被自动延伸？ |
| 拓扑 | 分流、再汇流、湖泊和牛轭湖的图版本是否一致？ |
| 时间 | 字段是瞬时值、时间平均值、区间累计量还是末态？ |
| 几何 | 通道、水面、峡谷、悬挑和洞穴是否具有各自可审计的表示？ |
| 多分辨率 | AMR 与 native/uniform 的体积、流量和关键断面误差是否在预算内？ |
| 可视化 | 图层是否明确区分诊断、候选、保存证据和认证结果？ |
| 可复现 | 参数、forcing、模型版本和随机种子是否足以重放？ |

---

## 5. 推荐的测试组织

### 合同测试

测试每个数据结构的维度、单位、有限性、掩码和边界规则。合同测试不依赖复杂场景，失败时应能指出字段级错误。

### 物理守恒测试

使用 Y 型汇流、封闭湖泊、单向开放边界、泥沙沉积、分流—再汇流、三角洲口门和地下洞穴体积作为固定案例。每个案例都应输出机器可读的 budget。

### 拓扑事件测试

为分流、再汇流、河道迁移、截弯、牛轭湖生成、湖泊转河段和三角洲分汊建立事件前后图版本比较。

### 失败测试

必须主动测试：深坑无法在 incision cap 内解决、无自然出口、unknown 下游、断裂河床、非法回水、负开放边界通量、泥沙库存无法归属、AMR 接缝不守恒和三维几何自交。

### 端到端测试

端到端测试必须从 TerrainGrid 和 forcing 开始，经过 hydrology、network、hydraulics、sediment、geometry、save，再由 preview 读取。只测试单个函数不能证明主线接通。

---

## 6. 建议的状态和命名规范

推荐 metadata 至少包含：

```json
{
  "recipe": "...",
  "schema": "...",
  "status": "diagnostic|candidate|bounded|validated|publishable|unresolved",
  "diagnostic_only": true,
  "hydraulic_ready": false,
  "natural_outlet_verified": false,
  "artificial_boundary_outlet": false,
  "water_surface_source": "...",
  "discharge_semantics": "...",
  "unknown_semantics": "未知域外不追踪；仅记录域外出流",
  "complete_water_surface": false,
  "unresolved_cells": 0,
  "source_sha256": "...",
  "forcing_sha256": "...",
  "parameter_sha256": "...",
  "random_seed": null
}
```

禁止以下命名捷径：把 generated terrain 称为实测 DEM；把 receiver graph 称为最终自然河网；把 local runoff 称为主河流量；把保存水面投影称为细网格瞬时水面；把一条侧槽称为完整辫状水系；把固定口门沉积称为真实三角洲；把 VDM 表面位移称为完整洞穴；把有限窗口出流称为自然海口认证。

---

## 7. 交给 GPT 的执行提示词

```text
你正在维护 Terragenesis 的河流地貌系统。不要从零平行创建新的 river/lake solver。先读取并登记现有 terrain_pipeline、surface_rivers、metric、real_dem、mountain、dynamic 和 tests 模块，建立真实调用图和能力矩阵。

严格遵守以下边界：
1. rainfall_runoff.py 只负责独立 cell 产流和水量守恒，不把 local_q_m3_s 当河道流量。
2. surface_rivers.route/accumulate/carve_channels 是有界离线基线，不称完整动态河网。
3. real_dem_rainfall_routing.py 是线性储库延迟路由，不称 Saint-Venant、回水或自然出口认证。
4. 单 receiver 树不能表达一般辫状水系；主线需要有向多边 reach graph。
5. 分流、湖泊、牛轭湖、三角洲、峡谷、悬挑和洞穴必须使用各自的数据契约和状态。
6. 原生网格负责水量体积账本；AMR 是局部对照，不是自动真值。
7. open_outflow 禁止倒灌；unknown 不向外追踪；内流盆地保留为湖泊。
8. VDM 不能单独表达真正洞穴；洞穴和悬挑需要局部三维封闭几何。
9. 所有流量、体积、水面和泥沙字段必须说明单位和时间语义。
10. 每个阶段先写测试和失败案例，再实现代码；不得以渲染图代替物理验收。

执行顺序：
现有能力清点 → 契约统一 → 水量账本 → 支流/主河输运 → 湖泊/边界 → 一般分流和辫状 → 泥沙/侵蚀 → 曲流/牛轭湖 → 三角洲 → 峡谷/悬挑/洞穴 → AMR/前端/发布。

每次改动都必须说明：使用了哪些现有模块、为何不是重复实现、输入输出契约、守恒预算、失败状态、测试命令和仍不能宣称的能力。
```

---

## 8. 最终建议

最稳妥的长期路线不是一次性追求“所有自然现象”，而是先把已有模块收敛为一条能反复运行、能保存证据、能解释失败的主线。河流的总流量必须由流域源项和上游网络共同形成；辫状水系需要多分流图；牛轭湖需要保留旧河段并进行湖泊耦合；三角洲需要接收水体和泥沙边界；峡谷、悬挑和洞穴需要从二维河网进入局部三维岩体层。

当一个阶段只完成视觉候选时，就明确标记为 `candidate`。当它在有限边界内守恒时，标记为 `bounded`。当它通过该阶段的拓扑、物理和几何测试时，才提升为 `validated`。只有来源、时间、边界、保存证据和前端语义全部完整，才考虑 `publishable`。
