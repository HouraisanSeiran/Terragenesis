# Domain Docs

## 布局

采用 single-context：根目录 CONTEXT.md 与 docs/adr/。当前的 Java、Python 与预览代码属于同一工程，不因此拆成多个上下文。

## 探索前读取

- 优先读取根 CONTEXT.md；若以后存在 CONTEXT-MAP.md，则按其链接读取相关上下文。
- 读取 docs/adr/ 中与当前任务相关的架构决策。
- 文件不存在则直接继续，不把缺失视为阻塞，也不提前创建空文档。domain-modeling 会在术语或决策明确后按需创建。
- 现有工程约定仍见 CONTRIBUTING.md；优先级见 TODO.md；论文依据和实验状态保存在 research/，不能把实验假设当成已批准架构决策。

## 术语和决策

输出中的领域概念使用 CONTEXT.md 词汇，不随意改称。概念缺失时先核对是否确有需要，再记录供 domain-modeling 处理。

若提议与已存在的 ADR 矛盾，明确指出冲突的 ADR 和重新讨论的理由，不静默覆盖。
