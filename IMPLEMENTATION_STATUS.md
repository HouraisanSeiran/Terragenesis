# 实现状态（2026-09-28）

## 0.14.0 治理与网页预览候选（2026-09-29）

本轮将模式选择、预检和生成器合法组合校验接到 `TerrainModeRegistry`；派生来源区分显式区域准备与只读查询，同区准备合并，重计算不占缓存锁。瓦片缓存满载时等待、失败可重试、关闭结束等待。旧原始来源的隐式推理、跨进程写入锁和取消推理仍属后续事项。

地貌处理拆为特征测量、连续分类、海岸/峰值保护和分区融合。三个真实样本的派生高度、四类权重和主导分类与拆分前逐值相同，9 份原始/派生基线摘要不变。海面 Y62 与垂直 VDM 配方均未修改。并发、模式、派生存储及地貌回归通过，详见 `verification/governance/回归记录.md`。

真实模型低地样本通过生产 `.rmraw` → `.rmd` 流程准备有限区域，625 个网格点与处理器基准对应；相邻成品同坐标边缘一致；Minecraft 原版草方块、空气、基岩映射及离线重载高度检查通过。夹具采用真实高度、固定测试气候和无水条件，通过反射绑定来源到 `Terrain`；不是完整 `RemoteGenerator` 区块生成/存档验证，也未验证海岸水面。来源记录见 `verification/real-import/provenance.json`。

`web-preview` 已提供本机样本预览，包含三维旋转缩放、二维坐标查询、原始/处理后高度、主导地貌、四类权重和高度改变量。浏览器交互复测通过，无页面脚本错误。数据每 8 方块展示（原数据每 2 方块），XYZ 同比例；没有运行模型或修改游戏。启动见 `web-preview/README.md`，截图见 `verification/governance/web-preview-final.png` 和 `web-preview-mountain.png`。这仍是有限样本高度场预览，不是游戏截图。

候选测试包 `build/libs/Terragenesis-26.3-0.14.0.jar` 已从独立空编译目录构建，最终全套回归通过；Minecraft 26.3 / Fabric 0.19.5 的 CreateWorldScreen 与 Minecraft 类转换通过。文件大小 3,165,781 字节，SHA-256 为 `A4FCCB86E9F847BBF729B8D9CBB9A3A20C65826482B3340F81A80F1D9FD4B8C1`。未安装到用户游戏。完整新世界的区块保存重载、水体、跨区加载及客户端观感仍待验收。

## 维护优先与构建产物说明

用户最新优先级为代码可维护性，独立 `hydrology3d` / `erosion3d` 实验不接入默认生成。维护规范见 `CONTRIBUTING.md`；审查与设计见 `research/长期维护与三维河网设计.md` 和 `research/river-erosion/三维河网与Minecraft落地设计.md`。

本轮完成核心职责拆分：`Terrain` 保留查询门面，`TerrainSourceFactory` 负责原有来源与加工组合，`TerrainTileCache` 负责瓦片缓存及工作线程；三者整理为正常格式，保留现有生成与调度行为。锁内同步生成、模式定义分散仍是后续技术债。派生文件读取新增 `storedHeight` 有限值检查，拒绝校验和有效但高程字段为 NaN 的不一致文件。

最终隔离编译输出位于 `verification/river3d-review/core-classes`；重编译后的核心类优先加载，`CoreVerification` 21,794 项断言通过，`DerivedRegionVerification` 的原始输入不变、接缝、离线读取、NaN 字段和校验和回归通过。独立河网验证通过；侵蚀整理后由 `tools/verify_erosion3d.py` 验证通过。未据此宣称已经完成 Minecraft 画面验收或全部架构整改。

**构建产物状态变化：** 独立河网开发期间误调用完整构建，覆盖了工作区 `build/libs/Terragenesis-26.3-0.13.0.jar`。2026-09-28 本轮核对 SHA256 为 `CBA80D19A0563C30F7C4A5C358F2E531FAE52DE8F91AD6D62F84AEBE2AE19077`，与此前验收记录的 `8533D415505BF748A46C9933758D084B6F1D5FBD0545C06E62FC05970E8CF1EA` 不同。现存文件视为未验收开发候选，并非下面描述的原始交付包；也不包含本轮最后完成的全部维护重构。未安装到用户游戏。后续须重新明确版本并构建验收，不能沿用旧文件校验记录。

