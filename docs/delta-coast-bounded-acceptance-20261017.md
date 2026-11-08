# 三角洲首次入海终止与岸陆形态修正

日期：2026-10-17。本轮修正已完成代码审查、34项独立测试、16km实际图审、5倍来水一年演算与冷重放。新版构造算法为 `coast-bounded-explicit-delta-v2`。用户提供的软件截图作为岸陆形态参考，没有作为实测高程或泥沙输入。

本次完成的是首次入海终止、更宽河道和更丰富岸陆形态的风格化修正。河口平原仍由明确记账的地形构造提供，年度沉积仅使用有限上游实际交付的泥沙；二者分别记录。

## 结果入口

- [岸陆形态前后对比及三个首次海口](../.scratch/hydrological-planning-domain/coast-bounded-mouth-16km-20261017-02/scene01-vs-scene02-coast.png)
- [新版构造低地与河岸](../.scratch/hydrological-planning-domain/coast-bounded-mouth-16km-20261017-02/lowland-detail.png)
- [一年后完整16km场景](../verification/fluvial-delta/coast-bounded-16km-20261017-01/scene-16km.png)
- [年度前后对比](../verification/fluvial-delta/coast-bounded-16km-20261017-01/overview.png)、[自然沉积](../verification/fluvial-delta/coast-bounded-16km-20261017-01/deposition.png)
- [构造数组](../.scratch/hydrological-planning-domain/coast-bounded-mouth-16km-20261017-02/scene.npz)、[构造预算与参数](../.scratch/hydrological-planning-domain/coast-bounded-mouth-16km-20261017-02/summary.json)、[几何检查](../.scratch/hydrological-planning-domain/coast-bounded-mouth-16km-20261017-02/geometry-audit.json)
- [年度结果数组](../verification/fluvial-delta/coast-bounded-16km-20261017-01/result.npz)、[年度预算](../verification/fluvial-delta/coast-bounded-16km-20261017-01/summary.json)、[冷重放](../verification/fluvial-delta/coast-bounded-16km-20261017-01/cold-audit.json)、[主协调独立数组检查](../verification/fluvial-delta/coast-bounded-16km-20261017-01/primary-array-audit.json)
- [任务09](../.scratch/delta-completion/issues/09-coast-bounded-distributaries.md)

## 修正依据与实现

旧scene09的branch0沿程约2030.8至4338.7m两岸均低于海平面，随后4343.6至5279.5m又切入构造岛岸。旧检查仅验证连通和最终端点接海，漏掉了中途入海后继续切陆地的缺陷。旧03集成结果与增流量对照保留为历史数值记录，不能作为通过本项海岸约束的证据。

新版先从原始场景来源重建切槽前地形，修改低地与岸缘，再冻结海域：床面低于零且与场景边界D4连通。封闭内陆洼地单独保留；不因开挖河床低于海平面就把它自动当作外海。

候选支汊按不超过5m间距检查，二分定位第一次进入海域的位置，截断并按各支实际长度重采样。实际切槽同时受端部切平面和海域掩膜约束。旧跨海后方岛槽通过重建切槽前地形清除。来流与主干也检查没有提前进入冻结海域。

新场景三支首次入海距离约为2.033、2.737、1.521km。第三支更早进入新形成的连海低地，后面的南侧长水带属于海湾；水沙计算在其首次海口结束。三个末端均只有最后一个路径样本进入海域；实际河槽与海域重叠0格。

主干名义宽度200m，三支为170、145、120m；来流从保留上游的100m连续过渡至200m。构造断面使用沿程宽度变化和非对称岸坡。水力树使用名义宽度，尚未逐断面求解这些岸坡变化。

陆侧与近岸低地采用沿河方向的连续低脊、斜向岸带和浅湾下凹，限制在构造包络与低高程范围；扇顶下游650m及其上游、绝对高程8m以上均不施加此项扰动。实际附加高差为-3.9896至+2.5383m，高差超过0.1m的面积23.3724km²。相对初版海岸约束scene01，3.7132km²从海平面以上转到以下、1.5256km²反向变化，属于两版构造地形的差异。

