# Terragenesis 工程实现说明

更新时间：2026-10-23。本文回答“具体用什么模块、怎样实现、如何验证”，不是替代四阶段计划，也不把设计写成现状。逐文件职责与依赖见[模块台账](module-catalog/README.md)；总体范围见[四阶段总览](../terrain-diffusion-four-stage-roadmap.md)，详细组成见[R/G/V工作表](../../.scratch/terrain-four-stage-review-20261021/algorithm-components-review.md)。

## 1. 实现与设计的分界

| 标记 | 本文含义 |
| --- | --- |
| 现有入口/模块 | 已核对源码入口存在；不等于目标世界端到端认证 |
| 有界/候选 | 在明确输入、范围和参数下计算或验证，不外推完整自然过程 |
| 后续实现 | 必须依规格、依赖和预算另行实现/验收，不能靠调用名称授予能力 |

原始TD输入不可变，修正床面、材料和三维几何另存并绑定父身份。来源、算法版本、schema、参数、坐标/单位、时间、有效/unknown和能力声明分开保存。Python承担地形算法；Java/Mod在前三阶段成熟后转换消费。

当前已完成若干有限账本、几何和水动力链，但还没有一个完成全部四阶段的世界入口。`production_default_consumer_unvalidated`仅说明用户选择了显式发布CLI，不表示无限世界自动调度或publishable。

## 2. 共同实现方式

