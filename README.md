# Terragenesis（山川形意）

**现行文档入口：** [docs/README.md](docs/README.md)（必读、架构、专题、归档分列）。进度总览：[TODO.md](TODO.md)。

[世界生成系统模块总览与四阶段分类](docs/architecture/world-generation-system/README.md) · [本轮数据清理记录](docs/architecture/world-generation-system/data-cleanup.md)（2026-11-07；仅逻辑分类，模块代码不变）。过时对话/旧实现状态已迁入 [docs/archive/](docs/archive/README.md)；[1–3 阶段科学评估](Terragenesis-1-3阶段科学评估与开源对照-20261104.md)仍为现行参考，未归档。

## 工作区项目总览（2026-10-21）

**工程定位（用户重申，2026-11-03）：以无限世界为基础的地形生成算法系统。** 全部地形、山体、水系、环境和三维地貌功能围绕可扩展、确定性、按需生成及有界资源设计，目标是在世界生成场景中部分替代 World Machine / Gaea 的作用。有限区域是验证与交付单元；最终需要证明覆盖范围扩展时，局部生成仍具有明确的依赖与资源上界。[既有有界规划决策](docs/adr/0001-bounded-hydrological-planning.md)继续适用，当前尚未完成端到端无限世界验收。

项目共用世界种子及历史复验规则见 [CONTRIBUTING.md：共用世界种子](CONTRIBUTING.md#共用世界种子用户更新2026-11-03)。

**2026-11-08 火山岛体量与Voronoi纹理已修正为v5候选。** 按用户反馈拆开紧凑上锥与低缓熔岩裙坡，去除侵蚀型放射硬槽；固定种子、扭曲平滑Voronoi实际改变堆积厚薄、口缘与岛岸，`volcanic_lava_strength`可关闭。主工程148项与织梦31项通过，旧v4精确回放；15张同址新旧/关闭/开启图供用户继续判断自然度，不代表岩浆物理或游戏验收。普通岛仍按>25km²处理。[验收](.scratch/volcanic-islands-refinement-20261108/review.md) · [图集](验收图片/火山岛Voronoi形态修正-20261108/README.md) · [接口](docs/ocean-islands.md#特殊火山岛)。

**2026-11-07 岛屿山系面积条件已放宽。** 默认实际露海面积严格>25km²即可准备山系，无默认腹地宽度门槛；25–100km²岛requested峰高为300m加固定±10%波动，较大岛沿用原300–3000m面积曲线。普通世界生成已接线，CPU任务pending，显式GPU任务复用既有TD链；两遍整岛raw统计/共同scale保护海岸与区块接缝。真实TD单块及最终世界消费已验证，完整真实岛峰高仍因内存门槛未验。[当前规则](docs/island-mountains-current.md) · [放宽记录与统计](.scratch/ocean-islands-20261106/area25-relaxation/review.md) · [原模型验收](.scratch/ocean-islands-20261106/area100-world-system-v3/review.md)。


**山体当前方向（用户调整，2026-11-04）：大陆基底 → 世界尺度粗山系 → Terrain Diffusion 局部山地及特殊形态加工。** 当前补充真实冻结大陆上的弯曲山带、平行/斜支脉、分段峰鞍与山间低地，先满足世界地图尺度的低精度形状需求；不再将下述独立局部算法试验作为替代TD自然度的当前主线。具体范围见[世界粗山系规格](.scratch/world-mountain-belts-20261104/spec.md)。粗山系向TD的条件接线、局部多形态与新地形水文仍须分别验证。

世界粗山系首版[2km正式候选与5km预览](验收图片/大陆基底与世界粗山系-20261104/README.md)已交付：真实1600×1280km冻结大陆上生成弯曲山带/支脉/峰鞍/低地，18项核心/导出检查及主端全格心、灰度/快照/冷读审计通过。2km为512000格，核心生成2.123秒，采样RSS158.24MiB；[E1–E9与图审](.scratch/world-mountain-belts-20261104/review.md)保留串珠/模板感及跨精度插值误差，5/2km不能直接混接。有限粗布局候选通过不等于无限增量、局部自然山形、TD或水文已经完成。

[无限世界地形生成评价标准](无限世界地形生成评价标准.md)：全工程的按需生成、有限依赖、多尺度、山体形态与资源评价入口。2026-11-03 启动的独立多形态山体研发保留为[历史任务与证据](.scratch/mountain-morphology/spec.md)，不将其有限窗口成绩视为TD替代完成。

独立山体首轮实现采用世界坐标噪波 → Advanced Terrain Erosion Filter底座 → 区域特殊处理噪波；高度图仅为采样输出。可运行入口为`tools/prepare_procedural_mountains.py`，接口、实图审查和有限过程范围见[实施记录](.scratch/mountain-morphology/implementation-review.md)。当前为有形态缺口的候选，尚未切换默认TD来源或完成无限世界生产验收。

后续已实现[Voronoi结构与沟槽保护候选](.scratch/mountain-voronoi/review.md)：在Advanced底座上比较岩体、脊带与混合塑形，保存无保护/带保护对照，并重新检查路由。入口`tools/prepare_voronoi_mountains.py`；保护形态凹槽核心不等于保护完整河网。

直脊改进已完成[高斯柔化与噪波局部破缺功能候选](.scratch/mountain-ridge-breakup/review.md)：在固定世界辅助格点上柔化结构差值，叠加弯曲、正脊缺口和小幅岩面噪波；入口`tools/prepare_ridge_breakup.py`，保持Advanced底座与原保护位置。2026-11-04审查：75项相关测试通过，512²生成约18秒；[实图](验收图片/山脊柔化与破缺-20261104/README.md)仍有蜂窝组织和碎山，参考山自然度、真实河网保护及默认世界替换仍待完成。

另一条[连续山脊乘胞状体量试验](.scratch/mountain-product/review.md)先形成宏观山体，再以其坡度驱动Advanced。已交付[16位灰度高度图与三种乘法强度对照](验收图片/连续山脊乘Voronoi-20261104/README.md)，入口`tools/prepare_product_mountains.py`；54项相关测试通过，512²生成约5.3秒。山体仍偏宽缓，Advanced沿脊细线残留，自然度及水文接线未通过。

后续[局部胞状体量与深沟壑](.scratch/mountain-local-volume/review.md)仅取局部高值乘原山体后叠加，负雕刻深度增益2.4，并对低坡度淡入；[五组灰度及差分图](验收图片/局部Voronoi体量与深沟壑-20261104/README.md)已交付，48项相关测试通过，512²约11.5秒，参考山自然度仍未通过。[图形学方法筛选](research/图形学地形生成方法筛选-20261104.md)补充曲线骨架/可变截面、距离场、方向场及局部三维等研究方向，阅读结论与待验证接法分列。

本轮已试验[分级山脊骨架与可变截面](.scratch/mountain-skeleton/review.md)：固定主峰与两级弯曲主支脊，三种截面共用几何，叠加连续低幅基底与既有Advanced。已保存[七组灰度、关闭细节的峰体及剖面](验收图片/分级山脊骨架与可变截面-20261104/README.md)，65项相关检查通过，512²近/远10.66/9.89秒。轮廓差异成立，但三向模板、源间主脊连接和沿脊细线仍待改进，未验收自然山系或接入默认世界。

当前主线为 **Python 无限世界河网 → Python 地理环境与生态 → Python 非高度场三维地貌 → 算法成熟后的 Java/Minecraft 转换与导入**。前三阶段尚未整体验收；下方带日期的算法与 Mod 记录保留为历史，不代表新主线全部完成。

| 入口 | 内容 |
| --- | --- |
| [四阶段路线与当前进度](docs/terrain-diffusion-four-stage-roadmap.md) | 当前主线、阶段边界与未完成项 |
| [全仓模块职责台账](docs/architecture/module-catalog/README.md) | 逐文件作用、依据、符号、静态依赖与哈希；未审定项明确标记 |
| [工程实现说明](docs/architecture/implementation-guide.md) | 四阶段具体方法、真实入口/数据流、已有能力与后续接线 |
| [历史蓝图提炼与四阶段映射](docs/legacy-river-plan-takeaways-20261022.md) | 仍适用的方法与验收要求；两份根目录原文已移入 deprecated-plans/ |
| [模块版本收敛审计](.scratch/module-version-consolidation-20261022/report.md) · [A方案执行清单](.scratch/module-version-consolidation-20261022/plan.md) | 按族迁移；首批3份旧算法已隔离，其余未完成 |
| [首批独立验证](.scratch/module-version-consolidation-20261022/batch-01-independent-review.md) · [历史源码目录](legacy-code/README.md) | 默认最新版与显式历史复验分离；原始字节/哈希保留 |
| [四阶段算法组成与详细规划表](.scratch/terrain-four-stage-review-20261021/algorithm-components-review.md) | R1–R9、G1–G20、V1–V8 组成、现状、缺口与审阅稿边界；不是全量批准实施清单 |
| [第一阶段实施计划](.scratch/river-infinite-world/plan.md) | 任务顺序、依赖与验收门；同目录保存专题契约 |
| [环境依赖矩阵](docs/terrain-geography-dependency-matrix.md) | 第二阶段概念、依赖与外在表现 |
| [遥感式验收图片规范](docs/remote-sensing-acceptance.md) | 此后成果图片默认俯视遥感式合成影像，降水/气候等配同源定量专题图 |
| [非高度场地貌目录](docs/terrain-non-heightfield-landforms-inventory.md) | 第三阶段形态与 TD 集成门槛 |
| [自然环境交接](.scratch/infinite-world-geography/handoff-20261021.md) | 历史专题接口与证据，旧编号不换算为四阶段进度 |
| [DeepSeek 任务交接目录](.scratch/deepseek-harness/) | 规格、验收、请求回复及返工、本地网关 |
| [DeepSeek 代码审查报告](.scratch/deepseek-review-20261021/report.md) | 三个已复现问题、回归结果与审查限制；本次未修复 |
| [工作区接手说明](vantaloom.md) · [工程 TODO](TODO.md) | 完整交接目录索引与工作总览 |

具体进度以四阶段路线、专题契约与保存证据对照为准；第一阶段计划中的旧待办不覆盖后续已交付记录。

## 算法框架与代码仓库

[河网工程交互总览](docs/river-engineering-map.html)：展开模块查看成果、剩余问题和后续方向。[总览源文档](docs/river-engineering-map.md) · [Markmap 使用说明](tools/markmap/README.md)。

2026-10-15 [河流主导三角洲有限机制首版](docs/td-fluvial-delta-20261015.md)已完成：固定TD海口水沙输入、沉积及下一阶段水路反馈通过检查，保留入口淤堵反例。实际TD场景尚为水下沉积，合成浅水对照验证出露；潮汐须另行讨论后进入下一版，波浪在TODO。

2026-10-15 同源38.4km TD河网已加入代表性流量及床岸硬度驱动的宽深规则：209处汇流增流、204处展宽、207处加深。已有米制断面与粗栅格切削预览；30m地形尚未解析全部窄河槽，材料账未接输沙。[结果与边界](docs/td-discharge-rock-channel-geometry-20261015.md)。

2026-10-14 低地径流与可见河道分离首版已在同一38.4km TD大图实际运行：含季节性河道的低地密度减少43.30%，完整产流水量、主干连续性及湿地等同等承接对象水账通过关键检查。[报告与预览](docs/td-lowland-runoff-20261014.md)记录首版参数、未解终点及仍存在的形态问题，不代表成熟自然河网发布。

本工程同时包含独立米制地形算法和历史 Minecraft 适配器。算法入口见 [algorithm/README.md](algorithm/README.md)，Mod 边界见 [minecraft-mod/README.md](minecraft-mod/README.md)。地形输入、地表/地下水系、VDM 岩壁和后续侵蚀属于算法层，不以 Minecraft 方块尺度定义物理模型。

当前地表河槽已保存一个独立检查通过的真实 TD 派生片段：120节点、118条接回弧、18个分叉，最长连续路径1230m。地下闭环与VDM三维样例正在实施；实际交付状态见 [三维水系文档](docs/hybrid-river-network.md)。这不等于完整自然海口、全网水动力或地下水地质认证。

代码仓库不包含模型权重、Python运行环境、区域缓存和大型验证产物。安装与证据范围见 [源码交付说明](docs/source-publication.md)。下方版本、安装与游戏案例是既有Mod路线的记录，不代表新算法默认接入了游戏世界。

## 长期目标：TD 虚构世界中的自然可信河网

本工程的河网目标，是在 Terrain Diffusion（TD）生成的**虚构世界**中，形成受该世界地形、集水与边界约束，具有可信支流、河槽、湖泊、出口和水沙地貌响应的河网；不是逐点复原某条现实河流，也不以地图看起来像河流作为验收。所谓“自然可信”，应同时经得起拓扑连通、汇水与河阶、纵坡与床面、河宽/流量、水量和泥沙守恒、湖泊与出口语义，以及跨种子/降雨情景的统计和反例审查。现实流域资料可作为分布与过程的对照，不应被误标为 TD 世界的真实答案。

目前已有固定 TD 来源、局部河槽与若干有界形态候选，但这**不等于**全域自然河网、经认证自然海口或已耦合的三角洲分汊。真实 TD 高程上的人为划定陆水边界只能作为明确标注的局部算法测试；未经独立边界与水沙验收，候选不得升级成已发布河道。新算法遵循 [河网模块主线分类](docs/architecture/river-module-classification-20261009.md)，前端只读固定证据；Minecraft 是后续消费环节，不决定米制算法的物理语义。

现行开发总路线为[最新版四阶段开发总览](docs/terrain-diffusion-four-stage-roadmap.md)，各阶段详细组成见[四阶段算法组成与证据表](.scratch/terrain-four-stage-review-20261021/algorithm-components-review.md)（审阅稿，不自动批准全部候选）。旧阶段 0–5 规划已废弃并移入 [deprecated-plans/](deprecated-plans/README.md)，不再作为任务发布依据；历史验收证据继续按原范围保留。

阶段 0–5 本轮有限实现与评价交付见[最终报告](docs/td-natural-river-stages-0-5-20261011-final.md)：噪波气候接入原生河湖水账，独立留出 6 组中 5 组通过、1 组拒绝，原活动泥沙完整 900 秒空间与工程预算验收通过。最终只读页包含全部保存证据；形态仍为候选，不授予全域自然度或发布认证。

六份完整原始 TD 地形上的[实际河网与河床生成](docs/td-terrain-generated-rivers-20261011.md)已贯通噪波降雨、地形路由、连续床面和唯一全局河床：22569/27336 条候选河段形成实际河床，4767 条真实超出 4m 切深预算而拒绝，最终六源独立冷读通过。四个实际数值或几何过约束问题已修复；固定视角仍显示栅格折角与中心窄深槽。这些调试用来源不再作为独立留出集，断面自然度、深洼湖泊、域外延续和自然可信认证仍待完成。

[本轮河槽形态修复与六源关键验收已完成](docs/td-river-shape-repair-20261013-final.md)：第37批保留全部22569条旧接受河段、4767条旧拒绝，六源实际床面独立冷读通过；78张固定位置图已审阅，77处断面可完整比较、1处边界采样不足。普通≥30°转角5414→1604，实际底部与弯角整体改善，汇流口折角、局部不对称及谷侧偏位仍保留，不等于全域自然认证。论文采用程度与Nucleation候选见[交接记录](docs/river-progress-and-reference-use-20261013.md)。

水文规划域已完成有限粗规划、冻结归属查询和首例12个月周期水账；真实TD关键位置的地形衔接正在验收。49个固定支持范围中35个成功、14个明确拒绝；这不是全世界覆盖证明。首例海岸/内流双域分别约34,700/26,700km²，内流湖日步全年水位526.122967–526.281611m，日步与半日步的月水位最大差约0.345mm。规划级PET尚未观测标定，水账不代表全网水动力。设计、失败证据和剩余工作见[水文规划域实施记录](docs/hydrological-planning-domain-progress.md)。

2026-10-14现行v5开发样例的完整10km普通河段20片、14.142km海口29片和4.888km三臂联合床面已通过保存后独立检查及实际细粗端口连接；459个已归属粗单元到达合法终点。v5混合湖已通过年度重放、日/半日周期和190个临界水位连通检查，范围是细窗口及保留粗湖环。种子3、17、29固定12槽审查保留全部缺失与拒绝：部分河床不满足原约束，实际图中的条带、平整区、过度平滑和笔直路径使自然度不通过。本轮未训练或微调TD，已有TD模型提供原始地形，河网由后续规则和数值算法生成。水文准备默认两核低优先级，保留来源精度与冻结预算。详见[水文规划域实施记录](docs/hydrological-planning-domain-progress.md)及[本轮完成任务](.scratch/hydrological-planning-domain/issues/05-algorithm-completion.md)；当前只可冻结开发候选，首版整体仍未完成，Minecraft导入后置。

2026-10-14接续的[同源地形保留与河床修复](docs/td-hydrology-naturalness-improvement-20261014.md)已加入独立可选投影：平滑延拓冻结边界的高程位移，并在宏观阶段加入采样横断面规划包络。固定seed29普通河段相对旧目标方案减少约35%的地形绝对改写量，原失败位置的60m细床及同一完整固定窗口4.04km、9段河床均已通过独立检查，最大切深3.707m。当前仍有规则条带和长直路径，不授予自然度或Minecraft导入认证。

2026-10-14 的[38.4km 同源大图汇流修复](docs/td-large-map-confluence-20261014.md)已实际生成并保存后审查：浅洼溢流、同域共享下游和普通斜坡最大降坡选路接通，汇流点31→343、最长连续路径11.335→40.984km。静态页展示新旧全幅与汇流放大图。5个可见深洼、64个域端口和51个图幅边界端口仍未闭合；结果是路由/候选水面验收，不代表全图实际细床、自然度或Minecraft导入通过。

随后图审确认上述版本把10km粗域标签误当不可跨越墙，造成矩形截河。已在同一TD来源上完成[原生汇水重规划](docs/td-large-map-native-replan-20261014.md)：64个内部人工端口清零，问题位置全部有继续下游路径；粗标签现在只作不相容诊断。新版仍是固定38.4km窗口内的局部候选，窗口外延续、深洼、实际细床和自然度仍未认证。

## 既有Mod路线

模组 ID、世界预设命名空间和存档生成器标识继续使用 `remotemountains`。当前 0.12.0 是开发中的候选版本，尚未完成调参模型的实测验收。安装机制延续 0.11.0：首次启动在后台准备 Python、依赖和模型，默认写入游戏目录 `Terragenesis`，区域缓存写入其 `regions` 子目录。

候选默认模式为 **山川形意 · 扩散基础地形（调参）**：使用 `geographic_v2` 模型条件配置，保留 Terrain Diffusion 的高程起伏，不叠加区域高度改写、侵蚀岩壁、洞穴或非线性高度压缩。`raw_model_sea62_1024_v1` 在 Java 导入阶段不再额外放大，模型像素到方块、高程米数到方块的固定换算由服务 profile 定义；当前为每模型像素 2 方块、每高度方块 6 米，并非现实水平与竖直等比例。模型协议基准海面 Y=72 平移到游戏海面 Y=62，世界上界仍为 1024；没有三倍放大或自动拉峰。旧 `geographic_v1` 原始模式和旧区域塑形分别使用独立配方缓存。

## 区域数据生成

候选默认模式把模型高程、水与气候按 Minecraft 方块坐标写入独立 `.rmraw` 区域文件，按种子、模型身份、调参 profile 对应的配方和区域大小隔离；不生成 XYZ VDM。默认区域为 24×24 区块。最大 96×96 区块区域的单文件与生成内存较大，缓存预算仍需优化。

历史实验区域塑形路线保存基础高程、水、气候、地貌标签和完整 XYZ VDM，然后由区块读取 `.rmr` 并体素化。该路线每内部格对应 3 个世界方块，VDM 每 2 内部格采样，边缘保留 64 内部格缓冲；它不代表新默认模式。

地貌区与存储格网分开。新版地貌标签由世界种子决定，站点规模和边界不规则，标签在区域边界上使用同一全局坐标规则；当前标签不会自动改变 Terrain Diffusion 的山脉高度、河网或岩壁分布。区域交界的侵蚀和噪波处理保留版本化入口，当前 `none_v1` 没有执行这两项处理。设计和数据边界见 [区域数据流程](research/区域数据流程.md)。

候选版新建单机世界时选择 **山川形意 · 扩散基础地形（调参）**，点击原版 **自定义** 可切换旧原始 profile、旧区域塑形（实验）及其他展示模式。默认区域边长为 24×24 区块，可输入 3 至 96 间 3 的倍数。世界种子仍在原版创建世界界面设置。专用服务器的新世界使用 `level-type=remotemountains:landforms`；旧区域实验预设保留为 `remotemountains:region_landforms`。候选包路径为 `build/libs/Terragenesis-26.3-0.12.0.jar`，同一实例只保留一份本模组 JAR。配置示例可按需复制到游戏实例的 `config`；默认无需填写工作区路径。`offlineOnly=true` 会拒绝按需生成缺失区域。

在工作区构建后，可以提前准备有限矩形范围。下面的区域索引 `0 0 1 1` 对应世界 X/Z 均为 0..767 方块；运行时会沿用当前模型身份，并在首次准备时启动模型服务：

```powershell
runtime/venv/Scripts/python.exe -B tools/build_local.py
runtime/venv/Scripts/python.exe -B tools/export_regions.py "<游戏目录>/Terragenesis/regions" 20260927 0 0 1 1
```

预生成与游戏必须使用同一种子、模型身份、配方、区域尺寸及处理版本。缓存根目录下按种子和配方分目录，区域文件为 `r.X.Z.rmr`；同一数据集当前只应由一个进程准备。迁移游戏实例时需连同匹配的区域缓存一起移动。区域缓存不解决全域河网，也不保证未缓存区域瞬间加载；洞穴继续由独立三维密度处理。

## 模型服务安装与启动（0.12.0）

把 `build/libs/Terragenesis-26.3-0.12.0.jar` 放进 Fabric `mods`，并安装对应 Fabric API。首次启动的后台安装需要网络连接和数 GB 下载空间，具体时间取决于网络和机器性能；当前自动安装针对 Windows x64，真实模型推理默认需要支持 CUDA 的 NVIDIA 显卡。JAR 内含服务及安装代码，不含数 GB 模型权重或 Python 运行环境。安装成功后记录就绪状态；后续启动不自动加载模型服务，进入需要实时模型的世界时才启动。下载或验证失败时可在安装页重试，稍后也可从地貌设置打开安装页；安装日志位于 `Terragenesis/terrain-install.log`。旧配置里的显式 `home` 和 `regionDir` 会覆盖新默认目录，删除或注释这两项才会使用游戏目录 `Terragenesis`。`dist/config/remotemountains-diffusion.properties` 提供可选的目录和条件模式覆盖。

选择“山川形意 · 地貌世界”，在“自定义”中选择“实时全域”时，模组会在创建或加载前启动本地服务，并等待真实模型就绪。缺少依赖或模型身份不匹配时，游戏会显示可返回的错误页面，不生成替代地形。专用服务器使用相同的自动安装和按需启动路径，但当前自动安装的平台要求相同。新世界默认使用由种子生成的五通道地理条件（海拔、温度、温度年变化、降水、降水季节变化），运行时不读取 WorldClim/ETOPO 地图。旧模型世界可在配置里设置 `conditioningMode=legacy_worldclim` 以维持原身份。

## 0.9.0 河岸修正

安装包：`build/libs/Terragenesis-26.3-0.9.0.jar`。新建山海流域世界使用 `watershed_heightmap_v2`：河道开挖前沿河段采样原始两岸，水面顺着两岸允许的高度向下游衔接，河床在水体边界接回干地。旧存档 `watershed_demo_v1` 仍使用原有地形。纵向数据和对比图见 `preview/watershed/river-profile-v2.csv`、`preview/watershed/river-fix.png`；`WatershedHeightmapVerification` 检查三个种子的河岸，以及所报告 X382 Z36 一带最终三倍缩放的方块列。服务端验证脚本为 `tools/verify_world_presets.py`。

已知限制：扩展服务端河岸扫描仍在支流汇合附近发现水面高于相邻干地约 4 格（种子 20260927，世界坐标约 X1890 Z-48）。该边界尚未修复；不能据此宣称全流域已无悬空河水。普通单河段的自动检查通过，汇流处需要后续连续水面与最终 VDM 岸线联动修正。

## 峡谷岩壁扩展 0.8.0

新增两个独立世界预设：**山川形意 · 峡谷岩壁（混合角度）**、**山川形意 · 峡谷岩壁（统一类型）**。以原有山海流域基础地形为底，补充间断的谷壁面片；统一类型使用76°基准，实际表面随基础坡度、Voronoi节理与侵蚀变化。种子20260927用于对照。旧山海预设继续保留0.7.0生成配方。

这是巫峡照片启发的算法演示，不是DEM重建的巫峡。参考位置为109.8784069°E、31.07183301°N。当前面片布局只接入独立流域，任意全域峡谷识别仍待实现。

安装包：build/libs/RemoteMountains-26.3-0.8.0.jar。只保留一份RemoteMountains模组并新建世界选择对应预设。完成情况与验证路径见 IMPLEMENTATION_STATUS.md。

种子20260927，新建创造世界并开启飞行后查看：

| 新岩壁 | 混合模式基准角度 | 观察命令 |
|---|---|---|
| 上段谷壁 | 64.73° | `/tp @s 1956 850 -749` |
| 中段谷壁 | 77.34° | `/tp @s 3150 850 -553` |
| 下段谷壁 | 85.54° | `/tp @s 4170 850 635` |

统一类型预设的这三处均为76°。原河岸76°岩壁也保留。预览：[实际表面变化](preview/canyon/surfaces.png)、[中心横断面](preview/canyon/profiles.png)，不是客户端截图；预览坐标轴使用内部模型尺度，传送命令已乘世界水平比例3。

当前仍是三个固定候选河段筛选出的完整面片，面片尺寸一致，尚未做到照片中按岩层和山嘴分裂的自然崖带。新增面片按原坡面起伏、河道保护距离与旋转矩形间距筛选；每处接收基准河段流量0.8%，回传下游水沙，属于演示边界分配，不代表河水会逆坡爬上山体。真实坡面降雨/支沟到崖顶的地理连通有待后续加入。

## 山海流域基础版 0.7.0

Minecraft Java 26.3 / Fabric 0.19.5+，Java 25。安装包：build/libs/RemoteMountains-26.3-0.7.0.jar。只在新建世界时选择的自定义预设中生效；旧存档保持其生成器。安装时同一实例只保留一个 RemoteMountains JAR，并安装对应 Fabric API。

| 世界类型 | 用途 | 模型服务 |
|---|---|---|
| 山川形意 · 山海流域（独立演示） | 山区源流 → 支流汇合 → 河谷与侵蚀岩壁 → 入海口 | 无需启动，使用内置扩散样片细节 |
| 山川形意 · 地貌世界（有限演示） | 平原孤山、裂谷、喀斯特、石柱及三种岩壁展示 | 无需启动 |
| 山川形意 · 全域地貌世界 | 全域实时 Terrain Diffusion 和区域岩壁 | 配好模型目录后自动启动 |

新世界 Y=-64..1023（上边界 1024），海平面 Y=62。内部地形坐标横向放大3倍，海平面以上起伏放大3倍；海底仅平移。网格缩放后体素化，洞穴和岩层按逆变换采样。树木等装饰保持游戏尺度；高海拔矿物、生存平衡尚未专门调整。

## 体验独立山海流域

新建创造世界，种子使用 **20260927**，开启命令，世界类型选择 **山川形意 · 山海流域（独立演示）**。专用服务器设置 `level-type=remotemountains:watershed`。主河从西侧山地向东流，到世界 X≈4800 入海，全程约4800格；下界和末地维持原版。

先飞到高处再下降查看：

| 样点 | 命令 |
|---|---|
| 山区及三处源流 | `/tp @s 0 850 0` |
| 约Y=743的峰顶 | `/tp @s 0 850 864` |
| 两侧主支流汇入主河 | `/tp @s 1920 550 60` |
| VDM侵蚀岩壁附近 | `/tp @s 2700 500 228` |
| 入海口 | `/tp @s 4800 150 20` |

图示：[算法采样预览](preview/watershed/map.png)，不是游戏截图。最终验证记录见 IMPLEMENTATION_STATUS.md。

演示宏观坡降和支流布局由统一河网约束，Terrain Diffusion 内置样片提供细节，Perlin 山脊提供额外变化。它不是新训练的河网条件扩散模型。随后转为 XYZ VDM，并对局部河谷岩壁进行 Voronoi 节理、贴壁流水和侧蚀。

岩壁分配上游流量的2%，求解192步后将平均出水和泥沙回传下游。流域和局部账本都有守恒检查；一演示步记为60秒，但降雨参数未经过真实流域标定，3倍视觉放大不表示Minecraft方块空间也满足物理米制守恒。当前河床形态主要由河网宽度和坡降控制，泥沙通量尚未进一步塑造下游沙洲或三角洲。

## 旧有限地貌展示

新建世界选择“山川形意 · 地貌世界（有限演示）”，范围 X/Z=-768..2304。先开启创造飞行：

| 地貌/样点 | 命令 |
|---|---|
| 孤山 | `/tp @s 0 850 0` |
| 裂谷与90°垂直岩壁 | `/tp @s 1536 850 0` |
| 喀斯特与68°悬挑岩壁 | `/tp @s 0 850 1536` |
| 石柱群 | `/tp @s 1536 850 1536` |
| 76°斜壁 | `/tp @s 768 850 768` |

此前安装实例实际加载0.3.0，故没有后来增加的两处岩壁。诊断见 verification/installation-20260927-latest/诊断说明.md。本轮产物都在工作区，没有修改外部游戏安装。

## 全域地貌与限制

全域预设需要真实模型服务在线，不能使用时会报错，不自动降级到演示。全域跨区域流域连接尚未接入；本轮流域只在独立山海预设中实现。相邻实时模型瓦片存在约0.04内部方块的边缘误差，详见 verification/presets-global/tile-edges.json。

洞穴使用独立三维密度处理；VDM本身不负责产生任意拓扑孔洞。崩塌、落石、任意复杂面片自交修复，以及客户端画面确认仍待完成。历史版本坐标与说明归档至 research/history/README-pre-watershed-0.6.0.md。

## 模块

| 路径 | 职责 |
|---|---|
| diffusion/、terrain_pipeline/ | Terrain Diffusion 推理、基础地形转换与导出 |
| Java diffusion/ | 内置基础样片或可选本地推理服务 |
| Java vdm/ | XYZ 位移、专用塑形、三角面体素化 |
| Java core/ | 区域、气候、密度与独立洞穴 |
| Java watershed/ | 独立流域、河网水沙账本、山脊轮廓 |
| Java watershedcliff/ | 上游水量分配、局部岩壁侵蚀与下游回传 |
| Java world/ | Fabric 生成器、群系、方块与服务器验证 |
| vdm_diffusion/ | 原有直接 XYZ 扩散实验及部分几何工具，不是当前基础生成器 |

VDM 存储 Δx、Δy、Δz，单位为方块，参考平面 Y=72；最终顶点等于参考顶点加位移。它不是任意三维占据场，拓扑变化需要体积阶段。

## 工作区内验证

- 构建：runtime/venv/Scripts/python.exe -B tools/build_local.py。
- 三个预设的隔离服务器生成及重载：runtime/venv/Scripts/python.exe -B tools/verify_world_presets.py watershed（或 demo、global）；新测试目录和日志均位于工作区 verification/。
- 安装检查：runtime/venv/Scripts/python.exe -B tools/diagnose_installation.py "游戏实例目录" --output verification/installation/report.json；游戏目录只读，报告必须位于工作区。

已完成的服务器验证见 [results.json](verification/diffusion-server/results.json)。客户端自定义预设实际画面仍待确认。

所有产物、环境和资料保留在工作区；外部参考工程只读。

## 下一步

- [实现状态（已归档）](docs/archive/historical-reports/IMPLEMENTATION_STATUS.md) · [现行文档入口](docs/README.md)
- [工程 TODO](TODO.md)
- [Voronoi 岩壁、贴壁流水、侧蚀与倾角设计](research/岩壁Voronoi与贴壁流水设计.md)

此前直接 VDM 扩散路线文档已保留在 research/history/，不代表当前功能状态。

### 有限 TD 水量闭环验收

`runtime/venv/Scripts/python.exe -B -m tools.verify_td_water_cycle --output verification/td-natural-river-stages/<新目录>` 复用既有原生产流、Manning 河道与湖泊共享步求解。固定 TD 的诊断 receiver 决定 96 格贡献域，单个邻接河段连接一个原生底格湖库存；横断面、湖支持与出口是明确的有限工程假设，不是认证自然海口。

当前保存证据见 `verification/td-natural-river-stages/water-cycle-20261011-final-bound/`。`metric_water_cycle.py` 冷读验证来源/强迫/物理秒身份、贡献分域、河湖端口、原生面积、完整水账与 dense/sparse/hourly 保存帧；包内保存父来源、原生产流、河湖 trace 及采样结果。验收范围为 7200 秒局部有界水量闭环；不宣称二维全域联解、含湖床变或自然可信认证。详细实测与失败证据见 `.scratch/td-natural-river-stages/issues/02-water-morphology.md`。



