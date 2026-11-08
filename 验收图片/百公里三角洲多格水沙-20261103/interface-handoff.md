# 百公里三角洲接口与采样语义

本文件描述有限域工程接口；最终通过状态以主端验收报告及根验收图片中的README为准。来源为历史种子20261020的Voronoi板块/真实TD，原生TD30m，本案例派生计算格距600m。新正式世界种子按CONTRIBUTING.md。

## 已接通的链

`coastal_marine_product.prepare` 的沿岸宽陆架情景 → `coastal_delta_geological` 的有限物源地质构造 → `finalize_for_event` 限定真实物理悬沙并保留未分配量 → `coastal_delta_geological_network.construct` 复用非规则谷线及河宽材料接口 → `coastal_delta_evolution.advance_years/advance_event` → 共享海洋床沙、潮浪与实际口门交付。

地质构造的等效年与混合sweep不是物理秒，强迫不是实测上游流域水沙。四口初态是明确构造的多级分叉，不能称为本案例自发产生四次改道。先前小例的动态新汊与口门迁移证据保留在旧任务，不能直接移植成百公里已验结果。

## 读写与续算

```python
from terrain_pipeline.coastal_delta_evolution import load, save, advance_event
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig
from terrain_pipeline.coastal_marine_sediment import MarineConfig

state, progress = load(checkpoint_prefix)  # 配对 .npz / .json，不带扩展名
dem = state.bed_m  # 米，含孔隙沉积后的600m格平均床面
origin_x, origin_z = state.origin_xz_m
# 行r、列c的中心世界坐标: x=origin_x+c*spacing, z=origin_z+r*spacing
cfg = MarineConfig(step_s=600., tide_amplitude_m=.3, wave_height_m=.5,
    settling_velocity_m_s=.001, settling_rate_s=0., minimum_depth_m=1.,
    transport_rate_s=1e-6, entrainment_rate_s=1e-7,
    material_source='declared homogeneous scenario')
next_state, result = advance_event(state, progress, duration_s, cfg,
    input_id=unique_id, hydraulic_config=HydraulicConfig(15.),
    inlet_solid_rate_m3_s=20.)
save(new_checkpoint_prefix, next_state, result['updated_progress'])
```

输入ID不能重复；续算继承库存和物理时钟，不重复注入地质输入。一个完整事件用一次调用：活动层侵蚀额度按事件设定，拆成多次调用会改变该上限的语义。JSON记录已接收、未交付及内部搬运；内部gross交海不是新外源，不能重复加入总预算。`unresolved_solid_m3` 不自动供给物理河流。

## 消费者必须区分的几何

| 数据 | 含义 |
| --- | --- |
| `state.bed_m` | 600m格平均床面；不是30m河床DEM |
| `progress.route_geometry.nodes` | 复用非规则路径得到的实际XZ；不能以行列中心取代 |
| `progress.routes` | 共享前缀河网拓扑；共享河段只计一次流量/库存 |
| `hydraulic_sections.nodes` | 节点细槽床、有效宽、岸高等，不等于粗格高程 |
| `node_footprints` | 跨格独占面积份额及床沙/移动/滞留固体库存 |
| `river_hydraulics` | 指定海位和床面上求出的实际水面、流量、活动口门 |

`ChannelInventory` 负责细槽与粗格所有权同步；整格海洋更新后调用 `apply_grid_changes` 并 `commit`，不能拿粗格平均床面覆盖细槽。事件内保持平面足迹，垂向床面/水深/流量会变化。宽度由流量和材料初始设计，再受实际占地支持范围约束；连续横向岸蚀需另行更新足迹。

现已补充 `coastal_delta_avulsion.extend_mouths` 的多格适配：使用既有非规则谷线，在有限半径内寻找真实外海，新增短槽只接收未占用outer的面积和库存；旧parts保持。物理事件及年度步骤末尾进行显式追岸，属于离散形态更新；不能把它解释为每秒连续岸蚀。无可行路径时保留真实关闭及原因。允许的切槽只扣已有沉积，挖沙转移动库存，原基底不切。

`integrated.owner_cells` 的前六列为行、列、fine面积份额、fine床沙、mobile、stranded，后三列为基底/几何参考字段。最终v3存档已补齐统一九列；早期v1/v2试验的新行曾仅六列，不作为当前接口交付。权威基底来自state数组。新增河段及原末端的有效宽均按更新后的面积/控制长度同步。

出露陆块会被河道分割。尺寸分别报告总出露面积、最大单块和共同成因沉积体；沉积体含河槽和水下叶瓣，以高于派生陆架床面1m的连通厚沉积识别，不能把整张画布当三角洲。

## 明确限制

- 年度多格接口单次至多一年、需显式水力配置；未接年度潮位分相或外部水力解。年度固定足迹沉降为工程近似。
- 物理河段处理有限携沙与侵蚀，海洋使用已有潮浪搬运/沉降；不等同于全二维浅水动力或混合粒径模型。
- 默认漫滩距离400m小于本例600m格距，本例没有解析到漫滩交换。细潮沟、窄沙洲及真实30m局部细化仍需局部更细产品。
- 初始地质平原较平滑，前缘和部分河段仍有简化形态；数值混合强度未标定为真实年代。
- 不自动接默认世界、前端或跨区域调度。有限窗口成功不等于万公里世界或无限生成性质已验。
