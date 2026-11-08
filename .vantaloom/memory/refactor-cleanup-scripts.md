---
name: refactor-cleanup-scripts
description: 用户允许重构完成后删除重构过程中的脚本工具
scope: project
type: preference
---
用户 2026-11-05：脚本工具等重构完之后可以删除。
- 时机：整个算法重构（迁移、收尾、模块表重建）完成并验收后，作为最后一步清理，不提前删。
- 默认范围（主代理理解，删除前列清单给用户确认）：重构期间子代理写的一次性辅助脚本和中间转储，例如 .scratch/algorithm-refactor-20261105/ 下的 categories/v*.py、classify*.py、inv.*、view*.txt、r2/_old_impls*.txt、_dump_*.txt、r3/gen_kernels.py、_astclones.txt 等，以及会话临时目录的 pin_scan.py、r1_verify.py。
- 保留：报告（*.md）、sha-index、manifest、批次记录、规范草稿、legacy-code/ 下的归档与 manifest。
- 范围外需另问：根目录 temp_*、legacy-code/ 里已归档的 tools、三角洲 work/ 探针脚本。
- 删除前对清单做一次引用扫描，确认无活跃代码或测试引用。
