---
name: module-naming-no-version
description: 用户 2026-11-05：模块/工具/测试按功能命名，不再用 _v1/_v2 等版本后缀
scope: project
type: spec
---
用户 2026-11-05：重构中模块也要重命名，不再用 v1、v2 之类的版本分类。
- terrain_pipeline 模块、tools、tests 文件名只表达功能，不带 _vN，也不用 new/final/correction/legacy/draft 等新旧词。
- 版本或算法差异放在代码里（参数、PROFILES、命名变体函数），产物 manifest 的 algorithm_id 照旧记录。
- 已保存的产物目录名（native-event-v3、terrain-v3 等）不改，代码改为从参数/配置传路径。
- 三角洲族改名留到 R5；织梦依赖的三个模块名不变。
规则写在 .scratch/algorithm-refactor-20261105/merge/rules.md §7。
