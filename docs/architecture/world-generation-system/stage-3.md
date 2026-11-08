# 第3阶段模块细分

此表按职责关联；同一owner可出现多次。主归属只计一次；关联不代表完整实现、默认接线或验收通过。工具/测试列表另见support.md。

## S3/V1 三维表示与查询边界

关联文件 22 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [terrain_pipeline/adaptive_mesh.py](../../../terrain_pipeline/adaptive_mesh.py) | 跨项关联 | Consolidated adaptive_mesh implementations; numeric expressions preserved. |
| [terrain_pipeline/artifacts/__init__.py](../../../terrain_pipeline/artifacts/__init__.py) | 跨项关联 | Portable terrain artifacts, independent of game consumers. |
| [terrain_pipeline/artifacts/contracts.py](../../../terrain_pipeline/artifacts/contracts.py) | 跨项关联 | Validated physical coordinates and immutable artifact payloads. |
| [terrain_pipeline/common_infra.py](../../../terrain_pipeline/common_infra.py) | 跨项关联 | Shared low-level infrastructure: hashing, canonical JSON, seeds, coordinates, atomic IO, mmap. One home for helpers that were copied into dozens of modules. Eve… |
| [terrain_pipeline/hybrid_geometry.py](../../../terrain_pipeline/hybrid_geometry.py) | 主归属 | 从原生half-arm/prism及实体执行主Boolean并保存材料/阶段，不包含历史portal算法；current完整G2仍受精确表示门阻塞。 |
| [terrain_pipeline/special_terrain.py](../../../terrain_pipeline/special_terrain.py) | 跨项关联 | 节理胞多边形柱体与VDM柱壁雕刻的离线闭合实体原型；截面/体积证据不等于全局自交和无限世界接线通过。 |
| [terrain_pipeline/td_ported_junction.py](../../../terrain_pipeline/td_ported_junction.py) | 跨项关联 | Source-relative arm strips joined to a hub ring with complete four-point ports. |
| [terrain_pipeline/underground_rivers.py](../../../terrain_pipeline/underground_rivers.py) | 跨项关联 | Consolidated underground_rivers implementations; numeric expressions preserved. |
| [terrain_pipeline/vdm_cuts.py](../../../terrain_pipeline/vdm_cuts.py) | 主归属 | 当前断层recipe类型与选择权重公共职责，不保留v1完整生成算法。；保留已变形VDM来源的局部断层切割，保存边来源与插值证据；只认证已声明的局部几何范围。 |
| [vdm_diffusion/__init__.py](../../../vdm_diffusion/__init__.py) | 主归属 | Conditional diffusion whose denoised variable is an XYZ displacement map. |
| [vdm_diffusion/__main__.py](../../../vdm_diffusion/__main__.py) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [vdm_diffusion/checkpoint.py](../../../vdm_diffusion/checkpoint.py) | 主归属 | Explicit provenance prevents untrained/synthetic checkpoints masquerading as terrain models. |
| [vdm_diffusion/conditions.py](../../../vdm_diffusion/conditions.py) | 主归属 | Terrain Diffusion elevation/climate is a condition, not a replacement for denoised XYZ. |
| [vdm_diffusion/config.py](../../../vdm_diffusion/config.py) | 主归属 | Versioned model and coordinate contract, shared by training and sampling. |
| [vdm_diffusion/data.py](../../../vdm_diffusion/data.py) | 主归属 | Paired displacement/condition data. A height-only raster is not accepted as XYZ ground truth. |
| [vdm_diffusion/export.py](../../../vdm_diffusion/export.py) | 主归属 | Lossless float32 XYZ map + displaced mesh. No height-to-vector postprocessing. |
| [vdm_diffusion/landforms.py](../../../vdm_diffusion/landforms.py) | 主归属 | Special geometry operators act after diffusion and only through explicit masks. |
| [vdm_diffusion/network.py](../../../vdm_diffusion/network.py) | 主归属 | Small time-conditioned U-Net: noisy XYZ vectors + conditioning -> three noise channels. |
| [vdm_diffusion/postprocess.py](../../../vdm_diffusion/postprocess.py) | 主归属 | Keep raw neural output and specialist landform output as separate artifacts. |
| [vdm_diffusion/process.py](../../../vdm_diffusion/process.py) | 主归属 | DDPM epsilon training and deterministic DDIM reverse sampling of all XYZ channels. |
| [vdm_diffusion/sample.py](../../../vdm_diffusion/sample.py) | 主归属 | Generate XYZ directly by reverse diffusion; never substitute displacement rules. |
| [vdm_diffusion/train.py](../../../vdm_diffusion/train.py) | 主归属 | Train three-channel denoising from paired, world-space VDM maps. |

## S3/V2 天坑、竖井与天窗

