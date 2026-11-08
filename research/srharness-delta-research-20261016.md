# SRHarness 与三角洲算法研究的适用性

日期：2026-10-16。范围：回答能否用于算法研究；未安装工具、未提交模型任务、未更改模拟代码。用户确认所指Mechanism Discovery Benchmark是SRHarness配套项目，已定位同作者的[yuzhTHU/mdbench](https://github.com/yuzhTHU/mdbench)。

## 当前算法的性质

当前工程中有两类实现，不能把“包含数学公式”等同于“已经具有物理预测能力”。

- `terrain_pipeline/surface_rivers/metric_fluvial_morphodynamics.py` 是固定 pyDeltaRCM 2.3.0 的适配，使用近似稳态水场与泥沙/床面更新逐步演化。它是基于模型规则的数值模拟，现实预测能力仍需数据和独立验证；既有案例的形态验收尚未通过。
- `terrain_pipeline/surface_rivers/metric_stylized_wetland.py` 的当前v2是多尺度噪声、叶瓣足迹、指定分汊路径和设计水位组成的程序化地形构造。16km scene02的实际地形和连通检查通过，不代表给定岩性/来水会自然形成该形态，也不提供上游真实供沙。
- [任务11](../.scratch/deepseek-harness/issues/11-upstream-sediment-supply.md)拟接入上游侵蚀、输沙、沿程留存及河口实际交付。这类局部关系是符号回归的合理研究对象；当前尚未实现这条同源链。

以上判断来自当前仓库代码及[进度快照](../docs/delta-progress-handoff-20261016.md)。

## SRHarness 官方能力

已确认项目为[yuzhTHU/SRHarness](https://github.com/yuzhTHU/SRHarness)，名称为“A Harness for Agentic Symbolic Regression”。官方README说明它提供语言模型驱动的符号回归流程，支持数据准备、分析、拟合、候选公式评估与持久化搜索记录，以及普通表达式和图/超图表达式。[官方README](https://github.com/yuzhTHU/SRHarness/blob/master/README.md)

官方Evaluator文档区分表达式计算和任务评估；用户可配置训练/验证划分、拟合、指标、候选评估和复杂度。内置工具包括OOD/时间划分、ODE积分与轨迹误差，GraphEvaluator处理带关系表的图数据。这提供接入自定义水沙评估的扩展点，但守恒、量纲、材料库存和领域有效性规则仍需我们定义，不能假定工具自动提供。[官方Evaluator说明](https://github.com/yuzhTHU/SRHarness/blob/master/docs/evaluator.en.md)

安装要求Python>=3.12。完整代码执行和自定义Evaluator依赖Linux Landlock ABI>=3及seccomp；官方说明不具备该沙箱的系统会在相应入口报错。当前工程运行在Windows，完整研究流程宜在满足要求的Linux/WSL2环境中部署，并先核查实际内核支持；不能仅凭有WSL/Docker就假定可用。模型服务支持列表包含DeepSeek，但现有DashScope路由的具体接法尚未验证。[官方安装说明](https://github.com/yuzhTHU/SRHarness/blob/master/docs/install.md)

本次通过GitHub API读取官方源文档；raw.githubusercontent.com直接访问失败后改用contents API。未独立复现README中的benchmark准确率，也不将这些准确率外推为三角洲研究成功率。

## 推荐的研究切口

先研究小范围、可检验的物理关系，再把通过的候选嵌入完整流程：

| 研究对象 | 候选输入 | 可比较的输出 |
| --- | --- | --- |
| 岩石/松散层侵蚀 | 岩性或硬度、阈值、局部剪切或流量/宽深/坡度、可蚀库存 | 侵蚀率与时间窗固体产沙量 |
| 河段搬运与滞留 | 入流水沙、流速/水深、粒级、坡度、河段尺度 | 出口固体通量、沉积/再侵蚀量 |
| 河口留存 | 实际交付Qs和Q、近岸水深、粒级、计算时长及声明边界 | 留存比例、沉积体积、出露或仅水下增长 |

不建议第一步直接搜索“所有输入→整张三角洲高度图”的单一公式。河网输送、空间边界和材料守恒仍由数值流程承担，符号回归优先比较某个局部经验关系或建立有明确适用范围的快速近似。这是本项目建议，不是官方现成的水文功能。

## 数据与验证

1. 先解决现有河床和场景base的高程不一致，冻结一致的几何、单位和来源。错误几何产生的数据可能使搜索学到实现缺陷。
2. 构建成组对照：同水力条件改变可蚀性；同材料改变来水/坡度；同入流水沙改变湖口/海口水深。每组保存完整时间窗和材料账，尽量区分不同机制的影响。
3. 数据来源决定结论：已有公式生成的合成数据适合验证公式恢复；可信模拟器数据适合做模型内规律分析或代理模型；独立实验/观测数据才有助于检验对真实过程的适用性。当前程序化岛湾形状不能作为沉积机制真值。
4. 保留水与固体守恒、非负库存和固体/含孔隙体积换算作为明确约束。对候选关系检查量纲、边界情况和长期积分稳定性，不只比较点误差。
5. 按完整河段/情景/运行划分搜索与验证数据，并另留不参与公式搜索的最终测试集；不能将同一次模拟的相邻时间步随机拆分后就声称跨河流泛化。
6. 比较当前公式与新候选的误差、公式复杂度、计算耗时、范围外表现、完整轨迹和最终床面。模拟器上更准确或更快的关系不自动构成新自然定律。

入湖口和汇流可复用这种研究流程；河流袭夺另外需要拓扑和分水岭变化机制，不能由一个沉积公式自动解决。

## Mechanism Discovery Benchmark 的作用和边界

MDB官方README描述两项评估：可观测输入输出关系在train/ID/OOD数据上的表现，以及隐藏机制在独立机制探针上的表现。任务用YAML定义观测量、内部变量、代数机制、单位、采样范围和探针；公开problem与私有answer严格分开。评分采用符号等价和数值准确性，不依赖LLM裁判。[官方README](https://github.com/yuzhTHU/mdbench/blob/main/README.md)；入口以[仓库默认分支](https://github.com/yuzhTHU/mdbench)为准。

其方法论明确指出，可观测规律拟合得好不等于恢复了内部机制；同一观测规律可能由不同机制产生，出现这种不可辨识性时不能简单把不同于预设答案的机制判为错误。水沙研究若只有河口一个最终沉积量，往往不足以区分上游少产沙、沿途多滞留和河口多输出，需要额外观测或对照。[官方proposal](https://github.com/yuzhTHU/mdbench/blob/main/proposal.md)

官方proposal还明确限制：复杂ODE/PDE求解推导当前不支持，机制探针需能够表示成受支持的显式代数表达式。因此先用受控、可求解的局部水沙机制构造测试，评估工具能否恢复侵蚀、滞留和出口交付的关系；完整二维地形演化的检验仍在我们的数值流程中进行。MDB不是现成的三角洲数据集、全场求解器或真实因果证明。

建议组合方式：SRHarness搜索可解释的局部公式；MDB测试已知机制的恢复、范围外表现和内部量预测；工程数值算例验证守恒、有限库存及长期床变；再以独立实验/观测资料验证现实适用性。

唯一背景研究员核查MDB当前源码后，确认没有直接的SRHarness适配器，`dsh`指DeepSeek Harness。实际组合需要适配运行与机制探针接口，本次未安装或验证接入。确切快照、源码引用、任务示例及范围限制见[MDB专项记录](mechanism-discovery-benchmark-20261016.md)。
