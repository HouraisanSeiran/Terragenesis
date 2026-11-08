---
name: terragenesis-reference-only
description: Terragenesis在织梦任务中不改代码；其冻结产品可作为地图数据源只读消费
scope: project
type: preference
---
织梦任务中不修改/删除Terragenesis代码与数据，不在其共用生成目录写入。用户2026-11-01决定以Terragenesis世界生成替代civ-atlas，故其**已冻结、身份校验通过**的产品可经配置（DREAM_TERRAIN_SOURCES）只读作为织梦地图数据源，不import其代码。运行其生成器/模型/GPU（如A3万公里板块与5km DEM）仍须用户明确授权或由Terragenesis主线发布。
