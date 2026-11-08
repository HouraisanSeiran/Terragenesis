<!-- vantaloom-import: AGENTS.md -->
## 导入自 AGENTS.md（2026-10-18）

# Terragenesis 工程约定

先阅读 CONTRIBUTING.md。保留 TODO.md 作为工作总览；具体任务与规格放在下述本地任务目录。

## Agent skills

### Issue tracker

任务与规格采用本地 Markdown，保存在 .scratch/<feature>/。详见 docs/agents/issue-tracker.md。

### Triage labels

使用五个默认分类标签。详见 docs/agents/triage-labels.md。

### Domain docs

采用 single-context：根 CONTEXT.md 与 docs/adr/，按需创建。详见 docs/agents/domain.md。

<!-- vantaloom-import: agents.md -->
## 导入自 agents.md（2026-10-18）

# Terragenesis 工程约定

先阅读 CONTRIBUTING.md。保留 TODO.md 作为工作总览；具体任务与规格放在下述本地任务目录。

## Agent skills

### Issue tracker

任务与规格采用本地 Markdown，保存在 .scratch/<feature>/。详见 docs/agents/issue-tracker.md。

### Triage labels

使用五个默认分类标签。详见 docs/agents/triage-labels.md。

### Domain docs

采用 single-context：根 CONTEXT.md 与 docs/adr/，按需创建。详见 docs/agents/domain.md。

## 工作区项目总览与交接入口（2026-10-21）

先阅读 `CONTRIBUTING.md`，再核对以下计划、契约与证据。`TODO.md` 保留工作总览，具体规格与交接在 `.scratch/`。

### 当前开发计划

- 总路线与进度权威入口：`docs/terrain-diffusion-four-stage-roadmap.md`。
- 用户确认的四阶段详细组成表：`.scratch/terrain-four-stage-review-20261021/algorithm-components-review.md`，按 R1–R9、G1–G20、V1–V8 列出组成、局部实现、缺口和验收；文件状态为审阅稿，不能把所有候选自动升级为实施任务。第四阶段 Java/Mod 仍之后置门槛为准。
- 第一阶段：Python / Terrain Diffusion 无限世界河网。实施计划为 `.scratch/river-infinite-world/plan.md`，同目录保存域闭合、水量、泥沙、水沙耦合、消费者、接缝及床变反馈契约。阶段一尚未完成端到端认证；计划中旧待办与路线图最新增量有差异时，对照契约与保存证据，不重复执行已交付任务。
- 第二阶段：Python 地理环境、气候、材料与生态；依赖与表现验收矩阵为 `docs/terrain-geography-dependency-matrix.md`。
- 第三阶段：Python 非高度场三维地貌；形态与集成门槛为 `docs/terrain-non-heightfield-landforms-inventory.md`。离线原型不等于无限 TD 世界已集成。
- 第四阶段：算法成熟后 Java 转换 Python 产物、导入群系等内容并以 Minecraft Mod 交付；当前后置是用户确定的次序，不是算法缺陷。

### 工程交接目录

- `.scratch/river-infinite-world/`：现行第一阶段实施计划与契约族。
- `.scratch/infinite-world-geography/handoff-20261021.md`：自然环境专题交接、接口和验收边界；旧 P1–P6 属历史编号，不能换算为四阶段进度。
- `.scratch/deepseek-harness/`：DeepSeek 历史任务交接；`issues/` 为规格与验收，`tasks/` 保存请求、回复及返工，`agent_mcp_gateway/` 为本地网关。
- `.scratch/deepseek-review-20261021/report.md`：本次代码审查，含账户凭据选择、认证标志及残差报告一致性三个已复现问题；本次仅审查未修复，后续状态须以修复和回归证据更新。
- `.scratch/terrain-framework/handoff-next-agent.md`：早期河网架构与历史接续索引，不取代现行主线。
- `docs/claude-delta-handoff-20261016.md`：三角洲历史交接；最新自然形态验收入口为 `docs/delta-natural-acceptance-20261019.md`，不从旧风格化交付推断完整自然三角洲已完成。

