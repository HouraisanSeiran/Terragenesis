---
name: map-style-split
description: 地图三种风格与图示规则；东方郡县制都城唯一；种族城镇保留主西幻
scope: project
type: spec
---
用户2026-11-01：地图风格分三种。①simple（简化地图）：沿用现有 app/static/map-art/map-art.svg 图样与分层设色底图，可用山脉等地形符号。②medieval（西式手绘）与③eastern（东方）：各自专属图示 sprite（map-art-medieval.svg / map-art-eastern.svg），只含资源、城市、道路相关图样；不叠地形符号，地形只由底图表现。资源符号 id 与 manifest.json 的 res-{kind} 一致以便跨风格共用。
东方城市分级按**郡县制**：town-hamlet=村、town-town=县城、town-city=郡城、town-capital=都城；都城**全国唯一**（含种族城镇的 capital 级），多于一个应拒绝。西式为村落/城镇/城市/王都，无唯一限制。
旧种族城镇图示（map-art.svg 的 town-{elf|dwarf|orc|halfling}-{tier}）保留，**主要西幻用，东方也可用**；未知种族回落到该风格的人类城镇符号。
