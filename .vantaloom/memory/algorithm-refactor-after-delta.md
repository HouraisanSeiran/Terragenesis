---
name: algorithm-refactor-after-delta
description: 全工程算法重构：三角洲验收后执行；模块越少越好；海洋输沙与河口连接并入新三角洲；证据索引入库
scope: project
type: spec
---
用户 2026-11-05：认为 Terragenesis 算法模块普遍存在「新版 import 旧版、多版本堆积、重复实现」问题。评估报告已落盘 .scratch/algorithm-audit-20261105/00–05（00-summary.md 为汇总，含 P1–P16 问题、RC1–RC37 规范候选、11 项待决）。
决定：
1. **等三角洲水网形态验收之后**再重构；重构规则写进《算法模块重构与编码规范》，最终并入 CONTRIBUTING.md 或 docs/architecture/。
2. 已定的归档（旧 coastal_delta_* 27 个文件及其测试、delta_network v1–v3）并入这次重构统一执行。
3. **用户原则：模块越少越好**。一功能一内核，能合并就合并；版本差异用参数/规则身份区分，不再叠 _vN 文件；公共设施（哈希、原子写、mmap 读、种子派生、坐标换算、常数）各收成一处。
4. 用户同意（2026-11-05）：coastal_marine_sediment、coastal_marine_longterm、coastal_river_connector 不单独保留为孤儿，合并成尽量少的模块供新三角洲 P3 演化使用，私有函数（_park_and_release、_plume_field、_wet_receiver、_face_transfer）改为公开接口；海岸底图/群岛/细化产品线保持。
5. 用户同意：verification/ 与关键 .scratch 证据至少把证据索引（路径+SHA256）纳入 git。
原则：被证据 pin 文件只归档不改内容（rainfall_runoff、geography_physical、hydrology_detail_td、hybrid 水力旧版等，只能新加一层显式传参）；只移动不删除（大量文件 git 未跟踪）；每批合并后跑测试、复跑核 SHA256、重建模块表。汇总里其余 8 项待决（v5 去留、山体实验线、分层、两个世界种子、temp_* 等）在起草规范时给建议交用户确认。
