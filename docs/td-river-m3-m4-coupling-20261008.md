# Claude 蓝图 M3 接续与 M4 有限湖盆耦合验收

2026-10-08：M3 河道输送已接入共同内部时间步；M4 完成有界的湖泊储量、溢流、湖河交换与动态边界基线。验收状态为 `accepted_bounded_coupling`。天然湖盆合并、Saint-Venant 回水、全流域及最终河床几何尚未完成；`hydraulic_ready`、`natural_outlet_verified`、`publishable` 均为 false。

## 实现与接口

- `terrain_pipeline/surface_rivers/metric_lake_storage.py`：不可变原床支撑格、精确分段线性 V(h) 与反函数、湿足迹/水深/湿面积；显式多出口关系 `Q=C*max(h-crest,0)^1.5`。没有出口时储水；超出有限容量时拒绝继续计算。
- `terrain_pipeline/surface_rivers/metric_boundary_coupling.py`：矩形 Manning 河道与湖泊在共同显式步中更新，内部转移成对记账；局部释放逐源一次输入。支持 open、closed、unknown、prescribed_stage、prescribed_discharge。正边界 Q 表示域外出流，负值仅在明确许可的规定边界中表示入流。水位边界采用显式有限导水系数，不等于完整回水模型。
- `terrain_pipeline/surface_rivers/metric_coupled_product.py`：保存几何、参数、来源、forcing、逐节点轨迹及失败前缀；冷读独立重算通量、连续性、稳定性与账本。求解后采样保持初末状态和累计边界体积。

公开契约见 [m4-interface](../.scratch/td-river-blueprint/m4-interface.md)。已有 M3 求解器与诊断产品继续独立存在。输出预算为 128 MiB，湖泊支撑总量上限 65,536 格；所有候选状态通过非负性、容量、有限值与稳定性检查后才提交。

## 独立基准与审查

143 项相关新旧 unittest 通过（19.646 s）。新增湖泊、边界、保存产品和审查回归共 23 项。审查修正了嵌套认证标志伪造、大高程基准下的水位伪造、总储量溢出、伪造失败前缀、拒绝顺序不一致，以及水位平衡时遗漏导水稳定性约束的问题。

独立参考使用解析阈值、闭式水位响应与 SciPy DOP853；湖泊反函数参考由原床柱体二分计算，不调用实现中的反函数。固定细步体积误差门槛为 0.5%，时间细化必须改善误差。

| 基准 | 粗步相对体积误差 | 细步相对体积误差 |
| --- | ---: | ---: |
| 洼地蓄水、双出口溢流 | 0.139731% | 0.0348894% |
| 河道到湖泊到河道 | 0.381218% | 0.0950233% |
| 规定水位先入流后出流 | 0.292207% | 0.0728230% |

解析洼地在 10 s 达到堰顶；细步插值越阈值时刻为 10.000000000000016 s，首个正出口通量步为 10.125 s。越阈值和显式步开始出流分别记录。规定流量先以 -0.2 m³/s 入流 10 s，再以 +0.1 m³/s 出流 10 s，最终储水 1 m³。M3 无湖配置的共同步轨迹与原求解器兼容。

实际容量失败案例要求运行到 20 s，在 2 s 后因 `channel depth limit exceeded` 拒绝；只保存已提交前缀及未完成区间 [2,20]，冷读独立验证下一候选的失败原因。

## 真实 TD 事件

M4 使用已有真实 256×256、30 m 地形，与同源冻结 D4 hierarchy 对应。此前真实 1024×1024 M3 的 96 节点事件及证据继续保留，本次没有重新生成 TD 或执行 1024 全域湖泊求解。

原始来源 `verification/mountain-real-td/mountain-run-20261001T080705728662Z/primary-source.npz`，SHA256 `6e7fdf63dc02e9f14e7d83550d0c5f806b42aa7f13367ea96012787bcf069382`。冻结层级 `verification/td-basin-generation/A-20261001T184113155960Z/hierarchy.npz`，SHA256 `36a50a14560d3f6bc178350786bcac5bbf53acf97d2754af0e81fef5c79df422`。

