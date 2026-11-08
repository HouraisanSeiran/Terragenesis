# Mechanism Discovery Benchmark 身份与适用范围

核查日期：2026-10-16。仅阅读一手资料，未安装、运行 benchmark、调用 DeepSeek 或修改算法。

## 确切身份

用户所指项目可确认为 [yuzhTHU/mdbench](https://github.com/yuzhTHU/mdbench)，官方 README 标题为 **Mechanism Discovery Benchmark**，与 [SRHarness](https://github.com/yuzhTHU/SRHarness) 位于同一个作者账号。用户随后确认其为所指配套项目。它不是 SRHarness README 中报告结果的 LLM-SRBench，不能混用两者名称、数据或成绩。[README](https://github.com/yuzhTHU/mdbench/blob/main/README.md)；[SRHarness README](https://github.com/yuzhTHU/SRHarness/blob/master/README.md)。

本次 mdbench 主分支快照为 `f133fd197f38135e748350670bf18b4acfb4491a`。下述实现判断对应该快照，不是对后续版本的保证。[仓库树 API](https://api.github.com/repos/yuzhTHU/mdbench/git/trees/main?recursive=1)。

## 它评什么

mdbench 区分两种能力：恢复可观测输入输出规律，以及恢复能够生成该规律的隐藏机制。任务以 YAML 声明观测/隐藏变量、代数机制、最终可观测规律、采样范围、单位与机制探针；程序验证可解性、符号关系、量纲和探针一致性，然后生成 train、ID、OOD 数据。可观测方程与探针答案采用符号等价和数值精度评分，无需 LLM 裁判。[README](https://github.com/yuzhTHU/mdbench/blob/main/README.md)；[方法设计 proposal](https://github.com/yuzhTHU/mdbench/blob/main/proposal.md)。

机制探针询问推导过程中具有科学意义、但不在最终输入输出公式中的内部量。例如其 Terminal Settling 原始任务从颗粒半径、颗粒/流体密度及黏度预测终端沉降速度，内部方程包括体积、净向下力和线性阻力；探针单独检查 `net_force`。这比只拟合沉降速度增加了内部关系检查，但任务本身仍是声明了假设的合成代数问题。[实际任务 YAML](https://github.com/yuzhTHU/mdbench/blob/main/tasks/physics/Terminal%20Settling/Terminal%20Settling%20-%20Original.yaml)。

README 所述流程会冻结发现阶段的最终状态，每个探针从其独立副本开始，避免前一个探针反馈影响后一个。proposal 较早的讨论则提示探针阶段“不修改机制”的约束可能只是提示约束；因此对具体算法应以适配器实际隔离行为为准，不能仅凭概念宣称强制不可修改。[README](https://github.com/yuzhTHU/mdbench/blob/main/README.md)；[proposal](https://github.com/yuzhTHU/mdbench/blob/main/proposal.md)。

## 代码、数据与现成集成

- 仓库公开，MIT 许可；`pyproject.toml` 版本为 0.8.0，开发状态标记 Alpha，要求 Python >= 3.12，主要依赖 NumPy、PyYAML、requests、SymPy，可选 FLINT 加速。[项目定义](https://github.com/yuzhTHU/mdbench/blob/main/pyproject.toml)；[LICENSE](https://github.com/yuzhTHU/mdbench/blob/main/LICENSE)。
- 数据通过随附 YAML 任务和固定 seed 导出，不必先取得现实观测数据集。公开 `problem/` 与私有 `answer/` 分离，评测智能体只应获得前者。当前库目录包括 biology、chemistry、material、physics；物理任务包含 Terminal Settling、Venturi Flow 等。README 快速示例仍引用 astronomy 路径，而本次树中没有 astronomy 目录，不能照抄该示例作为已验证入口。[README](https://github.com/yuzhTHU/mdbench/blob/main/README.md)；[任务库](https://github.com/yuzhTHU/mdbench/tree/main/tasks)。
- 当前算法注册器动态枚举 `src/algorithms/*.py`，目录中为 `claudecode`、`codex`、`direct_ask_codex`、`direct_ask_gold_m_codex`、`dsh`、`dummy`、`my_pysr`、`pysr_and_llm_direct`。没有 `srharness` 或 `sr_harness` 适配器。因此可将二者组成研究流程，但本次核查不能称为已有一键 SRHarness 集成；需要实现与检查 `run`、`get_ask` 等算法协议及状态/探针隔离。[注册器](https://github.com/yuzhTHU/mdbench/blob/main/src/algorithms/__init__.py)；[适配器目录](https://github.com/yuzhTHU/mdbench/tree/main/src/algorithms)。
- `dsh.py` 明确是 **DeepSeek Harness** 基线，通过 `dsh` CLI 的隔离 profile 运行，不是 SRHarness 的别名。其提示也明确要求代数方程、不使用微分方程。[DSH 适配器](https://github.com/yuzhTHU/mdbench/blob/main/src/algorithms/dsh.py)。
- 本次确认到的方法文档是仓库 `proposal.md`。README 未给出独立 MDB 论文引用；不把 SRHarness 的 arXiv 论文当作 MDB 已发表论文或实证成绩。

## 对本项目的用途与边界

可用作局部机制研究的评测骨架，例如把“流量/坡度/材料参数到侵蚀率”“粒径/密度/黏度到沉速”“供沙、出沙与储量变化的质量平衡”写成可解的简化任务，再分别检查输出和剪切力、可蚀性、运输能力、各材料库等内部量。这里是应用建议，不是已有河流侵蚀/三角洲数据集或已验证算法。

不能直接把整个二维侵蚀、输沙、河口沉积求解器放进当前代数任务协议后，就宣称获得机制发现验证。proposal 明确警告依赖复杂 ODE/PDE 求解、复杂方程反解等推导当前框架尚不支持或支持不完善；探针必须能仅由给定变量与常数唯一表示为框架可处理的显式代数式。[proposal 的任务变体与探针原则](https://github.com/yuzhTHU/mdbench/blob/main/proposal.md)。

尤其不能把 probe 通过解释为现实因果机制已获证明。proposal 专门讨论 **non-identifiability**：不同内部机制可能生成同样观测规律；一个自洽、合理且不明显更复杂的竞争机制即使未通过标准探针，也不应直接被判为没有发现机制。作者建议审查并剔除或重建此类任务。因而现实岩石硬度、流量与产沙研究仍需要独立观测、受控实验或可信物理基准、域外检验及质量守恒核验；该 benchmark 只能对已声明任务和探针给出恢复表现。[proposal 的 non-identifiable 章节](https://github.com/yuzhTHU/mdbench/blob/main/proposal.md)。

结论：MDB 身份、源码和生成式任务库均已确认；适合辅助评测简化机制恢复，和 SRHarness 的公式搜索能力有互补性。现成 SRHarness 适配、真实供沙数据、完整时空动力学验证均未在本次资料中得到确认，尚未进行安装或实验。
