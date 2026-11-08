---
name: legacy-coastal-delta-archive
description: 旧 coastal_delta_* 三角洲算法归档与 P3 独立演化的用户决定（2026-11-05）
scope: project
type: spec
---
用户 2026-11-05 确认：
1. 旧三角洲算法（coastal_delta_* 三角洲专用模块及对应测试）在复杂三角洲水网 v3 形态验收通过后归档到 legacy-code/coastal-delta-20261105/，附原路径+SHA256+理由清单；只移动不删除（文件在 git 中未跟踪）。海岸/海洋模块（coastal_terrain*、coastal_archipelago*、coastal_detail*、coastal_marine_* 等）保留原处。归档前：再扫证据 pin（含 >5MB 大文件）、查 coastal_* 族内部互相引用、登记 .scratch 驱动脚本（如 reference-case-v7/run.py）将无法原样复跑；归档后跑测试并重建 module-map / module-catalog --check。2026-11-05 扫描：族外非测试引用方 5 个，全部只引用海岸产品模块，无一引用 coastal_delta_*。
2. P3 短时水沙演化改为在新骨架（delta_network_*）上独立实现，只搬移问题单 24 的输沙公式（过剩剪应力能力 + 欠载冲刷 + 子步），不依赖旧 coastal_delta_multicell / ChannelInventory 事件链；问题单 24 的 coastal_delta_hydraulic_capacity/event 两模块随旧代码一并归档或由新实现取代。
