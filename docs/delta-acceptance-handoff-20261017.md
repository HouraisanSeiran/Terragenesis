# 三角洲验收与进度保存（2026-10-17）

**后续完成：** 风格化陆侧三角洲v10已修复并集成主工程，场景09通过6项聚焦测试、37份来源校验、精确重放与本轮图审，见[最终报告](delta-landward-v10-20261017.md)及[已完成任务](../.scratch/delta-completion/issues/02-complete-stylized-landward-delta.md)。有限供沙反馈与大场景显式构造分账，未发布默认世界。下文为恢复实施前冻结的失败验收记录，“只保存、不自动实施”已被用户随后恢复要求替代；旧证据继续保留。

## 恢复实施前结论

用户要求验收 Claude 的三角洲实现，随后要求保存目前进度。本轮完成只读审查、聚焦测试、保存场景冷审计和图审，没有修复、合并或发布算法。**整体三角洲未通过验收，任务保持未完成。**

- 06场景已经生成并保存在 Claude 工作树中，是 v6 静态设计候选；形态未通过。
- 当前 Claude 代码已标为 v7，但存在运行错误，没有相应新版场景与成功重放证据。
- 此前已验收的有限上游供沙/逐日反馈案例继续保留；本轮没有修改或重新验收该链。
- 本文覆盖 2026-10-16 交接中“06尚未生成”的旧状态。旧描述只适用于主目录当时的状态。

## 已确认的实际位置

主工程：`D:/codexwork/山川形意Terragenesis/`。

Claude 工作树：`D:/codexwork/山川形意Terragenesis/.claude/worktrees/delta-algorithm-dev-c6fa7b/`，分支 `claude/delta-algorithm-dev-c6fa7b`，验收时 HEAD 为 `fc794da2967b92d1d9b5fa519a85099d9ffbf9b3`。三个实现文件在该工作树中为未跟踪文件，不能仅用已提交差异判断交付内容。

用户最终确认的产物目录：

`D:/codexwork/山川形意Terragenesis/.claude/worktrees/delta-algorithm-dev-c6fa7b/.scratch/hydrological-planning-domain/stylized-mouth-16km-20261016-06/`

此前用户提到的 `D:/Claudework/` 在当前执行环境不存在，随后已纠正为上述目录，不再等待路径确认。不要将主目录中的同名模块与 Claude 工作树实现混用。

## 冻结的验收对象身份

下列 SHA256 在本轮读取确认；它们标记实际检查对象，不代表已建立新的备份或提交。

| 对象 | SHA256 |
| --- | --- |
| 工作树 `terrain_pipeline/surface_rivers/metric_stylized_wetland.py` | `10b6ea3d94534ee68d0defbe877a98c5022a50461e43898187d43eaa16ff7813` |
| 工作树 `tests/test_metric_stylized_wetland.py` | `a8368f6cca3ba8e819bc67cd8e0a34fa3875126c15e8a7cdf62f58d112e628d2` |
| 工作树 `tools/prepare_stylized_river_mouth.py` | `5630387168170357d52dc9b644b7dc6aa32a909f8035fbb32d991aba29e976fd` |
| 06 `scene.npz`，与 `summary.json` 声明一致 | `55538fe72bc45481f75566d28c8338de85041e6e56af8a3a32e1c5c361940120` |

## 实际验证与阻断项

运行环境为主工程 `.scratch/hydrological-planning-domain/pydeltarcm-venv/Scripts/python.exe`。一个数值进程，最多2核、BelowNormal，数值线程1；未启动 GPU、游戏或构建 JAR。

隔离工作树直接收集测试时缺少 `metric_discharge_geometry`。按场景工具已提供的 `TERRAGENESIS_SOURCE_ROOT` 机制，把主工程作为只读依赖来源，并先导入 `tools.prepare_stylized_river_mouth` 扩展包搜索路径后运行测试。已打印确认被测 `metric_stylized_wetland.py` 来自 Claude 工作树。

聚焦测试 `tests/test_metric_stylized_wetland.py`：**3项通过，2项失败**。

