# SRHarness 与 MDB 本地接入

日期：2026-10-16。对应[任务12](../.scratch/deepseek-harness/issues/12-srharness-mdbench-bridge.md)。本次验证研究工具调用链，不替代上游供沙、陆侧高程协调和完整地形演化验收。

## 本地来源与环境

已核验两个下载目录，检查时工作树均无修改：

| 项目 | 本地路径 | Git 提交 |
| --- | --- | --- |
| SRHarness 1.0.5 | `D:/llm/qwen3/external-projects/SRHarness` | `40cf358d20732842d42be2b56c73881b5b8b64db` |
| MDB 0.8.0 | `D:/llm/qwen3/external-projects/mdbench` | `f133fd197f38135e748350670bf18b4acfb4491a` |

本机已有 uv 管理的 CPython 3.12.14。独立依赖环境放在本工程 scratch；不复用或修改 qwen3 训练环境。Docker Linux 后台当前不可连接，WSL 仅列出 docker-desktop。

SRHarness 官方安装说明允许非 Linux 系统使用不涉及任意代码执行的功能。此次仅使用内置 DefaultEvaluator 与 `statistics_analysis`、`evaluate_formula`、`submit_formula`，运行真实 SRAgent 搜索循环。生成 Python 代码执行、自定义 Tool/Evaluator 仍需 Linux Landlock ABI≥3 和 seccomp，本次不启用、不绕过。

实际安装后发现该快照的 Windows 导入缺陷：`runtime/landlock.py`、`runtime/workspace.py` 和 `utils/openat2.py` 在模块顶层无条件调用 `ctypes.CDLL(None)`，尚未调用沙箱就抛出 TypeError；`openat2` 默认参数还引用 Windows 不存在的常量。已修复本工程 vendor 副本的平台加载判断；非 Linux 调用对应功能明确失败。原下载目录保持不变，兼容补丁与验证记录随任务保留。

## 调用关系

1. MDB 从随附 Terminal Settling 任务生成公开 problem/train 和私有 answer/ID/OOD。
2. SRHarness 仅接收公开变量、任务说明与训练数据，通过当前 DeepSeek 兼容服务搜索并评估候选表达式。
3. 固定最终候选及对话状态；官方 MDB 评分器独立读取私有数据。
4. 每个机制探针从固定状态的独立副本出发，按 MDB 标准提示回答；不提供工具、不把评分反馈送回搜索。

搜索预算为一条分支、一次启动、每轮一个样本，最多四轮。数值运行限制为两核、BelowNormal、数值库单线程。SRHarness 内置 DeepSeek 单价不能代表当前 DashScope 账单，记录 token 数，实际费用标记未知。

## 与三角洲工作的关系

本次内置沉降任务是已知公式生成的合成题，成功只说明工具可以搜索、提交和评估该局部关系。它不能证明真实沉降机制或当前三角洲已完成。后续可把上游侵蚀、河段留存和河口交付作为独立研究任务；先明确数据、单位与适用范围，再比较候选关系。完整流程仍由工程计算承担河网输送、有限材料库存、守恒与床变。

## 实测结果

**已跑通实际调用链。** 模型为当前配置的 `deepseek-v4.1-flash`，执行真实 SRAgent 三轮搜索，然后单独调用一次机制探针；没有用预填答案代替模型搜索。原始下载仓库在运行后仍无修改。

搜索得到并冻结的公式为：

```text
speed = 2 / 9 * (particle_density - fluid_density) * 9.81 * radius ** 2 / viscosity
```

MDB 的独立净受力探针回答为：

```text
net_force = (particle_density - fluid_density) * 4 / 3 * 3.141592653589793 * radius ** 3 * 9.81
```

| 评分项 | 训练集（128） | 同范围测试（64） | 范围外测试（64） |
| --- | --- | --- | --- |
| 沉降速度：数值等价 / 符号等价 | 均通过 | 均通过 | 均通过 |
| 净受力探针：数值等价 / 符号等价 | 均通过 | 均通过 | 均通过 |
| 沉降速度 NRMSE | 2.84e-16 | 2.00e-16 | 2.39e-16 |

这些误差处于浮点舍入量级，说明恢复了此合成题的既定关系。模型可能已知经典沉降定律，因此不能据此声称发现了新物理机制或证明复杂侵蚀任务也能成功。

五项聚焦测试通过，覆盖实际导出/读取、非法数据与私有字段拒绝，以及 Windows 导入和沙箱拒绝。冻结文件校验在评分前后通过。实验四次模型请求共 62,114 tokens，其中探针携带完整冻结搜索状态，占 45,677 tokens；代码编写与修复另计 41,815 tokens。实际服务账单未知，后续扩大批量前应注意探针上下文开销。

- [官方评分结果](../.scratch/deepseek-harness/tasks/srharness-mdbench-bridge-20261016-01/run01/evaluation/metrics.json)
- [冻结公式、候选与搜索状态](../.scratch/deepseek-harness/tasks/srharness-mdbench-bridge-20261016-01/run01/discovery/checkpoint.json)
- [搜索对话及工具结果](../.scratch/deepseek-harness/tasks/srharness-mdbench-bridge-20261016-01/run01/discovery/nodes.jsonl)
- [桥接入口](../tools/run_srharness_mdbench_bridge.py)
- [复跑与环境说明](../.scratch/deepseek-harness/tasks/srharness-mdbench-bridge-20261016-01/README.md)

本次可用范围是 Windows 上的内置表达式搜索与 MDB 代数机制评分。没有启用 SRHarness 生成代码执行、自定义 Evaluator 或完整 Linux 工作区功能；没有把候选自动写入三角洲模拟。