主协调查看了同色对比、全图、低地和三个海口细节，确认相对scene01有可辨的湾汊、陆块和岸缘变化。轮廓仍为风格化地形，没有声称已达到参考图的全部自然度。

## 施工与自然沉积分账

相对原始基础床面，本版总构造切方33,348,050.82m³、填方1,453,000,518.26m³、净填方1,419,652,467.44m³。单独低地起伏操作的切方15,739,364.46m³、填方8,378,535.46m³；该操作账与最终总构造账的参照面不同，不直接相加。

以上施工量包含继承的宽大构造平原，未用年度自然供沙支付。地形与海平面面积变化同样不能称为一年自然造陆。

年度演算继续使用同一有限上游物源，放大各节点来水而不放大材料库存。平均流量312.696467m³/s，为原62.539293m³/s的5倍；年度输入固体31,101.985844m³。

| 年度量 | 数值 |
| --- | ---: |
| 净留存固体 | 8,509.042611m³ |
| 海侧输出固体 | 22,592.943234m³ |
| 固体账残差 | 0m³ |
| 初始构造干地上净留存 | 2,258.714922m³ |
| 初始构造干地床升至少1mm面积 | 0.3084km² |
| 初始构造干地床升至少1cm面积 | 0.0036km² |
| 实际新增干地 | 0m² |

400m²床面越过海平面，但最终仍淹水。最大局部床升1.48504m主要位于河槽，不能当作大范围冲积平原增厚。水量输入约98.612亿m³，收支绝对残差0.000816m³，相对约8.28×10⁻¹⁴；分叉最大流量残差约1.80×10⁻⁹m³/s。

## 验收与使用边界

代码由唯一编程助手实现，主协调独立审查。最终34项聚焦测试独立通过，耗时4.75秒，覆盖集成水沙、流量缩放和新增海岸约束。主协调另行读取场景数组，重新计算D4海域、密采样海口、水深与保留上游，确认1428格旧槽恢复切槽前地形；旧branch0问题岛岸区189格全部恢复。

年度结果随后在新进程中精确冷重放；全局默认SCENE故意指向不存在的文件，仍由已记录的scene02完成来源裁切、逐日供沙和月度三角洲重放。相同来水的零沙对照床面不变。数值计算顺序执行，单进程、两核、BelowNormal、数值线程1。

主协调独立核对年度海域零净储沙、零毛沉积、零再搬运、床面不变与海面为零，按孔隙率及库存重建床面、按水面重建水深，并验证来流、扇顶和三个海口D4连通。全部保护区床面精确保留。四份年度输入hash与旧生成器、集成核心、scene09、03结果、旧5倍结果的既存hash均保持。

河流水沙在首次海口记入开放海洋输出，本轮未加入海侧羽流或近岸沉积求解。因此海域不继续作为虚构河槽演算，也不把输出泥沙视作本场景新增海侧陆地。模型仍采用固定三支拓扑与准稳态河道树，尚未模拟自主分汊或完整二维潮流、洪泛流量分配。Terrain Diffusion地形评估仍为后续阶段；本次没有发布默认世界或游戏。

复现需使用独立且不存在或为空的输出目录：

```powershell
.scratch/hydrological-planning-domain/pydeltarcm-venv/Scripts/python.exe -B tools/prepare_coast_bounded_delta.py --output .scratch/hydrological-planning-domain/coast-bounded-new
.scratch/hydrological-planning-domain/pydeltarcm-venv/Scripts/python.exe -B tools/prepare_coast_bounded_delta.py --output .scratch/hydrological-planning-domain/coast-bounded-new --inspect
.scratch/hydrological-planning-domain/pydeltarcm-venv/Scripts/python.exe -B tools/run_integrated_delta.py --scene .scratch/hydrological-planning-domain/coast-bounded-new/scene.npz --discharge-scale 5 --output verification/fluvial-delta/coast-bounded-new
.scratch/hydrological-planning-domain/pydeltarcm-venv/Scripts/python.exe -B tools/run_integrated_delta.py --audit verification/fluvial-delta/coast-bounded-new
```
