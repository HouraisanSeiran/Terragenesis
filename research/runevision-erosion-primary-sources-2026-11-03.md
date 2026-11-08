# Runevision Advanced Terrain Erosion Filter：替代山脉基础来源的可行性研究

研究日期：2026-11-03。初始状态为一手资料调查；同日已进入独立后端实施。下文“未移植”“尚未实验”等为初始研究时点，当前状态以本节补充和专题验收记录为准。

**实施补充（2026-11-03）：** 已取得并固定作者相关C#转换源码 [AdvancedTerrainErosion](https://github.com/lpmitchell/AdvancedTerrainErosion/tree/57e79cc331d17e2a45c897bea9c4c022d1fc5551)，原始文件、摘要与完整许可保存于 [third_party/runevision_advanced_terrain_erosion](../third_party/runevision_advanced_terrain_erosion/)。NumPy端移植其 `PhacelleNoise` 与 `ErosionFilter`，不包含Unity封装、立方球投影与原FBM。原始Shadertoy GLSL仍未逐值核验，不能将C#公式对照称为GLSL复现。Rune代码MPL-2.0及转换/辅助代码各自声明均保留。

原始浮点Hash2在远坐标出现小数位丢失：晶格2200000到2200099的100个偏移完全相同。因此生产默认改用uint64晶格哈希，另保留`hash_mode=upstream`进行原公式对照；新算法身份明确记录该差异。其余滤波公式与实际物理坡度仍分别说明，滤波器本身不模拟水沙守恒。

用户最后确认的执行路线为**世界坐标基础噪波 → Advanced底座 → 区域处理噪波 → 复用现有侵蚀、河流及冰川过程**。高度图为连续算法的输出采样，不是人工生成输入。原先建议的结构与地质机制为后续深化方向，不替代本轮路线；当前代码、实图和测量状态见[专题规格](../.scratch/mountain-morphology/spec.md)。

