# 第4阶段模块细分

此表按职责关联；同一owner可出现多次。主归属只计一次；关联不代表完整实现、默认接线或验收通过。工具/测试列表另见support.md。

J1–J6 是本轮导航分类，原规划没有这套编号，不构成新的Java开发批准。既有Java算法作为兼容实现保留，不替代前三阶段Python内核。

## S4/J1 Python产物/格式读取与转换

关联文件 13 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [terrain_pipeline/legacy_region.py](../../../terrain_pipeline/legacy_region.py) | 跨项关联 | Explicit import and read-only consumption of legacy region results. |
| [terrain_pipeline/minecraft_export.py](../../../terrain_pipeline/minecraft_export.py) | 主归属 | Explicit, checked snapshot for the read-only Minecraft surface adapter. |
| [src/main/java/com/remotemountains/diffusion/BakedTerrainSource.java](../../../src/main/java/com/remotemountains/diffusion/BakedTerrainSource.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/hydrology3d/RiverNetworkJson.java](../../../src/main/java/com/remotemountains/hydrology3d/RiverNetworkJson.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/prepared/PreparedArtifact.java](../../../src/main/java/com/remotemountains/prepared/PreparedArtifact.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/prepared/PreparedSurfaceModifier.java](../../../src/main/java/com/remotemountains/prepared/PreparedSurfaceModifier.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/prepared/PreparedTerrainExporter.java](../../../src/main/java/com/remotemountains/prepared/PreparedTerrainExporter.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/prepared/PreparedTerrainSource.java](../../../src/main/java/com/remotemountains/prepared/PreparedTerrainSource.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/prepared/PreparedVdmSource.java](../../../src/main/java/com/remotemountains/prepared/PreparedVdmSource.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/region/DerivedRegionArtifact.java](../../../src/main/java/com/remotemountains/region/DerivedRegionArtifact.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/region/RawRegionArtifact.java](../../../src/main/java/com/remotemountains/region/RawRegionArtifact.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/region/RegionArtifact.java](../../../src/main/java/com/remotemountains/region/RegionArtifact.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/region/RegionExport.java](../../../src/main/java/com/remotemountains/region/RegionExport.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |

## S4/J2 坐标、尺度、体积与材质/群系映射

关联文件 16 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [terrain_pipeline/conversion.py](../../../terrain_pipeline/conversion.py) | 主归属 | Lossless geometry conversion after explicit Minecraft vertical remapping. |
| [terrain_pipeline/minecraft_preset.py](../../../terrain_pipeline/minecraft_preset.py) | 主归属 | Pure export mapping; no changes to physical terrain or old binary exporters. |
| [src/main/java/com/remotemountains/core/TerrainScale.java](../../../src/main/java/com/remotemountains/core/TerrainScale.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/vdm/CliffSculptor.java](../../../src/main/java/com/remotemountains/vdm/CliffSculptor.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/vdm/DensityColumn.java](../../../src/main/java/com/remotemountains/vdm/DensityColumn.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/vdm/Displacement.java](../../../src/main/java/com/remotemountains/vdm/Displacement.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/vdm/GeneratedVdmSource.java](../../../src/main/java/com/remotemountains/vdm/GeneratedVdmSource.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/vdm/OptionalVdmSource.java](../../../src/main/java/com/remotemountains/vdm/OptionalVdmSource.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/vdm/SurfaceModifier.java](../../../src/main/java/com/remotemountains/vdm/SurfaceModifier.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/vdm/VdmBuilder.java](../../../src/main/java/com/remotemountains/vdm/VdmBuilder.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/vdm/VdmFile.java](../../../src/main/java/com/remotemountains/vdm/VdmFile.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/vdm/VdmTerrainSource.java](../../../src/main/java/com/remotemountains/vdm/VdmTerrainSource.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/vdm/VdmVoxelizer.java](../../../src/main/java/com/remotemountains/vdm/VdmVoxelizer.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/vdm/VectorDisplacementMap.java](../../../src/main/java/com/remotemountains/vdm/VectorDisplacementMap.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/world/SurfacePalette.java](../../../src/main/java/com/remotemountains/world/SurfacePalette.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/world/TerrainBiomeSource.java](../../../src/main/java/com/remotemountains/world/TerrainBiomeSource.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |

## S4/J3 来源选择与区域准备

关联文件 66 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [src/main/java/com/remotemountains/canyon/CanyonCliffLayout.java](../../../src/main/java/com/remotemountains/canyon/CanyonCliffLayout.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/canyon/CanyonCliffModifier.java](../../../src/main/java/com/remotemountains/canyon/CanyonCliffModifier.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/canyon/CanyonCliffStyle.java](../../../src/main/java/com/remotemountains/canyon/CanyonCliffStyle.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/cliff/CliffErosionSolver.java](../../../src/main/java/com/remotemountains/cliff/CliffErosionSolver.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/cliff/CliffGeometry.java](../../../src/main/java/com/remotemountains/cliff/CliffGeometry.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/cliff/CliffPatch.java](../../../src/main/java/com/remotemountains/cliff/CliffPatch.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/cliff/CliffPipeline.java](../../../src/main/java/com/remotemountains/cliff/CliffPipeline.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/cliff/CliffPlacement.java](../../../src/main/java/com/remotemountains/cliff/CliffPlacement.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/cliff/CliffSettings.java](../../../src/main/java/com/remotemountains/cliff/CliffSettings.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/cliff/CliffVdmModifier.java](../../../src/main/java/com/remotemountains/cliff/CliffVdmModifier.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/cliff/ErosionStatistics.java](../../../src/main/java/com/remotemountains/cliff/ErosionStatistics.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/cliff/RegionalCliffLayout.java](../../../src/main/java/com/remotemountains/cliff/RegionalCliffLayout.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/cliff/RegionalCliffModifier.java](../../../src/main/java/com/remotemountains/cliff/RegionalCliffModifier.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/cliff/RunoffBoundary.java](../../../src/main/java/com/remotemountains/cliff/RunoffBoundary.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/cliff/SurfaceRunoffSolver.java](../../../src/main/java/com/remotemountains/cliff/SurfaceRunoffSolver.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/cliff/Vec3.java](../../../src/main/java/com/remotemountains/cliff/Vec3.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/cliff/VoronoiRockField.java](../../../src/main/java/com/remotemountains/cliff/VoronoiRockField.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/cliff/WaterDetachment.java](../../../src/main/java/com/remotemountains/cliff/WaterDetachment.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/core/CaveModel.java](../../../src/main/java/com/remotemountains/core/CaveModel.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/core/ClimateModel.java](../../../src/main/java/com/remotemountains/core/ClimateModel.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/core/Hydrology.java](../../../src/main/java/com/remotemountains/core/Hydrology.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/core/InselbergShape.java](../../../src/main/java/com/remotemountains/core/InselbergShape.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/core/KarstShape.java](../../../src/main/java/com/remotemountains/core/KarstShape.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/core/Landform.java](../../../src/main/java/com/remotemountains/core/Landform.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/core/LandformShape.java](../../../src/main/java/com/remotemountains/core/LandformShape.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/core/Landscape.java](../../../src/main/java/com/remotemountains/core/Landscape.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/core/Noise.java](../../../src/main/java/com/remotemountains/core/Noise.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/core/PillarShape.java](../../../src/main/java/com/remotemountains/core/PillarShape.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/core/Regions.java](../../../src/main/java/com/remotemountains/core/Regions.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/core/RiftShape.java](../../../src/main/java/com/remotemountains/core/RiftShape.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/core/ShapePrimitives.java](../../../src/main/java/com/remotemountains/core/ShapePrimitives.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/core/Terrain.java](../../../src/main/java/com/remotemountains/core/Terrain.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/core/TerrainModeDescriptor.java](../../../src/main/java/com/remotemountains/core/TerrainModeDescriptor.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/core/TerrainModeRegistry.java](../../../src/main/java/com/remotemountains/core/TerrainModeRegistry.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/core/TerrainPreparation.java](../../../src/main/java/com/remotemountains/core/TerrainPreparation.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/core/TerrainSourceFactory.java](../../../src/main/java/com/remotemountains/core/TerrainSourceFactory.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/diffusion/DemoLandformField.java](../../../src/main/java/com/remotemountains/diffusion/DemoLandformField.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/diffusion/DiffusionTile.java](../../../src/main/java/com/remotemountains/diffusion/DiffusionTile.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/diffusion/PerlinLandformVariation.java](../../../src/main/java/com/remotemountains/diffusion/PerlinLandformVariation.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/erosion3d/Erosion3d.java](../../../src/main/java/com/remotemountains/erosion3d/Erosion3d.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/erosion3d/ErosionConfig.java](../../../src/main/java/com/remotemountains/erosion3d/ErosionConfig.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/erosion3d/ErosionResult.java](../../../src/main/java/com/remotemountains/erosion3d/ErosionResult.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/erosion3d/Point3.java](../../../src/main/java/com/remotemountains/erosion3d/Point3.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/erosion3d/SedimentLedger.java](../../../src/main/java/com/remotemountains/erosion3d/SedimentLedger.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/erosion3d/SurfaceSample.java](../../../src/main/java/com/remotemountains/erosion3d/SurfaceSample.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/erosion3d/SweptPath.java](../../../src/main/java/com/remotemountains/erosion3d/SweptPath.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/hydrology3d/Point3.java](../../../src/main/java/com/remotemountains/hydrology3d/Point3.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/hydrology3d/RiverConfig.java](../../../src/main/java/com/remotemountains/hydrology3d/RiverConfig.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/hydrology3d/RiverNetwork.java](../../../src/main/java/com/remotemountains/hydrology3d/RiverNetwork.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/hydrology3d/RiverNode.java](../../../src/main/java/com/remotemountains/hydrology3d/RiverNode.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/hydrology3d/RiverReach.java](../../../src/main/java/com/remotemountains/hydrology3d/RiverReach.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/region/RegionConfig.java](../../../src/main/java/com/remotemountains/region/RegionConfig.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/region/RegionLandformLayout.java](../../../src/main/java/com/remotemountains/region/RegionLandformLayout.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/region/RegionRuntime.java](../../../src/main/java/com/remotemountains/region/RegionRuntime.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/region/processing/GaussianFilter.java](../../../src/main/java/com/remotemountains/region/processing/GaussianFilter.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/region/processing/LandformClassifier.java](../../../src/main/java/com/remotemountains/region/processing/LandformClassifier.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/region/processing/LandformPolicies.java](../../../src/main/java/com/remotemountains/region/processing/LandformPolicies.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/region/processing/ProcessedTile.java](../../../src/main/java/com/remotemountains/region/processing/ProcessedTile.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/region/processing/ProcessingConfig.java](../../../src/main/java/com/remotemountains/region/processing/ProcessingConfig.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/region/processing/RegionFeatures.java](../../../src/main/java/com/remotemountains/region/processing/RegionFeatures.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/region/processing/RegionProcessor.java](../../../src/main/java/com/remotemountains/region/processing/RegionProcessor.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/region/processing/SurfaceProtection.java](../../../src/main/java/com/remotemountains/region/processing/SurfaceProtection.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/watershed/DrainageGraph.java](../../../src/main/java/com/remotemountains/watershed/DrainageGraph.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/watershed/MountainRelief.java](../../../src/main/java/com/remotemountains/watershed/MountainRelief.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/watershed/RiverProfile.java](../../../src/main/java/com/remotemountains/watershed/RiverProfile.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/watershedcliff/WatershedCliffModifier.java](../../../src/main/java/com/remotemountains/watershedcliff/WatershedCliffModifier.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |

## S4/J4 缓存、只读采样与区块交付

关联文件 19 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [src/main/java/com/remotemountains/core/BaseTerrainSource.java](../../../src/main/java/com/remotemountains/core/BaseTerrainSource.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/core/PrototypeTerrainSource.java](../../../src/main/java/com/remotemountains/core/PrototypeTerrainSource.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/core/TerrainTileCache.java](../../../src/main/java/com/remotemountains/core/TerrainTileCache.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/diffusion/DemoLandformSource.java](../../../src/main/java/com/remotemountains/diffusion/DemoLandformSource.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/diffusion/DiffusionTerrainSource.java](../../../src/main/java/com/remotemountains/diffusion/DiffusionTerrainSource.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/diffusion/TerrainSources.java](../../../src/main/java/com/remotemountains/diffusion/TerrainSources.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/region/DerivedRegionTerrainSource.java](../../../src/main/java/com/remotemountains/region/DerivedRegionTerrainSource.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/region/MetricProcessedTerrainSource.java](../../../src/main/java/com/remotemountains/region/MetricProcessedTerrainSource.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/region/RawRegionTerrainSource.java](../../../src/main/java/com/remotemountains/region/RawRegionTerrainSource.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/region/RegionTerrainSource.java](../../../src/main/java/com/remotemountains/region/RegionTerrainSource.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/watershed/WatershedTerrainSource.java](../../../src/main/java/com/remotemountains/watershed/WatershedTerrainSource.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/world/CanyonWorldVerification.java](../../../src/main/java/com/remotemountains/world/CanyonWorldVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/world/CliffWorldVerification.java](../../../src/main/java/com/remotemountains/world/CliffWorldVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/world/RegionalCliffWorldVerification.java](../../../src/main/java/com/remotemountains/world/RegionalCliffWorldVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/world/RemoteGenerator.java](../../../src/main/java/com/remotemountains/world/RemoteGenerator.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/world/TallWorldVerification.java](../../../src/main/java/com/remotemountains/world/TallWorldVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/world/VerificationProbe.java](../../../src/main/java/com/remotemountains/world/VerificationProbe.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/world/WatershedWorldVerification.java](../../../src/main/java/com/remotemountains/world/WatershedWorldVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/world/WorldGenerationStatus.java](../../../src/main/java/com/remotemountains/world/WorldGenerationStatus.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |

## S4/J5 运行安装、配置与服务资源

关联文件 15 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [src/main/java/com/remotemountains/client/LandformMode.java](../../../src/main/java/com/remotemountains/client/LandformMode.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/client/LandformSettingsScreen.java](../../../src/main/java/com/remotemountains/client/LandformSettingsScreen.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/client/TerrainInstallClient.java](../../../src/main/java/com/remotemountains/client/TerrainInstallClient.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/client/TerrainInstallScreen.java](../../../src/main/java/com/remotemountains/client/TerrainInstallScreen.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/client/TerrainPreflight.java](../../../src/main/java/com/remotemountains/client/TerrainPreflight.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/client/TerrainPreflightScreen.java](../../../src/main/java/com/remotemountains/client/TerrainPreflightScreen.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/client/mixin/CreateWorldPreflightMixin.java](../../../src/main/java/com/remotemountains/client/mixin/CreateWorldPreflightMixin.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/client/mixin/LandformPresetEditorMixin.java](../../../src/main/java/com/remotemountains/client/mixin/LandformPresetEditorMixin.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/client/mixin/WorldLoadPreflightMixin.java](../../../src/main/java/com/remotemountains/client/mixin/WorldLoadPreflightMixin.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/diffusion/DiffusionBootstrapAssets.java](../../../src/main/java/com/remotemountains/diffusion/DiffusionBootstrapAssets.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/diffusion/DiffusionClient.java](../../../src/main/java/com/remotemountains/diffusion/DiffusionClient.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/diffusion/DiffusionServiceManager.java](../../../src/main/java/com/remotemountains/diffusion/DiffusionServiceManager.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/diffusion/DiffusionServiceSources.java](../../../src/main/java/com/remotemountains/diffusion/DiffusionServiceSources.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/diffusion/ManagedTerrainInstallation.java](../../../src/main/java/com/remotemountains/diffusion/ManagedTerrainInstallation.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/main/java/com/remotemountains/diffusion/PortablePythonInstaller.java](../../../src/main/java/com/remotemountains/diffusion/PortablePythonInstaller.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |

## S4/J6 Mod注册、载入与兼容验证

关联文件 36 个。

| 当前模块 | 归属关系 | 职责/适用边界 |
| --- | --- | --- |
| [src/main/java/com/remotemountains/RemoteMountains.java](../../../src/main/java/com/remotemountains/RemoteMountains.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/canyon/CanyonPreview.java](../../../src/test/java/com/remotemountains/canyon/CanyonPreview.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/canyon/CanyonVerification.java](../../../src/test/java/com/remotemountains/canyon/CanyonVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/cliff/CliffPreviewExporter.java](../../../src/test/java/com/remotemountains/cliff/CliffPreviewExporter.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/cliff/CliffVerification.java](../../../src/test/java/com/remotemountains/cliff/CliffVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/cliff/RegionalCliffVerification.java](../../../src/test/java/com/remotemountains/cliff/RegionalCliffVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/core/ClientMixinLoadVerification.java](../../../src/test/java/com/remotemountains/core/ClientMixinLoadVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/core/CoreVerification.java](../../../src/test/java/com/remotemountains/core/CoreVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/core/DemoVerification.java](../../../src/test/java/com/remotemountains/core/DemoVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/core/DiffusionVerification.java](../../../src/test/java/com/remotemountains/core/DiffusionVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/core/IrregularHydrologyVerification.java](../../../src/test/java/com/remotemountains/core/IrregularHydrologyVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/core/LandformComparison.java](../../../src/test/java/com/remotemountains/core/LandformComparison.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/core/PreviewExporter.java](../../../src/test/java/com/remotemountains/core/PreviewExporter.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/core/TerrainModeRegistryVerification.java](../../../src/test/java/com/remotemountains/core/TerrainModeRegistryVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/core/TerrainScaleVerification.java](../../../src/test/java/com/remotemountains/core/TerrainScaleVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/core/TerrainTileCacheVerification.java](../../../src/test/java/com/remotemountains/core/TerrainTileCacheVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/diffusion/FirstInstallProbe.java](../../../src/test/java/com/remotemountains/diffusion/FirstInstallProbe.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/diffusion/ManagedInstallationVerification.java](../../../src/test/java/com/remotemountains/diffusion/ManagedInstallationVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/diffusion/ManagedServiceVerification.java](../../../src/test/java/com/remotemountains/diffusion/ManagedServiceVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/diffusion/ProfileMismatchVerification.java](../../../src/test/java/com/remotemountains/diffusion/ProfileMismatchVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/erosion3d/Erosion3dVerification.java](../../../src/test/java/com/remotemountains/erosion3d/Erosion3dVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/hydrology3d/RiverNetworkVerification.java](../../../src/test/java/com/remotemountains/hydrology3d/RiverNetworkVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/prepared/DerivedConcurrencyVerification.java](../../../src/test/java/com/remotemountains/prepared/DerivedConcurrencyVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/prepared/DerivedRegionVerification.java](../../../src/test/java/com/remotemountains/prepared/DerivedRegionVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/prepared/PreparedArtifactVerification.java](../../../src/test/java/com/remotemountains/prepared/PreparedArtifactVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/prepared/PreparedShowcaseVerification.java](../../../src/test/java/com/remotemountains/prepared/PreparedShowcaseVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/prepared/RawRegionVerification.java](../../../src/test/java/com/remotemountains/prepared/RawRegionVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/prepared/RegionVerification.java](../../../src/test/java/com/remotemountains/prepared/RegionVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/region/MetricProcessedVerification.java](../../../src/test/java/com/remotemountains/region/MetricProcessedVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/region/RealSampleImportVerification.java](../../../src/test/java/com/remotemountains/region/RealSampleImportVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/region/processing/RegionProcessingCli.java](../../../src/test/java/com/remotemountains/region/processing/RegionProcessingCli.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/region/processing/RegionProcessorVerification.java](../../../src/test/java/com/remotemountains/region/processing/RegionProcessorVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/watershed/WatershedHeightmapVerification.java](../../../src/test/java/com/remotemountains/watershed/WatershedHeightmapVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/watershed/WatershedPreview.java](../../../src/test/java/com/remotemountains/watershed/WatershedPreview.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/watershed/WatershedVerification.java](../../../src/test/java/com/remotemountains/watershed/WatershedVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
| [src/test/java/com/remotemountains/watershedcliff/WatershedCliffVerification.java](../../../src/test/java/com/remotemountains/watershedcliff/WatershedCliffVerification.java) | 主归属 | 职责待人工核对；仅登记可确认的静态结构 |
