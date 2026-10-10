# Terrain Diffusion 河网蓝图第一轮交付

按用户指定的根目录《Terraindiffusion河网算法完整实施建议》第九节第一轮 A-F 实施。本轮完成米制契约、原床排水诊断、独立格产流适配及保存包审计；状态为 `diagnostic_runoff`。这不是完整河道水动力，也不是最终自然河网。具体后续任务见 [.scratch 规格](../.scratch/td-river-blueprint/spec.md)。

## 现有能力审计

| 分层 | 已有能力 | 本轮处理与仍开放部分 |
| --- | --- | --- |
| 来源 | `mountain_source_adapter` 的外部 SHA 固定输入、原子保存、资源预算；固定真实 TD 地形与 D4 来源 | 复用固定原始输入，补来源种类、米制矩形格、掩码、模型修订及生成条件；原包缺 CRS，保持 `pending_provenance` |
| 排水 | `surface_rivers/drainage.py` 的 priority flood + D8；`td_basin_hierarchy.py` 的原床 D4 与合并树 | 两者保留。新增原床 D8 显式政策，不填真实洼地；新图不能替代既有 D4 湖盆证据 |
| 产流 | `rainfall_runoff.py` 的入渗、土壤及快慢库、逐格逐区间账本和保存校验 | 新适配器连接原生 `dx*dz`，全区间求解后抽取输出状态；支持固定等长物理区间，拒绝非等长区间 |
| 河道水力 | 已有局部/有界浅水、moment、AMR 和 hybrid 原型，包含历史接受、失败及拒绝证据 | 本轮不重算这些事件。新拓扑累积无旅行时间、无河道储量，不作为完整水力认证 |
| 湖泊 | 已有 D4 储量曲线、spill/storage 等分阶段实现 | 新 D8 图仅识别闭合终端及贡献域，未接入湖位、湿足迹、溢流或湖泊之间传播 |
| 河床几何 | `channel.py/carve_channels`、TD 原生/细床与部分完整端口、三维/地下候选 | 旧接口不变。当前统一新契约下尚无完整连续河床、全端口及自交认证 |
| 泥沙 | morphology、breach、delta、transport 等局部物质账及候选 | 尚无本轮统一时间轴上的河道侵蚀、Exner、湖泊及域外泥沙联合账本 |
| 渲染/发布 | Claude 的动态河网和地下预览改动、历史 review 消费器 | 本轮未修改前端；保留六项渲染审查任务，诊断图不升级为细网格瞬时水面或最终河流 |

## 接口与保存语义

新增 `terrain_pipeline/surface_rivers/metric_contracts.py`：`TerrainGrid`、`BoundaryGrid`、`RainfallForcing`、`RoutingGraph`。数组不可变，单位为米/秒/mm/h/m³/s；`[z,x]`，X 向东、Y 向上、Z 向南，`cell_id=z*nx+x`。无效地形不参与运算；其高程载荷在来源契约中规范为零。

`metric_drainage.py/route_diagnostic` 选择最陡正坡 D8，等高平台向明确种子做确定性 BFS。对角线不得越过 unknown 角点。有效外环必须声明边界；开放、指定水位/流量或 unknown 边界为明确终端；封闭洼地保留为 `lake_preserved`。`lake_id` 表示该终端的贡献域，不表示积水面积。`accumulate_local_discharge` 只作瞬时拓扑求和。

`BoundaryGrid.from_outlet_mask` 为旧掩码提供新类型适配；正通量向域外。`metric_runoff.py/boundary_flux` 仅过滤给定候选通量：open 只出不入，wall 零通量，指定边界仅在 `allow_inflow` 声明时允许负向通量，unknown 非零通量拒绝。这不是边界 Riemann 求解器，也不会用给定 stage 计算水流。

forcing 有 T+1 个 `time_seconds` 区间端点与 T 个区间平均雨强；native 状态有初值和 T 个区间末值。产流 Q 是对应区间平均释放；新图上的 Q 仍是区间平均量的即时累积。固定步长产流要求保存端点的差值严格相等，浮点端点舍入造成不等长时也拒绝。显式 `output_indices` 为递增的 1..T 区间末状态；默认包含初值。输出采样不减少实际求解区间，不改变账本。旧网页的 `state.time === 0`、`signedEdgeQ` 和 `flowInterval()` 语义未由本轮改动。

`metric_product.py` 保存原生地形、forcing、边界、拓扑、完整产流数组、各区间本地产流/累积/终端量及联合账本。冷读检查外部包 SHA/身份、契约身份、D8 邻接、真实边长/坡度、边界终端、湖贡献域、时间语义、认证标志、数组清单和水量；不生成地形、不重建排水图、不重新模拟产流。新图格式为 `terragenesis-river-diagnostic-v1`，算法政策为 `original_bed_d8_plateau_bfs_v1`。

## 实际 TD 证据

最终目录：`verification/td-river-diagnostic/run-20261007T131404530258Z-7321b3a0/`，包含 `product.npz`、`manifest.json`、`provenance.json`、`boundary-audit.json`、`mass-balance.json`、`diagnostics.json`。