关联文件 2 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [terrain_pipeline/hybrid_geometry.py](../../../terrain_pipeline/hybrid_geometry.py) | 跨项关联 | 从原生half-arm/prism及实体执行主Boolean并保存材料/阶段，不包含历史portal算法；current完整G2仍受精确表示门阻塞。 |
| [terrain_pipeline/special_terrain.py](../../../terrain_pipeline/special_terrain.py) | 跨项关联 | 节理胞多边形柱体与VDM柱壁雕刻的离线闭合实体原型；截面/体积证据不等于全局自交和无限世界接线通过。 |

## S3/V3 喀斯特溶洞与地下通道

关联文件 3 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [terrain_pipeline/hybrid_geometry.py](../../../terrain_pipeline/hybrid_geometry.py) | 跨项关联 | 从原生half-arm/prism及实体执行主Boolean并保存材料/阶段，不包含历史portal算法；current完整G2仍受精确表示门阻塞。 |
| [terrain_pipeline/special_terrain.py](../../../terrain_pipeline/special_terrain.py) | 跨项关联 | 节理胞多边形柱体与VDM柱壁雕刻的离线闭合实体原型；截面/体积证据不等于全局自交和无限世界接线通过。 |
| [terrain_pipeline/underground_rivers.py](../../../terrain_pipeline/underground_rivers.py) | 跨项关联 | Consolidated underground_rivers implementations; numeric expressions preserved. |

## S3/V4 地下暗河与地表复出

关联文件 2 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [terrain_pipeline/hybrid_hydraulics.py](../../../terrain_pipeline/hybrid_hydraulics.py) | 跨项关联 | 有界水力共享类型、断面几何与对照契约；只提供当前族公共结构，不自行求解。；当前解析原生断面Radau核，保持v6数值策略；是VC-04收敛后的当前实现，历史版本须经显式legacy工具复验。 |
| [terrain_pipeline/underground_rivers.py](../../../terrain_pipeline/underground_rivers.py) | 主归属 | Consolidated underground_rivers implementations; numeric expressions preserved. |

## S3/V5 河谷悬挑、外凸岩壁与壁洞

关联文件 3 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [terrain_pipeline/hybrid_geometry.py](../../../terrain_pipeline/hybrid_geometry.py) | 跨项关联 | 从原生half-arm/prism及实体执行主Boolean并保存材料/阶段，不包含历史portal算法；current完整G2仍受精确表示门阻塞。 |
| [terrain_pipeline/special_terrain.py](../../../terrain_pipeline/special_terrain.py) | 跨项关联 | 节理胞多边形柱体与VDM柱壁雕刻的离线闭合实体原型；截面/体积证据不等于全局自交和无限世界接线通过。 |
| [terrain_pipeline/vdm_cuts.py](../../../terrain_pipeline/vdm_cuts.py) | 跨项关联 | 当前断层recipe类型与选择权重公共职责，不保留v1完整生成算法。；保留已变形VDM来源的局部断层切割，保存边来源与插值证据；只认证已声明的局部几何范围。 |

## S3/V6 天然桥与岩拱

关联文件 2 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [terrain_pipeline/hybrid_geometry.py](../../../terrain_pipeline/hybrid_geometry.py) | 跨项关联 | 从原生half-arm/prism及实体执行主Boolean并保存材料/阶段，不包含历史portal算法；current完整G2仍受精确表示门阻塞。 |
| [terrain_pipeline/special_terrain.py](../../../terrain_pipeline/special_terrain.py) | 跨项关联 | 节理胞多边形柱体与VDM柱壁雕刻的离线闭合实体原型；截面/体积证据不等于全局自交和无限世界接线通过。 |

## S3/V7 石柱群与节理壁面

关联文件 1 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [terrain_pipeline/special_terrain.py](../../../terrain_pipeline/special_terrain.py) | 主归属 | 节理胞多边形柱体与VDM柱壁雕刻的离线闭合实体原型；截面/体积证据不等于全局自交和无限世界接线通过。 |

## S3/V8 结构、水路和消费者适配层