1. **P1：输出变量赋值错放作用域。** 旧入口第471行 `branch_widths = np.asarray(widths)` 报 `NameError: name 'widths' is not defined`，破坏旧版回归。第471至479行还使用旧入口未定义的 `shares`、`paths`、`branch_cuts` 等变量；相反，新版第813至814行使用的 `branch_shares`、`branch_widths`、`branch_paths`，以及第829行使用的 `branch_radii`、`branch_angles` 未在该函数中定义。新版后续输出错误由静态审查发现，实际执行先被下一项阻断。
2. **P1：新版上游到海洋不连通。** 陆侧平原测试在第730行调用 `connected_design_water` 时抛出 `ValueError: source_cell does not reach the sea`；用06保存输入重放当前生成器也在同处失败。新增主干第一个中心点相对扇顶约有76m横向偏移，主干掩膜在第725至728行被排除出最终 channel 掩膜，均需定位检查；本轮没有证明它们是全部断点或唯一原因。
3. **P2：产物版本与现行生成器不匹配。** 06保存身份为 `stylized-river-mouth-landward-plain-coastal-cone-v6`，当前源代码为 v7。旧 `cold-audit.json` 不能作为当前 v7 的成功重放证明。

冷审计直接调用 `audit_saved_scene`，没有覆盖旧 `cold-audit.json`。归档哈希、水深/水面、保存的三支D4核心、挖填账本、原陆地面积、上游核心与来源检查执行到生成器重放前未报错；随后在 `tools/prepare_stylized_river_mouth.py` 第452行调用当前生成器时因不连海失败。**不能把旧场景自身检查通过表述为当前实现重放通过。**

## 06场景实际形态与材料

尺寸16km × 16km，20m栅格，800 × 800。查看了保存的 `mouth-detail.png` 与 `actual-coast-and-radial-section.png`。

- 扇顶在原陆地，原床高程23.602109m，距原海域1753.282636m；扇顶800m带为100%原陆地，前缘诊断带约90.8847%为原海域，陆海方位符合用户要求。
- 原陆地旧主槽外改形4.1868km²，其中湿0.1992km²、干3.9876km²，确实包含陆侧改形。
- 仍有明显三叉放射布局、较直水道、三角形海湾及直线衔接，形态不接受。工作树任务 `.scratch/hydrological-planning-domain/issues/01-v6-delta-realism.md` 第12行也把06记录为形态失败样本；这是一份任务记录，不能代替实际图审。
- 挖方158,136,976.539566m³，填方1,481,832,995.071069m³，账本残差约−2.38419×10⁻⁷m³；上游岸坡支撑毛填方776,687,081.447953m³。
- 这些是显式构造挖填，不是由实际上游供沙生成的沉积体。`hydraulic_ready=false`、`publishable=false`，不接默认世界。

## 已接受的供沙案例保持独立

`verification/fluvial-delta/same-source-feedback-landward-20261016-02/`：84节点、8224.263439m、365日；交付67,932.416003m³固体，原陆地净沉积146.054384m³/4500m²，联合固体残差约−6.98×10⁻¹²m³。此前59项测试、14个子测试通过是该链的历史证据，不是本轮 v7 的测试结果。

它只延入陆侧约99m，仍不能证明公里级平原由自然供沙形成。保持准稳态、有限主干材料库存及未解完整回水等已声明边界。

## 下次接续顺序

1. 从 Claude 工作树读取当前文件与任务记录，先确认文件身份有无更新。
2. 修复各入口变量作用域，恢复旧入口回归。
3. 定位并修复来河、主干、分汊到海洋的实际湿格连续性；保留陆侧分汊验收，不能仅把断面移到海侧来绕过陆侧要求。
4. 聚焦测试通过后，另存新编号场景。保留05、06及其原审计，不用新生成器覆盖旧归档。
5. 对新版完成冷重放、来源、上游核心、修改范围外保持、材料账和实际图审。解决三角形/直线衔接后再决定形态是否通过。

本次用户只要求保存进度，不构成自动修复、派发、长跑或发布指令。袭夺、跨域交换、暗河及其他地貌工作仍保留第二阶段。
