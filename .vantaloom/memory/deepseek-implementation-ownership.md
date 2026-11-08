---
name: deepseek-implementation-ownership
description: 用户指定DeepSeek VMH负责编码，主代理仅任务发布/审查/报告/验收发布
scope: project
type: preference
---
用户2026-10-28最新明确：DeepSeek VMH（用户写vhm）渠道已经恢复，代码编写功能交给DeepSeek，主代理负责发布任务、报告和审查。后续生产/工具/测试实现与修复均委派DeepSeek，优先VMH Vantaloom Hub route plugin-channel~vantaloom-hub~official:deepseek-v4.1-flash（须以当前可用列表为准）；主代理不再亲写实现代码，可维护规格/任务/交付文档、独立运行验证和发布产物。不要因历史VMH forbidden记忆继续擅用主代理编码；渠道失败如需改路由明确说明，不默默变更用户分工。