- 固定来源：`verification/mountain-real-td/mountain-run-20261001T080705728662Z/primary-source.npz`。
- 来源 SHA-256：`6e7fdf63dc02e9f14e7d83550d0c5f806b42aa7f13367ea96012787bcf069382`，准备前后及独立冷读均相同。
- TD 模型：`xandergos/terrain-diffusion-30m`，修订 `9ef8030cb805b433b98ec25c5dddefbac07a9e26`，seed `20261001`，未重新运行推理。
- 256×256，65,536 有效格，30×30 m/格，面积 58,982,400 m²；完整单元窗口 7.68×7.68 km，节点间跨度 7.65 km。原点 X/Z 为 −184,320/61,440 m。基准保留 `sea_zero_m`，未虚构 CRS。
- forcing `[0,300,600,900]` s，首区间 30 mm/h，其余无雨；复用已有未校准默认水文参数，包括初始土壤 30 mm。参数 hash 和算法版本保存在清单及产品元数据。
- 64,066 条有效 receiver；1,470 个终端，其中工程外环 open 1,020、封闭洼地候选 450；unknown、环、unknown 穿越、隐式开放出口均为 0。此真实来源没有 unknown 格，unknown 行为由解析用例验证。

| 900 s 联合账目 | m³ |
| --- | ---: |
| 降雨输入 | 147456.000000000 |
| 蒸散 | 2211.840000000 |
| 土壤/快慢库净储量增加 | 131370.355345287 |
| 本地释放总量 | 13873.804654713 |
| 工程 open 终端出流 | 848.060019635 |
| 闭合终端累计贡献量 | 13025.744635078 |
| unknown/指定边界待解析量 | 0 |
| 联合残差 | −2.510205376893282e−10 |

`本地释放` 是下游分配的中间量，不能再与 open 和闭合贡献量重复扣减。闭合终端累计贡献量未求解湖泊水位、湖面积或溢出。总残差相对降雨为 1.70e−15；最大逐格产流残差 1.776e−15 m³，最大区间拓扑残差 1.066e−12 m³，最大联合区间残差 1.092e−10 m³。

产品 SHA-256：`86ea0e48f5e442211b07564115ccdccbc5a77ac97759becd7718eb57d747508c`；产品身份：`4293e21a4bc5c5dda640f2f6150a3eb202adf1d2afd62322efbf879505a1b681`。两次成功全域构造的产品 hash/identity 相同；后一包补齐清单字段，未覆盖前一包。

另一个进程核对了四份报告哈希及来源哈希，并在禁止调用 route/build runoff 的条件下完成产品冷读。保存验证不会改变 `hydraulic_ready=false`、`natural_outlet_verified=false`、`publishable=false`；源 CRS 缺失使来源状态继续为 `pending_provenance`。

## 审查与测试

由主协调集成、审查和验收；两名 GPT-6 Sol 子代理实现 D8 与产流/CLI，并做一次独立只读审查，未超过 3 个同时工作的智能体。此前两次 GPT-6 Luna 请求被配置账户以 404 拒绝，按用户后续明确选择换用 Sol。

本轮复现并修复：公共 graph 的非邻接/unknown 角点穿越，面积下溢与坐标范围溢出，NumPy 米制参数不能序列化，非等长区间被近似接受，保存时间/来源能力标志可被重新封装篡改，以及完整 TD 规模下不同求和顺序造成冷读残差误拒绝。汇总修复采用一致的区间分组顺序，未放宽守恒门槛。

首次实际全域运行因上述求和顺序问题拒绝：`verification/td-river-diagnostic/run-20261007T130753154154Z-2a5ed422/refusal.json`。保留该目录，状态 `refused`，没有成品产品。CLI 失败只发布拒绝原因；尚无动态水力求解及其 `failed_prefix`，该能力另列 M3 任务。

验证命令：

```powershell
D:/anaconda/python.exe -X utf8 -m unittest tests.test_metric_river_contracts tests.test_metric_river_drainage tests.test_metric_river_runoff tests.test_metric_river_product tests.test_prepare_td_river_diagnostic tests.test_surface_drainage tests.test_surface_rivers tests.test_rainfall_runoff tests.test_td_basin_source_hierarchy
```

68 项通过，其中新增 24 项；覆盖米制矩形格、平面/平台、Y 汇流、多出口、closed basin、unknown、open 单向及指定边界方向、pulse、水量与输出采样、非等长时间拒绝、输入/结果不变性、确定性、保存篡改与冷读、全域规模账本、CLI 不覆盖及拒绝发布。旧 `route`、`accumulate`、`carve_channels`、`rainfall_runoff` 兼容回归通过，`git diff --check` 通过。未启动服务、GPU、Java 或游戏。

## 诊断预览与复现

三个保存结果预览位于 `verification/td-river-diagnostic-previews/review-20261007-01/`：

- `terrain-and-routing.png`：原床与平均累积 Q 最高 3% 的图边，红点为封闭终端候选。线宽固定，不能当成真实河宽。
- `closed-terminal-catchments.png`：终端贡献域；色彩重复，绝不是湖泊湿足迹。
- `interval-water-ledger.png`：三个真实区间的联合账本，非连续瞬时水力曲线。

```powershell
D:/anaconda/python.exe -X utf8 -m tools.prepare_td_river_diagnostic
D:/anaconda/python.exe -X utf8 -m tools.plot_td_river_diagnostic --input verification/td-river-diagnostic/run-20261007T131404530258Z-7321b3a0 --output verification/td-river-diagnostic-previews/new-review
```

准备入口自动创建独立新目录；预览入口要求未存在的输出目录。M0-M8 的后续验收任务已发布，第一轮 A-F 的完成不表示这些里程碑已经全部完成。
