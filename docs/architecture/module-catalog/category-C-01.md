# 大类 C 三维地形 模块表 1

职责原文不代表认证；静态调用者只含Python AST本地导入。完整符号/依赖/hash见 catalog.json。

| 模块 | 类别／阶段 | 职责说明 | 说明依据 | 顶层符号／静态导入者数 |
| --- | --- | --- | --- | --- |
| [terrain_pipeline/hybrid_geometry.py](../../../terrain_pipeline/hybrid_geometry.py) | boolean-stage / S3/V1；S3/V2；S3/V3；S3/V5；S3/V6；S3/V8 | 从原生half-arm/prism及实体执行主Boolean并保存材料/阶段，不包含历史portal算法；current完整G2仍受精确表示门阻塞。 | manual-reviewed | canonical_json, identity, FilePin, read_pinned, RiverNode / 14 |
| [terrain_pipeline/hybrid_hydraulics.py](../../../terrain_pipeline/hybrid_hydraulics.py) | shared-numerical-core；bounded-hydraulics / S1/R7；S3/V4；S3/V8 | 有界水力共享类型、断面几何与对照契约；只提供当前族公共结构，不自行求解。；当前解析原生断面Radau核，保持v6数值策略；是VC-04收敛后的当前实现，历史版本须经显式legacy工具复验。 | manual-reviewed | _nonpositive_water_trial, _execution_failure, _diagnostic_stop, common_positive, common_submerged_intervals / 8 |
| [terrain_pipeline/special_terrain.py](../../../terrain_pipeline/special_terrain.py) | offline-volume-prototype / S3/V7；S3/V1；S3/V2；S3/V3；S3/V5；S3/V6；S3/V8 | 节理胞多边形柱体与VDM柱壁雕刻的离线闭合实体原型；截面/体积证据不等于全局自交和无限世界接线通过。 | manual-reviewed | as_origin, make_origin_normalizer, make_inside_by_winding, _finite_float, _pair / 6 |
| [terrain_pipeline/underground_rivers.py](../../../terrain_pipeline/underground_rivers.py) | algorithm-or-io / S3/V4；S1/R6；S3/V1；S3/V3；S3/V8 | Consolidated underground_rivers implementations; numeric expressions preserved. | source-docstring | UndergroundRecipe, plan_underground, save_underground, load_underground, Parameters / 3 |
| [terrain_pipeline/vdm_cuts.py](../../../terrain_pipeline/vdm_cuts.py) | shared-geometry-core；current-local-geometry / S3/V1；S2/G2；S3/V5；S3/V8 | 当前断层recipe类型与选择权重公共职责，不保留v1完整生成算法。；保留已变形VDM来源的局部断层切割，保存边来源与插值证据；只认证已声明的局部几何范围。 | manual-reviewed | _finite_number, CliffRecipe, _smooth, _triangles, _check_mesh / 11 |
| [vdm_diffusion/__init__.py](../../../vdm_diffusion/__init__.py) | generation-support / S3/V1；S3/V8 | Conditional diffusion whose denoised variable is an XYZ displacement map. | source-docstring | (无顶层命名声明) / 0 |
| [vdm_diffusion/__main__.py](../../../vdm_diffusion/__main__.py) | generation-support / S3/V1；S3/V8 | 职责待人工核对；仅登记可确认的静态结构 | unreviewed | main / 0 |
| [vdm_diffusion/checkpoint.py](../../../vdm_diffusion/checkpoint.py) | generation-support / S3/V1；S3/V8 | Explicit provenance prevents untrained/synthetic checkpoints masquerading as terrain models. | source-docstring | save, load / 3 |
| [vdm_diffusion/conditions.py](../../../vdm_diffusion/conditions.py) | generation-support / S3/V1；S3/V8 | Terrain Diffusion elevation/climate is a condition, not a replacement for denoised XYZ. | source-docstring | prepare / 1 |
| [vdm_diffusion/config.py](../../../vdm_diffusion/config.py) | generation-support / S3/V1；S3/V8 | Versioned model and coordinate contract, shared by training and sampling. | source-docstring | VdmConfig / 3 |
| [vdm_diffusion/data.py](../../../vdm_diffusion/data.py) | generation-support / S3/V1；S3/V8 | Paired displacement/condition data. A height-only raster is not accepted as XYZ ground truth. | source-docstring | load_pair, VdmDataset / 2 |
| [vdm_diffusion/export.py](../../../vdm_diffusion/export.py) | generation-support / S3/V1；S3/V8 | Lossless float32 XYZ map + displaced mesh. No height-to-vector postprocessing. | source-docstring | export / 3 |
| [vdm_diffusion/landforms.py](../../../vdm_diffusion/landforms.py) | generation-support / S3/V1；S3/V8 | Special geometry operators act after diffusion and only through explicit masks. | source-docstring | CliffSettings, CliffOperator / 3 |
| [vdm_diffusion/network.py](../../../vdm_diffusion/network.py) | generation-support / S3/V1；S3/V8 | Small time-conditioned U-Net: noisy XYZ vectors + conditioning -> three noise channels. | source-docstring | TimeEmbedding, ResidualBlock, VdmDenoiser / 3 |
| [vdm_diffusion/postprocess.py](../../../vdm_diffusion/postprocess.py) | generation-support / S3/V1；S3/V8 | Keep raw neural output and specialist landform output as separate artifacts. | source-docstring | sculpt / 1 |
| [vdm_diffusion/process.py](../../../vdm_diffusion/process.py) | generation-support / S3/V1；S3/V8 | DDPM epsilon training and deterministic DDIM reverse sampling of all XYZ channels. | source-docstring | VectorDiffusion / 3 |
| [vdm_diffusion/sample.py](../../../vdm_diffusion/sample.py) | generation-support / S3/V1；S3/V8 | Generate XYZ directly by reverse diffusion; never substitute displacement rules. | source-docstring | sample / 1 |
| [vdm_diffusion/train.py](../../../vdm_diffusion/train.py) | generation-support / S3/V1；S3/V8 | Train three-channel denoising from paired, world-space VDM maps. | source-docstring | train / 1 |