**用户补充（2026-11-03）：** 研发目标进一步明确为有辨识度的山体形态，参考 Yosemite、落基山脉及贡嘎群山，尤其贡嘎主峰。需要继续发展山体结构、峰壁谷组合与多种塑形过程，Advanced Filter 作为其中的方向性沟脊算子。具体目标与候选技术路线见[山体形态规格](../.scratch/mountain-morphology/spec.md)；本记录前文关于滤镜作用的判断仍成立，后续研发范围以该补充为准。新实验使用[项目共用世界种子](../CONTRIBUTING.md#共用世界种子用户更新2026-11-03)，旧 TD 成果仍按各自产物种子复验。

## 结论与证据边界

**评价前提补充（2026-11-03）：** 用户重申，整个工程从一开始就面向无限世界生成，意在部分替代 World Machine / Gaea 在世界生成中的作用。用户已熟悉这两款软件的能力与大范围高精度生产成本；有限地图制作能力不构成对本系统整体可替代性的充分判断。新算法须同时比较有界依赖、按需生成、跨尺度与跨区一致性及总成本，详见[工程定位](../README.md#工作区项目总览2026-10-21)和[山体形态规格](../.scratch/mountain-morphology/spec.md)。Rune 的局部求值特性与该目标相关，结构与冰蚀等扩展仍须单独证明其依赖上界。

以 Rune Skovbo Johansen 的 Advanced Terrain Erosion Filter 作为**程序化山地形状生成器中的侵蚀外观层**，技术上有明确依据：作者把它设计成能作用于任意高度函数、逐点独立求值的滤镜。因此“宏观山脉骨架／基础高度场 + 该滤镜”可以成为一个新的基础地形来源候选。[S1]

滤镜自身不承担山脉位置、整体走向、完整水系、流量或泥沙预算。作者明确以外观为目标，并承认排水纹理会在坡面中途终止、输出导数不精确。能否达到本工程已有基础地形的自然度和速度，仍须在同尺度、同区域和同下游水文处理条件下比较；目前不能宣称已达到 Terrain Diffusion 的质量，也没有本机速度倍数证据。[S1；工程推论]

本次直接请求三个 Shadertoy 页面均未取得正文或源码，返回 `Bad request`。谱系、算法与许可依据是 Rune 本人的两篇技术文章，其中逐一链接并说明了三个作品；文章正文通过其官方 Blogger JSON feed 读取。因此以下是**作者一手技术说明的核实**，不是三个着色器当前源码的逐行审计。未确认 Clay John、Fewes 两个原始作品各自的许可证；不应把 Rune 的 MPL 声明自动套用于整条谱系或页面中的所有展示代码。

## 三个链接的关系

| 作品 | 作者与年份 | 关系 |
| --- | --- | --- |
| [Eroded Terrain Noise — MtGcWh](https://www.shadertoy.com/view/MtGcWh) | Clay John，2018 | 原始侵蚀外观噪声版本，目标是在单遍像素着色器中获得分支结构并支持无限地形。 |
| [Terrain Erosion Noise — 7ljcRW](https://www.shadertoy.com/view/7ljcRW) | Felix Westin / Fewes，2023 | 在 Clay John 版本上调整侵蚀效果，显著改进展示；简化核函数中正弦分量乘用的方向向量。 |
| [Advanced Terrain Erosion Filter — wXcfWn](https://www.shadertoy.com/view/wXcfWn) | Rune Skovbo Johansen / runevision，2025–2026 开发 | 新增 fade approach、stacked fading、normalized gullies、straight gullies、峰尖控制及脊谷圆化，是作者文章所称最终版本。 |

上述作者、年份和关系均由 [S1] 的 Background / Links 与 [S2] 的 Function lineage 确认。Rune 的较早版本 [Clean Terrain Erosion Filter — 33cXW8](https://www.shadertoy.com/view/33cXW8) 仍采用 frequency approach，不应与 Advanced 混同。

## 算法的实际职责

1. 输入基础高度和坡度方向。在局部顺坡生成条纹，条纹高低成为沟与脊。
2. 把条纹分布到随机偏移的格网单元，混合邻近单元的余弦／正弦波，减轻旋转条纹带来的扭曲。
3. 逐 octave 增加更小的沟谷；前一层修改后的方向影响下一层，使细沟从粗沟两侧分叉。
4. 通过峰谷淡出、跨 octave 掩码、部分归一化和人为调整的方向斜率，保留更清晰的脊谷层次。

这些是局部几何构造；没有沿坡追踪水滴，也没有真实汇流累计或沉积输运。文章原话为 “produce the appearance of erosion without having to deal with simulating the process of it”，并明确每个点可独立求值。[S1]

“逐点独立”有利于分块、并行和按需计算；工程上仍须保证基础场、参数场、种子、坐标和尺度在边界一致。若输入来自离散 DEM，边缘梯度、插值及多分辨率过渡需要另外处理。局部滤镜易于分块，不等于完整地形与水文管线自动没有接缝。[S1；工程推论]

## Advanced 相比早期版本的具体改善

### 峰谷处理：frequency approach → fade approach

Clay John / Fewes 让条纹频率与坡度成比例。坡度趋近零时条纹无限变宽，有助于保峰，却会让谷底也落在条纹的“脊”上而鼓起。低海拔淡出可遮掩这个问题，但限制了清晰 V 形谷的表现。[S1，The frequency approach]

Rune 保持条纹宽度，在低坡度处向外部提供的 `fadeTarget` 淡出；该目标从谷地的 -1 到山峰的 +1。采用 `1 - (1 - saturate(slope))²` 一类整形，缓解早期 `sqrt(slope)` 在近零坡度附近骤变形成的折痕。它使侵蚀可在整个高度范围施加，并同时保留较清晰的峰和谷。[S1，The fade approach]

**限制：**作者演示按海拔决定 `fadeTarget`，并在附注承认这不普适，因为某个高原谷地可以高于另一座山的峰。曲率可能提供信息，但作者没有给出稳健通解；数值曲率有采样成本，解析曲率需要基础函数全链条支持二阶导数。[S1，Additional notes]

### 层级形状：stacked fading

每层完成后更新淡出目标和组合掩码，使新细沟避开已形成的大脊与大沟底，保留较粗尺度结构。作者给出的组合式为 `combiMask = pow_inv(combiMask, detail) * newMask`；较低 detail 把高频沟谷更多限制在陡坡上。这比简单增加噪声 octave 更有助于保留清晰分支。[S1，Stacked fading]

### 振幅稳定：normalized gullies

对混合后的 cosine/sine 二维向量做部分归一化，减少不同相位抵消造成的沟谷振幅差异。完全归一化会在向量接近零时产生尖刺、洞和环状伪影；作者采用 `k = 2`，把长度放大并截到 1，使原长度大于 0.5 的结果归一化，同时保留较短向量的衰减。[S1，Normalized gullies]

作者明确提到部分归一化留下局部的斜率突变，但多 octave 后视觉上不明显。这种“画面可接受”不应被当作高阶平滑性保证；如果下游依赖曲率，应自行验证。[S1；工程推论]

### 分叉角度：straight gullies

为避免细沟沿大脊平行一段再卷曲分出，内部方向计算使用正弦的符号来模拟三角波的恒定侧坡。实际高度仍保持原来的波形。内部 `gullySlope` 与输出 `heightAndSlope` 分开计算：后者按掩码淡向零，前者为保持分叉方向不这样淡出。[S1，Straight gullies]

作者明确说各代实现的输出解析导数一直不很准确。为基础高度的方向贡献，他最终还使用可调的“假定坡度”使峰谷附近层间作用更均匀。因此滤镜输出的 slope 可以辅助艺术分布，却不应直接作为水流方向、坡度稳定性或侵蚀输沙计算的精确几何导数。工程中应在最终 DEM 上重新求实际梯度，并按需要建立离散流向。[S1；工程推论]

### 峰尖和圆化控制

- 减小 `gully weight` 并反向提高整体侵蚀强度，可在保留沟谷幅度的同时增强峰尖。例如作者演示 half gully weight、double erosion strength；峰尖仍依赖 `fadeTarget` 接近 +1，极低 gully weight 会有不理想的重影结构。[S1，Pointy peaks]
- 山脊和沟底可分别设置 edge rounding，并随 lacunarity 补偿以使不同 octave 的圆化尺寸接近一致。基础地形特征的圆化需要额外输入，因为滤镜不知道基础山体尺度。[S1，Rounding of ridges and creases]
- 参数可空间变化，从而控制不同山地外观；作者建议未来按具体地貌参考扩展，但没有宣称已覆盖各类真实地貌。[S1，Future work]

## 水文、真实度和性能边界

**水文：**末层 fade target 与 mask 可产生 ridge map，用于着色显示树枝状排水痕迹。然而作者明确说明条纹混合不能始终产生连续线条，有些沟和对应水迹会在山坡中途停止，无法一路到最低可达点。ridge map 不能直接充当河网拓扑、集水面积或流量。[S1，Water drainage]

**地貌：**该方法擅长侵蚀外观的分支沟谷、尖峰、脊谷层级。大陆与造山带位置、山链走向、宽谷盆地、岩性结构，以及冰川或喀斯特等其它成因形态需要基础场或独立模型提供。后半句是根据方法输入与算子职责的工程推论，并非作者对所有地貌的逐项测试结论。

**性能：**[S2] 记录 Simple Phacelle 的每次求值访问 4×4 = 16 个单元，输入方向只取一次；Sampled 版本则每个单元取一次方向。Simple 允许连续多次调用而成本随调用数线性增加，不必逐层缓存，也不会因递归重复采样出现组合爆炸。这个计数针对作者解释的 Phacelle 版本，不能等价成 Advanced 完整着色器的帧率或整个工程的耗时。

没有获取当前完整着色器并跑本机基准，因此不提供与 Terrain Diffusion 的速度比。ShaderToy 的光线步进、阴影、材质与渲染帧率，也不应当作输出高度图的生成成本。面向工程的比较应测每百万高度样本的时间、内存、梯度成本、边界处理成本及目标采样间距。[S1/S2；工程推论]

## 许可与代码取得

Rune 在 [S1] 的 Future work 明确写道：“I’ve released my code under the Mozilla Public License v2 in order to encourage further sharing of improvements.” 因而其公开声明不是 Shadertoy 默认许可的推测。实际移植前仍应保存取得的代码版本及文件内署名、许可头，并核对所复用代码的范围。

[Mozilla 官方 MPL 2.0 FAQ](https://www.mozilla.org/en-US/MPL/2.0/FAQ/) 说明它是文件级 copyleft：对外分发修改后的 MPL 部分，需要提供对应受覆盖源码、保留必要许可通知并告知取得方式；没有包含 MPL 代码的新文件通常不因此被要求整体采用 MPL。不能把它描述成“整个项目必须开源”，也不能当作没有条件的任意复制。[S3，Q8–Q11]

作者文章链接了 Unity Burst、Godot、Houdini、Blender 等移植，以及 Minecraft 的 [catto](https://github.com/oovaa8/catto) 和 Hytale 相关扩展。这证明已有第三方采用路线的公开入口，但本次没有审查这些仓库质量、当前代码或许可兼容性，不能据此视为本工程可直接使用的依赖。[S1，Erosion filters in the wild]

## 一手来源

- **[S1]** Rune Skovbo Johansen，2026-03-30，[Fast and Gorgeous Erosion Filter](https://blog.runevision.com/2026/03/fast-and-gorgeous-erosion-filter.html)。谱系、Advanced 具体机制、局限、MPL 声明的主要一手来源。读取日期 2026-11-03；通过作者官方 [Blogger feed](https://blog.runevision.com/feeds/posts/default?alt=json&max-results=500) 获取正文和发布时间。
- **[S2]** Rune Skovbo Johansen，2026-01，[Phacelle — Cheap Directional Noise](https://blog.runevision.com/2026/01/phacelle-cheap-directional-noise.html)。方向噪声、核访问数量、谱系和实现限制；通过同一官方 feed 读取。
- **[S3]** Mozilla，[MPL 2.0 FAQ](https://www.mozilla.org/en-US/MPL/2.0/FAQ/)，直接读取官方页面，尤其 Q8–Q11 的分发义务与文件级边界。
- 用户指定的三个 Shadertoy 链接见上表；本次未直接取得它们的当前源码。正文所述其作者／谱系由 [S1/S2] 确认。


## Terragenesis 接入评估（主端核查，2026-11-03）

**结论：作为替代 Terrain Diffusion 山地基础生成职责的独立后端，可行且值得验证；现有证据不能证明它已达到 TD 的地貌丰富度和自然度。** 较合适的替代单位是“宏观布局及山体骨架 + Advanced Filter + 来源适配”，不是把一个着色器函数直接换进现有推理调用。以下为工程判断与建议，未实施、未做性能或视觉对比。

### 当前工程事实

- 基础地形允许来自扩散或其他方法；河网、侵蚀和游戏适配有分开的职责。这为另一个基础来源留下设计空间，但不代表读取协议已经通用。依据：[CONTEXT.md](../CONTEXT.md)、[CONTRIBUTING.md](../CONTRIBUTING.md)。
- 当前板块来源链把冻结板块产品采样为 TD 条件，再实际生成 30m 高程及五通道 climate；宏观场、原始 TD 和海岸派生床面分别保存。依据：[plate_td_conditioning.py](../diffusion/plate_td_conditioning.py)、[plate_td_backend.py](../diffusion/plate_td_backend.py)、[plate_td_product.py](../terrain_pipeline/plate_td_product.py)。
- TD 的五通道 climate 输出是温度、温度变率、降水、降水变率和温度高程回归系数；不要与五通道输入（包含高程）混淆。过滤器不会提供这些字段。现有程序化条件场可作为独立气候来源的起点，但要在新高程上重算相关量并记录近似与身份，不能照搬旧 TD 的 climate 标签。依据：[上游固定版本 world_pipeline.py 的 _compute_climate](../vendor/terrain-diffusion-e8dcb4b1a834ab2f6b1a6f5256ed7c9f2f3e8230/terrain_diffusion/inference/world_pipeline.py)、[geography_physical.py](../diffusion/geography_physical.py)。
- 来源适配器目前限制 artifact_kind 为 TD，并要求 td_inference_run=True；原生页读取器使用 td-native-page-v1 和固定 30m 契约。新后端需要明确的新来源类型/格式或共享的中立读取层，不能用伪造 TD 字段通过校验。依据：[mountain_source_adapter.py](../terrain_pipeline/mountain_source_adapter.py)、[native_30m_source.py](../terrain_pipeline/surface_rivers/native_30m_source.py)。
- 冻结板块→TD 已有真实推理证据，但海岸样本的强噪波和再次施加宏观场曾分别被否决；后者会抹平 TD 已有湾谷。这说明新来源应从一开始明确宏观与细节频段，不能认为“再加侵蚀噪波”自然就改善审美。该记录并非对 Advanced Filter 的实测评价。依据：[真实推理与形态复核](../.scratch/plate-td-source-20261101/real-inference-review.md)。

### 建议的生成链及边界

冻结板块/大陆布局 → 连续的山系、主脊、盆地与大谷骨架 → Advanced Filter 塑造山体和支沟 → 米制基础高程成果 → 现有汇水、河湖与河槽加工 → 水沙及其他地貌过程。

1. **大形先行。** 复用现有板块宏观来源，再补合适的中尺度山体骨架。滤波能形成沟脊外观，但整条山系位置、走向、山前平原、主谷和海陆布局仍须由基础场及约束定义。粗板块栅格插值到细分辨率本身不会生成这些结构。
2. **尺度与导数一致。** 若把世界坐标缩放为 x/L、高程为 h/H，导数转换必须携带 H/L。现有板块采样是双线性，梯度可能在格界跳变；应评估连续重建对滤波方向的影响。用解析梯度、固定米制差分或栅格插值的选择都要写入算法身份。
3. **避免把引导场作为物理坡度。** gullies/ridge masks 可用于诊断或外观；汇水、坡度、法线和河槽检查基于最终 DEM 重算。即使作者输出 heightAndSlope，也应验证其与最终高程差分是否一致。
4. **约束地貌过渡。** 侵蚀强度、尺度和形态可随山地、岩性及气候条件平滑变化；高海拔谷底、低海拔尖峰、山前平原和海岸单独检查。高度阈值不能普遍替代谷底识别。掩码变化也会改变最终坡度。
5. **固定基础面，再计算水系。** 在基础地形尚未冻结时改变侵蚀细节，可能改变分水岭和河道。若后续需要按河网再塑形，应有界重算受影响的路由/湖泊关系，不能沿用旧拓扑。
6. **点采样与世界水文分别评价。** 点式过滤有利于有界依赖、按需采样和重叠一致；前提是基础场、种子、邻域和参数也确定。它不会自动满足完整流域、共享分水岭和合法出口约束。[ADR 0001](../docs/adr/0001-bounded-hydrological-planning.md)中的规划原则仍适用。
7. **多分辨率有明确语义。** 近景增加噪声层能提供更多合成细节，不代表更高实测精度。物理基础 DEM 采用固定配方；预览 LOD 不得悄悄改变已经使用的河床和汇水。对 30m/90m 栅格限制超出采样能力的频段，检查混叠。
8. **保持几何范围明确。** 结果仍是单值高度场；悬挑、洞穴、地下河以及多层地表仍由后续三维表示负责。

### 能替代什么

| 职责 | 可行性判断 | 尚须补充 |
| --- | --- | --- |
| 具有侵蚀外观的山地基础高程 | 高，适合试作独立来源 | 宏观/中尺度骨架、米制标定及多种地貌验证 |
| 可控参数、局部重算及按需采样 | 有优势潜力 | 世界坐标与种子、插值连续性、跨后端数值一致性实测 |
| TD 学到的多样地貌组合和自然度 | 无等价证据 | 多样样本比较；评估条纹、重复、过度锐利和风格单一 |
| 气候字段 | 过滤器不提供 | 独立气候来源与新地形上的高程修正 |
| 完整流域、河湖、水沙守恒 | 不由该滤波器保证 | 继续复用与验证工程水文及地貌模块 |
| 悬挑和洞穴 | 高度场不能表达 | 后续 VDM/体积或其他三维几何 |

TD 本身也是基础生成方法，不能仅凭其输出推断水沙守恒或完整河网。替代评估应公平比较两种来源在相同后处理下的结果，而不是要求只有新来源证明所有自然过程。

### 最小决策实验

这是建议的下一步，尚未创建实施任务或运行实验：

- 使用项目共用世界种子及同一宏观布局约定，固定样本位置；选择山地内部、山前平原过渡、高原/高海拔谷地、低海拔起伏和沿海山地，避免只挑最漂亮的尖峰。新种子需生成独立宏观来源；已有冻结板块及 TD 产品仍按原种子单独作历史对照，不能只改元数据冒称同种子比较。
- 先比较三个基础面：TD、相同宏观来源下的基础山体、基础山体加 Advanced Filter。固定覆盖范围、格距和高程基准。允许宏观布局相近，不要求不同生成器逐像素同形。
- 使用同样俯视、斜视、阴影和高程范围，并看无材质几何、剖面、坡度/曲率和局地起伏分布；Shadertoy 的光照、材质、雾和 raymarch 画面不作为 DEM 质量证据。
- 再让两种候选基础面经过相同的河网/湖泊流程，比较内部洼地、断流、出口、主谷与汇水匹配度，以及修正高程的幅值/面积。目标按游戏用途的主要河湖合理与可承受成本评价，不预设科研级真实演化门槛。
- 验证重叠采样、负坐标、查询顺序、不同分块大小和固定种子复跑；至少检查相邻窗口的高度及坡向连续。
- 在同机同格数下记录总生成时间、冷/热启动、RAM/VRAM、保存与加载开销，拆出来源生成和水文加工时间。代码结构预示可以减少模型加载依赖，不能据此声称已快多少倍；Shadertoy 帧率也不能代替完整 DEM 生产基准。
- 本次评估允许提出新来源对照；现行 CONTRIBUTING 的正式验收仍绑定 TD。研究样本须诚实标为新后端候选，不将它写成已通过 TD 验收；若决定切换生产来源，再同步修订来源与验收约定。

**建议决策：先投入一个有边界的独立后端原型，保留 TD 为对照。** 若主要目标是更直接控制山系、减轻模型依赖并让游戏地形快速迭代，这条路线值得投入；若要求立即保持 TD 当前全部地貌风格和质量，现有来源不足以支持全面切换。先回答“同样宏观布局下，山体是否更可控、最终河湖是否更省修正、总成本是否下降”，再决定生产替换。

本轮仅做原始资料和代码阅读并保存研究记录；未移植着色器、未启动 GPU 或游戏、未生成对比图，未修改默认来源或已接受的架构决策。


## 补充：从“沟壑外观”转向有辨识度的山体（2026-11-03）

用户进一步指定的目标是优胜美地、落基山中具有辨识度的山峰，以及贡嘎群峰、尤其贡嘎主峰所体现的山体个性。本节据四项官方／原始研究来源校正成因，并提出生成器的职责；它不是对指定山峰的精确复原。新的共用世界种子为用户指定的 `20260903`；本节未改变历史产物的种子或身份。

**地质时间应分层理解。** 岩石形成、构造抬升与出露、河流／冰川切割、当代岩壁崩落是不同阶段。“经历数亿年地质历史”不意味着眼前山形已经被风连续雕刻数亿年，更不能给整个山体统一套用一个风蚀年龄。优胜美地官方说明明确把岩浆侵入形成花岗质岩石，与后来的抬升、侵蚀和冰川塑形分开叙述；还指出构造抬升和倾斜仍在进行。[G1]

| 参考山体 | 有依据的形态来源 | 对生成器的含义（工程推论） |
| --- | --- | --- |
| 优胜美地的 El Capitan / Half Dome 一类 | 强而整体性好的花岗质岩体能够维持大岩壁和穹丘；节理影响冰川侵蚀路径。El Capitan 的高直岩壁与其岩体强度和相对少裂隙有关。平行表面的片状节理可形成剥落，NPS 将 Half Dome 岩面列为实例；冰川又把先前河谷扩大为宽底陡壁的 U 形谷。[G1/G2] | 先控制巨大的完整岩体、穹丘／切面、节理组、主谷宽深和岩壁，再加入局部裂隙、崩落与坡脚堆积。不能用满铺细沟代替这些一级形状，也不宜把 Half Dome 简化成“冰川削去半颗球”。 |
| 贡嘎群峰／主峰 | 贡嘎的极高地势涉及青藏高原东缘构造抬升。2022 年磁大地电磁原始研究提出扬子克拉通下插及鲜水河斜滑断裂受阻弯曲处挤压等机制，同时明确抬升机制尚有争议。东坡第四纪冰川年代研究表明多次大范围冰进，谷地、盆地和山前保存多期冰川地貌及冰水沉积。[G3/G4] | 主峰显著性、主峰与卫峰比例、主支脊方向、两侧坡面差异、深切谷地和冰川谷的布局，应在细沟滤镜前明确。冰斗／刃脊／角峰可作为拟研究的高山形态算子，但本次资料不足以把贡嘎每条具体脊或每面岩壁逐项归因。 |

因此下一步可以按“**山体骨架与区域起伏 → 岩性／结构约束 → 冰川和河谷塑形 → 岩壁与重力坡面 → 局部 Rune 沟脊细化**”组织候选算法。这个顺序是面向可控生成的设计建议，不声称复现真实地质全过程。Rune 部分应当受地貌区域和尺度控制：完整巨壁、宽谷底、冰川侵蚀面不应自动套上同样密度的树枝状细沟。是否确需 VDM／体积几何，应按目标是否包含悬壁、超垂或真实多值岩面决定；高度图阶段可以先验证山体轮廓和谷地布局。

**资料与不确定性：**本次尚未确认用户记忆中落基山具体峰名，也没有把其它山峰当作其所指对象。贡嘎主峰的局部岩性分区、节理方向与断层几何还需要地质图或专门测绘资料；不能仅凭轮廓就赋予一套“花岗岩节理”参数。没有把论文摘要中的旧海拔值转录成项目基准，也没有把单篇构造解释当作定论。对生成器的直接验收应关注主峰轮廓、脊谷层级、巨壁连续性、山麓过渡和多视角辨识度，避免只检查沟槽数量。

- **[G1] 美国国家公园管理局（NPS），[Yosemite — Geology](https://www.nps.gov/yose/learn/nature/geology.htm)**：直接读取官方正文；岩石形成与后期抬升分期、El Capitan 花岗质岩体、节理与冰川作用、V 形谷到 U 形谷。
- **[G2] NPS，[Yosemite — Rockfall](https://www.nps.gov/yose/learn/nature/rockfall.htm)**：直接读取官方正文；sheeting joints、exfoliation、Half Dome 岩面、冻融及温度变化／崩落过程。
- **[G3] [Mechanism for the Uplift of Gongga Shan in the Southeastern Tibetan Plateau Constrained by 3D Magnetotelluric Data](https://doi.org/10.1029/2021GL097394)**，Geophysical Research Letters，2022：读取出版社提交至 Crossref 的原始论文摘要；120 站电磁数据反演、下插与挤压抬升解释，以及机制仍有争议的限制。未获取全文；这里不据此推定峰体的具体节理或岩性。
- **[G4] Wang 等，[Late Quaternary glacial chronology on the eastern slope of Gongga Mountain, eastern Tibetan Plateau, China](https://link.springer.com/article/10.1007/s11430-012-4514-0)**，Science China Earth Sciences，2013（2012 在线发表）：直接读取出版社摘要；依据 ESR／OSL 等测年讨论多期冰进和冰川／冰水沉积。证据范围是东坡研究区，不能外推成贡嘎所有坡面的精确演化史。

可选的落基山对照案例为 **Grand Teton**，这里只是研究者选择的例子，并不推断它就是用户记忆中的山峰。NPS 的 [Grand Teton — Geologic Activity](https://www.nps.gov/grte/learn/nature/geology.htm) 明确区分古老变质／花岗质岩石、较年轻的 Teton 断层抬升，以及更新世冰川加宽峡谷、锐化山峰和留下湖盆／冰碛的过程。它也说明落基山参考不能归为单一岩性或统一“老山风蚀”模板；不同岩层、构造抬升和冰川改造的组合会产生不同的峰群轮廓。本次已直接读取该官方页面，未据此提出精确复刻某一峰面的参数。
