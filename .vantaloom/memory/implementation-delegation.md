---
name: implementation-delegation
description: 子代理模型与分工：DeepSeek flash 做归类/迁移等执行工作，主代理审查和发布任务
scope: project
type: preference
---
用户 2026-11-05 18:2x 最新：归类、迁移等重构执行工作交给 **DeepSeek flash** 子代理（VMH · Vantaloom Hub:deepseek-v4.1-flash，route plugin-channel~vantaloom-hub~official:deepseek-v4.1-flash）。主代理只负责发布任务、审查代码与测试、看图、整合交付，不亲自承担主要编码。
VMH 渠道没有开通 Sonnet 5.5（报 not enabled）；Sonnet 测试渠道曾报 401。可用模型以系统提示「子代理模型」列表为准；需要更强推理时可用 VMH Opus 5.5。渠道不可用须告知用户再换。
已在跑的 Opus 子代理做完当前步骤即可，不中途强换。
