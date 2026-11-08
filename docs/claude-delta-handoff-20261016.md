# 三角洲交接给 Claude

**2026-10-17 状态已更新：** 用户恢复实施后，v10风格化陆侧三角洲已修复、验收并集成主工程，场景09及验证见[最终报告](delta-landward-v10-20261017.md)。大场景构造与已验收供沙02分账，未发布默认世界。下文是2026-10-16交给Claude时的历史快照，“06尚未生成”和停止指令不代表当前状态；恢复前失败证据见[历史验收](delta-acceptance-handoff-20261017.md)。

2026-10-16。用户要求“保存目前进度，我让claude来做”。编程子智能体已中断；已检查没有本任务的 Python 计算或测试进程。没有提交、推送或改动游戏/JAR。当前代码已在磁盘，包含尚未验证的第06版形态修改。

## 先读这些

- 根 `CONTRIBUTING.md`，以及 `docs/agents/issue-tracker.md`。
- 本文为最新交接入口。`TODO.md` 和其他历史文档中的“尚未实现供沙”等旧描述以本文及进度文档顶部为准。
- 工作区原本存在大量修改和未跟踪文件，含其他人在做的前端。不要回滚或提交整个工作区。
- 用户允许夸张三角洲/湿地，但要求基于已有河流、水量和上游材料计算泥沙。风格化挖填必须与自然输沙分账。
- 袭夺、跨水文域交换、河谷悬挑、地下暗河和地貌生成改进属于第二阶段，本轮不扩写。

## 用户最新的形态要求

用户指出04版太规整，要求大体以河流方向为中心的锥面/扇面。05版仍不满意，进一步明确：

> 锥面顶点、三角形收窄的一侧应在陆地，外部圆形一侧大概在海洋；外部不一定非要保持原有扇形。

应理解为沿河入海的沉积地形：陆侧扇顶接来河，向海展开，陆侧融入原地形，可见海岸不需要是固定扇形模板。不能仅将轮廓做成规则扇形、加少量噪声后就宣称形态通过。主协调此前对05版的初步形态认可已被用户后续反馈推翻。

## 已经可靠完成的供沙链

结果目录：`verification/fluvial-delta/same-source-feedback-landward-20261016-02/`。

- 84节点，8,224.263438616812m，365个物理日；控制体长度和与实际河长一致。
- 每日延续松散层、移动泥沙及剩余岩床；按节点到receiver真实距离重算坡度、Manning正常水深、剪应力及输沙能力，不重置全年库存。
- 陆侧交接在原海口上游98.930994m，截止上游计算后交给河口，避免重复计算交接点以下侵蚀。
- 年交付67,932.41600297875m³固体；河口净库存67,839.1045070913m³，外排93.31149588742817m³。
- 原陆地净留存146.05438417027798m³，覆盖4,500m²。这个小案例不代表公里级平原形成。
- 联合固体残差−6.98×10⁻¹²m³；同Q零供沙对照地形严格不变；五份输入hash前后相同。
- 上游与河口保存冷读、逐月库存和账本重放通过。主协调实际跑过59项测试、14个子测试，全部通过。

关键实现：

- `terrain_pipeline/surface_rivers/metric_upstream_sediment.py`
- `terrain_pipeline/surface_rivers/metric_dynamic_feedback.py`
- `terrain_pipeline/surface_rivers/metric_fluvial_delta.py`
- `tools/run_feedback_landward_case.py`
- `tests/test_dynamic_feedback.py`、`tests/test_metric_upstream_sediment.py`

边界：正常流准稳态，不是瞬态/完整回水双向耦合；硬度、5cm松散层和1m可蚀岩是显式程序情景。来水来自所选2500km²集水区，供沙材料只覆盖建模主干。前两个月后有限材料耗尽，不代表真实多年供沙预测。细床/30m地形交接高差1.21614m明确保留；未认证跨分辨率水力连续。原冻结参考为 `verification/upstream-sediment/same-source-20261016-04/`，保持原档。

## 16km 场景的实际版本

目录统一在 `.scratch/hydrological-planning-domain/stylized-mouth-16km-20261016-NN/`，20m、800×800。全部保留。

| 版本 | 状态 |
| --- | --- |
| 01 | 早期规则平台，未接受 |
| 02 | 已有海侧岛湾原型；未包含所要求的完整陆侧平原 |
| 03 | 陆侧低平原和三支实际水道已生成；上游槽肩约132m异常深水，未接受 |
| 04 | 补岸坡支撑，异常深水修正；陆侧等宽廊道+海侧椭圆太规整，用户要求改形 |
| 05 | 统一径向浅锥扇面；代码数值、保存重放通过，但用户仍不接受固定扇形边界，不能称为最终交付 |
| 06 | **尚未生成**。相关代码正在修改时被用户要求停止，未完成验证 |

05实际：扇顶 `[374612.595, -1425387.405]` 左右，原地形约23.602m，距原海域约1,753m；扇顶800m带为100%原陆地，4800–6000m前缘带约98.352%原海域。因此方位正确，问题主要是模板边界/衔接太明显。

