# 陆侧三角洲 v10 实现与验收（2026-10-17）

本轮完成风格化陆侧三角洲任务，并将审查后的三个实现文件集成到主工程。最终场景为09，算法版本为v10；两者编号不同。已有上游供沙/逐日反馈有限案例继续有效。大场景采用显式地形构造，构造挖填与实际输沙分别记账。

## 成果入口

- [16km场景总图](../.scratch/hydrological-planning-domain/stylized-mouth-16km-20261017-09/overview-16km.png)
- [河口细节](../.scratch/hydrological-planning-domain/stylized-mouth-16km-20261017-09/mouth-detail.png)
- [原陆地改造范围](../.scratch/hydrological-planning-domain/stylized-mouth-16km-20261017-09/construction-change-original-land.png)
- [实际岸线与径向剖面](../.scratch/hydrological-planning-domain/stylized-mouth-16km-20261017-09/actual-coast-and-radial-section.png)
- [完整数据](../.scratch/hydrological-planning-domain/stylized-mouth-16km-20261017-09/scene.npz)、[参数与结果](../.scratch/hydrological-planning-domain/stylized-mouth-16km-20261017-09/summary.json)、[冷读验收](../.scratch/hydrological-planning-domain/stylized-mouth-16km-20261017-09/cold-audit.json)
- [本轮任务](../.scratch/delta-completion/issues/02-complete-stylized-landward-delta.md)

场景为16km × 16km、20m栅格、800 × 800，种子84708600；方向来自保存河道的实际切线，基底、纵剖面和季节来水均有来源身份。

## 本轮改动

修复Claude v7草稿的变量作用域错误及主干不连海问题，恢复旧版默认入口。主干从扇顶零偏移接入，长500m，在距扇顶250m和500m处错开分汊；三支宽度82/66/52m，分流比例0.50/0.30/0.20。床面和设计水位采用共同下游坐标，父子节点一致，主干几何、掩膜、纵剖面和分流账本随场景保存。

扇顶位于原陆地，侧缘随下游方向弯曲展宽，海侧前缘不对称。近岸采用有界400m平滑，修正原岸线与扇面交接处的尖角；远端遇到另一处海岸岬角时回归原地形，避免扇面继续切入邻近高地。明确过渡段前的上游河槽核心以及构造范围外地形保持一致。

07（v8）修复运行后仍有岸边角点和距开阔海120m的支汊末端；08（v9）解决该问题，但总图暴露了误切邻近高地的问题。09（v10）修正岬角并增加对应回归。01至08均保留，未覆盖旧证据。

## 实际结果

| 项目 | 场景09结果 |
| --- | --- |
| 扇顶原地形高程 / 最近原海洋距离 | 23.602109m / 1753.282636m |
| 原陆地、旧主槽带外改造面积 | 5.0076km² |
| 其中连通湿区 / 干区 | 0.2652km² / 4.7424km² |
| 陆侧u=-700m横断面三支湿格 | 10 / 5 / 6，全部为原陆地 |
| 三支末端距河槽外连通海洋 | 40 / 28.284271 / 80m，均小于100m |
| 显式构造挖方 / 填方 | 28,674,127.175853 / 1,458,567,685.205750m³体积 |
| 构造账本残差 | 2.384185791015625e-7m³ |
| 原有上游护岸支撑毛填方 | 776,687,081.447953m³，已包含在构造核账范围 |

连通检查覆盖主干、每一支的正水深D4核心、节点以及海侧u=800/2000m横断面。这里的干湿依据保存的静态设计水面计算。

## 验收与集成

主协调检查了保存数组生成的总图、原陆地变化图和实际岸线/径向剖面。集成后在主工程确认模块加载位置，再执行验收：6项聚焦测试全部通过（8.87秒）；独立核对37份来源文件，哈希全部匹配；场景冷读和重新生成的数组逐项精确一致。水深/水面关系、主干与支汊连通、节点、原陆地面积、挖填账本、上游核心和外部地形保持检查通过。

仅集成以下三个文件；主工程原文件及已验证哈希的备份保存在 `backups/delta-before-v10-20261017-main/`。其他模块和前端在途修改保持原状。

| 对象 | SHA256 |
| --- | --- |
| `terrain_pipeline/surface_rivers/metric_stylized_wetland.py` | `7926db0fc736decc975680236b56149846e9051ab25e64020e666f8295ed6b4b` |
| `tests/test_metric_stylized_wetland.py` | `589524ab8e1e9c273f791df462511c5305130275171b6a23f6f2540eeb93de40` |
| `tools/prepare_stylized_river_mouth.py` | `d31da60b42fde6a64d63e69bdd2ec750ed7f759fe92bb82c04c6f2489729f3ff` |
| 09 `scene.npz` | `bc2e3e6630fae5ba26265d0383061fbfe41fc18625910560f7ccbc440c708e6f` |

场景的 `implementation/` 保存生成器与场景工具源码。可从主工程重放审计：

```powershell
.scratch/hydrological-planning-domain/pydeltarcm-venv/Scripts/python.exe -B tools/prepare_stylized_river_mouth.py --audit --output .scratch/hydrological-planning-domain/stylized-mouth-16km-20261017-09
```

新生成使用全新输出目录，不覆盖09。数值工作仍按单进程、最多两核、BelowNormal、数值线程1执行。本轮计算进程均已结束。

## 供沙与能力边界

此前[同源逐日供沙/陆侧沉积02](../verification/fluvial-delta/same-source-feedback-landward-20261016-02/summary.json)在84个控制体、8,224.263439m河段上推进365日，实际出口交付67,932.416003m³固体；河口净库存67,839.104507m³、海洋外排93.311496m³。原陆地沉积146.054384m³，覆盖4,500m²，交接仅深入陆侧约99m；联合收支残差约-6.98e-12m³。其59项测试和14个子测试是此前验收记录，本轮未重复执行或修改该链。

场景09的大范围填方属于风格化构造，不由上述一年供沙自然长成。两份成果尚未构成整个16km平原随实际供沙持续演化的统一水动力模型。供沙链采用有限材料、准稳态正常流反馈；大场景仍使用静态设计水位，`hydraulic_ready=false`、`publishable=false`。上游保存纵剖面与基底存在高程差，因此总图中的上游支撑脊仍可见，原宏观岸线部分直线特征也仍在。

本轮风格化陆侧范围验收完成，未发布到默认世界或游戏，未提交/推送。湖泊与其他沉积位置的复用结论见[河湖泥沙与拓扑评估](lake-sediment-reuse-and-topology-review-20261016.md)。袭夺、跨域交换、暗河、悬挑与新地貌保留第二阶段；潮汐和波浪也未在本轮加入。
