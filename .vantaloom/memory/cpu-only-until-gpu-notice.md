---
name: cpu-only-until-gpu-notice
description: 2026-11-05 晚用户通知：独立显卡可用于生成测试（旧 CPU-only 规则失效）
scope: project
type: preference
---
用户 2026-11-05 19:10 通知：后续任务**可以用独立显卡（RTX 2080 SUPER，8 GB）做生成测试**，也可另开子代理专门跑生成。旧的「一律 CPU、不运行 TD 生成」规则失效。
- 用显卡前查空闲显存与可用内存（内存低于 2 GiB 不启动），记录设备、耗时、峰值显存/内存到 runtime-stats.json（不进身份）。
- 显卡用 `--device cuda` 或 `auto` 显式指定；PowerShell 屏蔽显卡要设 `$env:CUDA_VISIBLE_DEVICES='-1'`（空字符串无效）。
- 同一时间只让一个任务占显卡，避免互抢。
- 织梦网页世界生成界面要提供「是否使用 GPU」选项（默认按检测结果，无显卡时禁用并说明）。
