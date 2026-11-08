# 第2阶段模块细分

此表按职责关联；同一owner可出现多次。主归属只计一次；关联不代表完整实现、默认接线或验收通过。工具/测试列表另见support.md。

## S2/G1 大尺度构造、山系、盆地与地形背景

关联文件 36 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [diffusion/__init__.py](../../../diffusion/__init__.py) | 跨项关联 | True learned terrain generation; never falls back to procedural mountain shapes. |
| [diffusion/__main__.py](../../../diffusion/__main__.py) | 跨项关联 | 职责待人工核对；仅登记可确认的静态结构 |
| [diffusion/backend.py](../../../diffusion/backend.py) | 跨项关联 | Pinned upstream model adapter. One seed at a time; caller serializes access. |
| [diffusion/config.py](../../../diffusion/config.py) | 跨项关联 | Immutable generation identity, shared by cache and runtime protocol. |
| [diffusion/geographic_noise.py](../../../diffusion/geographic_noise.py) | 主归属 | Tile-independent smooth noise from absolute conditioning-grid coordinates. |
| [diffusion/geography.py](../../../diffusion/geography.py) | 主归属 | Seeded geographic conditioning for the unchanged five-channel diffusion model. Coordinates are the upstream conditioning grid, not Minecraft blocks. The field i… |
| [diffusion/geography_physical.py](../../../diffusion/geography_physical.py) | 主归属 | Coordinate-continuous physical conditioning, not model-generated terrain. |
| [diffusion/geography_v2.py](../../../diffusion/geography_v2.py) | 主归属 | Versioned geographic conditioning with wider, intermittent mountain masses. |
| [diffusion/geography_v3.py](../../../diffusion/geography_v3.py) | 主归属 | Versioned low-relief geographic conditioning for the metre-scale consumer. |
| [diffusion/geography_v4.py](../../../diffusion/geography_v4.py) | 主归属 | Versioned metre-scale conditioning with bounded ocean depth. |
| [diffusion/geography_v5.py](../../../diffusion/geography_v5.py) | 主归属 | Coordinate-continuous soft-knee base conditioning with separate relief. |
| [diffusion/paths.py](../../../diffusion/paths.py) | 跨项关联 | Keep runtime, model and derived artifacts under the project root. |
| [diffusion/physical_backend.py](../../../diffusion/physical_backend.py) | 跨项关联 | Opt-in local TD inference; no legacy runtime or game-coordinate conversion. |
| [diffusion/physical_config.py](../../../diffusion/physical_config.py) | 跨项关联 | Independent metre-space identity; never a Minecraft generation profile. |
| [diffusion/plate_td_backend.py](../../../diffusion/plate_td_backend.py) | 跨项关联 | Explicit spawned, budget-supervised frozen-plate TD inference. |
| [diffusion/plate_td_conditioning.py](../../../diffusion/plate_td_conditioning.py) | 主归属 | Frozen tectonic conditioning for the physical TD checkpoint. All queries use absolute coordinates. The product's finite rectangle is enforced; its bilinear inte… |
| [diffusion/preview.py](../../../diffusion/preview.py) | 跨项关联 | Export unmodified model output, slope and provenance before any erosion. |
| [diffusion/service.py](../../../diffusion/service.py) | 跨项关联 | Serialized model access, bounded HTTP protocol; raw meters remain in persistent cache. |
| [diffusion/store.py](../../../diffusion/store.py) | 跨项关联 | Atomic, checksummed raw diffusion tiles. World seed and model settings isolate caches. |
| [diffusion/world_demand_backend.py](../../../diffusion/world_demand_backend.py) | 跨项关联 | Fixed physical TD page grid and supervised on-demand generation; resume pinned pages and retain failure records. |
| [diffusion/world_layout_backend.py](../../../diffusion/world_layout_backend.py) | 跨项关联 | 独立新布局单页TD入口，绝对坐标与一致种子、Windows spawn和资源停止；默认PID监测，WDDM不可测时拒绝；显式allocator选项仅限PyTorch配额/峰值，不覆盖驱动和其他进程。 |
| [diffusion/world_layout_conditioning.py](../../../diffusion/world_layout_conditioning.py) | 主归属 | 连续布局场转换为湖盆岸坡TD条件通道，确定性选岸边局部页并遵守上游signed-sqrt输入协议；气候为声明占位。 |
| [terrain_pipeline/coastal_terrain.py](../../../terrain_pipeline/coastal_terrain.py) | 主归属 | 海岸底图、海岸细化与群岛产品线（A 类）。 合并自 `coastal_detail_refinement`、`coastal_archipelago`、`coastal_terrain_product`、 `coastal_archipelago_product`、`coastal_detail_product`（本模… |
| [terrain_pipeline/fictional_world_overview.py](../../../terrain_pipeline/fictional_world_overview.py) | 主归属 | Finite 1600 km fictional-world overview: three continents, islands, mountains, rivers. What this module produces ------------------------- One low-resolution **… |
| [terrain_pipeline/island_mountains.py](../../../terrain_pipeline/island_mountains.py) | 主归属 | Fixed-grid, CPU-only qualification of exposed islands for explicit TD work. Default qualification is exposed area strictly greater than 100 square km. Width fil… |
| [terrain_pipeline/metric_region.py](../../../terrain_pipeline/metric_region.py) | 主归属 | Physical-metre regional landform processing. |
| [terrain_pipeline/metric_region_storage.py](../../../terrain_pipeline/metric_region_storage.py) | 跨项关联 | Explicit publication and read-only loading for metric region results. |
| [terrain_pipeline/mountain_forms.py](../../../terrain_pipeline/mountain_forms.py) | 主归属 | 山体形态生成：骨架、体量、破碎、山带与过程证据（A 类）。 合并自 `advanced_terrain_filter`、`product_mountains`、`local_volume_mountains`、 `procedural_mountains`、`voronoi_mountains`、`ridge_brea… |
| [terrain_pipeline/ocean_island_consumers.py](../../../terrain_pipeline/ocean_island_consumers.py) | 主归属 | CPU consumers of one frozen ocean-island plan, in absolute X/Z metres. Raster centres and finite area samples are derived views. The feature inventory remains a… |
| [terrain_pipeline/ocean_islands.py](../../../terrain_pipeline/ocean_islands.py) | 主归属 | Explicitly prepared ocean landforms on a finite, immutable plate background. Coordinates are metres, X east / Z south; ages are uncalibrated offline steps. This… |
| [terrain_pipeline/procedural_mountain_erosion.py](../../../terrain_pipeline/procedural_mountain_erosion.py) | 主归属 | Pointwise directional gully appearance, algorithm ``directional-gullies-v1``. A method-level adaptation of Rune Skovbo Johansen's Advanced Terrain Erosion Filte… |
| [terrain_pipeline/skeleton_mountains.py](../../../terrain_pipeline/skeleton_mountains.py) | 主归属 | World-anchored curved ridge ribbons and variable asymmetric sections. Coordinates/heights are metres, slopes metres/metre. Each independent source has three pri… |
| [terrain_pipeline/td_source.py](../../../terrain_pipeline/td_source.py) | 跨项关联 | 固定TD可信源的连续宏观基底与局部残差合成；全有限世界海洋分量规划、精确场岸线、过滤halo内固定裁切；千湖无预置水体。；显式大域磁盘预算、分块TD合成与不可变发布；相邻请求统一求解，冷读校验保存块。；Assemble trusted pinned TD support, verify overlaps and com… |
| [terrain_pipeline/tectonic.py](../../../terrain_pipeline/tectonic.py) | 主归属 | 板块构造演化、冻结宏观产品与板块条件 TD 源（A 类）。 合并自 `tectonic_shapes`、`tectonic_formation`、`tectonic_evolution`、`tectonic_product`、 `plate_td_product` 五个旧实现。代码逐块原样保留，只对同组重名符号起命名变… |
| [terrain_pipeline/world_water_formation.py](../../../terrain_pipeline/world_water_formation.py) | 跨项关联 | 合成床面接现有洼地、认证湖盆、有限蓄满溢流与岩性河槽核；分别保存普通汇流和实际溢流路径，待定状态传播至稳定，逐盆地及全域水量记账。 |
| [terrain_pipeline/world_water_layout.py](../../../terrain_pipeline/world_water_layout.py) | 主归属 | 固定世界坐标的大陆/千岛/千湖连续多尺度布局；有限世界按固定全域样本确定水比阈值，无限模式使用固定参考范围；不生成TD、不认证水文拓扑。 |

## S2/G2 岩性、层序、断层与材料场

关联文件 6 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [terrain_pipeline/environment_contract.py](../../../terrain_pipeline/environment_contract.py) | 跨项关联 | Consolidated environment_contract implementations; numeric expressions preserved. |
| [terrain_pipeline/environment_product.py](../../../terrain_pipeline/environment_product.py) | 跨项关联 | Consolidated environment_product implementations; numeric expressions preserved. |
| [terrain_pipeline/environment_query.py](../../../terrain_pipeline/environment_query.py) | 跨项关联 | 绝对30m坐标批量组合现气候/材料/岩性/土壤代理/群系，绑定输入和依赖源码身份；实测DEM雨影缺覆盖时明确pending/背景估计，精确请求内缓存；不推进动态ET、植被或默认世界。 |
| [terrain_pipeline/geology.py](../../../terrain_pipeline/geology.py) | 主归属 | Consolidated geology implementations; numeric expressions preserved. |
| [terrain_pipeline/tectonic.py](../../../terrain_pipeline/tectonic.py) | 跨项关联 | 板块构造演化、冻结宏观产品与板块条件 TD 源（A 类）。 合并自 `tectonic_shapes`、`tectonic_formation`、`tectonic_evolution`、`tectonic_product`、 `plate_td_product` 五个旧实现。代码逐块原样保留，只对同组重名符号起命名变… |
| [terrain_pipeline/vdm_cuts.py](../../../terrain_pipeline/vdm_cuts.py) | 跨项关联 | 当前断层recipe类型与选择权重公共职责，不保留v1完整生成算法。；保留已变形VDM来源的局部断层切割，保存边来源与插值证据；只认证已声明的局部几何范围。 |

## S2/G3 冷暖背景、海拔降温与季节温度

关联文件 13 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [diffusion/geographic_noise.py](../../../diffusion/geographic_noise.py) | 跨项关联 | Tile-independent smooth noise from absolute conditioning-grid coordinates. |
| [diffusion/geography.py](../../../diffusion/geography.py) | 跨项关联 | Seeded geographic conditioning for the unchanged five-channel diffusion model. Coordinates are the upstream conditioning grid, not Minecraft blocks. The field i… |
| [diffusion/geography_physical.py](../../../diffusion/geography_physical.py) | 跨项关联 | Coordinate-continuous physical conditioning, not model-generated terrain. |
| [diffusion/geography_v2.py](../../../diffusion/geography_v2.py) | 跨项关联 | Versioned geographic conditioning with wider, intermittent mountain masses. |
| [diffusion/geography_v3.py](../../../diffusion/geography_v3.py) | 跨项关联 | Versioned low-relief geographic conditioning for the metre-scale consumer. |
| [diffusion/geography_v4.py](../../../diffusion/geography_v4.py) | 跨项关联 | Versioned metre-scale conditioning with bounded ocean depth. |
| [diffusion/geography_v5.py](../../../diffusion/geography_v5.py) | 跨项关联 | Coordinate-continuous soft-knee base conditioning with separate relief. |
| [diffusion/plate_td_conditioning.py](../../../diffusion/plate_td_conditioning.py) | 跨项关联 | Frozen tectonic conditioning for the physical TD checkpoint. All queries use absolute coordinates. The product's finite rectangle is enforced; its bilinear inte… |
| [diffusion/world_layout_conditioning.py](../../../diffusion/world_layout_conditioning.py) | 跨项关联 | 连续布局场转换为湖盆岸坡TD条件通道，确定性选岸边局部页并遵守上游signed-sqrt输入协议；气候为声明占位。 |
| [terrain_pipeline/climate_forcing.py](../../../terrain_pipeline/climate_forcing.py) | 主归属 | v2合成气候修正层：风、地形抬升/雨影及温雨诊断；接口验收不等于生产季节水文默认接线。 |
| [terrain_pipeline/environment_contract.py](../../../terrain_pipeline/environment_contract.py) | 跨项关联 | Consolidated environment_contract implementations; numeric expressions preserved. |
| [terrain_pipeline/environment_product.py](../../../terrain_pipeline/environment_product.py) | 跨项关联 | Consolidated environment_product implementations; numeric expressions preserved. |
| [terrain_pipeline/environment_query.py](../../../terrain_pipeline/environment_query.py) | 跨项关联 | 绝对30m坐标批量组合现气候/材料/岩性/土壤代理/群系，绑定输入和依赖源码身份；实测DEM雨影缺覆盖时明确pending/背景估计，精确请求内缓存；不推进动态ET、植被或默认世界。 |

## S2/G4 风场、地形增雨与雨影

关联文件 13 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [diffusion/geographic_noise.py](../../../diffusion/geographic_noise.py) | 跨项关联 | Tile-independent smooth noise from absolute conditioning-grid coordinates. |
| [diffusion/geography.py](../../../diffusion/geography.py) | 跨项关联 | Seeded geographic conditioning for the unchanged five-channel diffusion model. Coordinates are the upstream conditioning grid, not Minecraft blocks. The field i… |
| [diffusion/geography_physical.py](../../../diffusion/geography_physical.py) | 跨项关联 | Coordinate-continuous physical conditioning, not model-generated terrain. |
| [diffusion/geography_v2.py](../../../diffusion/geography_v2.py) | 跨项关联 | Versioned geographic conditioning with wider, intermittent mountain masses. |
| [diffusion/geography_v3.py](../../../diffusion/geography_v3.py) | 跨项关联 | Versioned low-relief geographic conditioning for the metre-scale consumer. |
| [diffusion/geography_v4.py](../../../diffusion/geography_v4.py) | 跨项关联 | Versioned metre-scale conditioning with bounded ocean depth. |
| [diffusion/geography_v5.py](../../../diffusion/geography_v5.py) | 跨项关联 | Coordinate-continuous soft-knee base conditioning with separate relief. |
| [diffusion/plate_td_conditioning.py](../../../diffusion/plate_td_conditioning.py) | 跨项关联 | Frozen tectonic conditioning for the physical TD checkpoint. All queries use absolute coordinates. The product's finite rectangle is enforced; its bilinear inte… |
| [diffusion/world_layout_conditioning.py](../../../diffusion/world_layout_conditioning.py) | 跨项关联 | 连续布局场转换为湖盆岸坡TD条件通道，确定性选岸边局部页并遵守上游signed-sqrt输入协议；气候为声明占位。 |
| [terrain_pipeline/climate_forcing.py](../../../terrain_pipeline/climate_forcing.py) | 跨项关联 | v2合成气候修正层：风、地形抬升/雨影及温雨诊断；接口验收不等于生产季节水文默认接线。 |
| [terrain_pipeline/environment_contract.py](../../../terrain_pipeline/environment_contract.py) | 跨项关联 | Consolidated environment_contract implementations; numeric expressions preserved. |
| [terrain_pipeline/environment_product.py](../../../terrain_pipeline/environment_product.py) | 跨项关联 | Consolidated environment_product implementations; numeric expressions preserved. |
| [terrain_pipeline/environment_query.py](../../../terrain_pipeline/environment_query.py) | 跨项关联 | 绝对30m坐标批量组合现气候/材料/岩性/土壤代理/群系，绑定输入和依赖源码身份；实测DEM雨影缺覆盖时明确pending/背景估计，精确请求内缓存；不推进动态ET、植被或默认世界。 |

## S2/G5 季节、降水、蒸散与水分平衡

关联文件 15 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [terrain_pipeline/climate_forcing.py](../../../terrain_pipeline/climate_forcing.py) | 跨项关联 | v2合成气候修正层：风、地形抬升/雨影及温雨诊断；接口验收不等于生产季节水文默认接线。 |
| [terrain_pipeline/environment_contract.py](../../../terrain_pipeline/environment_contract.py) | 跨项关联 | Consolidated environment_contract implementations; numeric expressions preserved. |
| [terrain_pipeline/environment_product.py](../../../terrain_pipeline/environment_product.py) | 跨项关联 | Consolidated environment_product implementations; numeric expressions preserved. |
| [terrain_pipeline/environment_query.py](../../../terrain_pipeline/environment_query.py) | 跨项关联 | 绝对30m坐标批量组合现气候/材料/岩性/土壤代理/群系，绑定输入和依赖源码身份；实测DEM雨影缺覆盖时明确pending/背景估计，精确请求内缓存；不推进动态ET、植被或默认世界。 |
| [terrain_pipeline/environment_regional_hydraulics.py](../../../terrain_pipeline/environment_regional_hydraulics.py) | 跨项关联 | Consolidated environment_regional_hydraulics implementations; numeric expressions preserved. |
| [terrain_pipeline/large_delta_source.py](../../../terrain_pipeline/large_delta_source.py) | 跨项关联 | Whole-support known-local runoff under an explicitly full reservoir boundary. |
| [terrain_pipeline/runoff.py](../../../terrain_pipeline/runoff.py) | 跨项关联 | 对选定汇水调用已有土壤桶与reach时延路由，分别记录声明风暴设计峰值和瞬时诊断Q。 |
| [terrain_pipeline/soil_water.py](../../../terrain_pipeline/soil_water.py) | 主归属 | 材料厚度、坡度与年降雨输入的土壤合成条件代理；available_water不等同动态ET闭合含水量。 |
| [terrain_pipeline/surface_rivers/metric_domain_flow.py](../../../terrain_pipeline/surface_rivers/metric_domain_flow.py) | 跨项关联 | 域水量账本与本地产流拓扑累计；瓦片尺度证据不能自动认证跨瓦片累计输运。 |
| [terrain_pipeline/surface_rivers/metric_output.py](../../../terrain_pipeline/surface_rivers/metric_output.py) | 跨项关联 | Sample diagnostic hydrology states and integrate interval-average release. |
| [terrain_pipeline/surface_rivers/metric_water_cycle.py](../../../terrain_pipeline/surface_rivers/metric_water_cycle.py) | 跨项关联 | Cold-auditable finite TD runoff/channel/lake evidence; no new solver. |
| [terrain_pipeline/surface_rivers/native_30m_hydrology_event.py](../../../terrain_pipeline/surface_rivers/native_30m_hydrology_event.py) | 跨项关联 | Opt-in per-cell hydrology account for one declared native-30 m catchment event. Why this module exists rather than a keyword on ``run_catchment_event`` --------… |
| [terrain_pipeline/surface_rivers/native_30m_hydrology_ledger.py](../../../terrain_pipeline/surface_rivers/native_30m_hydrology_ledger.py) | 跨项关联 | Per-cell, per-interval hydrology accounts for the native-30 m catchment event. Scope of this module -------------------- This is an **accounting layer**. It add… |
| [terrain_pipeline/td_candidate_weather_jobs.py](../../../terrain_pipeline/td_candidate_weather_jobs.py) | 跨项关联 | Serial candidate weather plans and externally pinned cold execution evidence. |
| [terrain_pipeline/td_native_weather_storage_inputs.py](../../../terrain_pipeline/td_native_weather_storage_inputs.py) | 跨项关联 | Pure spatial-weather input contract for a separate v9 continuation acceptance. |

## S2/G6 土壤、地表覆盖与生态条件

关联文件 5 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [terrain_pipeline/environment_contract.py](../../../terrain_pipeline/environment_contract.py) | 跨项关联 | Consolidated environment_contract implementations; numeric expressions preserved. |
| [terrain_pipeline/environment_product.py](../../../terrain_pipeline/environment_product.py) | 跨项关联 | Consolidated environment_product implementations; numeric expressions preserved. |
| [terrain_pipeline/environment_query.py](../../../terrain_pipeline/environment_query.py) | 跨项关联 | 绝对30m坐标批量组合现气候/材料/岩性/土壤代理/群系，绑定输入和依赖源码身份；实测DEM雨影缺覆盖时明确pending/背景估计，精确请求内缓存；不推进动态ET、植被或默认世界。 |
| [terrain_pipeline/environment_regional_hydraulics.py](../../../terrain_pipeline/environment_regional_hydraulics.py) | 跨项关联 | Consolidated environment_regional_hydraulics implementations; numeric expressions preserved. |
| [terrain_pipeline/soil_water.py](../../../terrain_pipeline/soil_water.py) | 跨项关联 | 材料厚度、坡度与年降雨输入的土壤合成条件代理；available_water不等同动态ET闭合含水量。 |

## S2/G7 雪、积雪、冰川与融水

关联文件 3 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [terrain_pipeline/environment_contract.py](../../../terrain_pipeline/environment_contract.py) | 跨项关联 | Consolidated environment_contract implementations; numeric expressions preserved. |
| [terrain_pipeline/environment_product.py](../../../terrain_pipeline/environment_product.py) | 跨项关联 | Consolidated environment_product implementations; numeric expressions preserved. |
| [terrain_pipeline/soil_water.py](../../../terrain_pipeline/soil_water.py) | 跨项关联 | 材料厚度、坡度与年降雨输入的土壤合成条件代理；available_water不等同动态ET闭合含水量。 |

## S2/G8 洋流、海温、海岸与河口

关联文件 95 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [terrain_pipeline/coastal_delta_avulsion.py](../../../terrain_pipeline/coastal_delta_avulsion.py) | 跨项关联 | Activate terrain-derived candidate distributaries under measured river head. |
| [terrain_pipeline/coastal_delta_bank_formation.py](../../../terrain_pipeline/coastal_delta_bank_formation.py) | 跨项关联 | Explicit, conservative bank preparation using lagged saved water stages. |
| [terrain_pipeline/coastal_delta_branch_attachment.py](../../../terrain_pipeline/coastal_delta_branch_attachment.py) | 跨项关联 | 职责待人工核对；仅登记可确认的静态结构 |
| [terrain_pipeline/coastal_delta_branching.py](../../../terrain_pipeline/coastal_delta_branching.py) | 跨项关联 | Optional, conservative distributary experiment over the shared marine stock. Routes are D4-connected raster corridors, not resolved hydraulics. Depositional obs… |
| [terrain_pipeline/coastal_delta_deposition_scaling.py](../../../terrain_pipeline/coastal_delta_deposition_scaling.py) | 跨项关联 | Empirical conversion of a reference reach deposition fraction by length. |
| [terrain_pipeline/coastal_delta_evolution.py](../../../terrain_pipeline/coastal_delta_evolution.py) | 跨项关联 | Finite overbank exchange on a shared marine sediment state. This optional building block treats channel stage and throughflow as boundary conditions. It does no… |
| [terrain_pipeline/coastal_delta_formation.py](../../../terrain_pipeline/coastal_delta_formation.py) | 跨项关联 | Delta formation API; the rejected prototype is archived in .scratch. |
| [terrain_pipeline/coastal_delta_geological.py](../../../terrain_pipeline/coastal_delta_geological.py) | 跨项关联 | Finite-volume, coarse geological sediment spreading on a MarineState. Transport sweeps are numerical redistribution iterations, not physical seconds. The inunda… |
| [terrain_pipeline/coastal_delta_geological_network.py](../../../terrain_pipeline/coastal_delta_geological_network.py) | 跨项关联 | Connect explicitly chosen coastal outlets using irregular valley geometry. |
| [terrain_pipeline/coastal_delta_growth.py](../../../terrain_pipeline/coastal_delta_growth.py) | 跨项关联 | Shoreline-driven, finite-stock extensions of the v7 delta network. |
| [terrain_pipeline/coastal_delta_hydraulic_capacity.py](../../../terrain_pipeline/coastal_delta_hydraulic_capacity.py) | 跨项关联 | Hydraulic sediment-transport capacity for multi-cell delta channel nodes (issue 24). Opt-in rule that replaces the legacy ``capacity = Q * 0.01 * duration`` lim… |
| [terrain_pipeline/coastal_delta_hydraulic_event.py](../../../terrain_pipeline/coastal_delta_hydraulic_event.py) | 跨项关联 | Opt-in physical event for multi-cell deltas with hydraulic transport capacity (issue 24). Mirrors ``coastal_delta_multicell.advance_event`` (which stays unchang… |
| [terrain_pipeline/coastal_delta_lobes.py](../../../terrain_pipeline/coastal_delta_lobes.py) | 跨项关联 | Experimental shoreline lobe switching over the single formation ledger. Scores use local water-column accommodation and finite deposit blockage. They are game-s… |
| [terrain_pipeline/coastal_delta_morphology.py](../../../terrain_pipeline/coastal_delta_morphology.py) | 跨项关联 | Explicit, finite morphology preparation and representative discharge capture. |
| [terrain_pipeline/coastal_delta_mouth_extension.py](../../../terrain_pipeline/coastal_delta_mouth_extension.py) | 跨项关联 | Finite shoreline extension using only unowned multi-cell inventory. |
| [terrain_pipeline/coastal_delta_multicell.py](../../../terrain_pipeline/coastal_delta_multicell.py) | 跨项关联 | Fixed-footprint annual and physical exchange for multi-cell channels. |
| [terrain_pipeline/coastal_delta_multicell_avulsion.py](../../../terrain_pipeline/coastal_delta_multicell_avulsion.py) | 跨项关联 | Bounded deposition-triggered trials for multi-cell distributaries. |
| [terrain_pipeline/coastal_delta_network_plan.py](../../../terrain_pipeline/coastal_delta_network_plan.py) | 跨项关联 | Deterministic, bounded distributary planning on a connected coastal plain. The resulting forks and route shares are inputs to geological_network.construct. Dept… |
| [terrain_pipeline/coastal_delta_node_inventory.py](../../../terrain_pipeline/coastal_delta_node_inventory.py) | 跨项关联 | Conservative ownership of multi-cell channel-node sediment inventories. |
| [terrain_pipeline/coastal_delta_pipeline.py](../../../terrain_pipeline/coastal_delta_pipeline.py) | 跨项关联 | Entry point for a single irregular trunk and subsequent candidate refresh. |
| [terrain_pipeline/coastal_delta_plain.py](../../../terrain_pipeline/coastal_delta_plain.py) | 跨项关联 | Statistical tidal windows for finite-source distributary formation. Each equal-weight phase represents a fraction of equivalent geological time; physical event … |
| [terrain_pipeline/coastal_delta_product.py](../../../terrain_pipeline/coastal_delta_product.py) | 跨项关联 | Finite experimental geological delta, with restartable scenario metadata. One raster cell is the minimum channel corridor; formative widths are subgrid hydrauli… |
| [terrain_pipeline/coastal_delta_regional.py](../../../terrain_pipeline/coastal_delta_regional.py) | 跨项关联 | Bounded regional construction calls on the existing integrated delta ledger. All volumes are solid cubic metres; geological years are equivalent forcing time, d… |
| [terrain_pipeline/coastal_delta_routes.py](../../../terrain_pipeline/coastal_delta_routes.py) | 跨项关联 | Terrain-constrained subgrid river connection to the actual window ocean. |
| [terrain_pipeline/coastal_delta_window.py](../../../terrain_pipeline/coastal_delta_window.py) | 跨项关联 | Prepare an auditable 100 m window from fixed-owner native TD pages. |
| [terrain_pipeline/coastal_marine_base.py](../../../terrain_pipeline/coastal_marine_base.py) | 主归属 | Regional, source-bound coast-following geological scenario (no sediment). |
| [terrain_pipeline/coastal_marine_longterm.py](../../../terrain_pipeline/coastal_marine_longterm.py) | 主归属 | Implicit, finite-time 2-D marine solid transport on a shared MarineState. Velocity is a prescribed depth-averaged scenario (m/s), diffusivity is in m²/s, and se… |
| [terrain_pipeline/coastal_marine_product.py](../../../terrain_pipeline/coastal_marine_product.py) | 主归属 | Explicit preparation and verified loading of marine base products. |
| [terrain_pipeline/coastal_marine_sediment.py](../../../terrain_pipeline/coastal_marine_sediment.py) | 主归属 | Finite, restartable reduced marine sediment transport on a common SI grid. |
| [terrain_pipeline/coastal_river_connector.py](../../../terrain_pipeline/coastal_river_connector.py) | 主归属 | Independent, scenario geometry for a surveyed river-to-coast connection. Coordinates are absolute x,z metres; arrays are indexed z,x. The surface is an imposed … |
| [terrain_pipeline/coastal_terrain.py](../../../terrain_pipeline/coastal_terrain.py) | 跨项关联 | 海岸底图、海岸细化与群岛产品线（A 类）。 合并自 `coastal_detail_refinement`、`coastal_archipelago`、`coastal_terrain_product`、 `coastal_archipelago_product`、`coastal_detail_product`（本模… |
| [terrain_pipeline/complete_delta.py](../../../terrain_pipeline/complete_delta.py) | 跨项关联 | Independent engineered delta, finite monthly forcing and replayable state. Coordinates are metres at raster cell centres. Construction bulk volumes and natural … |
| [terrain_pipeline/delta_network_site.py](../../../terrain_pipeline/delta_network_site.py) | 跨项关联 | Site, local frame and base surface for the complex delta network v1. The delta is built in a rotated local metric frame (u seaward, v along shore). Everything s… |
| [terrain_pipeline/delta_network_skeleton.py](../../../terrain_pipeline/delta_network_skeleton.py) | 跨项关联 | Procedural channel skeleton for the complex delta network v1 (P1). Everything here lives in the local metric frame of ``delta_network_site`` (u seaward, v along… |
| [terrain_pipeline/delta_network_skeleton_v2.py](../../../terrain_pipeline/delta_network_skeleton_v2.py) | 跨项关联 | Channel skeleton for the complex delta network v2 (rework of v1). What changed against ``delta_network_skeleton`` (v1) -----------------------------------------… |
| [terrain_pipeline/delta_network_skeleton_v3.py](../../../terrain_pipeline/delta_network_skeleton_v3.py) | 跨项关联 | Channel skeleton for the complex delta network v2 (rework of v1). What changed against ``delta_network_skeleton`` (v1) -----------------------------------------… |
| [terrain_pipeline/delta_network_skeleton_v4.py](../../../terrain_pipeline/delta_network_skeleton_v4.py) | 跨项关联 | Channel skeleton for the complex delta network v4. v4 changes only the land building (``delta_network_terrain_v4``): the review of v3 against the reference imag… |
| [terrain_pipeline/delta_network_terrain.py](../../../terrain_pipeline/delta_network_terrain.py) | 跨项关联 | Land building for the complex delta network v1 (P2). Input: the channel graph from ``delta_network_skeleton`` plus the TD-derived site surface from ``delta_netw… |
| [terrain_pipeline/delta_network_terrain_v2.py](../../../terrain_pipeline/delta_network_terrain_v2.py) | 跨项关联 | Land building for the complex delta network v2 (rework of ``delta_network_terrain``). What changed against v1 ----------------------- * The shoreline is **built… |
| [terrain_pipeline/delta_network_terrain_v3.py](../../../terrain_pipeline/delta_network_terrain_v3.py) | 跨项关联 | Land building for the complex delta network v3 (rework of v2 / ``delta_network_terrain``). What changed against v2 (v3) ---------------------------- * Old lobes… |
| [terrain_pipeline/delta_network_terrain_v4.py](../../../terrain_pipeline/delta_network_terrain_v4.py) | 跨项关联 | Land building for the complex delta network v4 (post-processing of ``build_terrain_v3``). Why v4 (user: "按参考图的形态作为基准") ---------------------------------------- … |
| [terrain_pipeline/environment_coastal_delta.py](../../../terrain_pipeline/environment_coastal_delta.py) | 跨项关联 | Same-mouth finite channel-tree deposition and bounded marine water/heat export. Consumes already-debited regional boundary packets exactly once. Original saved … |
| [terrain_pipeline/environment_delta_fv.py](../../../terrain_pipeline/environment_delta_fv.py) | 跨项关联 | Persistent finite FV delta, with no prescribed downstream channel graph. |
| [terrain_pipeline/environment_delta_source.py](../../../terrain_pipeline/environment_delta_source.py) | 跨项关联 | Pin saved coastal terrain and debit witnessed regional packets into FV delta. |
| [terrain_pipeline/environment_product.py](../../../terrain_pipeline/environment_product.py) | 跨项关联 | Consolidated environment_product implementations; numeric expressions preserved. |
| [terrain_pipeline/island_mountains.py](../../../terrain_pipeline/island_mountains.py) | 跨项关联 | Fixed-grid, CPU-only qualification of exposed islands for explicit TD work. Default qualification is exposed area strictly greater than 100 square km. Width fil… |
| [terrain_pipeline/large_delta_active_network.py](../../../terrain_pipeline/large_delta_active_network.py) | 跨项关联 | Freshwater distributary construction and finite event routing on a supplied bed. Coordinates are x,z metres, arrays indexed z,x. This is a deterministic, steady… |
| [terrain_pipeline/large_delta_active_source.py](../../../terrain_pipeline/large_delta_active_source.py) | 跨项关联 | Active 30-day sediment delivery from retained mouth-5879 formation stock. |
| [terrain_pipeline/large_delta_coupled.py](../../../terrain_pipeline/large_delta_coupled.py) | 跨项关联 | Checkpointed finite delta sediment and geographic tide operator splitting. |
| [terrain_pipeline/large_delta_evolution.py](../../../terrain_pipeline/large_delta_evolution.py) | 跨项关联 | Finite branched sediment/section continuation for forward TD deltas. One frozen-water routing interval is solved per reach. Downstream allocations follow water … |
| [terrain_pipeline/large_delta_formation_source.py](../../../terrain_pipeline/large_delta_formation_source.py) | 跨项关联 | Finite geological source scenario on a contracted native catchment graph. |
| [terrain_pipeline/large_delta_forward.py](../../../terrain_pipeline/large_delta_forward.py) | 跨项关联 | Forward-constrained delta formation on an explicitly surveyed coastal outlet. Geological initialization is a finite-volume scenario, not a time simulation. |
| [terrain_pipeline/large_delta_landform_prototype.py](../../../terrain_pipeline/large_delta_landform_prototype.py) | 跨项关联 | Bounded finite-sediment redistribution experiment; not a delta generator. |
| [terrain_pipeline/large_delta_landform_regional.py](../../../terrain_pipeline/large_delta_landform_regional.py) | 跨项关联 | Provisional finite-stock, terrain-routed regional delta formation experiment. |
| [terrain_pipeline/large_delta_landform_v2.py](../../../terrain_pipeline/large_delta_landform_v2.py) | 跨项关联 | Terrain-constrained regional alluvial initialization, experimental v2. |
| [terrain_pipeline/large_delta_shelf_fan.py](../../../terrain_pipeline/large_delta_shelf_fan.py) | 跨项关联 | Finite geological fan initialization on the approved derived TD shelf. |
| [terrain_pipeline/large_delta_shelf_product.py](../../../terrain_pipeline/large_delta_shelf_product.py) | 跨项关联 | Saved pre-event forward delta on the explicit, pinned shelf scenario. |
| [terrain_pipeline/large_delta_shelf_scenario.py](../../../terrain_pipeline/large_delta_shelf_scenario.py) | 跨项关联 | Explicit local geological shelf scenario over a pinned TD regional source. The transform changes only known ocean bathymetry. It is not a sediment ledger. |
| [terrain_pipeline/large_delta_state.py](../../../terrain_pipeline/large_delta_state.py) | 跨项关联 | Persistent delta state and conservative mapping to geographic solver nodes. |
| [terrain_pipeline/large_delta_suite.py](../../../terrain_pipeline/large_delta_suite.py) | 跨项关联 | Finite-inventory delta initialization on a coordinate-pinned regional source. Initialization is geometric; it does not represent a specified elapsed time. |
| [terrain_pipeline/large_delta_suite_network.py](../../../terrain_pipeline/large_delta_suite_network.py) | 跨项关联 | Scale-aware, terrain-routed distributaries on an initialized delta plain. |
| [terrain_pipeline/large_delta_suite_source.py](../../../terrain_pipeline/large_delta_suite_source.py) | 跨项关联 | Read-only, coordinate-preserving regional sampling of the frozen TD mosaic. |
| [terrain_pipeline/large_delta_suite_tidal.py](../../../terrain_pipeline/large_delta_suite_tidal.py) | 跨项关联 | Suite-case coastal tide adapter. Coordinates are source cell centres in metres. |
| [terrain_pipeline/large_delta_terrain_product.py](../../../terrain_pipeline/large_delta_terrain_product.py) | 跨项关联 | Native-grid, finite-budget initialization of the mouth 5879 delta plain. |
| [terrain_pipeline/large_delta_tidal_product.py](../../../terrain_pipeline/large_delta_tidal_product.py) | 跨项关联 | Prepare, run and publish the reduced tidal storage-graph experiment. |
| [terrain_pipeline/large_delta_tidal_product_v4.py](../../../terrain_pipeline/large_delta_tidal_product_v4.py) | 跨项关联 | Source-bound segmented tidal model with partitioned subgrid storage. |
| [terrain_pipeline/large_delta_tidal_source.py](../../../terrain_pipeline/large_delta_tidal_source.py) | 跨项关联 | Reference-bound pre-event inputs for the large delta tidal alternative. |
| [terrain_pipeline/native_hierarchical_delta.py](../../../terrain_pipeline/native_hierarchical_delta.py) | 跨项关联 | Finite hierarchical kinematic routing for a constructed delta tree. |
| [terrain_pipeline/new_world_delta.py](../../../terrain_pipeline/new_world_delta.py) | 跨项关联 | Bind actual mouth interval forcing to the existing integrated delta kernel. |
| [terrain_pipeline/new_world_game_delta.py](../../../terrain_pipeline/new_world_game_delta.py) | 跨项关联 | Local, frozen-water game delta adapters; no water routing is replayed here. |
| [terrain_pipeline/ocean_island_consumers.py](../../../terrain_pipeline/ocean_island_consumers.py) | 跨项关联 | CPU consumers of one frozen ocean-island plan, in absolute X/Z metres. Raster centres and finite area samples are derived views. The feature inventory remains a… |
| [terrain_pipeline/ocean_islands.py](../../../terrain_pipeline/ocean_islands.py) | 跨项关联 | Explicitly prepared ocean landforms on a finite, immutable plate background. Coordinates are metres, X east / Z south; ages are uncalibrated offline steps. This… |
| [terrain_pipeline/surface_rivers/delta.py](../../../terrain_pipeline/surface_rivers/delta.py) | 跨项关联 | Conservative river-mouth deposition geometry with an explicit ocean gate. |
| [terrain_pipeline/surface_rivers/metric_coast_bounded_delta.py](../../../terrain_pipeline/surface_rivers/metric_coast_bounded_delta.py) | 跨项关联 | Explicit coastal construction with channels terminating at first open sea. |
| [terrain_pipeline/surface_rivers/metric_coastal_transport.py](../../../terrain_pipeline/surface_rivers/metric_coastal_transport.py) | 主归属 | Finite coastal active layer, driven by connected tidal stages and wave rays. This is a reduced morphological experiment, not a momentum/Exner solver. Every face… |
| [terrain_pipeline/surface_rivers/metric_delta.py](../../../terrain_pipeline/surface_rivers/metric_delta.py) | 跨项关联 | Bounded deterministic delta-growth candidates on a metric terrain grid. |
| [terrain_pipeline/surface_rivers/metric_delta_product.py](../../../terrain_pipeline/surface_rivers/metric_delta_product.py) | 跨项关联 | Auditable saved artifacts for bounded metric delta candidates. This module deliberately separates candidate generation from persistence. A saved artifact contai… |
| [terrain_pipeline/surface_rivers/metric_delta_sediment_product.py](../../../terrain_pipeline/surface_rivers/metric_delta_sediment_product.py) | 跨项关联 | Saved delta candidates driven by a witnessed upstream water/sediment export. |
| [terrain_pipeline/surface_rivers/metric_fluvial_delta.py](../../../terrain_pipeline/surface_rivers/metric_fluvial_delta.py) | 跨项关联 | Finite river-led deposition and bed-feedback routing approximation. Intervals pass prescribed volumes through a connectivity DAG, not a transient hydraulic solv… |
| [terrain_pipeline/surface_rivers/metric_fluvial_distributary.py](../../../terrain_pipeline/surface_rivers/metric_fluvial_distributary.py) | 跨项关联 | Finite terrain-derived distributary excavation with explicit material escrow. Water volumes set a generative section scale, not a discharge or erosion clock. Ex… |
| [terrain_pipeline/surface_rivers/metric_fv_coastal_coupling.py](../../../terrain_pipeline/surface_rivers/metric_fv_coastal_coupling.py) | 主归属 | Operator-split FV water/finite bedload, preserving the live hydraulic state. Updates the existing v7 support arrays in place at interval boundaries. The existin… |
| [terrain_pipeline/surface_rivers/metric_fv_coastal_sediment.py](../../../terrain_pipeline/surface_rivers/metric_fv_coastal_sediment.py) | 主归属 | Conservative finite-bed MPM transport using FV water and incident waves. Straight D4 Airy rays shoal and break, but do not refract or force water momentum. Symm… |
| [terrain_pipeline/surface_rivers/metric_fv_incident_wave_vectorized.py](../../../terrain_pipeline/surface_rivers/metric_fv_incident_wave_vectorized.py) | 跨项关联 | Independent D4 Airy helper; no production caller is changed. Rays advance in the original order, vectorized across parallel rays only. Dispersion and each ray's… |
| [terrain_pipeline/surface_rivers/metric_integrated_delta.py](../../../terrain_pipeline/surface_rivers/metric_integrated_delta.py) | 跨项关联 | Integrated reduced channel-tree morphodynamics for the stylized 16 km scene. Public surface: ChannelTreeGeometry - geometry bundle for the trunk/branch tree Int… |
| [terrain_pipeline/surface_rivers/metric_morphology_product.py](../../../terrain_pipeline/surface_rivers/metric_morphology_product.py) | 跨项关联 | Saved native inputs and reproducible uncommitted morphology proposals. |
| [terrain_pipeline/surface_rivers/metric_natural_delta.py](../../../terrain_pipeline/surface_rivers/metric_natural_delta.py) | 跨项关联 | New-start finite-supply shallow-basin DeltaRCM mechanism experiment. No downstream path, island, mouth bar or branch count is prescribed. The hydraulic time com… |
| [terrain_pipeline/surface_rivers/metric_natural_delta_continuation.py](../../../terrain_pipeline/surface_rivers/metric_natural_delta_continuation.py) | 跨项关联 | Native checkpoint continuation with unchanged floor and new finite supply. The experiment hooks mirror the existing natural model. Kept separate so in-progress … |
| [terrain_pipeline/surface_rivers/metric_river_dominant_delta.py](../../../terrain_pipeline/surface_rivers/metric_river_dominant_delta.py) | 跨项关联 | River-dominant distributary budget and thin grid adapter around the fluvial kernel. The non-spatial comparator is an explicitly abstract volume comparison. The … |
| [terrain_pipeline/surface_rivers/metric_td_delta_initialization.py](../../../terrain_pipeline/surface_rivers/metric_td_delta_initialization.py) | 跨项关联 | Pure TD river-aligned initialization; no downstream landform construction. |
| [terrain_pipeline/surface_rivers/metric_tidal_creek_construction.py](../../../terrain_pipeline/surface_rivers/metric_tidal_creek_construction.py) | 跨项关联 | Explicit initial tidal island, flat and channel excavation. |
| [terrain_pipeline/surface_rivers/metric_tidal_island_geometry.py](../../../terrain_pipeline/surface_rivers/metric_tidal_island_geometry.py) | 跨项关联 | Prescribed island/channel initial geometry, with an explicit tidal storage proxy. |
| [terrain_pipeline/surface_rivers/metric_tide_wave_morphology.py](../../../terrain_pipeline/surface_rivers/metric_tide_wave_morphology.py) | 跨项关联 | Bounded tide and wave shaping for a frozen delta preview. This is a derived coastal morphology stage. It changes only open marine cells near the first-marine bo… |
| [terrain_pipeline/surface_rivers/transport.py](../../../terrain_pipeline/surface_rivers/transport.py) | 主归属 | Finite, conservative sediment routing on an explicitly wet ocean grid. This is an isolated project approximation, not a DeltaRCM implementation. |
| [terrain_pipeline/td_native_partition_transport.py](../../../terrain_pipeline/td_native_partition_transport.py) | 主归属 | Bounded synchronous native-tile SSP-RK2 transport prototype; no solver import. |
| [terrain_pipeline/world_acceptance_delta.py](../../../terrain_pipeline/world_acceptance_delta.py) | 跨项关联 | Bind a local engineered delta simulation to an actual TD world river mouth. No old scene is loaded. Coordinates are cell centres, rows increase world +z. Distri… |

## S2/G9 风化与成土过程

关联文件 4 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [terrain_pipeline/environment_contract.py](../../../terrain_pipeline/environment_contract.py) | 跨项关联 | Consolidated environment_contract implementations; numeric expressions preserved. |
| [terrain_pipeline/environment_processes.py](../../../terrain_pipeline/environment_processes.py) | 主归属 | Consolidated environment_processes implementations; numeric expressions preserved. |
| [terrain_pipeline/environment_product.py](../../../terrain_pipeline/environment_product.py) | 跨项关联 | Consolidated environment_product implementations; numeric expressions preserved. |
| [terrain_pipeline/soil_water.py](../../../terrain_pipeline/soil_water.py) | 跨项关联 | 材料厚度、坡度与年降雨输入的土壤合成条件代理；available_water不等同动态ET闭合含水量。 |

## S2/G10 坡面质量搬运：滑坡、崩塌、滚石与泥石流

关联文件 3 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [terrain_pipeline/environment_processes.py](../../../terrain_pipeline/environment_processes.py) | 跨项关联 | Consolidated environment_processes implementations; numeric expressions preserved. |
| [terrain_pipeline/environment_product.py](../../../terrain_pipeline/environment_product.py) | 跨项关联 | Consolidated environment_product implementations; numeric expressions preserved. |
| [terrain_pipeline/surface_rivers/metric_fluvial_slope_stability.py](../../../terrain_pipeline/surface_rivers/metric_fluvial_slope_stability.py) | 跨项关联 | Conservative repose relaxation of an explicitly bounded mobile column. Composition is a homogeneous-column approximation for this gravity phase. It does not imp… |

## S2/G11 含水层、地下水补给/排泄、泉与地表—地下交换

关联文件 2 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [terrain_pipeline/environment_processes.py](../../../terrain_pipeline/environment_processes.py) | 跨项关联 | Consolidated environment_processes implementations; numeric expressions preserved. |
| [terrain_pipeline/environment_product.py](../../../terrain_pipeline/environment_product.py) | 跨项关联 | Consolidated environment_product implementations; numeric expressions preserved. |

## S2/G12 冻土、季节冻融、冰缘地貌与热融沉降

关联文件 2 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [terrain_pipeline/environment_processes.py](../../../terrain_pipeline/environment_processes.py) | 跨项关联 | Consolidated environment_processes implementations; numeric expressions preserved. |
| [terrain_pipeline/environment_product.py](../../../terrain_pipeline/environment_product.py) | 跨项关联 | Consolidated environment_product implementations; numeric expressions preserved. |

## S2/G13 风成过程：风蚀、风积、沙丘与黄土

关联文件 2 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [terrain_pipeline/environment_processes.py](../../../terrain_pipeline/environment_processes.py) | 跨项关联 | Consolidated environment_processes implementations; numeric expressions preserved. |
| [terrain_pipeline/environment_product.py](../../../terrain_pipeline/environment_product.py) | 跨项关联 | Consolidated environment_product implementations; numeric expressions preserved. |

## S2/G14 太阳辐射、坡向与局地微气候

关联文件 3 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [terrain_pipeline/climate_forcing.py](../../../terrain_pipeline/climate_forcing.py) | 跨项关联 | v2合成气候修正层：风、地形抬升/雨影及温雨诊断；接口验收不等于生产季节水文默认接线。 |
| [terrain_pipeline/environment_processes.py](../../../terrain_pipeline/environment_processes.py) | 跨项关联 | Consolidated environment_processes implementations; numeric expressions preserved. |
| [terrain_pipeline/environment_product.py](../../../terrain_pipeline/environment_product.py) | 跨项关联 | Consolidated environment_product implementations; numeric expressions preserved. |

## S2/G15 火灾、扰动与生态演替

关联文件 2 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [terrain_pipeline/environment_processes.py](../../../terrain_pipeline/environment_processes.py) | 跨项关联 | Consolidated environment_processes implementations; numeric expressions preserved. |
| [terrain_pipeline/environment_product.py](../../../terrain_pipeline/environment_product.py) | 跨项关联 | Consolidated environment_product implementations; numeric expressions preserved. |

## S2/G16 土壤化学性：盐分、碱化、有机质与养分

关联文件 2 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [terrain_pipeline/environment_processes.py](../../../terrain_pipeline/environment_processes.py) | 跨项关联 | Consolidated environment_processes implementations; numeric expressions preserved. |
| [terrain_pipeline/environment_product.py](../../../terrain_pipeline/environment_product.py) | 跨项关联 | Consolidated environment_product implementations; numeric expressions preserved. |

## S2/G17 河流袭夺、分水岭迁移、洪泛平原与河道侧移

关联文件 2 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [terrain_pipeline/environment_processes.py](../../../terrain_pipeline/environment_processes.py) | 跨项关联 | Consolidated environment_processes implementations; numeric expressions preserved. |
| [terrain_pipeline/environment_product.py](../../../terrain_pipeline/environment_product.py) | 跨项关联 | Consolidated environment_product implementations; numeric expressions preserved. |

已有有限网络迁移机制保留；河流袭夺后续开发按原要求暂停，本轮只登记。

## S2/G18 火山、岩浆侵入、火山灰与地热

关联文件 2 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [terrain_pipeline/environment_processes.py](../../../terrain_pipeline/environment_processes.py) | 跨项关联 | Consolidated environment_processes implementations; numeric expressions preserved. |
| [terrain_pipeline/environment_product.py](../../../terrain_pipeline/environment_product.py) | 跨项关联 | Consolidated environment_product implementations; numeric expressions preserved. |

## S2/G19 海岸波浪、潮汐、沿岸漂移、河口混合与盐度

关联文件 90 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [terrain_pipeline/coastal_delta_avulsion.py](../../../terrain_pipeline/coastal_delta_avulsion.py) | 跨项关联 | Activate terrain-derived candidate distributaries under measured river head. |
| [terrain_pipeline/coastal_delta_bank_formation.py](../../../terrain_pipeline/coastal_delta_bank_formation.py) | 跨项关联 | Explicit, conservative bank preparation using lagged saved water stages. |
| [terrain_pipeline/coastal_delta_branch_attachment.py](../../../terrain_pipeline/coastal_delta_branch_attachment.py) | 跨项关联 | 职责待人工核对；仅登记可确认的静态结构 |
| [terrain_pipeline/coastal_delta_branching.py](../../../terrain_pipeline/coastal_delta_branching.py) | 跨项关联 | Optional, conservative distributary experiment over the shared marine stock. Routes are D4-connected raster corridors, not resolved hydraulics. Depositional obs… |
| [terrain_pipeline/coastal_delta_deposition_scaling.py](../../../terrain_pipeline/coastal_delta_deposition_scaling.py) | 跨项关联 | Empirical conversion of a reference reach deposition fraction by length. |
| [terrain_pipeline/coastal_delta_evolution.py](../../../terrain_pipeline/coastal_delta_evolution.py) | 跨项关联 | Finite overbank exchange on a shared marine sediment state. This optional building block treats channel stage and throughflow as boundary conditions. It does no… |
| [terrain_pipeline/coastal_delta_formation.py](../../../terrain_pipeline/coastal_delta_formation.py) | 跨项关联 | Delta formation API; the rejected prototype is archived in .scratch. |
| [terrain_pipeline/coastal_delta_geological.py](../../../terrain_pipeline/coastal_delta_geological.py) | 跨项关联 | Finite-volume, coarse geological sediment spreading on a MarineState. Transport sweeps are numerical redistribution iterations, not physical seconds. The inunda… |
| [terrain_pipeline/coastal_delta_graph_hydraulics.py](../../../terrain_pipeline/coastal_delta_graph_hydraulics.py) | 跨项关联 | Finite DAG stage/flow approximation with one discharge per physical edge. |
| [terrain_pipeline/coastal_delta_growth.py](../../../terrain_pipeline/coastal_delta_growth.py) | 跨项关联 | Shoreline-driven, finite-stock extensions of the v7 delta network. |
| [terrain_pipeline/coastal_delta_hydraulic_capacity.py](../../../terrain_pipeline/coastal_delta_hydraulic_capacity.py) | 跨项关联 | Hydraulic sediment-transport capacity for multi-cell delta channel nodes (issue 24). Opt-in rule that replaces the legacy ``capacity = Q * 0.01 * duration`` lim… |
| [terrain_pipeline/coastal_delta_hydraulic_event.py](../../../terrain_pipeline/coastal_delta_hydraulic_event.py) | 跨项关联 | Opt-in physical event for multi-cell deltas with hydraulic transport capacity (issue 24). Mirrors ``coastal_delta_multicell.advance_event`` (which stays unchang… |
| [terrain_pipeline/coastal_delta_hydraulics.py](../../../terrain_pipeline/coastal_delta_hydraulics.py) | 跨项关联 | Quasi-steady rectangular-channel stages on a shared distributary DAG. Manning friction and critical-depth controls are engineering approximations; no floodplain… |
| [terrain_pipeline/coastal_delta_lobes.py](../../../terrain_pipeline/coastal_delta_lobes.py) | 跨项关联 | Experimental shoreline lobe switching over the single formation ledger. Scores use local water-column accommodation and finite deposit blockage. They are game-s… |
| [terrain_pipeline/coastal_delta_morphology.py](../../../terrain_pipeline/coastal_delta_morphology.py) | 跨项关联 | Explicit, finite morphology preparation and representative discharge capture. |
| [terrain_pipeline/coastal_delta_mouth_extension.py](../../../terrain_pipeline/coastal_delta_mouth_extension.py) | 跨项关联 | Finite shoreline extension using only unowned multi-cell inventory. |
| [terrain_pipeline/coastal_delta_multicell.py](../../../terrain_pipeline/coastal_delta_multicell.py) | 跨项关联 | Fixed-footprint annual and physical exchange for multi-cell channels. |
| [terrain_pipeline/coastal_delta_multicell_avulsion.py](../../../terrain_pipeline/coastal_delta_multicell_avulsion.py) | 跨项关联 | Bounded deposition-triggered trials for multi-cell distributaries. |
| [terrain_pipeline/coastal_delta_node_inventory.py](../../../terrain_pipeline/coastal_delta_node_inventory.py) | 跨项关联 | Conservative ownership of multi-cell channel-node sediment inventories. |
| [terrain_pipeline/coastal_delta_pipeline.py](../../../terrain_pipeline/coastal_delta_pipeline.py) | 跨项关联 | Entry point for a single irregular trunk and subsequent candidate refresh. |
| [terrain_pipeline/coastal_delta_plain.py](../../../terrain_pipeline/coastal_delta_plain.py) | 跨项关联 | Statistical tidal windows for finite-source distributary formation. Each equal-weight phase represents a fraction of equivalent geological time; physical event … |
| [terrain_pipeline/coastal_delta_product.py](../../../terrain_pipeline/coastal_delta_product.py) | 跨项关联 | Finite experimental geological delta, with restartable scenario metadata. One raster cell is the minimum channel corridor; formative widths are subgrid hydrauli… |
| [terrain_pipeline/coastal_delta_regional.py](../../../terrain_pipeline/coastal_delta_regional.py) | 跨项关联 | Bounded regional construction calls on the existing integrated delta ledger. All volumes are solid cubic metres; geological years are equivalent forcing time, d… |
| [terrain_pipeline/coastal_marine_base.py](../../../terrain_pipeline/coastal_marine_base.py) | 跨项关联 | Regional, source-bound coast-following geological scenario (no sediment). |
| [terrain_pipeline/coastal_marine_longterm.py](../../../terrain_pipeline/coastal_marine_longterm.py) | 跨项关联 | Implicit, finite-time 2-D marine solid transport on a shared MarineState. Velocity is a prescribed depth-averaged scenario (m/s), diffusivity is in m²/s, and se… |
| [terrain_pipeline/coastal_marine_product.py](../../../terrain_pipeline/coastal_marine_product.py) | 跨项关联 | Explicit preparation and verified loading of marine base products. |
| [terrain_pipeline/coastal_marine_sediment.py](../../../terrain_pipeline/coastal_marine_sediment.py) | 跨项关联 | Finite, restartable reduced marine sediment transport on a common SI grid. |
| [terrain_pipeline/coastal_river_connector.py](../../../terrain_pipeline/coastal_river_connector.py) | 跨项关联 | Independent, scenario geometry for a surveyed river-to-coast connection. Coordinates are absolute x,z metres; arrays are indexed z,x. The surface is an imposed … |
| [terrain_pipeline/complete_delta.py](../../../terrain_pipeline/complete_delta.py) | 跨项关联 | Independent engineered delta, finite monthly forcing and replayable state. Coordinates are metres at raster cell centres. Construction bulk volumes and natural … |
| [terrain_pipeline/delta_network_skeleton.py](../../../terrain_pipeline/delta_network_skeleton.py) | 跨项关联 | Procedural channel skeleton for the complex delta network v1 (P1). Everything here lives in the local metric frame of ``delta_network_site`` (u seaward, v along… |
| [terrain_pipeline/delta_network_skeleton_v2.py](../../../terrain_pipeline/delta_network_skeleton_v2.py) | 跨项关联 | Channel skeleton for the complex delta network v2 (rework of v1). What changed against ``delta_network_skeleton`` (v1) -----------------------------------------… |
| [terrain_pipeline/delta_network_skeleton_v3.py](../../../terrain_pipeline/delta_network_skeleton_v3.py) | 跨项关联 | Channel skeleton for the complex delta network v2 (rework of v1). What changed against ``delta_network_skeleton`` (v1) -----------------------------------------… |
| [terrain_pipeline/delta_network_skeleton_v4.py](../../../terrain_pipeline/delta_network_skeleton_v4.py) | 跨项关联 | Channel skeleton for the complex delta network v4. v4 changes only the land building (``delta_network_terrain_v4``): the review of v3 against the reference imag… |
| [terrain_pipeline/delta_network_terrain.py](../../../terrain_pipeline/delta_network_terrain.py) | 跨项关联 | Land building for the complex delta network v1 (P2). Input: the channel graph from ``delta_network_skeleton`` plus the TD-derived site surface from ``delta_netw… |
| [terrain_pipeline/delta_network_terrain_v2.py](../../../terrain_pipeline/delta_network_terrain_v2.py) | 跨项关联 | Land building for the complex delta network v2 (rework of ``delta_network_terrain``). What changed against v1 ----------------------- * The shoreline is **built… |
| [terrain_pipeline/delta_network_terrain_v3.py](../../../terrain_pipeline/delta_network_terrain_v3.py) | 跨项关联 | Land building for the complex delta network v3 (rework of v2 / ``delta_network_terrain``). What changed against v2 (v3) ---------------------------- * Old lobes… |
| [terrain_pipeline/delta_network_terrain_v4.py](../../../terrain_pipeline/delta_network_terrain_v4.py) | 跨项关联 | Land building for the complex delta network v4 (post-processing of ``build_terrain_v3``). Why v4 (user: "按参考图的形态作为基准") ---------------------------------------- … |
| [terrain_pipeline/delta_tidal_validation.py](../../../terrain_pipeline/delta_tidal_validation.py) | 跨项关联 | Sea-side connected prism validation on a saved annual delta bed. The prescribed tide drives a reduced water/salt reservoir exchange, not a 2D momentum solution … |
| [terrain_pipeline/environment_coastal_delta.py](../../../terrain_pipeline/environment_coastal_delta.py) | 跨项关联 | Same-mouth finite channel-tree deposition and bounded marine water/heat export. Consumes already-debited regional boundary packets exactly once. Original saved … |
| [terrain_pipeline/environment_delta_fv.py](../../../terrain_pipeline/environment_delta_fv.py) | 跨项关联 | Persistent finite FV delta, with no prescribed downstream channel graph. |
| [terrain_pipeline/environment_delta_source.py](../../../terrain_pipeline/environment_delta_source.py) | 跨项关联 | Pin saved coastal terrain and debit witnessed regional packets into FV delta. |
| [terrain_pipeline/environment_processes.py](../../../terrain_pipeline/environment_processes.py) | 跨项关联 | Consolidated environment_processes implementations; numeric expressions preserved. |
| [terrain_pipeline/environment_product.py](../../../terrain_pipeline/environment_product.py) | 跨项关联 | Consolidated environment_product implementations; numeric expressions preserved. |
| [terrain_pipeline/large_delta_active_network.py](../../../terrain_pipeline/large_delta_active_network.py) | 跨项关联 | Freshwater distributary construction and finite event routing on a supplied bed. Coordinates are x,z metres, arrays indexed z,x. This is a deterministic, steady… |
| [terrain_pipeline/large_delta_coupled.py](../../../terrain_pipeline/large_delta_coupled.py) | 跨项关联 | Checkpointed finite delta sediment and geographic tide operator splitting. |
| [terrain_pipeline/large_delta_evolution.py](../../../terrain_pipeline/large_delta_evolution.py) | 跨项关联 | Finite branched sediment/section continuation for forward TD deltas. One frozen-water routing interval is solved per reach. Downstream allocations follow water … |
| [terrain_pipeline/large_delta_forward.py](../../../terrain_pipeline/large_delta_forward.py) | 跨项关联 | Forward-constrained delta formation on an explicitly surveyed coastal outlet. Geological initialization is a finite-volume scenario, not a time simulation. |
| [terrain_pipeline/large_delta_landform_prototype.py](../../../terrain_pipeline/large_delta_landform_prototype.py) | 跨项关联 | Bounded finite-sediment redistribution experiment; not a delta generator. |
| [terrain_pipeline/large_delta_landform_regional.py](../../../terrain_pipeline/large_delta_landform_regional.py) | 跨项关联 | Provisional finite-stock, terrain-routed regional delta formation experiment. |
| [terrain_pipeline/large_delta_landform_v2.py](../../../terrain_pipeline/large_delta_landform_v2.py) | 跨项关联 | Terrain-constrained regional alluvial initialization, experimental v2. |
| [terrain_pipeline/large_delta_shelf_fan.py](../../../terrain_pipeline/large_delta_shelf_fan.py) | 跨项关联 | Finite geological fan initialization on the approved derived TD shelf. |
| [terrain_pipeline/large_delta_shelf_product.py](../../../terrain_pipeline/large_delta_shelf_product.py) | 跨项关联 | Saved pre-event forward delta on the explicit, pinned shelf scenario. |
| [terrain_pipeline/large_delta_shelf_scenario.py](../../../terrain_pipeline/large_delta_shelf_scenario.py) | 跨项关联 | Explicit local geological shelf scenario over a pinned TD regional source. The transform changes only known ocean bathymetry. It is not a sediment ledger. |
| [terrain_pipeline/large_delta_state.py](../../../terrain_pipeline/large_delta_state.py) | 跨项关联 | Persistent delta state and conservative mapping to geographic solver nodes. |
| [terrain_pipeline/large_delta_suite.py](../../../terrain_pipeline/large_delta_suite.py) | 跨项关联 | Finite-inventory delta initialization on a coordinate-pinned regional source. Initialization is geometric; it does not represent a specified elapsed time. |
| [terrain_pipeline/large_delta_suite_event.py](../../../terrain_pipeline/large_delta_suite_event.py) | 跨项关联 | Short, finite reduced-graph tidal event on suite network reaches. The graph has analytic channel plan areas and separate offshore buffers. It has no floodplain … |
| [terrain_pipeline/large_delta_suite_network.py](../../../terrain_pipeline/large_delta_suite_network.py) | 跨项关联 | Scale-aware, terrain-routed distributaries on an initialized delta plain. |
| [terrain_pipeline/large_delta_suite_tidal.py](../../../terrain_pipeline/large_delta_suite_tidal.py) | 主归属 | Suite-case coastal tide adapter. Coordinates are source cell centres in metres. |
| [terrain_pipeline/large_delta_terrain_product.py](../../../terrain_pipeline/large_delta_terrain_product.py) | 跨项关联 | Native-grid, finite-budget initialization of the mouth 5879 delta plain. |
| [terrain_pipeline/large_delta_tidal_dynamics.py](../../../terrain_pipeline/large_delta_tidal_dynamics.py) | 跨项关联 | Conservative reduced storage-graph primitives for tidal delta experiments. Volumes are m3, beds/stages metres, times physical seconds. Optional face sections us… |
| [terrain_pipeline/large_delta_tidal_product.py](../../../terrain_pipeline/large_delta_tidal_product.py) | 跨项关联 | Prepare, run and publish the reduced tidal storage-graph experiment. |
| [terrain_pipeline/large_delta_tidal_product_v4.py](../../../terrain_pipeline/large_delta_tidal_product_v4.py) | 跨项关联 | Source-bound segmented tidal model with partitioned subgrid storage. |
| [terrain_pipeline/large_delta_tidal_reconstruction.py](../../../terrain_pipeline/large_delta_tidal_reconstruction.py) | 跨项关联 | Conservative native coastal water relaxation; this is not a momentum solver. Inputs use metres and square metres. River water is a separate stock and must not b… |
| [terrain_pipeline/large_delta_tidal_source.py](../../../terrain_pipeline/large_delta_tidal_source.py) | 跨项关联 | Reference-bound pre-event inputs for the large delta tidal alternative. |
| [terrain_pipeline/native_hierarchical_delta.py](../../../terrain_pipeline/native_hierarchical_delta.py) | 跨项关联 | Finite hierarchical kinematic routing for a constructed delta tree. |
| [terrain_pipeline/new_world_delta.py](../../../terrain_pipeline/new_world_delta.py) | 跨项关联 | Bind actual mouth interval forcing to the existing integrated delta kernel. |
| [terrain_pipeline/new_world_game_delta.py](../../../terrain_pipeline/new_world_game_delta.py) | 跨项关联 | Local, frozen-water game delta adapters; no water routing is replayed here. |
| [terrain_pipeline/surface_rivers/delta.py](../../../terrain_pipeline/surface_rivers/delta.py) | 跨项关联 | Conservative river-mouth deposition geometry with an explicit ocean gate. |
| [terrain_pipeline/surface_rivers/metric_coast_bounded_delta.py](../../../terrain_pipeline/surface_rivers/metric_coast_bounded_delta.py) | 跨项关联 | Explicit coastal construction with channels terminating at first open sea. |
| [terrain_pipeline/surface_rivers/metric_coastal_transport.py](../../../terrain_pipeline/surface_rivers/metric_coastal_transport.py) | 跨项关联 | Finite coastal active layer, driven by connected tidal stages and wave rays. This is a reduced morphological experiment, not a momentum/Exner solver. Every face… |
| [terrain_pipeline/surface_rivers/metric_delta.py](../../../terrain_pipeline/surface_rivers/metric_delta.py) | 跨项关联 | Bounded deterministic delta-growth candidates on a metric terrain grid. |
| [terrain_pipeline/surface_rivers/metric_delta_product.py](../../../terrain_pipeline/surface_rivers/metric_delta_product.py) | 跨项关联 | Auditable saved artifacts for bounded metric delta candidates. This module deliberately separates candidate generation from persistence. A saved artifact contai… |
| [terrain_pipeline/surface_rivers/metric_delta_sediment_product.py](../../../terrain_pipeline/surface_rivers/metric_delta_sediment_product.py) | 跨项关联 | Saved delta candidates driven by a witnessed upstream water/sediment export. |
| [terrain_pipeline/surface_rivers/metric_fluvial_delta.py](../../../terrain_pipeline/surface_rivers/metric_fluvial_delta.py) | 跨项关联 | Finite river-led deposition and bed-feedback routing approximation. Intervals pass prescribed volumes through a connectivity DAG, not a transient hydraulic solv… |
| [terrain_pipeline/surface_rivers/metric_fluvial_distributary.py](../../../terrain_pipeline/surface_rivers/metric_fluvial_distributary.py) | 跨项关联 | Finite terrain-derived distributary excavation with explicit material escrow. Water volumes set a generative section scale, not a discharge or erosion clock. Ex… |
| [terrain_pipeline/surface_rivers/metric_fv_coastal_coupling.py](../../../terrain_pipeline/surface_rivers/metric_fv_coastal_coupling.py) | 跨项关联 | Operator-split FV water/finite bedload, preserving the live hydraulic state. Updates the existing v7 support arrays in place at interval boundaries. The existin… |
| [terrain_pipeline/surface_rivers/metric_fv_coastal_sediment.py](../../../terrain_pipeline/surface_rivers/metric_fv_coastal_sediment.py) | 跨项关联 | Conservative finite-bed MPM transport using FV water and incident waves. Straight D4 Airy rays shoal and break, but do not refract or force water momentum. Symm… |
| [terrain_pipeline/surface_rivers/metric_fv_incident_wave_vectorized.py](../../../terrain_pipeline/surface_rivers/metric_fv_incident_wave_vectorized.py) | 主归属 | Independent D4 Airy helper; no production caller is changed. Rays advance in the original order, vectorized across parallel rays only. Dispersion and each ray's… |
| [terrain_pipeline/surface_rivers/metric_integrated_delta.py](../../../terrain_pipeline/surface_rivers/metric_integrated_delta.py) | 跨项关联 | Integrated reduced channel-tree morphodynamics for the stylized 16 km scene. Public surface: ChannelTreeGeometry - geometry bundle for the trunk/branch tree Int… |
| [terrain_pipeline/surface_rivers/metric_morphology_product.py](../../../terrain_pipeline/surface_rivers/metric_morphology_product.py) | 跨项关联 | Saved native inputs and reproducible uncommitted morphology proposals. |
| [terrain_pipeline/surface_rivers/metric_natural_delta.py](../../../terrain_pipeline/surface_rivers/metric_natural_delta.py) | 跨项关联 | New-start finite-supply shallow-basin DeltaRCM mechanism experiment. No downstream path, island, mouth bar or branch count is prescribed. The hydraulic time com… |
| [terrain_pipeline/surface_rivers/metric_natural_delta_continuation.py](../../../terrain_pipeline/surface_rivers/metric_natural_delta_continuation.py) | 跨项关联 | Native checkpoint continuation with unchanged floor and new finite supply. The experiment hooks mirror the existing natural model. Kept separate so in-progress … |
| [terrain_pipeline/surface_rivers/metric_river_dominant_delta.py](../../../terrain_pipeline/surface_rivers/metric_river_dominant_delta.py) | 跨项关联 | River-dominant distributary budget and thin grid adapter around the fluvial kernel. The non-spatial comparator is an explicitly abstract volume comparison. The … |
| [terrain_pipeline/surface_rivers/metric_td_delta_initialization.py](../../../terrain_pipeline/surface_rivers/metric_td_delta_initialization.py) | 跨项关联 | Pure TD river-aligned initialization; no downstream landform construction. |
| [terrain_pipeline/surface_rivers/metric_tidal_creek_construction.py](../../../terrain_pipeline/surface_rivers/metric_tidal_creek_construction.py) | 跨项关联 | Explicit initial tidal island, flat and channel excavation. |
| [terrain_pipeline/surface_rivers/metric_tidal_island_geometry.py](../../../terrain_pipeline/surface_rivers/metric_tidal_island_geometry.py) | 跨项关联 | Prescribed island/channel initial geometry, with an explicit tidal storage proxy. |
| [terrain_pipeline/surface_rivers/metric_tide_wave_morphology.py](../../../terrain_pipeline/surface_rivers/metric_tide_wave_morphology.py) | 跨项关联 | Bounded tide and wave shaping for a frozen delta preview. This is a derived coastal morphology stage. It changes only open marine cells near the first-marine bo… |
| [terrain_pipeline/surface_rivers/transport.py](../../../terrain_pipeline/surface_rivers/transport.py) | 跨项关联 | Finite, conservative sediment routing on an explicitly wet ocean grid. This is an isolated project approximation, not a DeltaRCM implementation. |
| [terrain_pipeline/td_native_partition_transport.py](../../../terrain_pipeline/td_native_partition_transport.py) | 跨项关联 | Bounded synchronous native-tile SSP-RK2 transport prototype; no solver import. |
| [terrain_pipeline/world_acceptance_delta.py](../../../terrain_pipeline/world_acceptance_delta.py) | 跨项关联 | Bind a local engineered delta simulation to an actual TD world river mouth. No old scene is loaded. Coordinates are cell centres, rows increase world +z. Distri… |

## S2/G20 动物栖息地与生态网络

关联文件 2 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [terrain_pipeline/environment_processes.py](../../../terrain_pipeline/environment_processes.py) | 跨项关联 | Consolidated environment_processes implementations; numeric expressions preserved. |
| [terrain_pipeline/environment_product.py](../../../terrain_pipeline/environment_product.py) | 跨项关联 | Consolidated environment_product implementations; numeric expressions preserved. |

## 盘点期间并行新增模块

| 文件 | 主归属 | 关联 |
| --- | --- | --- |
