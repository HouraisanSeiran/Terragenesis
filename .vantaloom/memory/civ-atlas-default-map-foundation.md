---
name: civ-atlas-default-map-foundation
description: 地图基础方向：Terragenesis世界生成替代civ-atlas；保留civ-atlas接口；旧存档仅测试
scope: project
type: spec
---
用户2026-11-01更新：Terragenesis的世界生成（冻结DEM产品：板块骨架/世界DEM/按需30m TD）**替代civ-atlas**作为织梦地图基础；地图美化与玩法功能在织梦中完成。读取经 app/terrain_source.py 只读适配层（米制平面X东Z南，不做球面映射，不经civ-atlas PNG高度图/raster改形链）。**保留civ-atlas接口**（导入/宿主/API不删，作为可选旧来源）；**旧civ存档仅作测试夹具**，不迁移其文明数据到新地形。原则保留：稳定world/branch/version/entity映射，flux不当可用水量、物产不当库存，缺失数据标注。详见 docs/terrain-source-adapter.md。