## 0.13.0 区域派生地貌

“长垣 · 地貌世界”的新建世界默认使用 `region_diffusion_processed_v1` / `regional-processed-vdm-v1`；创建世界界面显示“区域派生地貌”，仍可选择调参原始地形。处理模块以每 2 方块一个高程样本和四周 25 样本 halo 计算平原、丘陵、高原、高山连续权重，独立缓存派生高程及垂直 VDM，区块从派生区域读取。原始模型缓存与现有四类群系标签保持独立，Terrain Diffusion 模型没有修改。算法不含河网或侵蚀。

三个真实模型样窗的离线对照见 `verification/region-processing/report.json` 和同目录图像：平原候选低坡占比由 13.48% 增至 37.86%，其最高点降低 2.97 方块；高地样窗最高点 Y751.409 不变。已完成 0.13.0 JAR 离线构建与无 GUI 客户端类变换验证。大尺度平原整平仍有限；冷缓存需要准备 halo 邻近原始区域。尚未在真实新世界验收画面、水岸、跨区边界或区块保存重载，详见 `verification/region-processing/实现与验收.md`。

## 0.12.0 调参扩散基础地形候选

候选默认 `region_diffusion_tuned_v1` / `regional-tuned-diffusion-v1` 使用 `geographic_v2` profile；旧原始 profile 与历史区域 VDM 塑形分别保留独立配方和缓存。新 `raw_model_sea62_1024_v1` 在 Java 导入阶段不再叠加三倍放大或非线性压缩；模型像素到方块、高程米数到方块由 profile 固定换算，协议海面 Y=72 平移到游戏 Y=62，世界上界仍为 1024。原始模式专用 scale 已消除复用 `TALL` 3 倍语义的问题。缓存存储模型高程，超界高程由 Minecraft 世界边界限制，尚未完成最大区域尺寸的内存优化。

已完成代码与合成数据契约验证，并对 `geographic_v2` 做了 6 次真实模型推理与参数对照；第二种子高地样窗最高点 Y751.409，结果见 `verification/tuned-model/peak-seeds/summary.json` 及 `verification/region-processing/report.json`。平原候选仍偏丘陵；水面、自然过渡和真实客户端画面仍需在新世界验收。旧程序化山海流域的 Y743 检查属于另一条生成路径。

## 0.11.0 首次安装与按需服务

首次启动在后台准备 Python、依赖和模型，默认写入游戏目录 `Terragenesis`；区域文件默认位于 `Terragenesis/regions`。安装页显示阶段和失败重试，后续启动依据安装标记跳过服务启动，生成需要真实模型的地形时再启动。显式配置的旧 `home`、`regionDir` 仍优先于默认路径。自动安装当前针对 Windows x64，真实模型推理默认需要支持 CUDA 的 NVIDIA 显卡；JAR 不含数 GB 权重或 Python 环境。

已完成现有 Java 回归、无 GUI 的 Fabric 客户端类变换，以及本地 HTTP 对大文件下载的断点续传、完整分片和校验失败测试。工作区隔离的首次安装从网络下载 Python 与依赖，模型使用经校验的本地副本；完整标记、真实模型服务健康检查和采样、服务关闭，以及下一次启动跳过服务端口检查均通过。记录见 `verification/first-install-latest.json`、`verification/bootstrap-cold/managed-service.json`（采样高度 76.5988）。这不等于模型权重从网络重新下载的验收，也不等于客户端画面验收；本轮没有操纵外部游戏实例。

## 0.10.1 创建世界界面修复

修复 `CreateWorldScreen` Mixin 错误遮蔽继承自 `Screen` 的 `minecraft` 字段。该字段不在目标类自身，Fabric 转换时抛出 `InvalidMixinException`，使创建世界界面只显示背景。现在通过 `Minecraft.getInstance()` 获取客户端；不改变世界生成配方。

## 0.10.0 区域数据路线

新增独立世界预设 `remotemountains:region_landforms`（`region_diffusion_v1` / `regional-xyz-vdm-v1`），旧预设与存档配方不变。默认区域为 24×24 区块；先准备基础高程、水、气候、随机形状地貌标签及完整 XYZ VDM，写成带 SHA-256 校验的 `.rmr`，再由区块读取。基础字段每内部格（3 世界格）采样，VDM 每 2 内部格（6 世界格）采样，外围保留 64 内部格缓冲。存储区域是固定格网，逻辑地貌区另由 `landform_layout_v1` 决定标签；Terrain Diffusion 高度、河网及岩壁位置未受新标签重塑。`region_processing=none_v1` 仅预留交界处理身份，未实现新侵蚀/噪波。