| 责任 | 简要方法 | 落地要求 |
| --- | --- | --- |
| 随机/时空输入 | 项目共用 `WORLD_SEED` 见 [CONTRIBUTING.md](../../CONTRIBUTING.md#共用世界种子用户更新2026-11-03)，以稳定用途名派生固定子种子；绝对坐标和明确物理时间采样 | 记录派生法/实际值；旧冻结来源按原种子复验，新种子产生独立来源；不用系统熵、时间、内置hash或加载顺序决定结果 |
| 数据契约 | ndarray批量字段、明确类型的参数/返回对象；契约入口拒绝非法值、缺输入与越预算 | `metric_contracts`等现有契约优先；不再造第二套同名账本 |
| 共享状态 | 公共字段只读复用，过程返回变化量/候选状态，由指定流程统一提交 | 每份水/沙/岩石/能量源只计一次；有状态过程明确初末库存 |
| 时间层级 | 地质塑形、长期地貌、季节状态、单次事件分别声明初始化/演化语义 | 不混用物理秒、离线步与游戏tick；长期等效规则不能冒充逐时物理解 |
| 调度/反馈（后续统一） | 显式依赖图与有上限的反馈迭代；小步联合求解与职责边界分离 | 设停止/拒绝条件、版本和状态所有者，不允许模块循环覆盖同一数组 |
| 效率 | 单进程轻量职责模块、批量数值内核、已验证热点编译/融合与有身份缓存 | 不为R/G/V每编号创建服务、进程或逐格对象；完整校验在IO/提交边界，内循环保留安全门 |
| 贡献/成本 | 同输入同种子启停对照，记录变化、阈值、长期累计和间接效应及冷/热缓存成本 | 不以“暂不可见”删除过程，也不为凑模块强行制造可见影响 |

统一调度是实现约束与后续工作，并不声称当前所有专题已接入同一个调度器。

## 3. 第一阶段：来源、完整水系与河网

### 3.1 基础来源（R1）

现有 `diffusion/backend.py:TerrainDiffusionBackend` 包装固定上游 `WorldPipeline`，通过 `GenerationConfig.identity()` 记录生成身份；`generate(seed,x,z,size)`获取高程与气候通道，返回原生分辨率和来源元数据。已实现的自定义条件是高程、温度、温差、降水及季节变化等明确通道，不假设模型已理解任意河谷/岩性标签。CUDA不可用时按配置拒绝，不静默改成程序化地形冒充原模型。

后续河网生成测试严格以30 m TD**生成地形**为基准，不称实测DEM。旧10 km规划条件场与账本仍为其原有诊断，分辨率转换不是简单放大数组或把原总供沙集中到细格；需重新核对来源、面积、出口、汇水和水沙身份。模型调用需要明确运行预算，本文不启动推理。

### 3.2 水系规划与域产品（R2–R4/R9）

现有链：

```text
显式seed/世界坐标
 → PlanningConfig / metric_domain_closure
 → outlet_at / territory_of / 有界拒绝
 → metric_domain_pipeline.resolve_domain_products
 → 按出口去重的域产品、逐点拒绝、索引
 → load_domain_product 冷读身份核对
```

`tools/generate_river_domains.py`是域产品显式CLI：`--seed`、重复的`--point X Z`、`--output-dir`、`--spacing-m`和`--report`。不提供output-dir是内存构建/可选报告，不是“不计算”；合法拒绝与非法输入退出码分别处理。它不是水动力入口，也不能用`--spacing-m 30`就证明粗规划已变成真实TD水系。

目标规划单位是一条完整干流水系及汇水范围，支流共享域对象；瓦片只作存储/计算块。现有固定core+margin方法不证明任意无限流域闭合。大域可有界分解为子流域/河段或粗远场＋30 m走廊，但必须交接侧向水沙、库存、时间与误差；有回水需额外水头/边界耦合。超过依赖/资源预算明确拒绝，不靠无限追踪补齐。

### 3.3 产流到水沙账本（R5/R8）

现有显式发布链由 `tools/publish_domain_bundle.py:run` 组装：

```text
check_domain_closed（先检查点选域，失败不发布）
 → resolve_domain_products
 → solve_domain_flow / solve_domain_sediment / solve_domain_coupled
 → solve_domain_bed_feedback
 → 保存各产品并冷读重算身份
 → bundle.json（角色、选域范围、附带未验证域、claims与limitations）
```

该工具确有 `--seed`、`--point X Z`、`--rain-mm-h`、`--dt-s`、`--intervals`、`--output-dir`；本快照记录的旧代码默认seed为20261020，不代表2026-11-03更新后的项目共用种子。新正式运行须显式传入共用种子并核对产物，固定旧来源入口另行接线。flow与coupled共享同一产流水文参数对象。既有账本按tile保存、域产品按outlet保存，不能把包内未选域认证为完整tile；索引的范围与claims必须保留。

方法上水桶核对降水、入渗/初末土壤、快慢释放与ET；局地释放不是河道Q。coupled使用声明的宽深关系、剪切与输沙容量限制起动，并按有限来源/输出/库存分账。既有床变反馈将固体按声明空间规则转派生床面，只作一次孔隙换算；不自动重算水力或认证沿程沉积。

后续补链：区分超渗、蓄满、壤中流/基流；R8按沿程来沙/容量/沉速和实际活动几何沉积，不把常数比例当自然落点；G9风化/G10坡面输送/G11地下水以显式源与交换接入，不能重复供沙/计水。

### 3.4 河槽、湖泊与水动力（R6–R8）

| 对应模块 | 已有方法与边界 | 后续接线/验证 |
| --- | --- | --- |
| `metric_channel_geometry`等几何层 | 连续中心线、canonical fan4床面、共享端口及切深/材料约束 | 30 m宽河须横向展开，多格岸坡；窄河需亚网格断面/有预算细化，不能只切D8骨架一格 |
| `metric_channel_solver` / `metric_channel_state` | 有界DAG河道库存、Manning基线传播、CFL与failed_prefix | 地形坡/床坡/水力能坡分开；不把Manning本身称完整回水 |
| `metric_lake_storage` / `metric_lake_channel_coupling` | 有限库容—水位、面积、湖河端口与边界交换 | 洼地按库容、来水/损失、可证鞍部判断溢流；不自动填洼或永久终止所有30 m低点 |
| `metric_domain_channel_hydraulics` | 区间土壤释水驱动有限域原床运动波候选 | 原床验证不代表已消费R6切槽床；切槽/床变后须重验 |
| `metric_sediment` / `metric_bed_update` / `metric_morphology_coupling` | 有限泥沙库存、剪切容量、侵蚀/沉积、Exner换算与受影响重耦合 | 固体/bulk/岩石区分，源耗尽/零水零沙合法；几何/水力/湖河端口重新核对 |

入口与每个符号的全量文件位置在模块表，不将以上不同范围的模块拼成已经运行的完整世界链。分流再汇流、截弯/牛轭湖等事件需保存新旧拓扑、库存迁移和重验；不能只删除旧线。

### 3.5 当前FV增长族的方法与调用

```text
run_natural_fv_growth.py → run_natural_fv_growth_v4
 → natural_fv_growth_scheduler（trial/chunk提交）
 → natural_fv_growth_interval（forcing与packet）
 → metric_fv_growth_coupling_v4（显式算子装配）
 → metric_fv_growth_core + 床载/悬沙/交换/水动力内核
 → natural_fv_growth_state_io（current CP真实闭包、参数/库存校验）
```

current CLI仍需明确的完整`--resume`检查点和输出，不自动把旧CP换标签。公共步进保持床载→坡移→悬沙→交换→床变/水场联合提交顺序；载体限制约束同向净水转移，未表示完整振荡波驱动逆向输沙。拒绝trial不消费源cursor/额度，完整chunk后才提交；wall预算到达保留可读的最后提交点，不写成功summary。

v4原算法到重构v4按同父同chunk数值等价；v2/v3升级v4是显式物理升级，单列来源和参数。旧完整增长/runner从活跃路径隔离，通过 `tools/replay_natural_fv_growth_legacy.py`及可信源码/参数模板pin复验，不默认fallback。该族结构迁移通过不等于自然三角洲露陆、持续分汊或整体形态认证。

## 4. 第二阶段：环境、物源与生态（G1–G20）

G9–G20已获用户范围批准；范围批准不是每项已实现，也不是必须并行启动全部高成本求解。按下表逐模块立契约，并复用已有字段，不为概念再建独立守恒真源。

| 工作域 | 方法摘要 | 当前基础与待完成 |
| --- | --- | --- |
| G1/G2 地形背景、岩性/层序 | 区域合成背景及材料端元；抗蚀/强度、可溶性、渗透性、节理分别声明 | 已有解析背景/材料厚度代理，不能据此冒称板块或真实地层 |
| G3/G4/G8 温度、风、水汽/海洋 | 多尺度背景＋地形修正，有限水汽来源/耗竭/补给及相容风温雨条件 | `metric_climate_refinement`有v2诊断；与生产季节水文同源接线仍需验证，洋流不可随机贴标签 |
| G5/G6 水分与土壤/植被 | 时段水桶记录储量、ET、产流与交换；植被覆盖/功能型/根系、糙率和ET作用明确 | `metric_soil_condition`可用水是代理，不是ET后真实含水；Budyko仅长期平均对照 |
| G7/G12 雪冰与冻土 | 降水相态、SWE、积累消融与热状态按适用层级；冰川另需多年平衡/运动 | 冻结高程掩码不能代替积雪或冰川；不把温度条件自动转成融水输入 |
| G9/G10/G11 物源/坡移/地下水 | 有限风化库存、条件失稳搬运、补给/基流/漏失及交换账 | 优先支撑R5/R8与地下形态；代理和原型不能冒充自然含水层 |
| G13–G20 其余扩展 | 风成、辐射、演替、土壤化学、域迁移、火山、海岸动力、栖息地按过程尺度分批 | 每项区分显式计算、等效累计、条件触发或有依据简化；量纲、源项和启停贡献先验收 |

关键验收是同一(seed,x,z,time)的地形→温雨→水土→产流/生态联合输出与真实消费者，而不是16档群系分类可达。参见[环境依赖矩阵](../terrain-geography-dependency-matrix.md)。

## 5. 第三阶段：局部三维实体（V1–V8）

现有 `hybrid_rock_boolean` / `hybrid_cave_geometry` 提供局部实体、Manifold网格与体积保存，`special_terrain_l1_*`和`special_terrain_pillars3d`提供离线形态。VDM表达表面位移；洞顶/洞底共存及空腔拓扑需要体积/网格，不由单值高度图证明。

方法：先明确影响范围、所有权、材料/空腔优先级与TD/已发布河床接缝，再构造局部solid/cutter，保存before/after/removed与体积账；端口用明确局部坐标与完整接口证据检查，不能只看图。岩溶需可溶岩、地下水分带/历史基准面；流向验总水头与损失，不强制每段洞底下降。悬挑区分河流侧蚀与风化等机制，顶板厚度结合跨度、节理和支撑，未算岩石力学只称设计约束。

几何当前集成链：`prepare_hybrid_geometry_current`调用无版本prism/材料/Boolean公共职责和最新rational slice/portal，保存阶段再独立audit/faces。**G2仍blocked**：派生blocked域精确非零而显示面积0，strict reader拒绝；run02–04为refused，不能忽略微小域或放宽门。四个旧mesh/faces/composition内核因此保留，历史source hash路径还须明确隔离。此链不是完成全部三维世界集成。

断层族已抽common并只用v2当前生成，旧v1完整复验显式归档；浅水v4/v8旧薄入口亦已隔离。其余带版本数字的文件可能是公共内核、codec或不同模型，按[版本收敛执行表](../../.scratch/module-version-consolidation-20261022/plan.md)验证后退休，不按编号删除。

三维每类分别验局部几何/材料、同坐标与跨窗联合结果、消费者读取。已通过水平截面或体积不等于整体无自交；地下几何连通不等于地下水力完成。参见[形态接入门槛](../terrain-non-heightfield-landforms-inventory.md)。

## 6. 第四阶段：Java/Minecraft转换（后置）

`src/main/`及`src/test/`有既有Mod代码，台账登记它们的消费/测试角色，不因有代码而宣称新Python世界已接入。前三阶段拟交付范围成熟后才启动新一轮转换：读取完成的Python包→核对来源/单位→坐标和材质/群系映射→空腔/水体体素化→区块写入/重载。

验收依据实际米—方块比例、体素算法和连通规则，分别检查薄壁/洞顶、微坡水面台阶、跨区块断流/穿孔及性能；不假定1方块=1m或固定3m厚度能保证拓扑。Java不在单区块中重新决定完整河网。

## 7. 新增/修改模块的最小工作流

1. 在四阶段R/G/V任务中写清职责、输入/输出、方法/假设、单位、依赖和状态所有权；查台账避免重复实现。
2. 写固定种子的小案例及反例，定义守恒/来源/资源门；修改公开符号前查实际调用方。
3. 复用现有契约与数值函数，存储版本和算法身份分别变更；重构不夹带调参。
4. 运行目标回归，保存阶段/失败前缀；独立冷读重算关键量、父身份和能力声明，不能仅验证hash。
5. 有规模证据后才做目标发布/消费者验证；分别报告计算规则、联合观察与消费者接线。
6. 更新 `module-catalog/annotations.json` 中人工职责，运行生成器`--write`，再`--check`；更新本文对应方法/入口与软件执行树，不改写旧验收证据。

## 8. 管理与证据入口

- [逐文件职责管理表](module-catalog/README.md)：完整路径、说明来源、角色、阶段、符号和静态本地依赖；未审定项显式标记，静态零调用者不等于可删。
- [河网职责分类](river-module-classification-20261009.md)：历史基准分类与禁止重复实现规则，当前状态以更新的总览/契约为准。
- [四阶段总览](../terrain-diffusion-four-stage-roadmap.md)与[详细组成表](../../.scratch/terrain-four-stage-review-20261021/algorithm-components-review.md)：工作范围与当前缺口。
- [版本收敛计划](../../.scratch/module-version-consolidation-20261022/plan.md)、[FV迁移报告](../../.scratch/module-version-consolidation-20261022/fv-recovery-implementation.md)、[几何阻塞报告](../../.scratch/module-version-consolidation-20261022/geometry-recovery-report.md)。

本文不创建新服务、算法或默认自动调度，也不替代各族契约；源码若发生变化，入口和方法需随台账检查同步维护。