映射 D4 叶节点 8 到 D8 终端格 63161。湖泊支撑为 5 格、每格 900 m²；D8 贡献域为 70 格，单独保存，不能用作湖面。选定上游格 62648 的原 D8 边进入湖泊支撑格 62905，河道长度、坡度与床高绑定原床；宽 2 m、Manning n=0.035、深度上限 5 m 为显式未校准工程参数。

首个 D4 鞍点高程为 1347.1527099609375 m。初始湖储量显式设为 2343.39365234375 m³，即距达到鞍点容量尚缺 0.1 m³；这是近溢流预置状态，不是本场降雨形成的储量。鞍点以上保持固定支撑，采用隔离直壁有限池近似，最高允许水位为鞍点加 0.05 m。出口 C=2，域外转移代表排入未纳入本事件的相邻盆地，不代表经认证的自然海口。

| 900 s 事件指标 | 最大步长 2 s | 最大步长 0.5 s |
| --- | ---: | ---: |
| 局部输入体积 | 1.335814003830 m³ | 1.335814003830 m³ |
| 累计出口体积 | 0.002151935270 m³ | 0.002158081578 m³ |
| 总储量变化 | 1.333662068559 m³ | 1.333655922255 m³ |
| 全局质量残差 | 9.78e-13 m³ | -3.07e-12 m³ |
| 插值越堰顶时刻 | 124.224633 s | 124.214638 s |
| 首个正出口通量步 | 126 s | 124.5 s |

全历史最大水位差 9.606881e-7 m（0.000960688 mm），累计出口差 0.284804%，分别通过 1 mm 和 1% 门槛。密集/稀疏采样的初末状态和累计外通量一致。独立核验鞍点以下的原床种子连通湿足迹、冻结 V(h)、源格互斥输入及最终水深体积；超过鞍点的天然合并足迹没有认证。

## 保存证据与复现

最终准备目录：`verification/td-river-lake-coupling/m3-m4-20261008-02/`，包含 11 份产品、原床湿足迹及 `acceptance.json`。最终冷审目录：`verification/td-river-lake-cold/m3-m4-20261008-03/`，`cold-audit.json` 状态 passed。

冷审禁用 solve_coupled、solve_channel、build_basin_hierarchy、route_diagnostic、build_diagnostic_product 和两种 runoff_from_forcing 入口，全部 11 份产品仍通过独立校验；原始来源及 D4/D8 映射、分离局部输入、湿足迹、失败前缀和采样积分均通过。

```powershell
D:/anaconda/python.exe -X utf8 -m tools.verify_td_river_lake_coupling --output <新的准备目录>
D:/anaconda/python.exe -X utf8 -m tools.audit_td_river_lake_coupling --input verification/td-river-lake-coupling/m3-m4-20261008-02 --output <新的冷审目录>
```

![保存结果独立冷读预览](../verification/td-river-lake-cold/m3-m4-20261008-03/td-lake-cold-preview.png)

## 后续依赖

[06](../.scratch/td-river-blueprint/issues/06-lake-boundary-coupling.md) 限定基线 resolved；[07](../.scratch/td-river-blueprint/issues/07-channel-geometry.md) 处理真实谷地中心线、直线/直角、断面及湖岸连接。天然湖盆合并与回水扩展在 [11](../.scratch/td-river-blueprint/issues/11-natural-lake-merging-and-backwater.md) 保持开放，不能用本次固定支撑验证替代。

M3/M4 没有修复河线形态，也没有将湖泊水位推广为细网格瞬时水面。原始 TD、冻结 D4、历史失败证据和 Claude 前端在途改动保留；本次未启动服务、GPU、游戏或 Java 构建。
