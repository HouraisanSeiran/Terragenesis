# Claude TD 河网蓝图：M1 / M2 交付

本轮完成用户指定的编号 Milestone 1「静态诊断排水」和 Milestone 2「时间变产流」，并补齐 M0 的来源登记与 tile 窗口前提。依据为根目录 [完整实施建议](../Terraindiffusion河网算法完整实施建议.md)，具体规格与状态见 [.scratch 任务](../.scratch/td-river-blueprint/spec.md)。Main 发布任务、审查与集成，两名用户指定 GPT-6 Sol 实施；同时最多三个智能体。

## 实现

- `metric_source.py`：原始来源文件 SHA、地形与边界身份、生成模型/种子/条件、dtype/形状/高程范围/未知比例登记；半开 tile 窗口保留父坐标与唯一格面积。内部切口标为 unknown，不创建自然出口。
- `metric_routing_comparison.py`：原床 D8、独立优先泛洪工作面 D8、新边界适配 D4；保存 receiver、downstream-first order、donors CSR、米制边长/坡度、终端与贡献域标签、工作面填高量及政策/tie-break。无显式已知出口的组件保持原床；原床 unknown 终端贡献域不参与已知出口填洼。
- `metric_forcing.py`：复用已有绝对坐标噪声场，独立雨量 seed=20261002；尺度/权重为 3840m/0.55、960m/0.30、240m/0.15。固定参考域均值校准，幅度0.35，正值倍率界0.6–1.4；保存基准雨强、实际统计与坐标规则。同一参考配方用于全部 tile。
- `metric_output.py`：消费保存的原生时序，分别保存初始/区间末状态、区间平均本地 Q、区间体积与累计量。稀疏采样积分全部原 forcing 区间，不取最后一次 Q 代替区间水量；独立输出格式不更改 v1 诊断包冷读。
- `prepare_td_river_milestones.py`、`audit_td_river_milestones.py`、`plot_td_river_milestones.py`：新目录准备、独立禁重算冷审与科学预览。失败目录只留下 refusal。

原始来源、旧 priority flood、旧 rainfall_runoff、固定 TD D4 hierarchy 及已交付包保持原 SHA。Claude 的前端修改与 `state.time === 0`、`signedEdgeQ`、`window.surfaceRenderer.flowInterval()` 不在本轮写集；本轮没有重启服务、GPU、Java 或游戏。

## 真实 TD 验收

主验收目录：[1024 完整包](../verification/td-river-milestones/td1024-20261008-01/manifest.json)，[账本与政策对照](../verification/td-river-milestones/td1024-20261008-01/acceptance.json)，[独立冷读](../verification/td-river-milestones/td1024-20261008-01/cold-audit.json)。

输入是此前实际 GPU 生成并保存的四个 TD 513² 窗口的西北512²核心拼接，未插值扩大旧256地形。原生间距30m，1024²唯一格，格面积窗口30.72km × 30.72km，总面积943,718,400m²；采样点首尾跨度30.69km。来源 SHA256：

```text
66bb82f254af54b1fa20a886dafa766ebe345abdc481c90403f4ee197d17d9b3
```

四个512²消费 tile 的高程、坐标和降雨切片一致，雨量逐 bit 相等，面积无重复，内部切口开放出口数为0。全域降雨倍率均值1.0，最小0.720663、最大1.306241，未触及截断界。参考域/目标域不同或触及截断界时，不宣称目标域均值仍为1。

暴雨基准为三个300秒 interval-average 区间，30/0/0 mm/h；保留未校准的概念土壤、入渗、蒸散及快慢储库参数，不作为观测暴雨或校准流量。

| 1024 政策 | Receiver 数 | 开放终端 | 闭合候选 | 累计开放边界量 m³ |
| --- | ---: | ---: | ---: | ---: |
| 原床 D8 | 1,041,151 | 4,092 | 3,333 | 6,859.029189 |
| 独立工作面优先泛洪 D8 | 1,044,484 | 4,092 | 0 | 221,980.874475 |
| 新边界适配原床 D4 | 1,035,973 | 4,092 | 8,511 | 4,136.404677 |

