# 岛屿面积、TD山系与峰高（当前v3）

2026-11-07按用户要求放宽：默认按固定1km格分析实际露海连通岛，面积严格 **>25km²** 即可准备山系；等于25不通过，100km²已可通过。`IslandMountainConfig(min_area_km2=...)`及CLI的`--min-area-km2`可配置门槛。默认不设腹地宽度门槛，海岸渐变只保护混合。大陆相连、触有限域边界、登记潟湖环缘及含特殊火山锥的组件排除。面积是栅格近似，不能保证接近门槛的精确矢量面积。

岛屿v4/v5中的特殊火山岛保留自身阶段锥体；计划以`special-volcanic-morphology`排除该连通岛，采样端也保护`volcano_weight>0`位置。此类岛不套普通TD峰高归一化。见[火山阶段规则](ocean-islands.md#特殊火山岛)。

用户确认峰高按海拔计算：默认下限300m、上限3000m，极值±10%波动，均可配置。公开函数：

```python
from terrain_pipeline.island_mountains import peak_height_for_area
peak_m = peak_height_for_area(241, min_m=300, max_m=3000,
    seed=20260903, island_key="stable-key", ripple_fraction=0.1,
    threshold_area_km2=100, saturation_area_km2=2000)
```

无波动时 `t=clip(log(A/100)/log(2000/100),0,1)`，峰高为 `300+2700*t`，再乘固定0.9–1.1扰动。资格门槛25km²与峰高曲线起点100km²分别处理：新纳入的25–100km²岛requested峰高为300m加固定±10%波动，已有岛的目标峰高不因放宽资格而变化。2000km²仍为高度饱和参考。无波动时100/200/500/1000/2000km²分别约300/925/1751/2375/3000m。固定岛key下随面积单调；不同岛的波动可能改变相近面积岛的高低顺序。

稳定key来自岛产品和组件全局首格，窗口、tile、请求顺序不改变目标；参数及target进入计划身份。当前算法`island-mountains-area-peaks-v3`，政策`frozen-island-global-raw-area-peak-v3`。旧v1/v2按原政策只读回放，派生另存。

## 整岛统一高度

先准备或复用完整岛的30m raw TD，第一遍统计全岛raw范围，第二遍求共同scale。令`u=clip((raw-min)/(max-min),0,1)`、`a=base*(1-w)+w*land_floor`，最终`a+scale*w*u`；常量raw确定使用u=1。所有tile共用统计与scale，避免独立归一化接缝。

共同scale使完整岛30m采样最高点达到effective target。岸线保护底座a高于requested时，明确记录约束和effective；超过配置总允许上限则拒绝。海水、潟湖、原陆与零权重处保留base，原raw不变。缺块组件pending，不宣称峰高完成。保证针对30m采样，2km世界图可能错过最高点。

公开API：`analyze_island_mountains`、`save_mountain_plan`、`load_mountain_plan`、`sample_mountain_weights`、`sample_mountain_components`、`component_native_tiles`、`PeakNormalizationBuilder`、`apply_peak_surface`。原始TD/plan/normalization与派生SHA绑定，缓存按新身份隔离。

## 普通世界生成

织梦后端已接入：骨架→冻结岛屿及计划→岛屿TD调度→最终世界高程/侵蚀/海陆与水系→图集。GPU选项显式准备；CPU发布pending，不启动模型。地图查询只读。派生相对解析岛基底的delta先加入世界岛体target，再统一处理下游，地图与图集读取同一最终场。

全源1km分析默认预算4M格，更大世界用固定完整feature支持组的局部计划；不按查询改变资格精度。超大单组明确pending-analysis，不等同于完整无限上游完成。

TG计划CLI支持所有配置参数；织梦`prepare_island_mountains.py`支持`--raw-root`复用冻结raw、重复`--tile`显式子集及`--dry-run`。普通GPU世界任务默认全合格岛；子集其他岛pending。显存/内存门槛保持。

旧v3产品在25km²资格下真实主源24岛合格、面积27–323km²，所需去重原生30m块数86；旧100km²资格为12岛、61块。原12岛的面积/key/requested峰高逐项不变，新增12岛。详见[25km²调整记录](../.scratch/ocean-islands-20261106/area25-relaxation/review.md)。同源v4默认火山情景有3个特殊火山组件保留解析锥体、21个普通TD合格组件，见[火山验收](../.scratch/volcanic-islands-20261107/review.md)。真实TD单tile及最终世界消费已验证；完整真实岛新峰高验证因主机可用内存不足被门槛拒绝，未降门槛。旧模型验收见[原验收](../.scratch/ocean-islands-20261106/area100-world-system-v3/review.md)；本次未启动模型，原计划与raw保留。
