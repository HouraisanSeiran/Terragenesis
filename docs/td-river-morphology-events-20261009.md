# TD 河网形态事件 V1

## 统一事件

`terrain_pipeline/surface_rivers/metric_morphology_events.py` 定义 `MorphologyEvent`。事件绑定父图身份、父几何身份、受影响边、增加边、退役边、水量转移、固体泥沙转移、材料账、参数和重验范围。

事件状态目前允许 `candidate`、`bounded`、`validated`。第一版三角洲和截弯结果均为 `candidate`，并保持 `hydraulic_ready=false`、`natural_outlet_verified=false`、`publishable=false`。

事件记录可通过 `to_record()` / `event_from_record()` 往返，身份由完整记录计算；参数和账本在对象内冻结。拓扑事件不能只改一条线，必须声明旧边、增加边和后续重验。

## 河口三角洲 V1

入口：`terrain_pipeline.surface_rivers.metric_delta.build_delta_candidate`。

输入为 `TerrainGrid`、土地掩膜、水体掩膜、相邻主河路径、固体泥沙输入以及父图/父几何身份。算法要求主路径存在合法陆地到水体入口，并只消费该入口所属的四邻域连通水体。

输出为：

- 水域内沉积高度候选 `height_delta_m` 和 `deposit_mask`。
- 水体连通掩膜 `water_component_mask`。
- 有界确定性分汊线候选，不直接改写河网。
- `deposited_solid_m3`、`unresolved_solid_m3`、孔隙沉积体积和事件身份。

沉积按前向/侧向权重分配，每个格子有最大沉积深度。固体输入满足：

```text
input_solid = deposited_solid + unresolved_solid
```

当前版本不模拟潮汐、波浪、岸线推进、海岸漂移、真实分汊水动力或分汊拓扑写回。它是可审查的河口沉积候选，后续需要接入湖海边界、M6材料账和共同水面。

## 截弯取直 V1

入口：`terrain_pipeline.surface_rivers.metric_cutoff.find_cutoff_candidate`。

输入为有效米制地形、连续中心线、每段唯一边身份、父图/父几何身份及要转移的水量和泥沙量。算法查找非相邻中心线节点组成的河颈，要求：

- 河颈距离在 `neck_distance_m` 内。
- 原曲流长度减捷径长度达到 `min_loop_length_m`。
- 捷径沿线全部位于有效地形。
- 捷径最高床面不超过端点高程加 `max_bed_rise_m`。
- 不穿过其他中心线段。

输出新捷径、保留的旧曲流 `loop_xz_m`、牛轭湖候选、节省长度和 `cutoff` 事件。旧曲流不会被删除；事件将旧边标为退役候选并要求后续湖泊、几何、水动力和泥沙重验。

当前版本不执行图拓扑写回、不重算水量、不生成真实湖泊水面，也不表示自然截弯已经发生。合法河颈不存在时返回明确拒绝状态。

## 河岸冲刷与分汊 V1

入口：`terrain_pipeline.surface_rivers.metric_bank_braiding.py`。

`build_bank_pointbar_candidate` 根据中心线局部曲率生成外弯冲刷和内弯点坝候选，限制最大冲刷/沉积深度并保护unknown；事件类型为 `bank_migration`。`build_braided_candidate` 在合法湿区内生成2到3条共享入口/出口的有限分汊候选，记录流量比例、沙洲掩膜和沉积账；它不写回 `RoutingGraph`。

## 冲积扇与洪泛平原 V1

入口：`terrain_pipeline.surface_rivers.metric_fan_floodplain.py`。

`build_alluvial_fan_candidate` 从山口沿流向和扇形角度生成有限沉积扇，检查有效地形/坡降并保存沉积与未解析固体。`build_floodplain_candidate` 沿中心线生成受最大宽度、河岸高程和水深限制的洪泛带，输出湿润足迹和 `storage_proxy_m3`；storage proxy 不伪装成河道流量。

两个候选都保持水动力、自然出口和发布能力为 false，真实TD接入和保存后冷审仍待完成。

## 测试边界

`tests/test_metric_morphology_events.py`、`tests/test_metric_delta.py`、`tests/test_metric_delta_product.py`、`tests/test_metric_cutoff.py`、`tests/test_metric_bank_braiding.py` 和 `tests/test_metric_fan_floodplain.py` 共22项定向测试通过，覆盖身份往返、篡改拒绝、沉积守恒、容量未解析库存、曲率冲刷/点坝、有限分汊、冲积扇、洪泛带、U形河颈、unknown/高程障碍和确定性。

真实TD全域事件尚未运行。本版应选择已保存TD局部河段和明确的局部水陆解释，生成独立候选包，再由冷审检查父身份、唯一材料所有权和重验依赖；不能直接接入默认世界或Minecraft。

2026-10-10 已完成真实TD256局部候选集：`verification/td-morphology-candidates/td256-20261010-01/`，并通过独立冷审：`verification/td-morphology-candidates/td256-20261010-01-audit-05/audit.json`。它绑定原始TD文件SHA `6e7fdf63dc02e9f14e7d83550d0c5f806b42aa7f13367ea96012787bcf069382`、来源身份、已保存原床D8图身份和局部解释身份，包含 `delta`、`cutoff`、`bank_pointbar`、`braided`、`alluvial_fan`、`floodplain` 六项产物。该包是候选集，不是自然河口、真实水陆边界或水动力通过证书；六项能力保持 false。