三政策 DAG、显式终端、unknown 阻断与合流账均通过；逐节点最大流量残差5.69e-14m³/s，区间路由体积残差最大1.20e-10m³。完整图用于验收，图像只筛选高流量边显示。

优先泛洪抬高67,725个工作面格，最大114.137329m，诊断填高体积1,827,078,602.124m³。此量不是水体体积、实际填土或侵蚀材料账。原床保持不变；工作面闭合候选为0并不证明自然湖泊消失或自然出口成立。

原床 D8 的水量账：

| 量 | m³ |
| --- | ---: |
| 雨量输入 | 2,359,296.000000 |
| 蒸散 | 35,389.440000 |
| 土壤/快慢储库变化 | 2,101,925.685525 |
| 本地产流释放 | 221,980.874475 |
| 工程开放边界诊断量 | 6,859.029189 |
| 闭合终端候选接收量 | 215,121.845286 |
| unknown / 指定边界候选量 | 0 |
| 联合残差 | −3.958121e−9 |

保存0/300/600/900秒密集帧与0/900秒稀疏帧的最终 soil/fast/slow 状态逐 bit 相同；累计本地释放与各终端类别水量一致。独立冷审逐项对应原产品状态和原区间积分，同时禁用16个地形/降雨/路由/求解入口，不重新生成图或重新求解产流。

1024准备实测401.29s，其中政策对照与保存257.72s，产流产品与保存69.67s；独立禁重算冷审55.92s。原生产品数组799,015,064B，政策包数组209,522,264B，各包小于其声明的1GiB/512MiB上限。准备进程冷审前峰值工作集2,005,991,424B，独立冷审峰值2,093,457,408B；不将单包预算冒充整进程1GiB保证。

另对固定真实256² TD来源完成同样准备，见 [256对照包](../verification/td-river-milestones/td256-20261008-01/acceptance.json)。其原床与历史固定D4为同一窗口，可以比较政策；1024是另一扩大窗口，历史256 D4仅作冻结参考。固定D4的1,085个静态终端与原床D8的450个闭合候选具有不同邻接及边界语义，不能直接解释为自然湖泊数量。

## 验证与预览

目标测试覆盖矩形米制格、平面/平台/单洼地/多出口、指定水位与流量边界、unknown及其贡献域、三政策重复身份、跨tile降雨、pulse账本、保存采样与重新计算身份后的篡改拒绝。最终相关新旧回归103项全部通过（15.70s），`git diff --check`通过。

复现主验收：

```powershell
D:/anaconda/python.exe -X utf8 -m tools.prepare_td_river_milestones --source-format td_1024 --source verification/td-1024-source/expanded-20261007-01/source.npz --source-sha256 66bb82f254af54b1fa20a886dafa766ebe345abdc481c90403f4ee197d17d9b3 --output verification/td-river-milestones/new-run
D:/anaconda/python.exe -X utf8 -m tools.audit_td_river_milestones --input verification/td-river-milestones/td1024-20261008-01 --output verification/td-river-milestones/td1024-20261008-01/new-cold-audit.json
```

预览：[三政策](../verification/td-river-milestones-previews/td1024-20261008-03/routing-policy-comparison.png)、[空间雨量与工作面填高](../verification/td-river-milestones-previews/td1024-20261008-03/rainfall-and-working-fill.png)、[时间变产流账本](../verification/td-river-milestones-previews/td1024-20261008-03/m2-water-ledgers.png)。这些是原生格诊断，不表示细网格瞬时水面。早先01/02预览保留，03修正了标题间距与边缘标签裁切。

## 后续边界

本轮完成 M1/M2 的诊断验收，不提升 `hydraulic_ready`、`natural_outlet_verified`、`publishable`。CRS 缺失继续为 pending_provenance；TD拼接接缝最大约0.198m只通过生成诊断，未获水文接缝认证。instantaneous accumulation 没有旅行时间、河道储水、回水、湖泊溢流和河床侵蚀。

下一项为 [M3 河道储量与简化水动力](../.scratch/td-river-blueprint/issues/05-channel-storage.md)：先审查单支流/Y汇流的守恒和脉冲传播基准，再扩域。不恢复历史失败的大型水力事件，不直接将填洼线路接入默认世界。
