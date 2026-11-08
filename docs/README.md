# 现行文档入口

进度与任务总览仍以根目录 [TODO.md](../TODO.md) 为准；本页只整理**当前仍应优先阅读**的文档。过时报告已迁入 [archive/](archive/README.md)，不作为任务发布依据。

## 必读

| 文档 | 用途 |
| --- | --- |
| [../README.md](../README.md) | 工程定位与近期交付摘要 |
| [../CONTEXT.md](../CONTEXT.md) | 领域词汇与系统语境 |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | 维护约定、种子、验收规则 |
| [../AGENTS.md](../AGENTS.md) | Agent 工作约定 |
| [../无限世界地形生成评价标准.md](../无限世界地形生成评价标准.md) | 无限世界评价入口 |
| [../Terragenesis-1-3阶段科学评估与开源对照-20261104.md](../Terragenesis-1-3阶段科学评估与开源对照-20261104.md) | 1–3 阶段科学评估与开源对照（现行参考） |
| [terrain-diffusion-four-stage-roadmap.md](terrain-diffusion-four-stage-roadmap.md) | 四阶段主线与未完成项 |

## 架构与模块

| 文档 | 用途 |
| --- | --- |
| [architecture/world-generation-system/README.md](architecture/world-generation-system/README.md) | 世界生成系统模块总览 |
| [architecture/module-catalog/README.md](architecture/module-catalog/README.md) | 全仓模块职责台账 |
| [architecture/module-map.md](architecture/module-map.md) | 模块地图 |
| [architecture/implementation-guide.md](architecture/implementation-guide.md) | 四阶段实现与数据流 |
| [architecture/river-module-classification-20261009.md](architecture/river-module-classification-20261009.md) | 河网模块主线分类 |
| [adr/](adr/) | 架构决策记录 |
| [agents/](agents/) | 本地任务 / 标签 / 领域文档约定 |

## 现行专题（算法接口）

| 文档 | 用途 |
| --- | --- |
| [ocean-islands.md](ocean-islands.md) | 海洋岛屿与岛链调用 |
| [island-mountains-current.md](island-mountains-current.md) | 岛屿山系当前规则 |
| [island-mountains.md](island-mountains.md) | 大型岛 TD 山系 |
| [delta-engineering.md](delta-engineering.md) | 三角洲工程说明 |
| [remote-sensing-acceptance.md](remote-sensing-acceptance.md) | 遥感式验收图片规范 |
| [terrain-geography-dependency-matrix.md](terrain-geography-dependency-matrix.md) | 环境依赖矩阵 |
| [terrain-non-heightfield-landforms-inventory.md](terrain-non-heightfield-landforms-inventory.md) | 非高度场地貌目录 |
| [hybrid-river-network.md](hybrid-river-network.md) | 三维水系（若仍对接） |
| [source-publication.md](source-publication.md) | 源码交付与证据范围 |

## 交接与外部编排

| 文档 | 用途 |
| --- | --- |
| [handovers/](handovers/) | 织梦 / RPG DEM 等跨项目交接 |
| [../vantaloom.md](../vantaloom.md) | 工作区接手与目录索引 |
| [../.vantaloom/memory/](../.vantaloom/memory/) | 跨会话决策记忆（勿当规格全文） |

## 调研

| 文档 | 用途 |
| --- | --- |
| [../research/README.md](../research/README.md) | 调研入口 |
| [../research/](../research/) | 文献与方法筛选；`history/` 为旧镜像 |

## 任务与验收证据（按需）

| 位置 | 用途 |
| --- | --- |
| [../.scratch/](../.scratch/) | 本地任务：`spec.md` / `progress.md` / `review.md` |
| [../验收图片/](../验收图片/) | 战役图集与 README；总台账见 `验收图片/目录.md` |
| [../algorithm/README.md](../algorithm/README.md) · [../tests/README.md](../tests/README.md) | 算法目录与测试约定 |

活跃任务以 `TODO.md` 置顶与对应 `.scratch/<feature>/` 为准；结案任务的 Markdown 可留作证据，大体积 `npz`/`npy` 另议清理。

## 明确过时 / 只读

| 位置 | 说明 |
| --- | --- |
| [archive/](archive/README.md) | 已迁出的根目录评估、对话与旧实现状态 |
| [architecture/archive/module-docs-20261105/](architecture/archive/module-docs-20261105/README.md) | 模块台账快照；现行以 `module-catalog/` 为准 |
| [island-mountains-v1-historical.md](island-mountains-v1-historical.md) | 岛屿山系 v1 历史规则 |
| [../deprecated-plans/](../deprecated-plans/README.md) | 废弃的阶段 0–5 规划原文 |
| [../legacy-code/](../legacy-code/) | 重构前代码与 README，非现行实现 |
| `docs/` 下大量 `*-202610*.md` 里程碑报告 | 历史交付记录；读现行专题接口与 TODO，勿当未结任务 |

数据占用与可再生清理另见 [architecture/world-generation-system/data-cleanup.md](architecture/world-generation-system/data-cleanup.md)。