`RegionExport` / `tools/export_regions.py` 可预生成有限区域矩形。完整区域优先读盘，缺失才初始化真实模型；种子、模型身份、配方、尺寸、处理版本不匹配时拒绝混用。配置示例在 `dist/config/terragenesis-regions.properties`。同一数据集目前只由单进程准备，尚无跨进程锁。

真实模型验证：种子 20260927、24 区块区域 `(0,0)` 已导出 `verification/regions/real-model/seed-20260927/regional-xyz-vdm-v1-24-none_v1/r.0.0.rmr`（1,081,863 字节），再次以离线模式、不可用模型路径与另一个端口读盘成功。离线 VDM 体素化为密度列在 `(0,0)`、`(15,15)`、`(383,383)` 三点也通过；最终构建及 `RegionVerification` 通过。尚未完成真实 Minecraft 区块保存重载和客户端画面验收。旧流域种子 20260927 在世界约 `(1890,-48)` 的汇流悬水仍未修复。

## 0.9.0 随机地理条件与模组管理服务

新全域世界默认使用 geographic_v1：世界种子和全局坐标生成粗高程、年均温、温度季节性、年降水及降水变异，随后交给原有 Terrain Diffusion 模型推理。平滑值噪声与简化地形气候规则取代运行时 WorldClim/ETOPO 地图及统计表依赖；未重新训练模型，尚未实现完整气候动力学或全域河网。

16项Python测试通过，包含条件场边界精确拼接、种子0、物理单位、海岸连续性，以及禁止调用上游真实地理数据读取函数的条件接入检查。模组管理服务已经实测从无服务状态启动真实模型、请求地形瓦片、拒绝错误模型身份并关闭自身进程，记录在verification/managed-diffusion-latest.json。全域Minecraft验证在verification/presets-global/20260928-021515/results.json：5处区块保存重载一致，341个岩壁近表层方块通过。该次使用诊断构建，正式包另行正常构建；深部方块受到原版后续装饰影响，不能以纯地形预测逐块比较。

服务代码随JAR分发，Python运行时与模型权重使用配置指定的配套目录。本机示例在dist/config/remotemountains-diffusion.properties。当前环境依赖本机Anaconda，不能宣称复制JAR就能在任意电脑独立运行。代码MIT版权声明已随包保留。

客户端已完成启动与资源加载检查；用户要求停止直接操纵、由用户最终验收，尚未完成进入新世界后的视觉确认。

有限高程/水面/VDM资产原型位于preview/prepared，属于固定种子的导出导入验证，不是随机种子默认预设；其数据读写类拆分与更完整岸线验收仍待完善。

## 0.9.0 河岸修正

**未全部完成：** 普通河岸与截图附近的局部检查通过，但加强后的实际服务器回归仍在汇流附近发现水面/岸地不一致，例如世界 `(1890,-48)`。河段合并实验未收敛，已停止继续扩大修改；保留失败检查，后续优先修复。不得把早期保存重载通过或局部检查通过表述为全流域悬河问题已经解决。

山海流域新世界使用 watershed_heightmap_v2。RiverProfile 在河道开挖前沿每条可见河段采样原始两岸地形，将水面限制在两岸允许的高度，并沿支流汇合处向下游连续传递。河床在水体边界与干地衔接；旧存档 watershed_demo_v1 保留原有身份与生成路径。

WatershedHeightmapVerification 检查三个种子的水陆边界，以及所报告 X382 Z36 附近最终三倍缩放的 VDM 方块列。纵向剖面数据为 preview/watershed/river-profile-v2.csv，对比图为 preview/watershed/river-fix.png。服务端检查由 WatershedWorldVerification 和 tools/verify_world_presets.py 执行；图和自动检查并非客户端截图。

未通过全流域验收：扩展服务端河岸扫描在支流汇合附近（种子 20260927，世界 X1890 Z-48）仍发现约 4 格水陆高差，单河段修正不能保证汇流处连续。该失败保留在验证检查中，下一步需统一汇流的水面与最终 VDM 岸线。

## 0.8.0 峡谷补充岩壁（2026-09-28）

