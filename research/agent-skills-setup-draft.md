# 工程技能配置草案（待确认，不是生效配置）

已确认：本地 Markdown 任务单、默认五个分类标签。当前项目没有多包工作区信号，采用单一上下文；不创建空的 CONTEXT.md 或 ADR。

待选择：根目录创建 AGENTS.md 或 CLAUDE.md。下列内容会写入所选文件及三个 docs/agents 文件。

## 根入口文件的内容

```markdown
# Terragenesis 工程约定

先阅读 CONTRIBUTING.md。保留 TODO.md 作为工作总览；具体任务与规格放在下述本地任务目录。

## Agent skills

### Issue tracker

任务与规格采用本地 Markdown，保存在 .scratch/<feature>/。详见 docs/agents/issue-tracker.md。

### Triage labels

使用五个默认分类标签。详见 docs/agents/triage-labels.md。

### Domain docs

采用 single-context：根 CONTEXT.md 与 docs/adr/，按需创建。详见 docs/agents/domain.md。
```

## docs/agents/issue-tracker.md 的内容

```markdown
# Issue tracker: Local Markdown

本项目的任务和规格保存在工作区 .scratch/。TODO.md 保持总体优先级和里程碑；具体任务链接到独立文件，避免维护相互矛盾的重复状态。

## 约定

- 每个功能一个目录：.scratch/<feature-slug>/。
- 规格：.scratch/<feature-slug>/spec.md。
- 实施任务：.scratch/<feature-slug>/issues/<NN>-<slug>.md，从 01 编号，每项独立文件。
- 分类状态在文件顶部用 Status: 记录；标签见 triage-labels.md。
- 评论和对话追加到文件末尾的 ## Comments。

## 发布或读取任务

技能要求发布到任务系统时，在上述目录创建 Markdown 文件。读取任务时使用用户给出的文件路径或任务编号；不创建远程 Issue。

## Wayfinder 约定

- 地图：.scratch/<effort>/map.md，记录 Notes、Decisions-so-far、Fog。
- 子任务：issues/NN-<slug>.md，Type: 为 research/prototype/grilling/task；正文保留待回答的问题。
- Wayfinder 自身的工作状态使用 Status: claimed/resolved，区别于分类标签。
- 依赖：Blocked by: NN, NN；全部依赖 resolved 才解除阻塞。
- 选择最小编号的未解决、未认领且无阻塞任务；先写 claimed，再开始工作。
- 解决后追加 ## Answer，标 resolved，并把摘要和链接写回地图 Decisions-so-far。
```

## docs/agents/triage-labels.md 的内容

```markdown
# Triage Labels

| Canonical role | 本地 Status 值 | 含义 |
| --- | --- | --- |
| needs-triage | needs-triage | 待维护者评估 |
| needs-info | needs-info | 等待补充信息 |
| ready-for-agent | ready-for-agent | 规格清楚，可交给代理实施 |
| ready-for-human | ready-for-human | 需要人工实施 |
| wontfix | wontfix | 不计划处理 |

技能提到分类角色时使用此映射；后续可以直接编辑第二列。
```

## docs/agents/domain.md 的内容

```markdown
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
```
