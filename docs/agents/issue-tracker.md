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