新增canyon包三类：CanyonCliffStyle倾角配方、CanyonCliffLayout原坡面/河距/间距筛选、CanyonCliffModifier局部侵蚀和VDM组合。两个独立预设canyon与canyon_single使用版本化配方，不改变已有0.7.0世界配方。

种子20260927新增3个面片：世界(1956,-749)、(3150,-553)、(4170,635)。混合模式基准角度64.728°、77.343°、85.542°；统一模式76°。保留原河岸面片。新面片每处以基准流量0.8%作演示入流，将平均出流水沙接回下游；河网几何采用稳定基础流量，保证重建幂等。

验证：统一构建全部通过；新增9,549项检查含505个河道保护采样、相邻VDM瓦片接缝、重复构建、两种配方、水沙守恒。真实Minecraft26.3/Fabric服务器两种模式均完成保存重载一致性验证，各检查2,214个新增岩壁方块。记录：verification/presets-canyon/20260928-005742/results.json；verification/presets-canyon_single/20260928-005740/results.json。原有7个水体样点和峰顶Y743.0756检查同时通过。

预览：preview/canyon/surfaces.png、profiles.png以及实际顶点CSV。它们为模型面片采样和横断面，不是客户端截图，也不表示复刻巫峡DEM。面片尺寸仍一致、候选河段仍预设，沿岩层/山嘴分裂的自然崖带、全域峡谷识别、真实崖顶汇水路径仍待完成。配置角度不等于基础山坡叠加与侵蚀后每个三角面的角度。

## 0.7.0 独立山海流域

安装包 build/libs/RemoteMountains-26.3-0.7.0.jar；新世界预设 remotemountains:watershed，显示为“长垣 · 山海流域（独立演示）”。旧有限地貌展示和全域世界仍保留。全部新产物位于本工作区，未修改用户游戏安装。

种子20260927的最终真实服务器验证：verification/presets-watershed/20260927-234100/results.json。两次启动/保存重载一致。峰顶(0,864)实测Y743.0756；海平面Y62；7处水体样点、74个高山实体方块、902个VDM岩壁方块通过，岩壁相对基础地形最大高度变化约68.97格。232549目录是调参前中间版本，最终证据以234100为准。服务器验证不等于客户端截图确认。

统一构建通过已有核心/扩散协议/侵蚀/有限地貌/区域岩壁/高度缩放检查，并新增70,503项流域检查及岩壁水沙回传、重复构建幂等检查。预览见preview/watershed/map.png；CSV和audit.json是基础地形/河网采样，未包含VDM岩壁最终表面；图中Bank cliff仅标位置。

模块拆分为DrainageGraph（跨区块共享河网/水沙）、MountainRelief（Perlin山脊）、WatershedTerrainSource（内置扩散样片与有限流域）、WatershedCliffModifier（面片入流/出流连接）。局部岩壁先求解、再生成区块；河道几何使用基础流量，水沙审计使用回传后的流量，避免生成顺序和重复构建改变地形。

当前是人工约束宏观布局的流域原型，山体细节来自内置Terrain Diffusion与Perlin，不是训练完成的河网条件扩散。水沙账本近浮点误差守恒，但还没有驱动下游三角洲/沙洲沉积几何。河网有平滑弯曲，支流布局和有限边界仍较规则；全域跨区域河网、完整物理时间标定、动态河床演化仍列TODO。山高700–800的调参和验证针对新流域预设，不是强行将所有旧展示与全域山峰改到同一高度。

## 0.6.0 高度与比例

新世界独立维度类型 overworld_1024：min_y=-64，height=1088，上边界 1024。terrain_scale=relief_3x_sea62_1024_v1 持久化；旧存档缺省 legacy。地上 XYZ 地貌按海平面基准放大 3 倍，世界海平面为 62；海底深度不放大。通过缩放完整 VDM 网格再体素化保留悬挑，不重复拉伸方块列。洞穴与岩层使用逆变换采样，树木等原版装饰未放大。

用户实例只读诊断：实际加载 0.3.0，新增的两处岩壁尚不在该安装包中。未进行客户端窗口操作。

最终海平面 Y=62 验证：verification/presets-demo/20260927-225651/results.json，有限演示高度约 443，检查了旧上限以上 110 个实体方块，三处岩壁共 2,706 个方块；保存重载一致。全域测试位于 verification/presets-global/20260927-225703。Y=72 的较早 0.6.0 测试目录属于被替换的中间版本，不能作为最终配置证据。