### 接手纪律

当前用户指令优先；随后核对总路线、专题计划、契约与实际保存证据。规则可算、同坐标联合观察、消费者实际接线分别报告。保留旧失败和原始数据，不覆盖其他会话修改；本文只维护入口，具体进度在对应权威文档维护。

## 模块管理与实现说明

**接手任何模块前，先读 `docs/architecture/module-map.md`。** 它按目录列出全部 2139 个活跃模块的作用、公开符号、依赖、被引用数、版本族归属与**冻结证据 pin 次数**，并附 180 个多版本族的总览（数字于 2026-11-05 重新生成模块表后核对：未核对职责 558 个、被证据 pin 568 个；旧版模块表归档在 `docs/architecture/archive/module-docs-20261105/`）。三件事能避免绝大多数误伤：

1. **证据 pin > 0** → 该文件被 `verification/` 里的验收记录用 SHA256 点名。改一个字节（哪怕只改 import 或注释）都会让历史证据校验失败。不要动，除非用户明确批准并另立证据修订记录。
2. **被引用 = 0 且证据 pin = 0** → 可能是死代码，但仍须排除 CLI 调用、动态导入、字符串路径引用后才能归档。
3. **版本族 > 1** → 同目录存在多版本。**最新 ≠ 应删旧的**：实测 `hybrid_river_hydraulics` v8 依赖 v6、浅水 v9 依赖 `execution_v8` 与 `support_v6`、FV 依赖 `execution_v7`；`benchmark_height_budget` 与 `_v5` 名字像版本关系，实则函数集完全不相交、职责不同。

- `docs/architecture/module-catalog/README.md`：一方源码逐文件职责台账；完整记录在catalog.json，人工核定职责在annotations.json。源码docstring不是独立验收，缺说明项保持待核对；静态无调用方不能据此删除。
- `docs/architecture/implementation-guide.md`：四阶段的具体实现方法、输入输出、入口、验收与缺口，区分现有/候选/后续实现。
- 新增、删除、迁移模块或职责变更时，更新人工说明并运行 `runtime/venv/Scripts/python.exe -B tools/build_module_catalog.py --write`，随后 `--check` 核对覆盖与源码漂移。该检查不替代算法测试或产物认证，不修改历史归档和verification。
- 模块作用表由 `runtime/venv/Scripts/python.exe -B tools/build_module_map.py` 生成（`docs/architecture/module-map.md` 与人读、`module-map.json` 供检索）；模块增删或职责变化后重跑，保持表与实际一致。

### 版本收敛现状（2026-10-23 审计）

`.scratch/module-version-consolidation-20261022/duplicate-audit-20261023.md` 记录了全仓版本族与重复代码的实测结论：32 个版本族、136 处跨文件完全克隆。当前**没有可零风险直接删除的活跃模块**——每个旧版本至少被活跃 import、冻结证据 pin、旧 checkpoint 读取链、或不同物理语义之一绑定。已归档 2 个「活跃代码零引用且证据零引用」的工具（`legacy-code/zero-reference-tools-20261023/`）。改被 pin 文件等于改证据，须先获用户批准并另立修订记录。


## 算法模块重构进行中（2026-11-06）

算法模块合并重构（一功能一模块）已开始，正在执行中。**接手前先读交接文档**：

`.scratch/algorithm-refactor-20261105/merge/HANDOFF.md`

它包含：已完成/未完成状态、事故经过与四条硬纪律、已定决策（含用户拍板的 D1–D7）、执行顺序与开工方式、可复用成果、已知遗留问题、环境与命令。

同目录另有：`INCIDENT-20261106.md`（事故根因，必读）、`rules.md`（执行规则）、`arbitration.md`（待决项裁定）、`M1-A/` `M2-C/` `M3-D/` `M4-B-drainage/` `M5-B-channel/`（各批详细预案）。

范围：本轮只做 **M1–M5**，M6/M7 不做。当前 M0 已完成并验收。