05形态参数：实际保存河道切线为轴，扇顶约旧口上游1800m；名义半径5800m、张角80°，三支向不同前缘发散。原陆地旧主槽外改形2.3508km²，湿0.2160km²、干2.1348km²。全景挖方21,216,120.517m³、填方1,169,033,516.669m³；其中上游岸坡支撑毛填方约776,687,081.448m³。**这是构造材料，不能算上游输沙。** 保存的旧上游纵剖高于场景base，保留纵剖所需的大型支撑山脊仍显得人工；该限制未解决。

05上游保留河床核心，u≈−4500..−2200m显式高程过渡，三支从−1800m开始。主槽保留/过渡/平原入口最大水深分别3.0/2.999934/1.674667m。水面为局部设计值，非求解水动力。

05归档SHA256：`e7d20e9b83fb34e4e2ba610d8ccb2a788bb86b03069e678603fc3c0ffd2a87a6`。

先看05的 `mouth-detail.png`、`overview-16km.png`、`construction-change-original-land.png` 和 `cold-audit.json`，理解用户不满意的位置，不要用测试通过代替图形验收。

## 停止时的代码状态

本轮形态写集：

- `terrain_pipeline/surface_rivers/metric_stylized_wetland.py`：原v2默认路径保留，`landward_plain=True`走新路径；`_river_fan_fields`为浅锥扇面生成。
- `tools/prepare_stylized_river_mouth.py`：输入、保存、图集和 `--audit` 冷读重放。
- `tests/test_metric_stylized_wetland.py`：保留基线检查，新增陆侧连通/材料账、扇宽递增和旋转方向检查。

这些文件已包含第06版**未验证**修改：实际交接点为扇顶；约1200m横向过渡替代窄角度切边；非对称半径变化约12%+6%；海侧增加渐深坡脚；新增实际原海岸/新零高程线/扇顶轴向及径向剖面诊断。请先审查现存代码和测试再运行，不能假设它与05归档仍逐数组一致。05冷重放检查依赖当前生成器，新算法变更后应对新版单独保存，旧归档不覆盖。

第06版尚无实际生成、图审或测试通过证据。停止时未发现仍在运行的计算进程。需要接续时另存新目录，保留05。

## 验证入口

Python环境：`.scratch/hydrological-planning-domain/pydeltarcm-venv/Scripts/python.exe`，已在此隔离环境安装pytest；系统Python没有pytest。

```powershell
# 新代码先做相关行为检查，不要先跑全工程。
.scratch/hydrological-planning-domain/pydeltarcm-venv/Scripts/python.exe -m pytest -q tests/test_metric_stylized_wetland.py

# 这是接续用入口，当前06尚未执行。
.scratch/hydrological-planning-domain/pydeltarcm-venv/Scripts/python.exe tools/prepare_stylized_river_mouth.py --landward-plain --output .scratch/hydrological-planning-domain/stylized-mouth-16km-20261016-06
.scratch/hydrological-planning-domain/pydeltarcm-venv/Scripts/python.exe tools/prepare_stylized_river_mouth.py --audit --output .scratch/hydrological-planning-domain/stylized-mouth-16km-20261016-06
```

运行约束：一个数值进程，2核、BelowNormal、数值线程1；入口已有resource_limits。检查实际水深、三支D4连通、上游核心、修改范围外保持、材料账及原始来源hash，然后看实际保存图。不要再次接受模板轮廓明显的结果并直接称为“完成”。

## 湖泊与泥沙复用问题的答案

已完成文档：`docs/lake-sediment-reuse-and-topology-review-20261016.md`。

湖泊可以作为入湖河段终点及出湖河段起点。`metric_boundary_coupling.solve_coupled`已有河→湖→河的简化水量连接。`metric_lake_channel_coupling`支持有符号端口反流，但端口限制在开放河段末端；负流注入末端并不代表已解决干流侧接后的下游传播。完整鄱阳湖式顶托、倒灌、干流侧接及湖内泥沙未全部接通。

泥沙框架可复用于入湖口、汇流、山口冲积扇、宽谷洪泛平原、沙洲/辫状河、出湖河道和闭合盆地；每处需要对应的水位、连通或分流边界。袭夺保留第二阶段。

## 本地任务和记录

- `.scratch/delta-completion/issues/01-sequential-feedback-landward.md`：供沙反馈已验收，形态尚未完成。
- `.scratch/deepseek-harness/issues/10-landward-delta-plain.md`：大范围陆侧平原与用户最新形状修正；目录名是历史，不代表继续使用DeepSeek。
- `docs/delta-progress-handoff-20261016.md`：历史与顶部最新进度。
- `docs/dynamic-feedback-and-landward-plain-v1.md`：公式和准确能力边界。

用户现在交由Claude接续。本代理停止代码实施，不自动向其他聊天发送任务。