## 当前实际路线

Terrain Diffusion 基础高度 → XYZ VDM → 固定专用悬崖算子 → 三角面/密度 → Minecraft 方块；洞穴由独立三维噪声处理。

已新增两个世界预设：有限演示预设在内置样片四个象限加入地貌测试区；全域预设强制按世界坐标调用实时 Terrain Diffusion。

## 已验证

- 0.4.1 Perlin 有限演示：真实 Minecraft 服务器四地貌区生成、岩壁检查与保存重载一致，见 verification/presets-demo/20260927-220039/results.json。

- 0.4.0 有限演示：四种实际地貌区、对应群系、岩壁侵蚀方块及保存重载通过，见 verification/presets-demo/20260927-211651/results.json。
- 0.4.0 全域：真实模型服务生成 ±8192 远处及原点附近区块，保存重载一致，见 verification/presets-global/20260927-211703/results.json。
- 真实模型瓦片边界检查：74 张缓存瓦片、116 对相邻边缘，最大差异为 1.198 米原始高程（不超过 0.04 方块）；不是逐值一致，见 verification/presets-global/tile-edges.json。
- Java 核心、协议、岩壁测试通过；有限演示另新增 13,589 项验证。

- 真实 Terrain Diffusion 模型已完成推理，JAR 默认内置有限样片。
- 有效样片和前后对照：preview/terrain-pipeline/20260927_-7680_0_513。
- 0.3.0 悬崖采用 76° 可倾斜基准面、非均匀 Voronoi 岩块/节理、重力投影贴壁水流、横向侧蚀、离壁下落/重新接触和局部体积体素化，位于 (256,256) 附近。
- verification/diffusion-server/results.json 的 passed、restart_identical 均为 true：打包模组的生成、保存和重载验证通过。该记录是服务器验证，不是客户端画面认证。
- 2026-09-27 只读检查用户实例：0.2.0 已加载；“新的世界”和“新的世界 (1)”的主世界生成器均为 minecraft:noise。因此在这两个存档中看不到本模组地形。
- 世界类型“长垣 · 地貌世界”已注册。需要新建时选择，对应 remotemountains:landforms。

## 当前限制

- 基础样片覆盖 X/Z -256..768，边缘渐变到海洋，范围外是海床。
- 默认样片固定，不是对任意世界种子在线无限生成。
- 有限演示已有四类程序化塑形和对应群系；全域已有扩散基础地形及区域岩壁，完整四类特色山形尚未全域铺开。
- Voronoi 岩壁、贴壁径流、侧蚀和倾角已完成局部实验；崩塌和崖脚沉积未完成。
- 复杂 VDM 的自交、重网格化、拓扑修复与任意悬挑验证仍需完善。
- 客户端使用正确预设后的实际截图仍待确认。

## 下一版设计

详见 research/岩壁Voronoi与贴壁流水设计.md。先做倾角可控的局部岩壁，Voronoi 提供岩块/裂隙/耐蚀度；沿真实三维表面计算受重力影响的水流及法向侵蚀。岩壁局部求解接收上游汇水边界；悬挑处允许水脱离；穿孔和独立落石进入体积阶段。

## 历史实验

vdm_diffusion 的直接 XYZ 扩散短训和旧0.1.0程序化地形均保留为研究代码。它们不应被描述为当前真实 Terrain Diffusion 基础样片的来源。旧说明已存入 research/history/。

## 0.5.0 区域岩壁

- 独立模块：CliffPlacement 坐标变换、RegionalCliffLayout 布局、RegionalCliffModifier 缓存与面片侵蚀。
- 新增 1,937 项检查：旋转、负坐标接缝、种子、海底跳过、缓存淘汰重建与三种演示壁体素化。
- 有限演示三处岩壁 924 个方块检查、中央侵蚀 5,184 个方块检查及保存重载通过：verification/presets-demo/20260927-222150/results.json。
- 全域真实模型地形上的区域岩壁通过 308 个方块检查与保存重载：verification/presets-global/20260927-222627/results.json。种子 20260927，位置约 (6698,8959)，倾角约 70°。
- 实际 Java VDM 网格预览：preview/regional-cliffs/comparison.png，非游戏截图。
- 崩塌、崖脚堆积、区域间水沙连接仍未完成。

