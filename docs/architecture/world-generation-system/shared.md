# 共享能力

工程支持文件也纳入系统目录；实际运行/测试未在本轮执行，分类不能代替运行认证。

| 文件 | 主归属 | 支持细项 | 职责 |
| --- | --- | --- | --- |
| [diffusion/preview.py](../../../diffusion/preview.py) | X3 | S1/R1、S2/G1 | Export unmodified model output, slope and provenance before any erosion. |
| [terrain_pipeline/__init__.py](../../../terrain_pipeline/__init__.py) | X1 | S1/R1、S1/R9、S3/V8 | Terrain Diffusion height -> vector displacement -> local sculpting. |
| [terrain_pipeline/artifacts/__init__.py](../../../terrain_pipeline/artifacts/__init__.py) | X1 | S1/R1、S1/R9、S3/V1、S3/V8 | Portable terrain artifacts, independent of game consumers. |
| [terrain_pipeline/artifacts/contracts.py](../../../terrain_pipeline/artifacts/contracts.py) | X1 | S1/R1、S1/R9、S3/V1、S3/V8 | Validated physical coordinates and immutable artifact payloads. |
| [terrain_pipeline/coastal_delta_pipeline.py](../../../terrain_pipeline/coastal_delta_pipeline.py) | X2 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Entry point for a single irregular trunk and subsequent candidate refresh. |
| [terrain_pipeline/common_infra.py](../../../terrain_pipeline/common_infra.py) | X1 | S1/R1、S1/R9、S3/V1、S3/V8 | Shared low-level infrastructure: hashing, canonical JSON, seeds, coordinates, atomic IO, mmap. One h… |
| [terrain_pipeline/environment_contract.py](../../../terrain_pipeline/environment_contract.py) | X1 | S1/R9、S2/G2、S2/G3、S2/G4、S2/G5、S2/G6、S2/G7、S2/G9 | Consolidated environment_contract implementations; numeric expressions preserved. |
| [terrain_pipeline/environment_product.py](../../../terrain_pipeline/environment_product.py) | X2 | S1/R5、S1/R7、S1/R8、S1/R9、S2/G2、S2/G3、S2/G4、S2/G5、S2/G6、S2/G7、S2/G8、S2/G9、S2/G10、S2/G11、S2/G12、S2/G13、S2/G14、S2/G15、S2/G16、S2/G17、S2/G18、S2/G19、S2/G20 | Consolidated environment_product implementations; numeric expressions preserved. |
| [terrain_pipeline/environment_query.py](../../../terrain_pipeline/environment_query.py) | X2 | S1/R9、S2/G2、S2/G3、S2/G4、S2/G5、S2/G6 | 绝对30m坐标批量组合现气候/材料/岩性/土壤代理/群系，绑定输入和依赖源码身份；实测DEM雨影缺覆盖时明确pending/背景估计，精确请求内缓存；不推进动态ET、植被或默认世界。 |
| [terrain_pipeline/large_scale_resource_preflight.py](../../../terrain_pipeline/large_scale_resource_preflight.py) | X2 | S1/R9 | Resource gates for large surface-network experiments. The preflight deliberately distinguishes bound… |
| [terrain_pipeline/regional_surface_review.py](../../../terrain_pipeline/regional_surface_review.py) | X3 | S1/R9 | Static full-grid review export; no routing, weather or surface advancement. |
| [terrain_pipeline/surface_identity.py](../../../terrain_pipeline/surface_identity.py) | X1 | S1/R1、S1/R9 | Consolidated surface_identity implementations; numeric expressions preserved. |
| [terrain_pipeline/surface_rivers/__init__.py](../../../terrain_pipeline/surface_rivers/__init__.py) | X1 | S1/R1、S1/R9、S3/V8 | Deterministic offline surface drainage on a height grid. |
| [terrain_pipeline/surface_rivers/diagnostics.py](../../../terrain_pipeline/surface_rivers/diagnostics.py) | X3 | S1/R9 | Optional first-cause and propagation masks for offline river failures. |
| [terrain_pipeline/surface_rivers/finite_river_block_schedule.py](../../../terrain_pipeline/surface_rivers/finite_river_block_schedule.py) | X2 | S1/R9 | 同一完整有限域按cell就绪跨2/4空间块调度土壤产流与D8端口一次交付，确定性归并，保存绑定前缀水账的interval末完整检查点并冷恢复；不含时延、脏状态或默认消费。 |
| [terrain_pipeline/surface_rivers/pipeline.py](../../../terrain_pipeline/surface_rivers/pipeline.py) | X2 | S1/R9 | Versioned offline surface-routing product; independent of the game generator. |
| [terrain_pipeline/td_candidate_weather_jobs.py](../../../terrain_pipeline/td_candidate_weather_jobs.py) | X2 | S1/R5、S1/R7、S1/R9、S2/G5 | Serial candidate weather plans and externally pinned cold execution evidence. |
| [terrain_pipeline/td_catchment_dynamic_review.py](../../../terrain_pipeline/td_catchment_dynamic_review.py) | X3 | S1/R9 | Exclusive catchment saved-frame accounts; no simulation or water interpolation. |
| [terrain_pipeline/td_native_dynamic_scale_preflight.py](../../../terrain_pipeline/td_native_dynamic_scale_preflight.py) | X3 | S1/R9 | Pinned, read-only historical v10 native-grid sizing and window preparation. |
| [terrain_pipeline/terrain_map_style.py](../../../terrain_pipeline/terrain_map_style.py) | X3 |  | Single source of truth for offline terrain-map styling. Every terrain figure in this repository draw… |