关联文件 27 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [terrain_pipeline/__init__.py](../../../terrain_pipeline/__init__.py) | 跨项关联 | Terrain Diffusion height -> vector displacement -> local sculpting. |
| [terrain_pipeline/artifacts/__init__.py](../../../terrain_pipeline/artifacts/__init__.py) | 跨项关联 | Portable terrain artifacts, independent of game consumers. |
| [terrain_pipeline/artifacts/contracts.py](../../../terrain_pipeline/artifacts/contracts.py) | 跨项关联 | Validated physical coordinates and immutable artifact payloads. |
| [terrain_pipeline/common_infra.py](../../../terrain_pipeline/common_infra.py) | 跨项关联 | Shared low-level infrastructure: hashing, canonical JSON, seeds, coordinates, atomic IO, mmap. One home for helpers that were copied into dozens of modules. Eve… |
| [terrain_pipeline/conversion.py](../../../terrain_pipeline/conversion.py) | 跨项关联 | Lossless geometry conversion after explicit Minecraft vertical remapping. |
| [terrain_pipeline/hybrid_geometry.py](../../../terrain_pipeline/hybrid_geometry.py) | 跨项关联 | 从原生half-arm/prism及实体执行主Boolean并保存材料/阶段，不包含历史portal算法；current完整G2仍受精确表示门阻塞。 |
| [terrain_pipeline/hybrid_hydraulics.py](../../../terrain_pipeline/hybrid_hydraulics.py) | 跨项关联 | 有界水力共享类型、断面几何与对照契约；只提供当前族公共结构，不自行求解。；当前解析原生断面Radau核，保持v6数值策略；是VC-04收敛后的当前实现，历史版本须经显式legacy工具复验。 |
| [terrain_pipeline/metric_region.py](../../../terrain_pipeline/metric_region.py) | 跨项关联 | Physical-metre regional landform processing. |
| [terrain_pipeline/metric_region_storage.py](../../../terrain_pipeline/metric_region_storage.py) | 跨项关联 | Explicit publication and read-only loading for metric region results. |
| [terrain_pipeline/minecraft_export.py](../../../terrain_pipeline/minecraft_export.py) | 跨项关联 | Explicit, checked snapshot for the read-only Minecraft surface adapter. |
| [terrain_pipeline/special_terrain.py](../../../terrain_pipeline/special_terrain.py) | 跨项关联 | 节理胞多边形柱体与VDM柱壁雕刻的离线闭合实体原型；截面/体积证据不等于全局自交和无限世界接线通过。 |
| [terrain_pipeline/surface_rivers/__init__.py](../../../terrain_pipeline/surface_rivers/__init__.py) | 跨项关联 | Deterministic offline surface drainage on a height grid. |
| [terrain_pipeline/underground_rivers.py](../../../terrain_pipeline/underground_rivers.py) | 跨项关联 | Consolidated underground_rivers implementations; numeric expressions preserved. |
| [terrain_pipeline/vdm_cuts.py](../../../terrain_pipeline/vdm_cuts.py) | 跨项关联 | 当前断层recipe类型与选择权重公共职责，不保留v1完整生成算法。；保留已变形VDM来源的局部断层切割，保存边来源与插值证据；只认证已声明的局部几何范围。 |
| [vdm_diffusion/__init__.py](../../../vdm_diffusion/__init__.py) | 跨项关联 | Conditional diffusion whose denoised variable is an XYZ displacement map. |
| [vdm_diffusion/__main__.py](../../../vdm_diffusion/__main__.py) | 跨项关联 | 职责待人工核对；仅登记可确认的静态结构 |
| [vdm_diffusion/checkpoint.py](../../../vdm_diffusion/checkpoint.py) | 跨项关联 | Explicit provenance prevents untrained/synthetic checkpoints masquerading as terrain models. |
| [vdm_diffusion/conditions.py](../../../vdm_diffusion/conditions.py) | 跨项关联 | Terrain Diffusion elevation/climate is a condition, not a replacement for denoised XYZ. |
| [vdm_diffusion/config.py](../../../vdm_diffusion/config.py) | 跨项关联 | Versioned model and coordinate contract, shared by training and sampling. |
| [vdm_diffusion/data.py](../../../vdm_diffusion/data.py) | 跨项关联 | Paired displacement/condition data. A height-only raster is not accepted as XYZ ground truth. |
| [vdm_diffusion/export.py](../../../vdm_diffusion/export.py) | 跨项关联 | Lossless float32 XYZ map + displaced mesh. No height-to-vector postprocessing. |
| [vdm_diffusion/landforms.py](../../../vdm_diffusion/landforms.py) | 跨项关联 | Special geometry operators act after diffusion and only through explicit masks. |
| [vdm_diffusion/network.py](../../../vdm_diffusion/network.py) | 跨项关联 | Small time-conditioned U-Net: noisy XYZ vectors + conditioning -> three noise channels. |
| [vdm_diffusion/postprocess.py](../../../vdm_diffusion/postprocess.py) | 跨项关联 | Keep raw neural output and specialist landform output as separate artifacts. |
| [vdm_diffusion/process.py](../../../vdm_diffusion/process.py) | 跨项关联 | DDPM epsilon training and deterministic DDIM reverse sampling of all XYZ channels. |
| [vdm_diffusion/sample.py](../../../vdm_diffusion/sample.py) | 跨项关联 | Generate XYZ directly by reverse diffusion; never substitute displacement rules. |
| [vdm_diffusion/train.py](../../../vdm_diffusion/train.py) | 跨项关联 | Train three-channel denoising from paired, world-space VDM maps. |
