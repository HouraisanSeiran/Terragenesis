---
name: refactor-snapshot-20261105
description: 算法重构的回退快照是 dist/Terragenesis-algorithms-20261105.zip，不打 git 提交
scope: project
type: spec
---
用户 2026-11-05：模块重构不打 git 提交，以 `dist/Terragenesis-algorithms-20261105.zip` 为整理前快照。
- zip SHA256 70D6346311A3CEBE4E1BD7FB7152295D1A65C93561359800E54F779F1BA4149C，2550 项，mtime 2026-11-05 02:15。
- 含 terrain_pipeline 593、tools 764、tests 725、diffusion 22 等；**不含** `.scratch/`、`verification/`、`验收图片/`。
- 主代理 07:14 核对：工作区 2124 个 .py 中，只有 delta_network_*（v1–v4）、run_delta_network_v1–v4、tools/delta_reference_metrics.py、对应测试不在快照里（三角洲族，本轮重构不动）；`diffusion/plate_td_conditioning.py` 在快照之后被修改过（可能是并行会话），R1–R3 不要动它，否则回退会丢失那次修改。
- 因快照不含 .scratch/verification，重构中这两个目录只读不改。
